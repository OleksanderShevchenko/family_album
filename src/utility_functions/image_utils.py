from datetime import datetime
import os
from typing import Optional

import cv2
import exifread
from geopy.geocoders import Nominatim
from matplotlib import pyplot as plt
from PIL import Image
import requests
from typing import Tuple


def is_file_a_picture(file_name: str) -> bool:
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


def get_image_capture_date(file_name: str) -> Optional[datetime]:
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


def get_image_creation_date(file_name: str) -> Optional[datetime]:
    """
    This function try to get image's creation date by using pillow lib

    :param file_name: full (absolute) name of the file.
    :return: datetime value is success or None otherwise
    """
    if not os.path.isfile(file_name):
        return None

    with Image.open(file_name) as image:
        exif = image._getexif()
        if exif:
            creation_date = []
            if 306 in exif.keys():  # The date and time of image creation
                creation_date.append(datetime.strptime(exif[306], '%Y:%m:%d %H:%M:%S'))
            if 36867 in exif.keys():  # DateTimeOriginal
                creation_date.append(datetime.strptime(exif[36867], '%Y:%m:%d %H:%M:%S'))
            if 36868 in exif.keys():  # DateTimeDigitized
                creation_date.append(datetime.strptime(exif[36868], '%Y:%m:%d %H:%M:%S'))
            if 50971 in exif.keys():  # PreviewDateTime
                creation_date.append(datetime.strptime(exif[50971], '%Y:%m:%d %H:%M:%S'))
            if len(creation_date) > 0:
                return min(creation_date)
        return None


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
            tags = exifread.process_file(f, stop_tag='GPSLongitude')
            if all(key in tags for key in ['GPSLatitude', 'GPSLongitude']):
                lat_ref = str(tags['GPSLatitudeRef'])
                lat = str(tags['GPSLatitude'])
                lon_ref = str(tags['GPSLongitudeRef'])
                lon = str(tags['GPSLongitude'])
                lat_parts = lat.split('/')
                lat_float = float(lat_parts[0]) / float(lat_parts[1])
                lon_parts = lon.split('/')
                lon_float = float(lon_parts[0]) / float(lon_parts[1])
                if lat_ref == 'S':
                    lat_float = -lat_float
                if lon_ref == 'W':
                    lon_float = -lon_float
                return (lat_float, lon_float)
        return None
    except Exception:
        return None


def get_image_maker(file_name: str) -> Optional[str]:
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
            return None

def _imshow(title="Image", image=None, size=10):
    w, h = image.shape[0], image.shape[1]
    aspect_ratio = w/h
    plt.figure(figsize=(size * aspect_ratio,size))
    plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    plt.title(title)
    plt.show()