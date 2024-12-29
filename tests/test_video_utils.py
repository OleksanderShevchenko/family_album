import pandas as pd
import os.path
import unittest
from datetime import datetime

from src.family_album.utility_functions.video_utils import *


class TestVideoUtils(unittest.TestCase):

    def setUp(self):
        self._image_path = os.path.abspath('./data/images/')
        self._video_path = os.path.abspath('./data/video/')

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
