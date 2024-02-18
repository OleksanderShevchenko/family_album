import os
import platform
import time
import datetime
from typing import Optional


def get_file_creation_date(file_name: str) -> Optional[datetime]:
    """
    The function returns date of the file creation

    :param file_name: full (absolute) name of the file.
    :return: date of the file creation i datetime format or None, in case of error.
    """
    if not os.path.isfile(file_name):  # check if passed string represent a file
        return False
    try:
        return _get_creation_date(file_name)
    except OSError:
        return None


def _get_creation_date(file_path):
    creation_date = []
    # Windows-specific approach
    if platform.system() == 'Windows':
        creation_date.append(os.path.getctime(file_path))
        creation_date.append(os.path.getmtime(file_path))
        creation_date.append(os.path.getatime(file_path))
    # Mac or Linux -specific approach
    elif platform.system() == 'Darwin' or platform.system() == 'Linux':
        try:
            creation_date.append(os.stat(file_path).st_birthtime)
        except AttributeError:
            pass  # ignore
        creation_date.append(os.stat(file_path).st_atime)
        creation_date.append(os.stat(file_path).st_mtime)
        creation_date.append(os.stat(file_path).st_ctime)
        creation_date.append(os.path.getmtime(file_path))

    # If none of the above approaches worked, try to get the earliest date
    if len(creation_date) == 0:
        creation_date = [os.path.getctime(file_path), os.path.getmtime(file_path)]

    # Convert the timestamp to a datetime object
    creation_date = datetime.datetime.fromtimestamp(min(creation_date))

    return creation_date


def get_file_size(file_name: str) -> Optional[int]:
    """
    The function returns size of the file in bytes.

    :param file_name: full (absolute) name of the file.
    :return: Size of the file in bytes if successful or None in case of error
    """
    try:
        return os.path.getsize(file_name)
    except OSError:
        return None
