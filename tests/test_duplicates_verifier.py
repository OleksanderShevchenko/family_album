"""
Unit and integration tests for Stage 2 Duplicate Verification (`ResumableDuplicatesVerifier`),
two-stage `DuplicationCheckMemento` serialization, and `DuplicationChecker` widget integration.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest

from PyQt6.QtWidgets import QApplication, QMainWindow, QProgressBar

# Ensure QApplication instance exists for PyQt6 widget tests
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from src.family_album.gui.widgets.duplication_checker import DuplicationChecker
from src.family_album_lib.duplication_memento import (
    DuplicationCheckMemento,
    DuplicationCheckStatus,
    DuplicationSaveManager,
    DuplicationStage,
)
from src.family_album_lib.resumable_duplicate_analyser import ResumableDuplicateAnalyser
from src.family_album_lib.resumable_duplicates_verifier import ResumableDuplicatesVerifier


class _MockMainWindow(QMainWindow):
    """Minimal MainWindow mock exposing progressBar and lifecycle callbacks for widget tests."""

    def __init__(self) -> None:
        super().__init__()
        self.progressBar = QProgressBar(self)
        self.progressBar.setRange(0, 100)
        self._interval = 1000
        self.log_messages = []
        self.analysis_finished_calls = 0

    def evt_start_analysis(self, msg: str) -> None:
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

    def evt_update_progress(self, finished: int, total: int) -> None:
        if total > 0:
            self.progressBar.setValue(int(finished / total * 100))

    def evt_finish_analysis(self, msg: str) -> None:
        self.analysis_finished_calls += 1

    def log_event(self, msg: str) -> None:
        self.log_messages.append(msg)


class TestResumableDuplicatesVerifier(unittest.TestCase):
    """Tests for Stage 2 multithreaded byte-size verification and pause/save/resume."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.saves_dir = tempfile.mkdtemp()
        self.save_manager = DuplicationSaveManager(self.saves_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.saves_dir, ignore_errors=True)

    def _write_file(self, rel_path: str, content: bytes) -> str:
        full_path = os.path.normpath(os.path.join(self.temp_dir, rel_path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(content)
        return full_path

    def test_verify_genuine_duplicates_multithreaded(self) -> None:
        """All true duplicates with matching byte sizes are confirmed; unique files are skipped."""
        self._write_file("group1_orig.jpg", b"A" * 512)
        self._write_file("sub/group1_dup1.jpg", b"A" * 512)
        self._write_file("sub/group1_dup2.jpg", b"A" * 512)
        self._write_file("group2_orig.jpg", b"B" * 1024)
        self._write_file("group2_dup.jpg", b"B" * 1024)
        self._write_file("unique_1.jpg", b"UNIQUE_1")
        self._write_file("unique_2.jpg", b"UNIQUE_2_LONGER")

        # Run Stage 1 hashing synchronously
        analyser = ResumableDuplicateAnalyser(self.temp_dir, instantly_opened_files=2)
        analyser.start_analysis_thread(run_in_background=False)
        self.assertEqual(analyser.status, DuplicationCheckStatus.COMPLETED)
        self.assertEqual(len(analyser.duplicate_files), 2)

        progress_updates = []
        finish_messages = []

        verifier = ResumableDuplicatesVerifier(
            directory=self.temp_dir,
            duplicate_files=analyser.duplicate_files,
            files_hashes=analyser.files_hashes,
            processed_files=analyser.processed_files,
            files_count=analyser.files_count_in_directory,
            subdirectories_count=analyser.subdirectories_count_in_directory,
            update_progress=lambda done, total: progress_updates.append((done, total)),
            finish_verification=lambda msg: finish_messages.append(msg),
            max_workers=4,
        )
        verifier.start_verification_thread(run_in_background=False)

        self.assertEqual(verifier.status, DuplicationCheckStatus.COMPLETED)
        self.assertEqual(verifier.total_groups_count, 2)
        self.assertEqual(verifier.verified_groups_count, 2)
        self.assertEqual(verifier.mismatched_files, [])
        self.assertEqual(verifier.failed_files, [])
        self.assertEqual(len(finish_messages), 1)
        self.assertEqual(progress_updates[-1], (2, 2))

        # Every Stage 1 duplicate group is confirmed identically
        self.assertEqual(set(verifier.verified_duplicates.keys()), set(analyser.duplicate_files.keys()))
        for orig, dups in analyser.duplicate_files.items():
            self.assertEqual(sorted(verifier.verified_duplicates[orig]), sorted(dups))

    def test_detects_simulated_hash_collision_by_size_mismatch(self) -> None:
        """
        Simulated hash collision where two files share a hash bucket but differ in size
        must be caught, logged as a warning, and excluded from verified_duplicates.
        """
        orig_1 = self._write_file("orig_1.bin", b"X" * 100)
        real_dup_1 = self._write_file("real_dup_1.bin", b"X" * 100)
        collision_1 = self._write_file("collision_1.bin", b"Y" * 250)

        orig_2 = self._write_file("orig_2.bin", b"Z" * 50)
        collision_2 = self._write_file("collision_2.bin", b"W" * 99)

        # Simulate Stage 1 hash buckets containing artificial collisions
        simulated_hashes = {
            "hash_group_1": [orig_1, real_dup_1, collision_1],
            "hash_group_2": [orig_2, collision_2],
        }
        simulated_dups = {
            orig_1: [real_dup_1, collision_1],
            orig_2: [collision_2],
        }
        logs = []

        verifier = ResumableDuplicatesVerifier(
            directory=self.temp_dir,
            duplicate_files=simulated_dups,
            files_hashes=simulated_hashes,
            files_count=5,
            subdirectories_count=0,
            log_event=logs.append,
            max_workers=2,
        )
        verifier.start_verification_thread(run_in_background=False)

        self.assertEqual(verifier.status, DuplicationCheckStatus.COMPLETED)
        # Group 1 keeps real_dup_1 and excludes collision_1
        self.assertIn(orig_1, verifier.verified_duplicates)
        self.assertEqual(verifier.verified_duplicates[orig_1], [real_dup_1])
        # Group 2 had only a collision, so it is completely removed from verified_duplicates
        self.assertNotIn(orig_2, verifier.verified_duplicates)

        # Both mismatches recorded with accurate sizes
        self.assertEqual(len(verifier.mismatched_files), 2)
        by_candidate = {m["candidate"]: m for m in verifier.mismatched_files}
        self.assertEqual(by_candidate[collision_1]["original_size"], 100)
        self.assertEqual(by_candidate[collision_1]["candidate_size"], 250)
        self.assertEqual(by_candidate[collision_1]["reason"], "size_mismatch")
        self.assertEqual(by_candidate[collision_2]["original_size"], 50)
        self.assertEqual(by_candidate[collision_2]["candidate_size"], 99)

        # Warnings were logged
        warning_logs = [m for m in logs if "WARNING" in m and "mismatch" in m.lower()]
        self.assertEqual(len(warning_logs), 2)

    def test_stage2_memento_preserves_stage1_and_resumes_across_sessions(self) -> None:
        """
        Pausing Stage 2 mid-way, saving a `stage='verifying'` memento, and resuming on a
        brand-new verifier instance preserves full Stage 1 hash data and completes remaining groups.
        """
        # Create 4 duplicate groups + 2 unique files = 10 files total
        for idx in range(1, 5):
            payload = f"GROUP_{idx}_".encode("utf-8") * (20 * idx)
            self._write_file(f"g{idx}_orig.dat", payload)
            self._write_file(f"g{idx}_dup.dat", payload)
        self._write_file("unique_a.dat", b"UNIQUE_A_CONTENT")
        self._write_file("unique_b.dat", b"UNIQUE_B_CONTENT")

        # Complete Stage 1
        analyser = ResumableDuplicateAnalyser(self.temp_dir, instantly_opened_files=2)
        analyser.start_analysis_thread(run_in_background=False)
        self.assertEqual(len(analyser.duplicate_files), 4)
        self.assertEqual(len(analyser.processed_files), 10)

        # Session 1: verify 2 of 4 groups with single worker, then pause cooperatively
        verifier_s1: ResumableDuplicatesVerifier

        def _pause_after_two(verified_count: int, total: int) -> None:
            if verified_count >= 2:
                verifier_s1._stop_event.set()

        verifier_s1 = ResumableDuplicatesVerifier(
            directory=self.temp_dir,
            duplicate_files=analyser.duplicate_files,
            files_hashes=analyser.files_hashes,
            processed_files=analyser.processed_files,
            files_count=analyser.files_count_in_directory,
            subdirectories_count=analyser.subdirectories_count_in_directory,
            update_progress=_pause_after_two,
            max_workers=1,
        )
        verifier_s1.start_verification_thread(run_in_background=False)

        self.assertEqual(verifier_s1.status, DuplicationCheckStatus.PAUSED)
        self.assertEqual(verifier_s1.verified_groups_count, 2)

        # Save Stage 2 memento to disk
        memento = verifier_s1.create_memento()
        self.assertEqual(memento.stage, DuplicationStage.VERIFYING.value)
        self.assertEqual(len(memento.verified_originals), 2)
        self.assertEqual(memento.candidate_duplicate_groups_count, 4)
        # Full Stage 1 results MUST be preserved
        self.assertEqual(len(memento.processed_files), 10)
        self.assertEqual(memento.files_count, 10)
        self.assertEqual(len(memento.files_hashes), 6)  # 4 duplicate hashes + 2 unique hashes

        self.save_manager.save_memento(memento)

        # Simulate closing and restarting the application on another day
        reloaded = self.save_manager.load_memento(self.temp_dir)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.stage, DuplicationStage.VERIFYING.value)
        is_valid, reason = self.save_manager.verify_location(reloaded)
        self.assertTrue(is_valid, reason)

        verifier_s2 = ResumableDuplicatesVerifier(directory=self.temp_dir, max_workers=2)
        verifier_s2.restore_memento(reloaded)
        self.assertEqual(verifier_s2.status, DuplicationCheckStatus.PAUSED)
        self.assertEqual(verifier_s2.verified_groups_count, 2)
        self.assertEqual(verifier_s2.total_groups_count, 4)

        # Resume and finish remaining 2 groups
        resumed_progress = []
        verifier_s2._update_progress = lambda done, total: resumed_progress.append((done, total))
        verifier_s2.start_verification_thread(run_in_background=False)

        self.assertEqual(verifier_s2.status, DuplicationCheckStatus.COMPLETED)
        self.assertEqual(verifier_s2.verified_groups_count, 4)
        # Only the remaining 2 groups should have triggered progress updates (3/4 and 4/4)
        self.assertEqual(resumed_progress, [(3, 4), (4, 4)])
        self.assertEqual(set(verifier_s2.verified_duplicates.keys()), set(analyser.duplicate_files.keys()))
        # Preserved Stage 1 hashes remain completely intact after completion
        self.assertEqual(len(verifier_s2.files_hashes), 6)
        self.assertEqual(len(verifier_s2.processed_files), 10)

    def test_memento_backwards_compatibility_defaults_to_hashing_stage(self) -> None:
        """Legacy memento JSON dicts without Stage 2 keys load cleanly as `stage='hashing'`."""
        f1 = self._write_file("legacy.txt", b"hello")
        legacy_dict = {
            "directory": self.temp_dir,
            "files_count": 1,
            "subdirectories_count": 0,
            "processed_files": {f1: "abc"},
            "files_hashes": {"abc": [f1]},
            "timestamp": 123456.0,
        }
        memento = DuplicationCheckMemento.from_dict(legacy_dict)
        self.assertEqual(memento.stage, DuplicationStage.HASHING.value)
        self.assertEqual(memento.verified_originals, [])
        self.assertEqual(memento.verified_duplicates, {})
        self.assertEqual(memento.mismatched_files, [])


class TestDuplicationCheckerVerificationWidget(unittest.TestCase):
    """GUI integration tests for Stage 2 Verify Duplicates button, save, and resume."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.saves_dir = tempfile.mkdtemp()
        self.mock_parent = _MockMainWindow()
        self.widget = DuplicationChecker(self.mock_parent)
        # Isolate saves to temporary directory
        self.widget._save_manager = DuplicationSaveManager(self.saves_dir)

        # Create 2 duplicate groups + 1 unique file
        self.g1_a = os.path.normpath(os.path.join(self.temp_dir, "photo1.jpg"))
        self.g1_b = os.path.normpath(os.path.join(self.temp_dir, "photo1_copy.jpg"))
        self.g2_a = os.path.normpath(os.path.join(self.temp_dir, "photo2.jpg"))
        self.g2_b = os.path.normpath(os.path.join(self.temp_dir, "photo2_copy.jpg"))
        self.uniq = os.path.normpath(os.path.join(self.temp_dir, "unique.jpg"))

        for p, data in [
            (self.g1_a, b"IMG1" * 100),
            (self.g1_b, b"IMG1" * 100),
            (self.g2_a, b"IMG2" * 150),
            (self.g2_b, b"IMG2" * 150),
            (self.uniq, b"UNIQ" * 50),
        ]:
            with open(p, "wb") as f:
                f.write(data)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        shutil.rmtree(self.saves_dir, ignore_errors=True)

    def _wait_for_verifier(self, widget: DuplicationChecker, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            QApplication.processEvents()
            if (
                widget._verifier is not None
                and widget._verifier.status == DuplicationCheckStatus.COMPLETED
                and widget._verification_completed
            ):
                return
            time.sleep(0.02)

    def test_verify_button_states_and_stage2_save_resume_flow(self) -> None:
        """
        End-to-end GUI flow:
        1. `pbVerifyDuplicates` is disabled before Stage 1 completes.
        2. After Stage 1 finds duplicates, `pbVerifyDuplicates` becomes enabled.
        3. Saving a paused Stage 2 state persists `stage='verifying'` with Stage 1 hashes.
        4. A fresh `DuplicationChecker` detects the verification save and resumes Stage 2,
           completing cleanly without triggering Stage 1's `evt_finish_analysis`.
        """
        self.assertFalse(self.widget.pbVerifyDuplicates.isEnabled())

        self.widget.selected_path = self.temp_dir
        self.assertFalse(self.widget.pbVerifyDuplicates.isEnabled())

        # Complete Stage 1 synchronously and populate results
        self.widget._duplication_checker.start_analysis_thread(run_in_background=False)
        self.widget.populate_duplications()

        self.assertEqual(len(self.widget.duplications), 2)
        self.assertEqual(len(self.widget.files_hash), 3)
        self.assertTrue(self.widget.pbVerifyDuplicates.isEnabled())

        # Prepare a paused Stage 2 verifier with 1 of 2 groups verified and save via widget
        orig_keys = list(self.widget.duplications.keys())
        first_orig = orig_keys[0]
        self.widget._active_stage = DuplicationStage.VERIFYING.value
        self.widget._verifier = ResumableDuplicatesVerifier(
            directory=self.temp_dir,
            duplicate_files=self.widget.duplications,
            files_hashes=self.widget.files_hash,
            processed_files=self.widget._duplication_checker.processed_files,
            files_count=self.widget._duplication_checker.files_count_in_directory,
            subdirectories_count=self.widget._duplication_checker.subdirectories_count_in_directory,
            max_workers=2,
        )
        # Verify thread propagation via max_workers property
        self.widget.max_workers = 3
        self.assertEqual(self.widget._duplication_checker.num_of_threads, 3)
        self.assertEqual(self.widget._verifier.num_of_threads, 3)

        # Mark first group as verified and put verifier into PAUSED state
        self.widget._verifier._verified_originals = [first_orig]
        self.widget._verifier._verified_originals_set = {first_orig}
        self.widget._verifier._verified_duplicates = {
            first_orig: list(self.widget.duplications[first_orig])
        }
        self.widget._verifier._status = DuplicationCheckStatus.PAUSED
        self.widget._update_button_states()

        self.assertTrue(self.widget.pbSaveState.isEnabled())
        self.assertFalse(self.widget.pbVerifyDuplicates.isEnabled())

        # Save Stage 2 state using existing Save State button handler
        self.widget.evt_save_state()
        self.assertTrue(self.widget._save_manager.has_save(self.temp_dir))
        saved_memento = self.widget._save_manager.load_memento(self.temp_dir)
        self.assertEqual(saved_memento.stage, DuplicationStage.VERIFYING.value)
        self.assertEqual(len(saved_memento.files_hashes), 3)

        # Simulate application restart with a fresh DuplicationChecker
        fresh_parent = _MockMainWindow()
        fresh_widget = DuplicationChecker(fresh_parent)
        fresh_widget._save_manager = DuplicationSaveManager(self.saves_dir)
        fresh_widget.selected_path = self.temp_dir

        self.assertTrue(fresh_widget.pbResume.isEnabled())
        self.assertIn("Saved verification state found", fresh_widget.lblInfo.text())

        # Resume Stage 2 verification via existing Resume Check button handler
        fresh_widget.evt_resume_duplication()
        self._wait_for_verifier(fresh_widget)

        self.assertTrue(fresh_widget._verification_completed)
        self.assertEqual(fresh_widget._verifier.status, DuplicationCheckStatus.COMPLETED)
        self.assertEqual(len(fresh_widget.duplications), 2)
        # Stage 1 hashes remain preserved after Stage 2 resume!
        self.assertEqual(len(fresh_widget.files_hash), 3)
        # Save file cleaned up after verification completes
        self.assertFalse(fresh_widget._save_manager.has_save(self.temp_dir))
        # MainWindow.evt_finish_analysis was NOT called during Stage 2
        self.assertEqual(fresh_parent.analysis_finished_calls, 0)
        # Action buttons re-enabled
        self.assertTrue(fresh_widget.pbVerifyDuplicates.isEnabled())
        self.assertTrue(fresh_widget.pbDumpDuplications.isEnabled())
        self.assertTrue(fresh_widget.pbMove.isEnabled())
        self.assertIn("Verification complete", fresh_widget.lblInfo.text())

    def test_evt_verify_duplicates_directly_excludes_collision(self) -> None:
        """Clicking Verify Duplicates runs Stage 2 directly and removes size-mismatched candidates."""
        collision_file = os.path.normpath(os.path.join(self.temp_dir, "collision_diff_size.jpg"))
        with open(collision_file, "wb") as f:
            f.write(b"DIFFERENT_SIZE_PAYLOAD" * 50)

        self.widget.selected_path = self.temp_dir
        self.widget._duplication_checker.start_analysis_thread(run_in_background=False)
        self.widget.populate_duplications()

        # Inject a simulated hash collision into group 1
        target_orig = self.g1_a if self.g1_a in self.widget.duplications else self.g1_b
        self.widget.duplications[target_orig].append(collision_file)

        self.widget.evt_verify_duplicates()
        self._wait_for_verifier(self.widget)

        self.assertTrue(self.widget._verification_completed)
        self.assertNotIn(collision_file, self.widget.duplications.get(target_orig, []))
        self.assertEqual(len(self.widget._last_mismatched_files), 1)
        self.assertEqual(self.widget._last_mismatched_files[0]["candidate"], collision_file)
        self.assertIn("1 size mismatch(es) excluded", self.widget.lblInfo.text())
        self.assertTrue(
            any("DUPLICATE VERIFICATION SUMMARY REPORT" in m for m in self.mock_parent.log_messages)
        )


if __name__ == "__main__":
    unittest.main()
