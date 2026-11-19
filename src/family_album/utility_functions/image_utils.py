"""
Image utility module for the Family Album application.

Provides fast single-pass image header inspection (`inspect_image_fast`), image
type verification (`is_image_file`), pixel dimension queries (`get_image_size`),
and camera manufacturer retrieval (`get_image_maker`).
"""

import os
from typing import Optional

import cv2
import exifread
from PIL import Image

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
