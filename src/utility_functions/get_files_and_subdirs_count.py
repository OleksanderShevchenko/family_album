import os
from typing import Tuple


def get_files_and_subdirs_count(directory: str) -> Tuple[int, int]:
    file_counts = 0
    dir_counts = 0
    if os.path.isdir(directory):
            file_counts = sum([len(files) for _, _, files in os.walk(directory)])
            dir_counts = sum([len(dirs) for _, dirs, _ in os.walk(directory)])
    return file_counts, dir_counts