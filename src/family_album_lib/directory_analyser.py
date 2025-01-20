import os
from abc import ABC


class DirectoryAnalyser(ABC):

    def __init__(self, directory: str) -> None:
        if os.path.isdir(directory):
            self.__current_directory = directory
        else:
            raise NotADirectoryError(f"The argument passed in class constructor '{directory}' " +
                                     f"is not existing directory.")

    @property
    def files_count_in_directory(self) -> int:
        file_counts = sum([len(files) for _, _, files in os.walk(self.directory)])
        return file_counts

    @property
    def subdirectories_count_in_directory(self) -> int:
        dir_counts = sum([len(dirs) for _, dirs, _ in os.walk(self.directory)])
        return dir_counts

    @property
    def directory(self) -> str:
        return self.__current_directory

    @directory.setter
    def directory(self, new_directory: str) -> None:
        if not os.path.isdir(new_directory):
            raise NotADirectoryError(f"The argument passed in directory setter '{new_directory}' " +
                                     f"is not existing directory.")
        self.__current_directory = new_directory
