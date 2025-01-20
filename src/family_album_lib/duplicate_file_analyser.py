import json
import os
import hashlib
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from PyQt5.QtCore import pyqtSignal, QObject

from src.family_album_lib.directory_analyser import DirectoryAnalyser


class DuplicateFileAnalyser(QObject):

    _NUM_OPEN_FILES = 200
    start_analysis = pyqtSignal(str)
    update_progress = pyqtSignal(int, int)

    def __init__(self, directory: str, instantly_opened_files: int = 0) -> None:
        super().__init__()
        self._directory_analyser: DirectoryAnalyser = DirectoryAnalyser(directory)
        self.__files_hashes: Dict[str, List[str]] = {}
        self.__files_analysed: int = 0
        self.__progress: int = 0
        if instantly_opened_files <= 0:
            self.__num_of_threads = self._NUM_OPEN_FILES
        else:
            self.__num_of_threads = instantly_opened_files

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

    def find_duplicate_files_multithreaded(self) -> Dict[str, List[str]]:
        # create empty dicts for hash and for duplicates
        self.__files_hashes = {}
        self.__files_analysed = 0
        self.__progress = 0
        total_files = self._directory_analyser.files_count_in_directory
        self.start_analysis.emit("Start analysis.")
        lock = threading.Lock()  # use lock to avoid simultaneous edit dictionary 'file_hashes' from several threads

        def _get_files_hash(file_name: str) -> None:
            """
            Local function that calculates file's hash and update the resulting dictionary
            """
            if not os.path.isfile(file_name):
                return
            try:
                with open(file_name, 'rb') as file:
                    filehash = hashlib.blake2b(file.read()).hexdigest()
            except Exception as e:
                print(f"Error reading file {file_name}: {e}")
                return
            else:
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
                    self.update_progress.emit(self.__files_analysed, total_files)

        # create thread pool with max threads of _NUM_OPEN_FILES which limits
        with ThreadPoolExecutor(max_workers=self._NUM_OPEN_FILES) as executor:
            futures = []
            # iterate through all files and subdirectories
            for dirpath, _, file_names in os.walk(self.directory):
                for filename in file_names:
                    full_file_name = os.path.join(dirpath, filename)
                    futures.append(executor.submit(_get_files_hash, full_file_name))

            for future in as_completed(futures):
                future.result()  # wait for all threads to complete
        return self.__files_hashes
