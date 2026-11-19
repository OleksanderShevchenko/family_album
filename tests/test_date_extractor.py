import os
import unittest
from unittest.mock import patch
from datetime import datetime

from src.family_album.utility_functions.date_extractor import (
    extract_date_from_filename,
    extract_date_from_exif,
    is_valid_date,
    extract_media_date,
    MediaDateResult,
)


class TestDateExtractor(unittest.TestCase):

    def test_standard_camera_formats(self):
        # IMG_YYYYMMDD_HHMMSS
        dt = extract_date_from_filename("IMG_20230514_143022.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2023, 5, 14, 14, 30, 22))

        # VID_YYYYMMDD_HHMMSS
        dt = extract_date_from_filename("VID_20211025_091530.mp4")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2021, 10, 25, 9, 15, 30))

        # PXL_YYYYMMDD_HHMMSS with millisecond suffix
        dt = extract_date_from_filename("PXL_20220815_120530123.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2022, 8, 15, 12, 5, 30))

        # Compact YYYYMMDD_HHMMSS
        dt = extract_date_from_filename("20200412_182301.png")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2020, 4, 12, 18, 23, 1))

    def test_separated_date_time_formats(self):
        # 2020-04-12 18.23.01
        dt = extract_date_from_filename("2020-04-12 18.23.01.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2020, 4, 12, 18, 23, 1))

        # 2020-04-12_18-23-01
        dt = extract_date_from_filename("2020-04-12_18-23-01.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2020, 4, 12, 18, 23, 1))

        # macOS Screen Shot 2021-09-15 at 14.30.22
        dt = extract_date_from_filename("Screen Shot 2021-09-15 at 14.30.22.png")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2021, 9, 15, 14, 30, 22))

    def test_screenshot_patterns(self):
        # Screenshot_2022-01-01-23-59-59
        dt = extract_date_from_filename("Screenshot_2022-01-01-23-59-59.png")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2022, 1, 1, 23, 59, 59))

        # Screenshot_20220101-235959_WhatsApp.jpg
        dt = extract_date_from_filename("Screenshot_20220101-235959_WhatsApp.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2022, 1, 1, 23, 59, 59))

    def test_whatsapp_patterns(self):
        # WhatsApp Image 2021-06-25 at 15.30.45.jpeg
        dt = extract_date_from_filename("WhatsApp Image 2021-06-25 at 15.30.45.jpeg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2021, 6, 25, 15, 30, 45))

    def test_date_only_formats(self):
        # 2020-04-12.jpg
        dt = extract_date_from_filename("2020-04-12.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2020, 4, 12, 0, 0, 0))

        # WP_20170308_001.jpg
        dt = extract_date_from_filename("WP_20170308_001.jpg")
        self.assertIsNotNone(dt)
        self.assertEqual(dt, datetime(2017, 3, 8, 0, 0, 0))

    def test_invalid_dates_rejected(self):
        # Invalid month
        self.assertFalse(is_valid_date(2020, 13, 1))
        # Invalid day
        self.assertFalse(is_valid_date(2020, 2, 30))
        # Future year (> current + 1)
        self.assertFalse(is_valid_date(2099, 1, 1))
        # Past year (< 1970)
        self.assertFalse(is_valid_date(1950, 1, 1))

    def test_non_date_filenames_return_none(self):
        self.assertIsNone(extract_date_from_filename("wallpaper.jpg"))
        self.assertIsNone(extract_date_from_filename("avatar_profile.png"))
        self.assertIsNone(extract_date_from_filename("DSC00123.jpg"))
        self.assertIsNone(extract_date_from_filename("IMG_0001.JPG"))

    def test_media_date_result_properties(self):
        res_with_date = MediaDateResult(
            date=datetime(2023, 5, 14, 10, 0, 0),
            source="filename",
            detail="test"
        )
        self.assertTrue(res_with_date.has_date)
        self.assertEqual(res_with_date.year_folder, "2023")
        self.assertEqual(res_with_date.month_folder, "05")

        res_no_date = MediaDateResult(
            date=None,
            source="none",
            detail="no date found"
        )
        self.assertFalse(res_no_date.has_date)
        self.assertEqual(res_no_date.year_folder, "No_Date")
        self.assertEqual(res_no_date.month_folder, "")

    def test_fast_exif_extraction_via_pillow_skips_exifread(self):
        """Standard EXIF DateTimeOriginal in Sub-IFD 0x8769 is extracted via Pillow without invoking exifread."""
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        photo_with_exif = os.path.join(tests_dir, "data", "images", "test_photo3.jpg")
        with patch("src.family_album.utility_functions.date_extractor.exifread.process_file") as mock_er:
            dt = extract_date_from_exif(photo_with_exif)
            self.assertEqual(dt, datetime(2024, 2, 23, 11, 24, 48))
            mock_er.assert_not_called()


if __name__ == "__main__":
    unittest.main()
