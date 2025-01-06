import json
import os
import hashlib
from time import perf_counter
from typing import List, Dict


def find_duplicate_files(directory: str) -> Dict[str, List[str]]:
    # create empty dicts for hash and for duplicates
    file_hashes = {}

    # iterate though all files and subdirectories
    for dirpath, _, file_names in os.walk(directory):
        for filename in file_names:
            # calculate file hash
            full_file_name = os.path.join(dirpath, filename)
            with open(full_file_name, 'rb') as file:
                filehash = hashlib.blake2b(file.read()).hexdigest()

            # add hash and file name to dictionary
            if filehash in file_hashes.keys() and full_file_name not in file_hashes[filehash]:
                file_hashes[filehash].append(full_file_name)
            else:
                file_hashes[filehash] = [full_file_name]

    return file_hashes


if __name__ == "__main__":
    testing_directory = "<put your dir here>"  # dir to check for duplication
    save_result_directory = "<put your dir here>"  # dir to save results

    t1_start = perf_counter()
    duplicates = find_duplicate_files(testing_directory)
    t1_stop = perf_counter()
    duplications_only = {file[0]: file[1:] for _, file in duplicates.items()
                         if len(file) > 1}
    print(
        f'Synchronous function was checking dir "{testing_directory}" for duplicate files for {t1_stop - t1_start} seconds.')

    with open(os.path.join(save_result_directory, "duplicates_sync2.txt"), 'wt') as fp:
        fp.write(json.dumps(duplications_only))
    with open(os.path.join(save_result_directory, "hash_files_sync2.txt"), 'wt') as fp:
        fp.write(json.dumps(duplicates))
    print("Done!")
