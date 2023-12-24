import json
import os
import hashlib
from time import perf_counter


def find_duplicate_files(directory):
    # Створюємо порожні словники для зберігання хешів та дублікатів
    hashes = {}
    duplicates = {}

    # Ітеруємося по всіх файлах та папках в директорії
    for root, dirs, files in os.walk(directory):
        for filename in files:
            # Обчислюємо хеш файлу
            path = os.path.join(root, filename)
            with open(path, 'rb') as file:
                filehash = hashlib.md5(file.read()).hexdigest()

            # Додаємо хеш та шлях до словника hashes
            if filehash in hashes:
                hashes[filehash].append(path)
            else:
                hashes[filehash] = [path]

    # Перетворюємо словник hashes у словник duplicates
    for filehash, paths in hashes.items():
        if len(paths) > 1:
            for path in paths:
                if path in duplicates:
                    duplicates[path].extend(paths)
                    duplicates[path].remove(path)
                else:
                    duplicates[path] = list(set(paths) - set([path]))

    return duplicates


if __name__ == "__main__":
    path = "E:/"
    t1_start = perf_counter()
    duplicates = find_duplicate_files(path)
    t1_stop = perf_counter()

    print(f'Duplicates are: {duplicates}')
    print(f' Checking dir{path} for duplicate files takes {t1_stop - t1_start} seconds.')
    with open(r"C:\Users\Oleksander\duplicates.txt", 'wt') as fp:
        fp.write(json.dumps(duplicates))


