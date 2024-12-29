import pandas as pd
import os.path
import unittest
from datetime import datetime

from src.family_album.utility_functions.image_utils import (is_image_file, get_image_size, get_image_creation_date, get_image_exif)


class TestImageUtils(unittest.TestCase):

    def setUp(self):
        self._data_path = os.path.abspath('./data/images/')
        self._image_sizes = {'test_photo.jpg': (1600, 720),
                             'test_photo2.jpg': (720, 1600),
                             'test_photo3.jpg': (4000, 1800),
                             'test_photo4.jpg': (4000, 1800),
                             'test.jpg': (400, 300)}
        self._image_take_date = {'test_photo.jpg': pd.NaT,
                                 'test_photo2.jpg': pd.NaT,
                                 'test_photo3.jpg': datetime(year=2024, month=2, day=23, hour=11, minute=24, second=48),
                                 'test_photo4.jpg': datetime(year=2024, month=2, day=20, hour=11, minute=42, second=58),
                                 'test.jpg': datetime(year=2010, month=1, day=1, hour=0, minute=00, second=00)}
        self._exif_size = {'test_photo.jpg': 0,
                           'test_photo2.jpg': 0,
                           'test_photo3.jpg': 58,
                           'test_photo4.jpg': 58,
                           'test.jpg': 56}

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
                expected_date = self._image_take_date[file]
                if take_date is pd.NaT:
                    self.assertTrue(expected_date is take_date)
                else:
                    self.assertEqual(expected_date, take_date)

    def test_image_exif_data(self):
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                exif_ = get_image_exif(full_name)
                expected_size = self._exif_size[file]
                self.assertEqual(expected_size, len(exif_))
