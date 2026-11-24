import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

from src.family_album_lib.file_organizer_engine import (
    FileOrganizerEngine,
    OrganizerWorker,
    safe_copy_file,
    safe_move_file,
    check_disk_space,
    InsufficientDiskSpaceError,
)
from src.family_album_lib.organizer_db import OrganizerDatabase


class TestFileOrganizerEngine(unittest.TestCase):

    def setUp(self):
        self.temp_root = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_root, "camera_raw")
        self.target_dir = os.path.join(self.temp_root, "camera_raw_organized")
        os.makedirs(self.source_dir, exist_ok=True)

        # Create dummy test files
        self.file1 = os.path.join(self.source_dir, "IMG_20230514_120000.jpg")
        with open(self.file1, "wb") as f:
            f.write(b"image_content_2023_05_14")

        self.file2 = os.path.join(self.source_dir, "VID_20211025_091530.mp4")
        with open(self.file2, "wb") as f:
            f.write(b"video_content_2021_10_25")

        self.file3 = os.path.join(self.source_dir, "random_untitled.png")
        with open(self.file3, "wb") as f:
            f.write(b"no_date_content")
        # Assign pre-2000 placeholder epoch (1980-01-01) so it genuinely routes to No_Date
        bogus_ts = datetime(1980, 1, 1, 0, 0, 0).timestamp()
        os.utime(self.file3, (bogus_ts, bogus_ts))

    def tearDown(self):
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_default_target_dir_is_sibling(self):
        expected = os.path.join(self.temp_root, "camera_raw_organized")
        actual = FileOrganizerEngine.get_default_target_dir(self.source_dir)
        self.assertEqual(os.path.normpath(expected), os.path.normpath(actual))

    def test_safe_copy_and_collision_handling(self):
        dest_dir = os.path.join(self.temp_root, "dest")
        # 1. First copy
        success, path1, status = safe_copy_file(self.file1, dest_dir)
        self.assertTrue(success)
        self.assertEqual(status, "copied")
        self.assertTrue(os.path.isfile(path1))
        # Verify original still exists (Never delete!)
        self.assertTrue(os.path.isfile(self.file1))

        # 2. Identical copy (same content) should be recognized as duplicate
        success2, path2, status2 = safe_copy_file(self.file1, dest_dir)
        self.assertFalse(success2)
        self.assertEqual(status2, "identical_file_already_at_destination")

        # 3. Different content with same filename generates _copy1
        diff_file = os.path.join(self.temp_root, "diff", "IMG_20230514_120000.jpg")
        os.makedirs(os.path.dirname(diff_file), exist_ok=True)
        with open(diff_file, "wb") as f:
            f.write(b"different_content")

        success3, path3, status3 = safe_copy_file(diff_file, dest_dir)
        self.assertTrue(success3)
        self.assertIn("_copy1", path3)
        self.assertTrue(os.path.isfile(path3))

    def test_safe_move(self):
        dest_dir = os.path.join(self.temp_root, "dest_move")
        success, path1, status = safe_move_file(self.file1, dest_dir)
        self.assertTrue(success)
        self.assertTrue(os.path.isfile(path1))
        self.assertFalse(os.path.isfile(self.file1))

    def test_scan_and_plan_routing(self):
        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy"
        )
        self.assertEqual(len(plan), 3)

        plan_by_name = {item.file_name: item for item in plan}
        # Check IMG_20230514_120000.jpg routed to 2023/05
        item1 = plan_by_name["IMG_20230514_120000.jpg"]
        self.assertEqual(item1.date_result.year_folder, "2023")
        self.assertEqual(item1.date_result.month_folder, "05")
        self.assertIn("2023" + os.sep + "05", item1.target_path)

        # Check VID_20211025_091530.mp4 routed to 2021/10
        item2 = plan_by_name["VID_20211025_091530.mp4"]
        self.assertEqual(item2.date_result.year_folder, "2021")
        self.assertEqual(item2.date_result.month_folder, "10")
        self.assertIn("2021" + os.sep + "10", item2.target_path)

        # Check random_untitled.png routed to No_Date
        item3 = plan_by_name["random_untitled.png"]
        self.assertEqual(item3.date_result.year_folder, "No_Date")
        self.assertIn("No_Date", item3.target_path)

    def test_execute_plan_copy_and_db_created(self):
        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy"
        )
        stats = FileOrganizerEngine.execute_plan(
            plan=plan,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy"
        )
        self.assertEqual(stats.copied, 3)
        self.assertEqual(stats.errors, 0)

        # Check that target/.db/album.db was created
        self.assertTrue(OrganizerDatabase.has_database(self.target_dir))
        with OrganizerDatabase(self.target_dir) as db:
            self.assertEqual(db.count_organized_files(), 3)
            # Originals must still exist!
            self.assertTrue(os.path.isfile(self.file1))
            self.assertTrue(os.path.isfile(self.file2))
            self.assertTrue(os.path.isfile(self.file3))

    def test_disk_space_insufficient_raises_error(self):
        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            action_type="copy"
        )
        # Mock disk free space to 1 byte
        with patch("shutil.disk_usage") as mock_usage:
            # os.statvfs_result like object: (total, used, free)
            from collections import namedtuple
            Usage = namedtuple("Usage", ["total", "used", "free"])
            mock_usage.return_value = Usage(total=100000, used=99999, free=1)

            with self.assertRaises(InsufficientDiskSpaceError):
                FileOrganizerEngine.execute_plan(
                    plan=plan,
                    target_dir=self.target_dir,
                    action_type="copy"
                )

    def test_parallel_scan_and_execute_many_files(self):
        """Verify multithreaded scan_and_plan and execute_plan handle many files cleanly."""
        batch_src = os.path.join(self.temp_root, "batch_src")
        batch_dst = os.path.join(self.temp_root, "batch_dst")
        for folder_idx in range(6):
            sub = os.path.join(batch_src, f"dir_{folder_idx}")
            os.makedirs(sub, exist_ok=True)
            for file_idx in range(10):
                fname = f"IMG_2023{folder_idx + 1:02d}{file_idx + 1:02d}_101010_{folder_idx}_{file_idx}.jpg"
                with open(os.path.join(sub, fname), "wb") as f:
                    f.write(f"payload_{folder_idx}_{file_idx}".encode("utf-8"))

        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=batch_src,
            target_dir=batch_dst,
            mode="new_organization",
            action_type="copy",
            max_workers=8,
        )
        self.assertEqual(len(plan), 60)

        stats = FileOrganizerEngine.execute_plan(
            plan=plan,
            target_dir=batch_dst,
            mode="new_organization",
            action_type="copy",
            max_workers=8,
        )
        self.assertEqual(stats.copied, 60)
        self.assertEqual(stats.errors, 0)
        with OrganizerDatabase(batch_dst) as db:
            self.assertEqual(db.count_organized_files(), 60)

    def test_parallel_move_name_collision_safety(self):
        """Stress test: 20 threads moving 20 distinct files with identical names to the same target folder."""
        col_src = os.path.join(self.temp_root, "collision_src")
        col_dst = os.path.join(self.temp_root, "collision_dst")
        expected_contents = set()
        for i in range(20):
            sub = os.path.join(col_src, f"sub_{i:02d}")
            os.makedirs(sub, exist_ok=True)
            content = f"unique_content_number_{i}".encode("utf-8")
            expected_contents.add(content)
            with open(os.path.join(sub, "IMG_20230514_120000.jpg"), "wb") as f:
                f.write(content)

        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=col_src,
            target_dir=col_dst,
            mode="new_organization",
            action_type="move",
            max_workers=8,
        )
        self.assertEqual(len(plan), 20)

        stats = FileOrganizerEngine.execute_plan(
            plan=plan,
            target_dir=col_dst,
            mode="new_organization",
            action_type="move",
            max_workers=8,
        )
        self.assertEqual(stats.moved, 20)
        self.assertEqual(stats.errors, 0)

        dest_folder = os.path.join(col_dst, "2023", "05")
        arrived_files = os.listdir(dest_folder)
        self.assertEqual(len(arrived_files), 20)

        actual_contents = set()
        for fname in arrived_files:
            with open(os.path.join(dest_folder, fname), "rb") as f:
                actual_contents.add(f.read())
        self.assertEqual(actual_contents, expected_contents)

        with OrganizerDatabase(col_dst) as db:
            self.assertEqual(db.count_organized_files(), 20)

    def test_worker_reuses_existing_plan_without_rescanning(self):
        """OrganizerWorker reuses pre-built plan during organize operation without calling scan_and_plan again."""
        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy",
            max_workers=4,
        )
        worker = OrganizerWorker(
            source_dir=self.source_dir,
            target_dir=self.target_dir,
            mode="new_organization",
            action_type="copy",
            operation="organize",
            max_workers=4,
            existing_plan=plan,
        )
        with patch.object(FileOrganizerEngine, "scan_and_plan") as mock_scan:
            worker.run()
            mock_scan.assert_not_called()

        with OrganizerDatabase(self.target_dir) as db:
            self.assertEqual(db.count_organized_files(), 3)

    def test_single_pass_scan_skips_moviepy_on_dated_videos(self):
        """Real MP4 videos whose filename already contains a date bypass MoviePy completely."""
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        sample_mp4 = os.path.join(tests_dir, "data", "video", "test_2.mp4")
        vid_src = os.path.join(self.temp_root, "vid_src")
        vid_dst = os.path.join(self.temp_root, "vid_dst")
        os.makedirs(vid_src, exist_ok=True)
        shutil.copy2(sample_mp4, os.path.join(vid_src, "VID_20230514_120000.mp4"))

        with patch("src.family_album.utility_functions.video_utils.VideoFileClip") as mock_clip:
            plan = FileOrganizerEngine.scan_and_plan(
                source_dir=vid_src,
                target_dir=vid_dst,
                max_workers=4,
            )
            mock_clip.assert_not_called()

        self.assertEqual(len(plan), 1)
        self.assertTrue(plan[0].is_video)
        self.assertRegex(plan[0].resolution, r"^\d+x\d+$")
        self.assertEqual(plan[0].date_result.source, "filename")

    def test_scan_and_plan_bogus_exif_photo_and_video_use_last_modified(self):
        """
        End-to-end organizer test:
        - Generated JPEG with invalid 1970/1980 EXIF dates + valid Last Modified (2019-08-22) -> 2019/08 (filesystem)
        - Generated AVI video with no container date + valid Last Modified (2021-11-05) -> 2021/11 (filesystem)
        - File with invalid 1980 Last Modified -> No_Date (none)
        """
        mix_src = os.path.join(self.temp_root, "mix_src")
        mix_dst = os.path.join(self.temp_root, "mix_dst")
        os.makedirs(mix_src, exist_ok=True)

        # 1. Generated JPEG with bogus 1970/1980 EXIF + valid Last Modified
        jpg_path = os.path.join(mix_src, "google_animation_01.jpg")
        img = Image.new("RGB", (80, 60), color=(40, 120, 180))
        exif = img.getexif()
        exif[306] = "1980:01:01 00:00:00"
        exif[36867] = "1970:01:01 00:00:00"
        img.save(jpg_path, "JPEG", exif=exif)
        ts_jpg = datetime(2019, 8, 22, 14, 35, 0).timestamp()
        os.utime(jpg_path, (ts_jpg, ts_jpg))

        # 2. Generated small AVI video with no metadata date + valid Last Modified
        vid_path = os.path.join(mix_src, "home_clip.avi")
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(vid_path, fourcc, 10.0, (64, 64))
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        for _ in range(5):
            writer.write(frame)
        writer.release()
        ts_vid = datetime(2021, 11, 5, 8, 20, 0).timestamp()
        os.utime(vid_path, (ts_vid, ts_vid))

        # 3. File with bogus 1980 Last Modified -> No_Date
        nodate_path = os.path.join(mix_src, "undated_archive.png")
        with open(nodate_path, "wb") as f:
            f.write(b"raw_bytes")
        ts_bad = datetime(1980, 1, 1, 0, 0, 0).timestamp()
        os.utime(nodate_path, (ts_bad, ts_bad))

        plan = FileOrganizerEngine.scan_and_plan(
            source_dir=mix_src,
            target_dir=mix_dst,
            mode="new_organization",
            action_type="copy",
            max_workers=4,
        )
        by_name = {item.file_name: item for item in plan}

        jpg_item = by_name["google_animation_01.jpg"]
        self.assertTrue(jpg_item.is_image)
        self.assertEqual(jpg_item.resolution, "80x60")
        self.assertEqual(jpg_item.date_result.source, "filesystem")
        self.assertEqual(jpg_item.date_result.year_folder, "2019")
        self.assertEqual(jpg_item.date_result.month_folder, "08")

        vid_item = by_name["home_clip.avi"]
        self.assertTrue(vid_item.is_video)
        self.assertEqual(vid_item.resolution, "64x64")
        self.assertEqual(vid_item.date_result.source, "filesystem")
        self.assertEqual(vid_item.date_result.year_folder, "2021")
        self.assertEqual(vid_item.date_result.month_folder, "11")

        nodate_item = by_name["undated_archive.png"]
        self.assertEqual(nodate_item.date_result.source, "none")
        self.assertEqual(nodate_item.date_result.year_folder, "No_Date")


if __name__ == "__main__":
    unittest.main()
