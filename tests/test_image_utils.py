import os.path
import unittest

from src.family_album.utility_functions.image_utils import (
    has_image_extension,
    inspect_image_fast,
    is_image_file,
    get_image_size,
)


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
