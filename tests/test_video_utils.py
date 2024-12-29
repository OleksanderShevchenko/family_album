import pandas as pd
import os.path
import unittest
from datetime import datetime

from src.family_album.utility_functions.video_utils import *


class TestVideoUtils(unittest.TestCase):

    def setUp(self):
        self._image_path = os.path.abspath('./data/images/')
        self._video_path = os.path.abspath('./data/video/')
        self._video_take_date = {'test.3g2': datetime(year=2024, month=12, day=29, hour=19, minute=12, second=24,
                                                      microsecond=476345),
                                 'test.3gp': datetime(year=2024, month=12, day=29, hour=19, minute=11, second=36,
                                                      microsecond=659762),
                                 'test.avi': datetime(year=2024, month=12, day=29, hour=18, minute=58, second=20,
                                                      microsecond=268663),
                                 'test.flv': datetime(year=2024, month=12, day=29, hour=19, minute=6, second=32,
                                                      microsecond=292542),
                                 'test.mkv': datetime(year=2024, month=12, day=29, hour=19, minute=9, second=37,
                                                      microsecond=772402),
                                 'test.mov': datetime(year=2024, month=12, day=29, hour=19, minute=2, second=53,
                                                      microsecond=135194),
                                 'test.mp4': datetime(year=2024, month=12, day=29, hour=19, minute=4, second=34,
                                                      microsecond=251536),
                                 'test.gif': datetime(year=2024, month=12, day=29, hour=18, minute=45, second=10,
                                                      microsecond=505596),
                                 'test.mpeg': datetime(year=2024, month=12, day=29, hour=19, minute=10, second=57,
                                                       microsecond=903418),
                                 'test.mpg': datetime(year=2024, month=12, day=29, hour=19, minute=11, second=13,
                                                      microsecond=47858),
                                 'test.mts': datetime(year=2024, month=12, day=29, hour=19, minute=14, second=48,
                                                      microsecond=141947),
                                 'test.webm': datetime(year=2024, month=12, day=29, hour=19, minute=4, second=41,
                                                       microsecond=833414),
                                 'test.wmv': datetime(year=2024, month=12, day=29, hour=19, minute=7, second=45,
                                                      microsecond=266533),
                                 'test_2.mp4': datetime(year=2021, month=10, day=9, hour=11, minute=52, second=44,
                                                        microsecond=0),
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
                expected_date = self._video_take_date[file]
                take_date = get_video_creation_date(full_name)
                if take_date is pd.NaT:
                    self.assertTrue(expected_date is take_date)
                else:
                    self.assertEqual(expected_date, take_date)
