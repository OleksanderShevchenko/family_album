import pandas as pd
import os.path
import unittest
from datetime import datetime

from src.family_album.utility_functions.image_utils import (
    has_image_extension,
    inspect_image_fast,
    is_image_file,
    get_image_size,
    get_image_creation_date,
    get_image_exif
)
from src.family_album.utility_functions.file_utils import get_file_creation_date


class TestImageUtils(unittest.TestCase):

    def setUp(self):
        self._data_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'images'))
        self._image_sizes = {
            'test_photo.jpg': (1600, 720),
            'test_photo2.jpg': (720, 1600),
            'test_photo3.jpg': (4000, 1800),
            'test_photo4.jpg': (4000, 1800),
            'test.jpg': (400, 300)
        }
        # Files with embedded EXIF dates
        self._image_take_date = {
            'test_photo3.jpg': datetime(year=2024, month=2, day=23, hour=11, minute=24, second=48),
            'test_photo4.jpg': datetime(year=2024, month=2, day=20, hour=11, minute=42, second=58),
            'test.jpg': datetime(year=2010, month=1, day=1, hour=0, minute=0, second=0)
        }
        self._exif_size = {
            'test_photo.jpg': 0,
            'test_photo2.jpg': 0,
            'test_photo3.jpg': 58,
            'test_photo4.jpg': 58,
            'test.jpg': 108  # the only file that has got MakerNote IFD metadata
        }

    def test_is_image(self):
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertTrue(is_image_file(full_name))

    def test_image_size(self):
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertEqual(get_image_size(full_name), self._image_sizes[file])

    def test_image_creation_date(self):
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                take_date = get_image_creation_date(full_name)
                if file in self._image_take_date:
                    expected_date = self._image_take_date[file]
                    if take_date is pd.NaT:
                        self.assertTrue(expected_date is take_date)
                    else:
                        self.assertEqual(expected_date, take_date)
                else:
                    # Files without EXIF metadata (e.g. test_photo.jpg, test_photo2.jpg)
                    # should fall back to OS filesystem creation date
                    self.assertEqual(get_file_creation_date(full_name), take_date)

    def test_image_exif_data(self):
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                exif_ = get_image_exif(full_name)
                expected_size = self._exif_size[file]
                self.assertEqual(expected_size, len(exif_))

    def test_inspect_image_fast(self):
        """Single-pass Pillow inspection returns valid image flag, WxH resolution, and maker."""
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertTrue(has_image_extension(full_name))
                is_img, resolution, maker = inspect_image_fast(full_name)
                self.assertTrue(is_img)
                exp_w, exp_h = self._image_sizes[file]
                self.assertEqual(resolution, f"{exp_w}x{exp_h}")
                self.assertIsInstance(maker, str)

        is_img, resolution, maker = inspect_image_fast("nonexistent_file.jpg")
        self.assertFalse(is_img)
        self.assertEqual(resolution, "")
        self.assertEqual(maker, "")

