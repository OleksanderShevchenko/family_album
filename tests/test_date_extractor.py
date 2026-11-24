import os
import shutil
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime

import cv2
import numpy as np
from PIL import Image

from src.family_album.utility_functions.date_extractor import (
    extract_date_from_filename,
    extract_date_from_filesystem,
    extract_date_from_exif,
    extract_date_from_video,
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
        # Past dates earlier than default min_valid_date (2000-01-01), including 1970/1980 epochs
        self.assertFalse(is_valid_date(1950, 1, 1))
        self.assertFalse(is_valid_date(1970, 1, 1))
        self.assertFalse(is_valid_date(1980, 1, 1))
        self.assertFalse(is_valid_date(1999, 12, 31))
        # Boundary accepted with default 2000-01-01
        self.assertTrue(is_valid_date(2000, 1, 1))
        # Custom min_date override allows earlier dates when configured
        self.assertTrue(is_valid_date(1998, 5, 10, min_date=datetime(1995, 1, 1)))

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

    def test_extract_date_from_video_container_metadata(self):
        """Extracts creation_time from real MP4 container metadata via date_extractor."""
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        video_with_meta = os.path.join(tests_dir, "data", "video", "test_2.mp4")
        dt = extract_date_from_video(video_with_meta)
        self.assertEqual(dt, datetime(2021, 10, 4, 12, 59, 50))

    def test_google_photos_bogus_1970_1980_exif_falls_back_to_valid_last_modified(self):
        """
        Generates a real JPEG with bogus 1970/1980 EXIF dates (simulating Google Photos
        animations/collages) and a valid Last Modified timestamp (2019-08-22 14:35:00).
        Verifies 1970/1980 EXIF is rejected and Last Modified is selected via filesystem fallback.
        """
        tmp_dir = tempfile.mkdtemp(prefix="test_bogus_exif_")
        try:
            jpg_path = os.path.join(tmp_dir, "google_collage_animation.jpg")
            img = Image.new("RGB", (64, 64), color=(80, 140, 200))
            exif = img.getexif()
            exif[306] = "1980:01:01 00:00:00"    # Image DateTime (DOS/ZIP epoch)
            exif[36867] = "1970:01:01 00:00:00"  # DateTimeOriginal (Unix epoch)
            exif[36868] = "1980:01:01 00:00:00"  # DateTimeDigitized
            img.save(jpg_path, "JPEG", exif=exif)

            expected_dt = datetime(2019, 8, 22, 14, 35, 0)
            expected_ts = expected_dt.timestamp()
            os.utime(jpg_path, (expected_ts, expected_ts))

            # EXIF extraction must reject 1970 and 1980 under default min_valid_date (2000-01-01)
            self.assertIsNone(extract_date_from_exif(jpg_path, min_date=datetime(2000, 1, 1)))

            # Full extraction must fall back to Last Modified (2019-08-22)
            res = extract_media_date(jpg_path, min_date=datetime(2000, 1, 1))
            self.assertTrue(res.has_date)
            self.assertEqual(res.source, "filesystem")
            self.assertEqual(res.date, expected_dt)
            self.assertEqual(res.year_folder, "2019")
            self.assertEqual(res.month_folder, "08")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_generated_video_without_metadata_falls_back_to_valid_last_modified(self):
        """
        Generates a real small AVI video with no container creation_time and no date in filename,
        assigns a valid Last Modified timestamp (2021-11-05 08:20:00), and verifies filesystem fallback.
        """
        tmp_dir = tempfile.mkdtemp(prefix="test_gen_video_")
        try:
            vid_path = os.path.join(tmp_dir, "family_clip_untitled.avi")
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            writer = cv2.VideoWriter(vid_path, fourcc, 10.0, (64, 64))
            frame = np.zeros((64, 64, 3), dtype=np.uint8)
            for _ in range(5):
                writer.write(frame)
            writer.release()

            expected_dt = datetime(2021, 11, 5, 8, 20, 0)
            expected_ts = expected_dt.timestamp()
            os.utime(vid_path, (expected_ts, expected_ts))

            res = extract_media_date(vid_path, min_date=datetime(2000, 1, 1))
            self.assertTrue(res.has_date)
            self.assertEqual(res.source, "filesystem")
            self.assertEqual(res.date, expected_dt)
            self.assertEqual(res.year_folder, "2021")
            self.assertEqual(res.month_folder, "11")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_bogus_1980_filesystem_mtime_routes_to_no_date(self):
        """
        If a file's Last Modified timestamp itself is an epoch placeholder (< 2000-01-01,
        e.g., 1980-01-01), filesystem fallback rejects it rather than picking today's st_ctime.
        """
        tmp_dir = tempfile.mkdtemp(prefix="test_bogus_mtime_")
        try:
            f_path = os.path.join(tmp_dir, "old_zip_extract.png")
            with open(f_path, "wb") as f:
                f.write(b"dummy")
            bogus_ts = datetime(1980, 1, 1, 0, 0, 0).timestamp()
            os.utime(f_path, (bogus_ts, bogus_ts))

            self.assertIsNone(extract_date_from_filesystem(f_path, min_date=datetime(2000, 1, 1)))
            res = extract_media_date(f_path, min_date=datetime(2000, 1, 1))
            self.assertFalse(res.has_date)
            self.assertEqual(res.source, "none")
            self.assertEqual(res.year_folder, "No_Date")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
