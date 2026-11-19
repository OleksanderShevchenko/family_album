import os.path
import unittest
from unittest.mock import patch

from src.family_album.utility_functions.video_utils import (
    has_video_extension,
    is_file_a_video,
    get_video_resolution_fast,
)


class TestVideoUtils(unittest.TestCase):

    def setUp(self):
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        self._image_path = os.path.abspath(os.path.join(tests_dir, 'data', 'images'))
        self._video_path = os.path.abspath(os.path.join(tests_dir, 'data', 'video'))

    def test_is_video(self):
        for dir_name, _, files in os.walk(self._video_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertTrue(is_file_a_video(full_name))
        # images are not video
        for dir_name, _, files in os.walk(self._image_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertFalse(is_file_a_video(full_name))

    def test_is_video_does_not_invoke_moviepy_on_images(self):
        """Ensure is_file_a_video short-circuits on non-video extensions without launching MoviePy/FFmpeg."""
        with patch("src.family_album.utility_functions.video_utils.VideoFileClip") as mock_clip:
            for dir_name, _, files in os.walk(self._image_path):
                for file in files:
                    full_name = os.path.join(dir_name, file)
                    self.assertFalse(has_video_extension(full_name))
                    self.assertFalse(is_file_a_video(full_name))
            mock_clip.assert_not_called()

    def test_get_video_resolution_fast(self):
        """Fast OpenCV resolution lookup returns WIDTHxHEIGHT for videos and empty string for images."""
        for dir_name, _, files in os.walk(self._video_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                res = get_video_resolution_fast(full_name)
                self.assertRegex(res, r"^\d+x\d+$")
        for dir_name, _, files in os.walk(self._image_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                self.assertEqual(get_video_resolution_fast(full_name), "")
