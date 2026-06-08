# -*- coding: utf-8 -*-
import base64
import os
import sys


def single_ui_to_py(input_file: str, output_folder: str, make_executable: bool = False) -> None:
    # define current virtual environment interpreter location
    python_interpreter_path = os.path.abspath(sys.executable)
    # assume that pyuic5.exe shall be in same folder
    pyuic_path = os.path.join(os.path.split(python_interpreter_path)[0], "pyuic6.exe")
    if not os.path.isfile(pyuic_path):
        print(f'Could not find pyuic5.exe file in {os.path.split(python_interpreter_path)[0]}! ' +
              f"Fail to convert {input_file} ui file.")
        return
    if not os.path.isfile(input_file):
        print(f"File {input_file} could not be found as existing file!")
        return
    # define name for compiled ui file
    file_name = os.path.splitext(os.path.basename(input_file))[0]
    output_file = os.path.join(output_folder, file_name + ".py")
    if make_executable:
        chkEx = " -x"
    else:
        chkEx = ""
    os.system("{} {} {} -o {}".format(pyuic_path, chkEx, input_file, output_file))


def convert_main_interface_ui_files() -> None:
    input_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'src', 'family_album',
                              'gui', 'widgets','py_ui')
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'src', 'family_album',
                               'gui', 'widgets', 'py_ui')
    for filename in os.scandir(input_path):
        if filename.is_file():
            single_ui_to_py(filename.path, output_path)

    input_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'src', 'family_album',
                              'gui', 'py_ui')
    output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'src', 'family_album',
                               'gui', 'py_ui')
    for filename in os.scandir(input_path):
        if filename.is_file():
            single_ui_to_py(filename.path, output_path)


if __name__ == '__main__':
    convert_main_interface_ui_files()


