# -*- coding: utf-8 -*-
import base64
import os.path


def picture_to_string(file: str, variable_name: str) -> None:
    if not os.path.isfile(file):
        return

    with open(file, 'rb') as pic:
        content = '{} = {}\n'.format(variable_name, base64.b64encode(pic.read()))

    with open('../src/mantra_ui/resources/pictures.py', 'a') as f:
        f.write(content)


if __name__ == '__main__':
    dir_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'src', 'resources')
    for filename in os.scandir(dir_path):
        if filename.is_file() and (filename.name.endswith('.ico') or filename.name.endswith('.png') or filename.name.endswith('.jpg')):
            var_name = filename.name.split('.')[0]
            print(f'Picture {filename.path} will be saved into pictures.py file as binary string variable of name {var_name}')
            picture_to_string(filename.path, var_name)
