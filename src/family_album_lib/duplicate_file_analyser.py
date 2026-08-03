import os
import hashlib
from typing import List, Dict, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from src.family_album_lib.directory_analyser import DirectoryAnalyser


class DuplicateFileAnalyser:
    """
    A core component of the Family Album application responsible for identifying 
    duplicate files and directories within a specified target directory.

    Purpose and Ideas:
    ------------------
    This class orchestrates a high-performance, multithreaded file analysis.
    It relies on calculating a cryptographic hash (Blake2b) for the entire contents 
    of each file. Files that yield identical hashes are considered exact duplicates.

    The multithreaded approach, controlled by the `instantly_opened_files` 
    parameter, ensures that file reading is parallelized, reducing I/O wait times 
    especially on modern storage drives. To ensure thread safety when recording 
    file hashes and progress, a threading Lock is employed.

    Additionally, the class is designed to be extensible. It uses hook methods 
    (`_should_skip_file`, `_is_stopped`, `_should_reset_hashes`) to allow 
    subclasses (like `ResumableDuplicateAnalyser`) to inject custom pause/resume 
    and session persistence logic without duplicating the complex multithreading code.

    It also offers directory duplicate detection (`find_duplicate_directories`),
    identifying folders with identical contents regardless of file or folder name changes.
    """

    def __init__(self,
                 directory: str,
                 start_analysis: Callable,
                 update_analysis: Callable,
                 log_event: Callable,
                 instantly_opened_files: int) -> None:
        """
        Initializes the DuplicateFileAnalyser with required configuration and callbacks.

        Args:
            directory (str): The absolute or relative path to the directory to be analysed.
                             If the directory is not consistent, NotADirectoryError is raised.
            start_analysis (Callable): A callback function invoked when the analysis starts. 
                                       Expected signature: func(message: str).
            update_analysis (Callable): A callback function invoked to update the GUI progress.
                                        Expected signature: func(files_analysed: int, total_files: int).
            log_event (Callable): A callback function invoked to log an error or warning message.
                                  Expected signature: func(message: str).
            instantly_opened_files (int): The maximum number of concurrent threads/files 
                                          opened for reading at the same time. Must be > 0.
        
        Raises:
            ValueError: If `instantly_opened_files` is zero or negative.
            TypeError: If any of the provided callbacks are not callable.
        """
        super().__init__()
        # if directory is not consistent it raises NotADirectoryError error
        self._directory_analyser: DirectoryAnalyser = DirectoryAnalyser(directory)
        # check for argument correctness
        if instantly_opened_files <= 0:
            raise ValueError(f"Number of instantly opened files shall be positive int higher than zero! " +
                             f"Passed value '{instantly_opened_files}' is inconsistent.")
        if start_analysis is not None and not isinstance(start_analysis, Callable):
            raise TypeError(f"Argument 'start_analysis' is not callable.")
        if update_analysis is not None and not isinstance(update_analysis, Callable):
            raise TypeError(f"Argument 'update_analysis' is not callable.")
        if log_event is not None and not isinstance(log_event, Callable):
            raise TypeError(f"Argument 'log_event' is not callable.")

        self.__files_hashes: Dict[str, List[str]] = {}
        self.__failed_files: List[str] = []
        self._files_analysed: int = 0
        self.__progress: int = 0
        self.__num_of_threads: int = instantly_opened_files
        self._start_analysis: Callable = start_analysis
        self._update_progress: Callable = update_analysis
        self._log_event: Callable = log_event

    @property
    def directory(self) -> str:
        """str: Returns the current target directory being analysed."""
        return self._directory_analyser.directory

    @directory.setter
    def directory(self, new_directory: str) -> None:
        """
        Sets a new target directory and resets all internal analysis state variables.
        
        Args:
            new_directory (str): The new directory path to assign.
        """
        self._directory_analyser.directory = new_directory
        self.__files_hashes = {}
        self.__failed_files = []
        self._files_analysed = 0
        self.__progress = 0

    @property
    def files_count_in_directory(self) -> int:
        """int: Returns the total number of files discovered in the target directory."""
        return self._directory_analyser.files_count_in_directory

    @property
    def subdirectories_count_in_directory(self) -> int:
        """int: Returns the total number of subdirectories discovered in the target directory."""
        return self._directory_analyser.subdirectories_count_in_directory

    @property
    def files_hashes(self) -> Dict[str, List[str]]:
        """
        Dict[str, List[str]]: Returns a dictionary mapping computed file hashes to a list 
                              of file paths that possess that hash.
        """
        return self.__files_hashes

    @property
    def duplicate_files(self) -> Dict[str, List[str]]:
        """
        Dict[str, List[str]]: Returns a filtered dictionary containing only the files 
                              that have exact duplicates (i.e., hashes mapped to > 1 file path).
                              The key is the original file path, and the value is a list of duplicate paths.
        """
        if len(self.__files_hashes) > 0:
            return {file[0]: file[1:] for _, file in self.__files_hashes.items() if len(file) > 1}
        else:
            return {}

    @property
    def failed_files(self) -> List[str]:
        """List[str]: Returns a list of file paths that failed to be read or processed."""
        return self.__failed_files

    @staticmethod
    def find_duplicate_directories(files_hashes: Dict[str, List[str]]) -> Dict[str, Dict]:
        """
        Static utility method that detects exact duplicate directories based purely on their contents.
        
        It constructs a "signature" for each directory by aggregating the hashes of all files 
        within it, the total file count, and the total byte size. If two directories share 
        the exact same signature, they are marked as duplicates. 

        File and folder names DO NOT need to match for directories to be considered duplicates, 
        ensuring robustness against file renaming.

        Args:
            files_hashes (Dict[str, List[str]]): The mapping of file hashes to lists of file paths.

        Returns:
            Dict[str, Dict]: A dictionary mapping the original directory path to a dictionary 
                             containing its duplicates, total file count, and total byte size.
                             Format: { original_dir: {"duplicates": [dup_dir1, dup_dir2], "file_count": int, "total_size": int} }
        """
        if not files_hashes:
            return {}

        path_to_hash = {}
        path_to_size = {}

        for f_hash, paths in files_hashes.items():
            for p in paths:
                norm_p = os.path.normpath(p)
                path_to_hash[norm_p] = f_hash
                try:
                    path_to_size[norm_p] = os.path.getsize(norm_p)
                except Exception:
                    path_to_size[norm_p] = 0

        all_dirs = set(os.path.dirname(p) for p in path_to_hash.keys())
        dir_content_map = {}

        for d in all_dirs:
            file_hashes = []
            total_size = 0
            for p, f_hash in path_to_hash.items():
                if p == d or p.startswith(d + os.sep):
                    file_hashes.append(f_hash)
                    total_size += path_to_size[p]
            if file_hashes:
                # Signature = (file_count, total_byte_size, sorted_file_hashes_tuple)
                sig = (len(file_hashes), total_size, tuple(sorted(file_hashes)))
                dir_content_map[d] = sig

        sig_to_dirs = {}
        for d, sig in dir_content_map.items():
            sig_to_dirs.setdefault(sig, []).append(d)

        duplicate_dirs = {}
        for sig, dir_list in sig_to_dirs.items():
            if len(dir_list) > 1:
                # Sort by path length to choose shortest path as original
                dir_list.sort(key=lambda x: (len(x), x))
                orig_dir = dir_list[0]
                dup_dirs = dir_list[1:]
                duplicate_dirs[orig_dir] = {
                    "duplicates": dup_dirs,
                    "file_count": sig[0],
                    "total_size": sig[1]
                }

        filtered_duplicate_dirs = {}
        all_dup_paths = set()
        for orig, data in duplicate_dirs.items():
            for dup in data["duplicates"]:
                all_dup_paths.add(dup)

        for orig, data in duplicate_dirs.items():
            dups_clean = []
            for dup in data["duplicates"]:
                parent_is_dup = False
                parent = os.path.dirname(dup)
                while parent and parent != os.path.dirname(parent):
                    if parent in all_dup_paths and parent != dup:
                        parent_is_dup = True
                        break
                    parent = os.path.dirname(parent)
                if not parent_is_dup:
                    dups_clean.append(dup)
            if dups_clean:
                filtered_duplicate_dirs[orig] = {
                    "duplicates": dups_clean,
                    "file_count": data["file_count"],
                    "total_size": data["total_size"]
                }

        return filtered_duplicate_dirs

    @property
    def duplicate_directories(self) -> Dict[str, Dict]:
        """
        Dict[str, Dict]: Automatically calculates and returns the duplicate directories 
                         based on the current `files_hashes` state.
        """
        return self.find_duplicate_directories(self.__files_hashes)

    def _should_skip_file(self, file_name: str) -> bool:
        """
        Hook method designed for subclass overrides (e.g., Memento session resumption).
        
        Args:
            file_name (str): The full path of the file to check.

        Returns:
            bool: True if the file should be skipped during analysis. Default is False.
        """
        return False

    def _is_stopped(self) -> bool:
        """
        Hook method designed for subclass overrides (e.g., checking if the user paused the scan).

        Returns:
            bool: True if the analysis threads should stop processing early. Default is False.
        """
        return False

    def _should_reset_hashes(self) -> bool:
        """
        Hook method designed for subclass overrides (e.g., preventing reset when resuming a session).

        Returns:
            bool: True if `files_hashes` and progress state should be cleared before 
                  the analysis starts. Default is True.
        """
        return True

    def start_analysis_thread(self):
        """
        Public entry point to begin the multithreaded file analysis process.
        This method will block the calling thread until all executor threads complete.
        """
        self._find_duplicate_files_multithreaded()

    def _find_duplicate_files_multithreaded(self) -> None:
        """
        The core engine of the analyser. It performs a recursive multithreaded traversal 
        of the target directory, computing Blake2b hashes for each file to identify duplicates.

        Process Flow:
        -------------
        1. Evaluates hooks (`_should_reset_hashes`) to initialize or retain state.
        2. Iterates over all files via `os.walk`, checking the `_should_skip_file` hook.
        3. Submits file hashing tasks to a `ThreadPoolExecutor`.
        4. In the worker threads (`_get_files_hash`), the file is fully read and hashed.
        5. Thread-safe updates (using a Lock) are applied to `self.__files_hashes` and progress.
        6. Awaits the completion of all futures.
        """
        # initialize or reset dicts based on hook
        if self._should_reset_hashes():
            self.__files_hashes = {}
            self._files_analysed = 0
        self.__failed_files = []
        self.__progress = 0
        total_files = self._directory_analyser.files_count_in_directory

        if isinstance(self._start_analysis, Callable):
            self._start_analysis("Start analysis.")

        # Emit initial restored progress immediately so GUI progress bar jumps to resumed percentage on start
        if self._files_analysed > 0 and total_files > 0:
            self._recalculate_and_update_progress(total_files)

        lock = Lock()  # use lock to avoid simultaneous edit dictionary 'file_hashes' from several threads

        def _get_files_hash(file_name: str) -> None:
            """
            Local function executed within worker threads. Calculates the file's hash 
            by reading its full content and safely updates the resulting dictionary.

            Args:
                file_name (str): The full path of the file to hash.
            """
            if self._is_stopped() or not os.path.isfile(file_name):
                return
            filehash = None
            try:
                with open(file_name, 'rb') as file:
                    if not file.readable():
                        m = f"Could not reading file '{file_name}'"
                        if isinstance(self._log_event, Callable):
                            self._log_event(m)
                        print(m)
                        with lock:
                            self.__failed_files.append(file_name)  # add failed file to list of failed
                            self._files_analysed += 1  # assume file processed - to reach 100% in progress
                            self._recalculate_and_update_progress(total_files)
                        return
                    file_data = file.read()
                    filehash = hashlib.blake2b(file_data).hexdigest()
            except Exception as e:
                m = f"Error reading file {file_name}: {e}"
                if isinstance(self._log_event, Callable):
                    self._log_event(m)
                print(m)
                with lock:
                    self.__failed_files.append(file_name)  # add failed file to list of failed
                    self._files_analysed += 1  # assume file processed - to reach 100% in progress
                    self._recalculate_and_update_progress(total_files)
                return
            else:
                if filehash:  # if hash not none
                    with lock:  # context manager will release lock automatically even in case of an error
                        if self._is_stopped():
                            return
                        # add hash and file name to dictionary
                        if filehash in self.__files_hashes.keys() and file_name not in self.__files_hashes[filehash]:
                            self.__files_hashes[filehash].append(file_name)
                        else:
                            self.__files_hashes[filehash] = [file_name]
                        self._files_analysed += 1
                        self._recalculate_and_update_progress(total_files)

        # create thread pool with max threads of self.__num_of_threads which limits
        with ThreadPoolExecutor(max_workers=self.__num_of_threads) as executor:
            futures = []
            # iterate through all files and subdirectories
            for dirpath, _, file_names in os.walk(self.directory):
                if self._is_stopped():
                    break
                for filename in file_names:
                    if self._is_stopped():
                        break
                    full_file_name = os.path.normpath(os.path.join(dirpath, filename))
                    if not self._should_skip_file(full_file_name):
                        futures.append(executor.submit(_get_files_hash, full_file_name))

            for future in as_completed(futures):
                if self._is_stopped():
                    break
                try:
                    future.result()  # wait for all threads to complete
                except Exception as ex:
                    print(f"Execution error: {ex}")
        return

    def _recalculate_and_update_progress(self, total_files: int) -> None:
        """
        Calculates the current progress percentage and triggers the GUI update callback.
        
        Args:
            total_files (int): The total number of files designated for analysis.
        """
        current_progress = int(self._files_analysed / total_files * 100) if total_files > 0 else 0
        if current_progress >= self.__progress:
            self.__progress = current_progress
            if isinstance(self._update_progress, Callable):
                self._update_progress(self._files_analysed, total_files)