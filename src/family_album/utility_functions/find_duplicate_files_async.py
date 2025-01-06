import asyncio
import hashlib
import json
import os
from time import perf_counter
from typing import List, Dict, Tuple

import aiofiles

_BLOCK_SIZE = 65536
_NUM_OPEN_FILES = 200


async def _get_file_hash(file_full_name: str, semaphore: asyncio.Semaphore) -> Tuple[str, str]:
    """
    Calculate hash of the file asynchronously.
    """

    hasher = hashlib.blake2b()
    try:
        async with semaphore:
            async with aiofiles.open(file_full_name, 'rb') as file:
                while True:
                    buf = await file.read(_BLOCK_SIZE)
                    if not buf:
                        break
                    hasher.update(buf)
    except Exception as e:
        print(f"Error reading file {file_full_name}: {e}")
        return "", file_full_name
    return hasher.hexdigest(), file_full_name


async def find_duplicate_files_async(root_folder: str) -> Dict[str, List[str]]:
    """
    Asynchronously analyze files in a directory (and subdirectories) to find duplicated files.
    Files are considered duplicates if they have the same hash code.
    Returns a dictionary where the key is the hash code and the value is a list of file paths with that hash.
    """
    file_dict = {}
    tasks = []
    semaphore = asyncio.Semaphore(_NUM_OPEN_FILES)  # Limit the number of concurrent file operations
    for directory, _, filenames in os.walk(root_folder):
        for filename in filenames:
            file_path = os.path.join(os.fsdecode(directory), os.fsdecode(filename))
            tasks.append(_get_file_hash(file_path, semaphore))

    results = await asyncio.gather(*tasks)  # rau tasks
    for file_hash, file_full_name in results:
        if file_hash:
            if file_hash in file_dict.keys():
                if file_full_name not in file_dict[file_hash]:  # avoid duplicating same file
                    file_dict[file_hash].append(file_full_name)
            else:
                file_dict[file_hash] = [file_full_name]

    return file_dict


if __name__ == "__main__":
    testing_directory = "<put your dir here>"  # dir to check for duplication
    save_result_directory = "<put your dir here>"   # dir to save results
    t1_start = perf_counter()
    duplicates = asyncio.run(find_duplicate_files_async(testing_directory))
    t1_stop = perf_counter()
    duplications_only = {file[0]: file[1:] for _, file in duplicates.items()
                         if len(file) > 1}
    print(f'Async function was checking dir "{testing_directory}" for duplicate files for {t1_stop - t1_start} seconds.')

    with open(os.path.join(save_result_directory, "duplicates_async.txt"), 'wt') as fp:
        fp.write(json.dumps(duplications_only))
    with open(os.path.join(save_result_directory,"hash_files_async.txt"), 'wt') as fp:
        fp.write(json.dumps(duplicates))

    from src.family_album.utility_functions.find_duplicate_files import find_duplicate_files

    t1_start = perf_counter()
    duplicates = find_duplicate_files(testing_directory)
    t1_stop = perf_counter()
    duplications_only = {file[0]: file[1:] for _, file in duplicates.items()
                         if len(file) > 1}
    print(f'Synchronous function was checking dir "{testing_directory}" for duplicate files for {t1_stop - t1_start} seconds.')

    with open(os.path.join(save_result_directory, "duplicates_sync1.txt"), 'wt') as fp:
        fp.write(json.dumps(duplications_only))
    with open(os.path.join(save_result_directory, "hash_files_sync1.txt"), 'wt') as fp:
        fp.write(json.dumps(duplicates))
    print("Done!")
