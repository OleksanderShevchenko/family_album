import os
import shutil
import tempfile
import unittest
from datetime import datetime

from src.family_album_lib.organizer_db import OrganizerDatabase


class TestOrganizerDatabase(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_database_initialization(self):
        db = OrganizerDatabase(self.test_dir)
        db_path = OrganizerDatabase.get_db_path(self.test_dir)
        self.assertTrue(os.path.isfile(db_path))
        self.assertTrue(OrganizerDatabase.has_database(self.test_dir))
        self.assertTrue(OrganizerDatabase.is_valid_database(self.test_dir))
        db.close()

    def test_record_and_find_file(self):
        with OrganizerDatabase(self.test_dir) as db:
            db.record_organized_file(
                file_name="IMG_20230514_100000.jpg",
                original_path="C:/source/IMG_20230514_100000.jpg",
                organized_path="C:/target/2023/05/IMG_20230514_100000.jpg",
                file_size=1024,
                file_hash="hash123abc",
                date_taken=datetime(2023, 5, 14, 10, 0, 0),
                date_source="filename",
                is_video=False,
                resolution="1920x1080",
                maker="Canon"
            )

            # Find by hash
            found = db.find_by_hash("hash123abc")
            self.assertIsNotNone(found)
            self.assertEqual(found["file_name"], "IMG_20230514_100000.jpg")
            self.assertEqual(found["date_source"], "filename")
            self.assertEqual(found["file_size"], 1024)

            # Find by organized path
            found_path = db.find_by_organized_path("C:/target/2023/05/IMG_20230514_100000.jpg")
            self.assertIsNotNone(found_path)
            self.assertEqual(found_path["file_hash"], "hash123abc")

            # Nonexistent hash
            self.assertIsNone(db.find_by_hash("nonexistent"))

    def test_session_management(self):
        with OrganizerDatabase(self.test_dir) as db:
            session_id = db.start_session(
                source_dir=self.test_dir,
                target_dir=self.test_dir,
                mode="self_organization",
                action_type="move"
            )
            self.assertGreater(session_id, 0)

            db.log_action(session_id, "test_file.jpg", "moved", "Successfully moved to 2023/05")
            db.finish_session(session_id, total_processed=10, files_organized=9, files_skipped=1, files_errors=0)

            conn = db.get_connection()
            row = conn.execute("SELECT * FROM organizer_sessions WHERE session_id = ?", (session_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["mode"], "self_organization")
            self.assertEqual(row["files_organized"], 9)

    def test_catalog_actuality_verification(self):
        # Create a real file on disk
        target_file = os.path.join(self.test_dir, "test.jpg")
        with open(target_file, "wb") as f:
            f.write(b"content")

        missing_file = os.path.join(self.test_dir, "missing.jpg")

        with OrganizerDatabase(self.test_dir) as db:
            db.record_organized_file(
                file_name="test.jpg",
                original_path="orig/test.jpg",
                organized_path=target_file,
                file_size=len(b"content"),
                file_hash="hash_real",
                date_taken=datetime(2023, 1, 1),
                date_source="filename",
                is_video=False
            )
            db.record_organized_file(
                file_name="missing.jpg",
                original_path="orig/missing.jpg",
                organized_path=missing_file,
                file_size=100,
                file_hash="hash_missing",
                date_taken=datetime(2023, 1, 1),
                date_source="filename",
                is_video=False
            )

            stats = db.verify_catalog_actuality()
            self.assertEqual(stats["total_records"], 2)
            self.assertEqual(stats["valid_count"], 1)
            self.assertEqual(stats["missing_count"], 1)
            self.assertIn(missing_file, stats["missing_files"])


if __name__ == "__main__":
    unittest.main()
