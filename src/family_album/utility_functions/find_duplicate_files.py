import json
import os
import hashlib
from time import perf_counter


def find_duplicate_files(directory: str) -> dict:
    # create empty dicts for hash and for duplicates
    file_hashes = {}
    duplicate_files = {}

    # iterate though all files and subdirectories
    for root, dirs, files in os.walk(directory):
        for filename in files:
            # calculate file hash
            full_file_name = os.path.join(root, filename)
            with open(full_file_name, 'rb') as file:
                filehash = hashlib.blake2b(file.read()).hexdigest()

            # add hash and file name to dictionary
            if filehash in file_hashes:
                file_hashes[filehash].append(full_file_name)
            else:
                file_hashes[filehash] = [full_file_name]

    # convert file_hashes dict into duplicate_files dict
    for filehash, paths in file_hashes.items():
        if len(paths) > 1:
            for full_file_name in paths:
                if full_file_name in duplicate_files:
                    duplicate_files[full_file_name].extend(paths)
                    duplicate_files[full_file_name].remove(full_file_name)
                else:
                    duplicate_files[full_file_name] = list(set(paths) - set([full_file_name]))

    return duplicate_files


if __name__ == "__main__":
    path = "E:/"
    t1_start = perf_counter()
    duplicates = find_duplicate_files(path)
    t1_stop = perf_counter()

    print(f'Duplicates are: {duplicates}')
    print(f' Checking dir{path} for duplicate files takes {t1_stop - t1_start} seconds.')
    with open(r"C:\Users\Oleksander\duplicates.txt", 'wt') as fp:
        fp.write(json.dumps(duplicates))


