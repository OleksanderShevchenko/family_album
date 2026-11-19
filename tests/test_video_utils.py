import pandas as pd
import os.path
import unittest
from unittest.mock import patch
from datetime import datetime

from src.family_album.utility_functions.video_utils import (
    has_video_extension,
    is_file_a_video,
    get_video_resolution_fast,
    get_video_metadata,
    get_video_creation_date
)
from src.family_album.utility_functions.file_utils import get_file_creation_date


class TestVideoUtils(unittest.TestCase):

    def setUp(self):
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        self._image_path = os.path.abspath(os.path.join(tests_dir, 'data', 'images'))
        self._video_path = os.path.abspath(os.path.join(tests_dir, 'data', 'video'))
        # Only files with embedded container metadata (creation_time) have fixed dates
        self._video_take_date = {
            'test_2.mp4': datetime(year=2021, month=10, day=4, hour=12, minute=59, second=50)
        }

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

    def test_get_video_creation_date(self):
        for dir_name, _, files in os.walk(self._video_path):
            for file in files:
                full_name = os.path.join(dir_name, file)
                take_date = get_video_creation_date(full_name)
                if file in self._video_take_date:
                    expected_date = self._video_take_date[file]
                    if take_date is pd.NaT:
                        self.assertTrue(expected_date is take_date)
                    else:
                        self.assertEqual(expected_date, take_date)
                else:
                    # Videos without container creation metadata fallback to OS filesystem creation date
                    self.assertEqual(get_file_creation_date(full_name), take_date)

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
