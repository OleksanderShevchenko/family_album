import json
import os
import hashlib
from typing import List, Dict, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Thread, Lock

from src.family_album_lib.directory_analyser import DirectoryAnalyser


class DuplicateFileAnalyser():

    def __init__(self,
                 directory: str,
                 start_analysis: Callable,
                 update_analysis: Callable,
                 log_event: Callable,
                 instantly_opened_files: int) -> None:
        super().__init__()
        self._directory_analyser: DirectoryAnalyser = DirectoryAnalyser(directory)
        self.__files_hashes: Dict[str, List[str]] = {}
        self.__files_analysed: int = 0
        self.__progress: int = 0
        self.__num_of_threads: int = instantly_opened_files
        self._start_analysis: Callable = start_analysis
        self._update_progress: Callable = update_analysis
        self._log_event: Callable = log_event

    @property
    def directory(self) -> str:
        return self._directory_analyser.directory

    @directory.setter
    def directory(self, new_directory: str) -> None:
        self._directory_analyser.directory = new_directory
        self.__files_hashes = {}
        self.__files_analysed = 0

    @property
    def files_count_in_directory(self) -> int:
        return self._directory_analyser.files_count_in_directory

    @property
    def subdirectories_count_in_directory(self) -> int:
        return self._directory_analyser.subdirectories_count_in_directory

    @property
    def files_hashes(self) -> Dict[str, List[str]]:
        return self.__files_hashes

    @property
    def duplicate_files(self) -> Dict[str, List[str]]:
        if len(self.__files_hashes) > 0:
            return {file[0]: file[1:] for _, file in self.__files_hashes.items() if len(file) > 1}
        else:
            return {}

    def start_analysis_thread(self):
        self._find_duplicate_files_multithreaded()


    def _find_duplicate_files_multithreaded(self) -> None:
        # create empty dicts for hash and for duplicates
        self.__files_hashes = {}
        self.__files_analysed = 0
        self.__progress = 0
        total_files = self._directory_analyser.files_count_in_directory
        if isinstance(self._start_analysis, Callable):
            self._start_analysis("Start analysis.")
        lock = Lock()  # use lock to avoid simultaneous edit dictionary 'file_hashes' from several threads

        def _get_files_hash(file_name: str) -> None:
            """
            Local function that calculates file's hash and update the resulting dictionary
            """
            if not os.path.isfile(file_name):
                return
            filehash = None
            try:
                with open(file_name, 'rb') as file:
                    if not file.readable():
                        m = f"Could not reading file '{file_name}'"
                        if isinstance(self._log_event, Callable):
                            self._log_event(m)
                        print(m)
                        return
                    file_data = file.read()
                    filehash = hashlib.blake2b(file_data).hexdigest()
            except Exception as e:
                m = f"Error reading file {file_name}: {e}"
                if isinstance(self._log_event, Callable):
                    self._log_event(m)
                print(m)
                return
            else:
                if filehash:  # if hash not none
                    with lock:  # context manager will release lock automatically even in case of an error
                        # add hash and file name to dictionary
                        if filehash in self.__files_hashes.keys() and file_name not in self.__files_hashes[filehash]:
                            self.__files_hashes[filehash].append(file_name)
                        else:
                            self.__files_hashes[filehash] = [file_name]
                    self.__files_analysed += 1
                    current_progress = int(self.__files_analysed / total_files * 100)
                    if current_progress > self.__progress:
                        self.__progress = current_progress
                        if isinstance(self._update_progress, Callable):
                            self._update_progress(self.__files_analysed, total_files)

        # create thread pool with max threads of self.__num_of_threads which limits
        with ThreadPoolExecutor(max_workers=self.__num_of_threads) as executor:
            futures = []
            # iterate through all files and subdirectories
            for dirpath, _, file_names in os.walk(self.directory):
                for filename in file_names:
                    full_file_name = os.path.normpath(os.path.join(dirpath, filename))
                    futures.append(executor.submit(_get_files_hash, full_file_name))

            for future in as_completed(futures):
                future.result()  # wait for all threads to complete
        return
