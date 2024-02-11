from datetime import datetime
import os
from typing import Optional

import exifread
import cv2
from PIL import Image


def is_file_a_picture(file_name):
    try:
        img = Image.open(file_name)
        img.verify()  # перевірка на коректність зображення
        return True
    except:
        return False


def is_image_file(filename):
    try:
        img = cv2.imread(filename)
        if img is not None:
            return True
        else:
            return False
    except:
        return False

def get_file_size(filename: str) -> Optional[int]:
    """
    Функція, яка повертає розмір файлу у байтах.

    :param filename: Ім'я файлу.
    :return: Розмір файлу у байтах або None, якщо не вдається отримати інформацію про файл.
    """
    try:
        return os.path.getsize(filename)
    except OSError:
        return None


def get_file_creation_date(filename: str) -> Optional[datetime]:
    """
    Функція, яка повертає дату створення файлу.

    :param filename: Ім'я файлу.
    :return: Дата створення файлу у форматі datetime або None, якщо не вдається отримати дату створення файлу.
    """
    try:
        return datetime.fromtimestamp(os.path.getctime(filename))
    except OSError:
        return None


def get_file_exif_date(filename: str) -> Optional[datetime]:
    """
    Функція, яка повертає дату зйомки фотографії, якщо вона присутня в метаданих EXIF.

    :param filename: Ім'я файлу.
    :return: Дата зйомки фотографії у форматі datetime або None, якщо не вдається отримати дату з метаданих EXIF.
    """
    try:
        with open(filename, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            date_str = str(tags.get('EXIF DateTimeOriginal'))
            return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except (IOError, ValueError, AttributeError, KeyError):
        return None