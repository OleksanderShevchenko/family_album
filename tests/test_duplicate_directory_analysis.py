import os
import shutil
import tempfile
import unittest

from src.family_album_lib.resumable_duplicate_analyser import ResumableDuplicateAnalyser
from src.family_album_lib.duplicate_file_analyser import DuplicateFileAnalyser


class TestDuplicateDirectoryAnalysis(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

        # Create Folder A with files
        self.dir_a = os.path.join(self.temp_dir, "FolderA")
        os.makedirs(self.dir_a, exist_ok=True)
        with open(os.path.join(self.dir_a, "file1.txt"), "w") as f:
            f.write("content 1")
        with open(os.path.join(self.dir_a, "file2.txt"), "w") as f:
            f.write("content 2")

        # Create Folder B with exact same files (Duplicate folder)
        self.dir_b = os.path.join(self.temp_dir, "FolderB")
        os.makedirs(self.dir_b, exist_ok=True)
        with open(os.path.join(self.dir_b, "file1.txt"), "w") as f:
            f.write("content 1")
        with open(os.path.join(self.dir_b, "file2.txt"), "w") as f:
            f.write("content 2")

        # Create Folder C with different content
        self.dir_c = os.path.join(self.temp_dir, "FolderC")
        os.makedirs(self.dir_c, exist_ok=True)
        with open(os.path.join(self.dir_c, "file3.txt"), "w") as f:
            f.write("different content")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_duplicate_directory_detection(self):
        analyser = ResumableDuplicateAnalyser(self.temp_dir)
        analyser.start_analysis_thread(run_in_background=False)

        dup_dirs = analyser.duplicate_directories
        self.assertTrue(len(dup_dirs) > 0)

        # One directory should be original, the other should be in duplicates list
        orig_keys = [os.path.normpath(k) for k in dup_dirs.keys()]
        self.assertTrue(os.path.normpath(self.dir_a) in orig_keys or os.path.normpath(self.dir_b) in orig_keys)

        key = orig_keys[0]
        duplicates_list = [os.path.normpath(d) for d in dup_dirs[key]["duplicates"]]
        self.assertEqual(dup_dirs[key]["file_count"], 2)
        self.assertTrue(len(duplicates_list) == 1)

    def test_duplicate_directory_renamed_files(self):
        """Verify that duplicate directories are detected even if filenames are different."""
        dir_renamed = os.path.join(self.temp_dir, "FolderRenamed")
        os.makedirs(dir_renamed, exist_ok=True)
        with open(os.path.join(dir_renamed, "different_name_1.txt"), "w") as f:
            f.write("content 1")
        with open(os.path.join(dir_renamed, "different_name_2.txt"), "w") as f:
            f.write("content 2")

        analyser = ResumableDuplicateAnalyser(self.temp_dir)
        analyser.start_analysis_thread(run_in_background=False)

        dup_dirs = analyser.duplicate_directories
        norm_renamed = os.path.normpath(dir_renamed)

        found_renamed = False
        for orig, data in dup_dirs.items():
            norm_orig = os.path.normpath(orig)
            norm_dups = [os.path.normpath(d) for d in data["duplicates"]]
            if norm_renamed == norm_orig or norm_renamed in norm_dups:
                found_renamed = True
                self.assertEqual(data["file_count"], 2)

        self.assertTrue(found_renamed, "Renamed folder should be identified as a duplicate directory!")

    def test_duplicate_file_analyser_directory_detection(self):
        analyser = DuplicateFileAnalyser(self.temp_dir, None, None, None, 200)
        analyser.start_analysis_thread()

        dup_dirs = analyser.duplicate_directories
        self.assertTrue(len(dup_dirs) > 0)


if __name__ == '__main__':
    unittest.main()
