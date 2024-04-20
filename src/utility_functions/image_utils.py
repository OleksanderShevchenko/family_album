from datetime import datetime
import os
from typing import Optional

import cv2
import exifread
import pandas as pd
from geopy.geocoders import Nominatim
from matplotlib import pyplot as plt
from PIL import Image
import requests

from pandas._libs.missing import NAType


def is_image_file(file_name: str) -> bool:
    """
    Check if passed file is image by means of pillow and python-opencv libs together

    :param file_name: full (absolute) name of the file.
    :return: boolean flag - true if the file may assume as image, ot False otherwise.
    """
    return _is_image_pillow(file_name) or _is_image_cv2(file_name)


def _is_image_pillow(file_name: str) -> bool:
    if not os.path.isfile(file_name):  # check if passed string represent a file
        return False
    try:
        img = Image.open(file_name)
        img.verify()  # check if image is correct
        return True
    except Exception:
        return False


def _is_image_cv2(file_name: str) -> bool:
    if not os.path.isfile(file_name):  # check if passed string represent a file
        return False
    try:
        img = cv2.imread(file_name)
        if img is not None:
            return True
        else:
            return False
    except Exception:
        return False


def __get_image_capture_date(file_name: str) -> Optional[datetime]:
    """
    This function try to get image's take date by using metadata EXIF.

    :param file_name: full (absolute) name of the file.
    :return: datetime value is success or None otherwise
    """
    try:
        with open(file_name, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            date_str = str(tags.get('EXIF DateTimeOriginal'))
            return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except (IOError, ValueError, AttributeError, KeyError):
        return None


def get_image_exif(file_name: str, combine: bool = False) -> dict:
    result = {}
    if not os.path.isfile(file_name):
        return result
    result = _get_image_info(file_name)
    if result is not None:
        if combine:
            try:
                exif_ = _get_image_info_pil(file_name)
                result.update(exif_)
            except Exception:
                pass
        return result
    else:
        return _get_image_info_pil(file_name)


def _get_image_info_pil(file_name: str) -> dict:
    with Image.open(file_name) as image:
        exif_ = image.getexif()
        return {key: val for key, val in exif_.items()}


def _get_image_info(file_name: str) -> dict:
    try:
        with open(file_name, 'rb') as f:
            return exifread.process_file(f)
    except Exception:
        return {}


def get_image_creation_date(file_name: str) -> datetime|NAType:
    """
    This function try to get image's creation date by using pillow lib

    :param file_name: full (absolute) name of the file.
    :return: datetime value is success or None otherwise
    """
    if not os.path.isfile(file_name):
        return None

    with Image.open(file_name) as image:
        exif = image.getexif()
        creation_date = []
        if exif:
            if 306 in exif.keys():  # The date and time of image creation
                creation_date.append(datetime.strptime(exif[306], '%Y:%m:%d %H:%M:%S'))
            if 36867 in exif.keys():  # DateTimeOriginal
                creation_date.append(datetime.strptime(exif[36867], '%Y:%m:%d %H:%M:%S'))
            if 36868 in exif.keys():  # DateTimeDigitized
                creation_date.append(datetime.strptime(exif[36868], '%Y:%m:%d %H:%M:%S'))
            if 50971 in exif.keys():  # PreviewDateTime
                creation_date.append(datetime.strptime(exif[50971], '%Y:%m:%d %H:%M:%S'))
        capture_date = __get_image_capture_date(file_name)
        if isinstance(capture_date, datetime):
            creation_date.append(capture_date)
        if len(creation_date) > 0:
            return min(creation_date)
        return pd.NaT


def get_image_size(file_path: str) -> Optional[tuple[int, int]]:
    """
    This function try to get image's size in pixels by using pillow lib

    :param file_name: full (absolute) name of the file.
    :return: size of the image in pixels in cas of success or None otherwise
    """
    try:
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None


def get_image_gps_coordinates(file_name: str) -> Optional[tuple]:
    """
   This function try to get image's geolocation by means of exifread lib

   :param file_name: full (absolute) name of the file.
   :return: size of the image in pixels in case of success or None otherwise
   """
    try:
        with open(file_name, 'rb') as f:
            tags = exifread.process_file(f)

        return None, None
    except Exception:
        return None, None


def get_image_maker(file_name: str) -> str:
    """
    This function try to get image's geolocation by means of exifread lib

    :param file_name: full (absolute) name of the file.
    :return: size of the image in pixels in case of success or None otherwise
    """
    with open(file_name, 'rb') as f:
        tags = exifread.process_file(f, details=False)
        make = tags.get('Image Make', None)
        if make:
            return str(make)
        else:
            return ""  # return empty string instead of None


def _get_region_from_coords(latitude: float, longitude: float) -> str:
    geolocator = Nominatim(user_agent="my-application")
    location = geolocator.reverse(f"{latitude}, {longitude}")
    return location.raw['address']['state']


def _get_region_from_coords(latitude: float, longitude: float) -> str:
    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={latitude}&lon={longitude}"
    response = requests.get(url)
    json_data = response.json()
    return json_data['address']['country'] + ", " + json_data['address']['state'] + ", " + json_data['address']['town']


def _imshow(title="Image", image=None, size=10):
    w, h = image.shape[0], image.shape[1]
    aspect_ratio = w/h
    plt.figure(figsize=(size * aspect_ratio,size))
    plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    plt.title(title)
    plt.show()