import os.path
import unittest
from datetime import datetime

from src.utility_functions.image_utils import (is_file_a_picture, get_image_size, get_image_creation_date)


class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        self._data_path = os.path.abspath('./data/images/')
        self._image_sizes = {'test_photo.jpg': (1600, 720),
                             'test_photo2.jpg': (720, 1600),
                             'test_photo3.jpg': (4000, 1800),
                             'test_photo4.jpg': (4000, 1800)}
        self._image_take_date = {'test_photo.jpg': None,
                                 'test_photo2.jpg': None,
                                 'test_photo3.jpg': datetime(year=2024, month=2, day=23, hour=11, minute=24, second=48),
                                 'test_photo4.jpg': datetime(year=2024, month=2, day=20, hour=11, minute=42, second=58)}

    def test_is_image(self):
        for dir_name, _, files in os.walk(self._data_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertTrue(is_file_a_picture(full_name))

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
                self.assertEqual(expected_date, take_date)
