import os
import shutil
import tempfile
import unittest
from src.family_album_lib.duplication_memento import (
    DuplicationSaveManager,
    DuplicationCheckMemento,
    DuplicationCheckStatus
)


class TestDuplicationMemento(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.saves_temp_dir = tempfile.mkdtemp()
        self.save_manager = DuplicationSaveManager(self.saves_temp_dir)

        # Create dummy test files in temp_dir
        self.file1 = os.path.join(self.temp_dir, "file1.txt")
        self.file2 = os.path.join(self.temp_dir, "file2.txt")
        with open(self.file1, "w") as f:
            f.write("content 1")
        with open(self.file2, "w") as f:
            f.write("content 2")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.saves_temp_dir, ignore_errors=True)

    def test_status_enum(self):
        self.assertEqual(DuplicationCheckStatus.IDLE.value, "Idle")
        self.assertEqual(DuplicationCheckStatus.RUNNING.value, "Running")
        self.assertEqual(DuplicationCheckStatus.PAUSED.value, "Paused")
        self.assertEqual(DuplicationCheckStatus.COMPLETED.value, "Completed")

    def test_memento_serialization(self):
        processed = {self.file1: "hash1"}
        hashes = {"hash1": [self.file1]}
        memento = DuplicationCheckMemento(
            directory=self.temp_dir,
            files_count=2,
            subdirectories_count=0,
            processed_files=processed,
            files_hashes=hashes
        )

        data = memento.to_dict()
        restored = DuplicationCheckMemento.from_dict(data)

        self.assertEqual(restored.directory, os.path.abspath(self.temp_dir))
        self.assertEqual(restored.files_count, 2)
        self.assertEqual(restored.subdirectories_count, 0)
        self.assertEqual(restored.processed_files, processed)
        self.assertEqual(restored.files_hashes, hashes)

    def test_save_manager_save_and_load(self):
        memento = DuplicationCheckMemento(
            directory=self.temp_dir,
            files_count=2,
            subdirectories_count=0,
            processed_files={self.file1: "hash1"},
            files_hashes={"hash1": [self.file1]}
        )

        self.assertFalse(self.save_manager.has_save(self.temp_dir))
        save_path = self.save_manager.save_memento(memento)
        self.assertTrue(os.path.isfile(save_path))
        self.assertTrue(self.save_manager.has_save(self.temp_dir))

        loaded = self.save_manager.load_memento(self.temp_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.files_count, 2)

        self.save_manager.delete_save(self.temp_dir)
        self.assertFalse(self.save_manager.has_save(self.temp_dir))

    def test_location_verification(self):
        memento = DuplicationCheckMemento(
            directory=self.temp_dir,
            files_count=2,
            subdirectories_count=0,
            processed_files={self.file1: "hash1"},
            files_hashes={"hash1": [self.file1]}
        )

        is_valid, msg = self.save_manager.verify_location(memento)
        self.assertTrue(is_valid, msg)

        # Add a new file to break file count verification
        file3 = os.path.join(self.temp_dir, "file3.txt")
        with open(file3, "w") as f:
            f.write("content 3")

        is_valid, msg = self.save_manager.verify_location(memento)
        self.assertFalse(is_valid)
        self.assertIn("File count mismatch", msg)


if __name__ == '__main__':
    unittest.main()
