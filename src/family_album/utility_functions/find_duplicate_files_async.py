import asyncio
import hashlib
import json
import os
from time import perf_counter


async def hash_file(path) -> str:
    """
    Асинхронно обчислює хеш вмісту файлу за вказаним шляхом.
    """
    BLOCKSIZE = 65536
    hasher = hashlib.blake2b()
    with open(path, 'rb') as file:
        buf = file.read(BLOCKSIZE)
        while len(buf) > 0:
            hasher.update(buf)
            buf = file.read(BLOCKSIZE)
    return hasher.hexdigest()

async def find_duplicate_files_async(root_folder) -> dict:
    """
    Асинхронна функція для пошуку дублікатів файлів в директорії та її піддиректоріях.
    Повертає словник, де ключ - це оригінальний файл, а значеннями - список файлів, які його дублюють.
    """
    file_dict = {}
    tasks = []
    for dirpath, dirnames, filenames in os.walk(root_folder):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            task = asyncio.ensure_future(hash_file(path))
            tasks.append((path, task))
    for path, task in tasks:
        file_hash = await task
        if file_hash in file_dict:
            file_dict[file_hash].append(path)
        else:
            file_dict[file_hash] = [path]
    return file_dict


if __name__ == "__main__":
    path = "/home/oleksander/Family Album/Photo and video from Cloud"  # on the test flash card with 103 GB takes ~45 min
    t1_start = perf_counter()
    duplicates = asyncio.run(find_duplicate_files_async(path))
    t1_stop = perf_counter()
    print(f' Checking dir{path} for duplicate files takes {t1_stop - t1_start} seconds.')
    print(f'Duplicates are: {duplicates}')
    print(f' Checking dir{path} for duplicate files takes {t1_stop - t1_start} seconds.')
    with open(r"C:\Users\Oleksander\duplicates_async.txt", 'wt') as fp:
        fp.write(json.dumps(duplicates))
    print("Done!")
