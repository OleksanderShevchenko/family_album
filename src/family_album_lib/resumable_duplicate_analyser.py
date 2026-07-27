import os
import hashlib
from threading import Thread, Lock, Event
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Callable, Optional

from src.family_album_lib.duplicate_file_analyser import DuplicateFileAnalyser
from src.family_album_lib.duplication_memento import (
    DuplicationCheckStatus,
    DuplicationCheckMemento
)


class ResumableDuplicateAnalyser:
    """
    Wrapper around DuplicateFileAnalyser that adds Memento-based state saving,
    pausing, resuming, and location verification without modifying the original
    DuplicateFileAnalyser class.
    """

    _NUM_OPEN_FILES = 200

    def __init__(self,
                 directory: str,
                 start_analysis: Optional[Callable] = None,
                 update_analysis: Optional[Callable] = None,
                 log_event: Optional[Callable] = None,
                 finish_analysis: Optional[Callable] = None,
                 instantly_opened_files: int = 0) -> None:
        norm_dir = os.path.normpath(directory)
        if instantly_opened_files <= 0:
            instantly_opened_files = self._NUM_OPEN_FILES
        self._max_workers = instantly_opened_files
        self._analyser = DuplicateFileAnalyser(norm_dir,
                                               start_analysis,
                                               update_analysis,
                                               log_event,
                                               instantly_opened_files)
        self._processed_files: Dict[str, str] = {}  # full_file_path -> hash_digest
        self._files_hashes: Dict[str, List[str]] = {}  # hash_digest -> list[file_paths]
        self._status: DuplicationCheckStatus = DuplicationCheckStatus.IDLE
        self._stop_event = Event()
        self._worker_thread: Optional[Thread] = None

        self.start_analysis: Optional[Callable] = start_analysis
        self.update_progress: Optional[Callable] = update_analysis
        self.log_event: Optional[Callable] = log_event
        self.finish_analysis: Optional[Callable] = finish_analysis

    @property
    def directory(self) -> str:
        return os.path.normpath(self._analyser.directory)

    @directory.setter
    def directory(self, new_directory: str) -> None:
        self._analyser.directory = os.path.normpath(new_directory)
        self.reset()

    @property
    def files_count_in_directory(self) -> int:
        return self._analyser.files_count_in_directory

    @property
    def subdirectories_count_in_directory(self) -> int:
        return self._analyser.subdirectories_count_in_directory

    @property
    def files_hashes(self) -> Dict[str, List[str]]:
        return self._files_hashes

    @property
    def processed_files(self) -> Dict[str, str]:
        return self._processed_files

    @property
    def duplicate_files(self) -> Dict[str, List[str]]:
        if len(self._files_hashes) > 0:
            return {file[0]: file[1:] for _, file in self._files_hashes.items() if len(file) > 1}
        else:
            return {}

    @property
    def status(self) -> DuplicationCheckStatus:
        return self._status

    def reset(self) -> None:
        self.stop_analysis()
        self._processed_files = {}
        self._files_hashes = {}
        self._status = DuplicationCheckStatus.IDLE

    def create_memento(self) -> DuplicationCheckMemento:
        return DuplicationCheckMemento(
            directory=self.directory,
            files_count=self.files_count_in_directory,
            subdirectories_count=self.subdirectories_count_in_directory,
            processed_files={os.path.normpath(k): v for k, v in self._processed_files.items()},
            files_hashes={k: [os.path.normpath(f) for f in v] for k, v in self._files_hashes.items()}
        )

    def restore_memento(self, memento: DuplicationCheckMemento) -> None:
        self.stop_analysis()
        self._analyser.directory = os.path.normpath(memento.directory)
        self._processed_files = {os.path.normpath(k): v for k, v in memento.processed_files.items()}
        self._files_hashes = {k: [os.path.normpath(f) for f in v] for k, v in memento.files_hashes.items()}
        total_files = self.files_count_in_directory
        if len(self._processed_files) >= total_files and total_files > 0:
            self._status = DuplicationCheckStatus.COMPLETED
        else:
            self._status = DuplicationCheckStatus.PAUSED

    def stop_analysis(self) -> None:
        if self._status == DuplicationCheckStatus.RUNNING:
            self._stop_event.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2.0)
            self._status = DuplicationCheckStatus.PAUSED

    def start_analysis_thread(self, run_in_background: bool = True) -> None:
        self._stop_event.clear()
        if run_in_background:
            self._worker_thread = Thread(
                target=self._find_duplicate_files_multithreaded,
                daemon=True
            )
            self._worker_thread.start()
        else:
            self._find_duplicate_files_multithreaded()

    def _find_duplicate_files_multithreaded(self) -> None:
        self._status = DuplicationCheckStatus.RUNNING
        total_files = self.files_count_in_directory
        files_analysed = len(self._processed_files)
        progress = int(files_analysed / total_files * 100) if total_files > 0 else 0

        if isinstance(self.start_analysis, Callable):
            self.start_analysis("Start analysis.")

        lock = Lock()

        def _get_files_hash(file_name: str) -> None:
            nonlocal files_analysed, progress
            norm_file_name = os.path.normpath(file_name)
            if self._stop_event.is_set() or not os.path.isfile(norm_file_name):
                return
            try:
                hasher = hashlib.blake2b()
                with open(norm_file_name, 'rb') as file:
                    while chunk := file.read(1024 * 1024):
                        if self._stop_event.is_set():
                            return
                        hasher.update(chunk)
                filehash = hasher.hexdigest()
            except Exception as e:
                m = f"Error reading file {norm_file_name}: {e}"
                if isinstance(self.log_event, Callable):
                    self.log_event(m)
                print(m)
                return
            else:
                with lock:
                    if self._stop_event.is_set():
                        return
                    self._processed_files[norm_file_name] = filehash
                    if filehash in self._files_hashes:
                        if norm_file_name not in self._files_hashes[filehash]:
                            self._files_hashes[filehash].append(norm_file_name)
                    else:
                        self._files_hashes[filehash] = [norm_file_name]

                    files_analysed += 1
                    current_progress = int(files_analysed / total_files * 100) if total_files > 0 else 0
                    if current_progress > progress:
                        progress = current_progress
                    if isinstance(self.update_progress, Callable):
                        self.update_progress(files_analysed, total_files)

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = []
            for dirpath, _, file_names in os.walk(self.directory):
                if self._stop_event.is_set():
                    break
                for filename in file_names:
                    if self._stop_event.is_set():
                        break
                    full_file_name = os.path.normpath(os.path.join(dirpath, filename))
                    if full_file_name not in self._processed_files:
                        futures.append(executor.submit(_get_files_hash, full_file_name))

            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break
                try:
                    future.result()
                except Exception as ex:
                    print(f"Execution error: {ex}")

        if self._stop_event.is_set():
            self._status = DuplicationCheckStatus.PAUSED
            if isinstance(self.log_event, Callable):
                self.log_event("Duplicate analysis paused by user.")
        else:
            self._status = DuplicationCheckStatus.COMPLETED
            if isinstance(self.finish_analysis, Callable):
                self.finish_analysis("Finish analysis.")
