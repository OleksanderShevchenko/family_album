"""
Image utility module for the Family Album application.

Provides fast single-pass image header inspection (`inspect_image_fast`), image
type verification (`is_image_file`), EXIF extraction via Pillow and exifread,
creation date lookup, pixel dimension queries, and camera manufacturer retrieval.
"""

from datetime import datetime
import os
from typing import Optional

import cv2
import exifread
import pandas as pd
from geopy.geocoders import Nominatim
from matplotlib import pyplot as plt
from pandas._libs.missing import NAType
from PIL import Image
import requests

from src.family_album.utility_functions.file_utils import get_file_creation_date

IMAGE_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif',
    '.webp', '.heic', '.heif', '.ico', '.ppm', '.pgm', '.pbm',
)


def has_image_extension(file_name: str) -> bool:
    """
    Fast check whether a filename ends with a standard image extension.

    Args:
        file_name (str): Path or filename to inspect.

    Returns:
        bool: True if filename ends with a recognized image extension.
    """
    return bool(file_name and file_name.lower().endswith(IMAGE_EXTENSIONS))


def inspect_image_fast(file_path: str) -> tuple[bool, str, str]:
    """
    Single-pass lightweight image header inspection using Pillow.

    Opens the image header once (without decoding full pixel data) and extracts:
    - Whether the file is a valid image (`bool`)
    - Dimensions formatted as `'WIDTHxHEIGHT'` (`str`)
    - Camera manufacturer (`Make`, EXIF tag 271) (`str`)

    Args:
        file_path (str): Path to the candidate file.

    Returns:
        tuple[bool, str, str]: `(is_image, resolution, maker)`.
    """
    if not file_path or not os.path.isfile(file_path):
        return False, "", ""
    try:
        with Image.open(file_path) as img:
            w, h = img.size
            resolution = f"{w}x{h}" if (w and h) else ""
            maker = ""
            try:
                exif = img.getexif()
                if exif and 271 in exif:
                    maker = str(exif[271]).strip()
            except Exception:
                pass
            return True, resolution, maker
    except Exception:
        return False, "", ""


def is_image_file(file_name: str) -> bool:
    """
    Check if a file is a valid image using Pillow, falling back to OpenCV only
    for files with recognized image extensions.

    Args:
        file_name (str): Full (absolute) path to the file.

    Returns:
        bool: True if the file is a valid image, False otherwise.
    """
    return _is_image_pillow(file_name) or (has_image_extension(file_name) and _is_image_cv2(file_name))


def _is_image_pillow(file_name: str) -> bool:
    """Verify image integrity using Pillow with proper context manager cleanup."""
    if not os.path.isfile(file_name):
        return False
    try:
        with Image.open(file_name) as img:
            img.verify()
        return True
    except Exception:
        return False


def _is_image_cv2(file_name: str) -> bool:
    """Fallback image check using OpenCV imread."""
    if not os.path.isfile(file_name):
        return False
    try:
        img = cv2.imread(file_name)
        return img is not None
    except Exception:
        return False


def __get_image_capture_date(file_name: str) -> Optional[datetime]:
    """
    Extract an image's capture date from EXIF DateTimeOriginal using exifread.

    Args:
        file_name (str): Full (absolute) path to the file.

    Returns:
        Optional[datetime]: Capture datetime if found, or None otherwise.
    """
    try:
        with open(file_name, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            date_str = str(tags.get('EXIF DateTimeOriginal'))
            return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
    except (IOError, ValueError, AttributeError, KeyError):
        return None


def get_image_exif(file_name: str, combine: bool = False) -> dict:
    """
    Retrieve EXIF metadata tags from an image file.

    Args:
        file_name (str): Full path to the image file.
        combine (bool, optional): If True, merges Pillow EXIF tags with exifread tags. Defaults to False.

    Returns:
        dict: Dictionary of EXIF tags, or empty dict if unavailable.
    """
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
    """Extract top-level EXIF dictionary using Pillow."""
    with Image.open(file_name) as image:
        exif_ = image.getexif()
        return {key: val for key, val in exif_.items()}


def _get_image_info(file_name: str) -> dict:
    """Extract full EXIF tag dictionary using exifread."""
    try:
        with open(file_name, 'rb') as f:
            return exifread.process_file(f)
    except Exception:
        return {}


def get_image_creation_date(file_name: str) -> datetime | NAType:
    """
    Extract an image's creation date from Pillow EXIF tags and exifread,
    falling back to OS filesystem timestamps if no EXIF date is present.

    Args:
        file_name (str): Full (absolute) path to the image file.

    Returns:
        datetime | NAType: Earliest detected creation datetime, or pandas.NaT on failure.
    """
    output = pd.NaT
    if not os.path.isfile(file_name):
        return output

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
            output = min(creation_date)
        if output is pd.NaT:
            output = get_file_creation_date(file_name)
        return output


def get_image_size(file_path: str) -> Optional[tuple[int, int]]:
    """
    Retrieve image pixel dimensions `(width, height)` using Pillow.

    Args:
        file_path (str): Full (absolute) path to the image file.

    Returns:
        Optional[tuple[int, int]]: `(width, height)` tuple, or None on error.
    """
    try:
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None


def get_image_gps_coordinates(file_name: str) -> Optional[tuple]:
    """
    Placeholder helper to extract image GPS coordinates via exifread.

    Args:
        file_name (str): Full (absolute) path to the image file.

    Returns:
        Optional[tuple]: `(latitude, longitude)` tuple or `(None, None)`.
    """
    try:
        with open(file_name, 'rb') as f:
            tags = exifread.process_file(f, details=False)

        return None, None
    except Exception:
        return None, None


def get_image_maker(file_name: str) -> str:
    """
    Retrieve the camera or device manufacturer (`Make`) from image EXIF metadata.

    Attempts fast Pillow EXIF tag 271 lookup first, falling back to `exifread`
    with `details=False`.

    Args:
        file_name (str): Full (absolute) path to the image file.

    Returns:
        str: Camera manufacturer string, or empty string if absent.
    """
    try:
        with Image.open(file_name) as img:
            exif = img.getexif()
            if exif and 271 in exif:
                return str(exif[271]).strip()
    except Exception:
        pass

    try:
        with open(file_name, 'rb') as f:
            tags = exifread.process_file(f, details=False)
            make = tags.get('Image Make', None)
            if make:
                return str(make).strip()
    except Exception:
        pass
    return ""


def _get_region_from_coords(latitude: float, longitude: float) -> str:
    """Resolve human-readable region name from GPS coordinates using Nominatim."""
    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={latitude}&lon={longitude}"
    response = requests.get(url)
    json_data = response.json()
    return json_data['address']['country'] + ", " + json_data['address']['state'] + ", " + json_data['address']['town']


def _imshow(title="Image", image=None, size=10):
    """Debug utility to display an OpenCV BGR image using matplotlib."""
    w, h = image.shape[0], image.shape[1]
    aspect_ratio = w / h
    plt.figure(figsize=(size * aspect_ratio, size))
    plt.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    plt.title(title)
    plt.show()
