import json
import os
import hashlib
from time import perf_counter
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

_NUM_OPEN_FILES = 200


def find_duplicate_files_multithreaded(directory: str) -> Dict[str, List[str]]:
    # create empty dicts for hash and for duplicates
    file_hashes = {}
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
                if filehash in file_hashes.keys() and file_name not in file_hashes[filehash]:
                    file_hashes[filehash].append(file_name)
                else:
                    file_hashes[filehash] = [file_name]

    # create thread pool with max threads of _NUM_OPEN_FILES which limits 
    with ThreadPoolExecutor(max_workers=_NUM_OPEN_FILES) as executor:
        futures = []
        # iterate through all files and subdirectories
        for dirpath, _, file_names in os.walk(directory):
            for filename in file_names:
                full_file_name = os.path.join(dirpath, filename)
                futures.append(executor.submit(_get_files_hash, full_file_name))

        for future in as_completed(futures):
            future.result()  # wait for all threads to complete

    return file_hashes


if __name__ == "__main__":
    testing_directory = "<put your dir here>"  # dir to check for duplication
    save_result_directory = "<put your dir here>"  # dir to save results

    t1_start = perf_counter()
    duplicates = find_duplicate_files_multithreaded(testing_directory)
    t1_stop = perf_counter()
    duplications_only = {file[0]: file[1:] for _, file in duplicates.items()
                         if len(file) > 1}
    print(f'Multithread function was checking dir "{testing_directory}" for duplicate files for ' +
          f'{t1_stop - t1_start} seconds.')

    with open(os.path.join(save_result_directory, "duplicates_mthread3.txt"), 'wt') as fp:
        fp.write(json.dumps(duplications_only))
    with open(os.path.join(save_result_directory, "hash_files_mthread3.txt"), 'wt') as fp:
        fp.write(json.dumps(duplicates))
    print("Done!")
