import os
import shutil
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

from src.family_album_lib.file_organizer_engine import (
    FileOrganizerEngine,
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


if __name__ == "__main__":
    unittest.main()
