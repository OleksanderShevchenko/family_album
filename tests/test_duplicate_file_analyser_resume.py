import os
import hashlib
import shutil
import tempfile
import unittest
from src.family_album_lib.resumable_duplicate_analyser import ResumableDuplicateAnalyser
from src.family_album_lib.duplication_memento import DuplicationSaveManager, DuplicationCheckStatus


class TestDuplicateFileAnalyserResume(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.saves_temp_dir = tempfile.mkdtemp()
        self.save_manager = DuplicationSaveManager(self.saves_temp_dir)

        # Create subfolder and test files with duplicate content
        self.sub_dir = os.path.join(self.temp_dir, "photos")
        os.makedirs(self.sub_dir, exist_ok=True)

        self.f1 = os.path.join(self.temp_dir, "img1.jpg")
        self.f2 = os.path.join(self.temp_dir, "img2.jpg")
        self.f3 = os.path.join(self.sub_dir, "img1_dup.jpg")
        self.f4 = os.path.join(self.sub_dir, "img3.jpg")

        with open(self.f1, "wb") as f:
            f.write(b"PHOTO_DATA_A_12345")
        with open(self.f2, "wb") as f:
            f.write(b"PHOTO_DATA_B_67890")
        with open(self.f3, "wb") as f:
            f.write(b"PHOTO_DATA_A_12345")  # Duplicate of f1
        with open(self.f4, "wb") as f:
            f.write(b"PHOTO_DATA_C_11223")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.saves_temp_dir, ignore_errors=True)

    def test_single_session_vs_multi_session_equivalence(self):
        # 1. Single session check
        analyser_single = ResumableDuplicateAnalyser(self.temp_dir)
        analyser_single.start_analysis_thread(run_in_background=False)

        single_hashes = analyser_single.files_hashes
        single_duplicates = analyser_single.duplicate_files

        self.assertEqual(analyser_single.status, DuplicationCheckStatus.COMPLETED)

        # 2. Multi-session (Pause + Save Memento + Resume)
        analyser_session1 = ResumableDuplicateAnalyser(self.temp_dir)

        # Pre-populate f1 into memento as if paused after 1 file
        memento1 = analyser_session1.create_memento()
        with open(self.f1, "rb") as f:
            h1 = hashlib.blake2b(f.read()).hexdigest()
        memento1.processed_files[self.f1] = h1
        memento1.files_hashes[h1] = [self.f1]

        # Save memento to saves directory
        self.save_manager.save_memento(memento1)

        # Session 2: Resume from memento
        analyser_session2 = ResumableDuplicateAnalyser(self.temp_dir)
        loaded_memento = self.save_manager.load_memento(self.temp_dir)
        self.assertIsNotNone(loaded_memento)

        analyser_session2.restore_memento(loaded_memento)
        self.assertEqual(analyser_session2.status, DuplicationCheckStatus.PAUSED)
        self.assertEqual(len(analyser_session2.processed_files), 1)

        # Resume analysis
        analyser_session2.start_analysis_thread(run_in_background=False)
        self.assertEqual(analyser_session2.status, DuplicationCheckStatus.COMPLETED)

        resumed_hashes = analyser_session2.files_hashes
        resumed_duplicates = analyser_session2.duplicate_files

        # 3. Assert single session and multi-session produce IDENTICAL results
        self.assertEqual(len(single_hashes), len(resumed_hashes))
        self.assertEqual(single_duplicates, resumed_duplicates)


if __name__ == '__main__':
    unittest.main()
