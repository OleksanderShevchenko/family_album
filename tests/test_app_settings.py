"""
Unit tests for AppSettings (.settings/settings.json), SettingsDialog, and
thread count propagation to DuplicationChecker and FileOrganizer.
"""

import json
import os
import shutil
import tempfile
import unittest

from PyQt6.QtWidgets import QApplication

from src.family_album.gui.dialogs.settings_dialog import SettingsDialog
from src.family_album.gui.widgets.duplication_checker import DuplicationChecker
from src.family_album.gui.widgets.file_organizer import FileOrganizer
from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.file_organizer_engine import OrganizerWorker
from src.family_album_lib.resumable_duplicate_analyser import ResumableDuplicateAnalyser


class TestAppSettings(unittest.TestCase):
    """Test suite verifying AppSettings persistence, defaults, dialog, and tool integration."""

    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_app_settings_")

    def tearDown(self):
        # Reset singleton to avoid leaking temp_dir across tests
        AppSettings._instance = None
        if os.path.isdir(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_first_launch_creates_settings_file_with_recommended_threads(self):
        """On first launch, .settings/settings.json is created with cpu_cores * 2 threads."""
        settings = AppSettings(app_dir=self.temp_dir)
        expected_path = os.path.join(self.temp_dir, ".settings", "settings.json")

        self.assertTrue(os.path.isfile(expected_path))
        expected_threads = max(1, min(256, (os.cpu_count() or 4) * 2))
        self.assertEqual(settings.worker_threads, expected_threads)
        self.assertEqual(settings.last_selected_directory, "")

        with open(expected_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        self.assertEqual(saved_data["worker_threads"], expected_threads)

    def test_save_and_reload_settings(self):
        """Modified worker_threads and last_selected_directory persist across reloads."""
        settings1 = AppSettings(app_dir=self.temp_dir)
        sample_dir = os.path.join(self.temp_dir, "my_photos")
        os.makedirs(sample_dir, exist_ok=True)

        settings1.worker_threads = 12
        settings1.last_selected_directory = sample_dir
        settings1.save()

        settings2 = AppSettings(app_dir=self.temp_dir)
        self.assertEqual(settings2.worker_threads, 12)
        self.assertEqual(settings2.last_selected_directory, os.path.normpath(sample_dir))

    def test_worker_threads_clamping(self):
        """worker_threads is clamped between MIN_THREADS (1) and MAX_THREADS (256)."""
        settings = AppSettings(app_dir=self.temp_dir)
        settings.worker_threads = 0
        self.assertEqual(settings.worker_threads, AppSettings.MIN_THREADS)

        settings.worker_threads = 9999
        self.assertEqual(settings.worker_threads, AppSettings.MAX_THREADS)

    def test_settings_dialog_synchronization_and_save(self):
        """SettingsDialog syncs SpinBox and Slider and saves updated values to AppSettings."""
        settings = AppSettings(app_dir=self.temp_dir)
        dialog = SettingsDialog(settings=settings)

        # Changing SpinBox updates Slider
        dialog.sb_worker_threads.setValue(24)
        self.assertEqual(dialog.sl_worker_threads.value(), 24)

        # Changing Slider updates SpinBox
        dialog.sl_worker_threads.setValue(8)
        self.assertEqual(dialog.sb_worker_threads.value(), 8)

        # Saving applies changes to settings and writes to disk
        dialog.le_last_directory.setText(self.temp_dir)
        dialog._evt_save()

        reloaded = AppSettings(app_dir=self.temp_dir)
        self.assertEqual(reloaded.worker_threads, 8)
        self.assertEqual(reloaded.last_selected_directory, os.path.normpath(self.temp_dir))

    def test_both_tools_respect_configured_worker_threads(self):
        """Both DuplicationChecker/ResumableDuplicateAnalyser and FileOrganizer/OrganizerWorker use worker_threads."""
        settings = AppSettings.instance(app_dir=self.temp_dir)
        settings.worker_threads = 14
        settings.save()

        # 1. ResumableDuplicateAnalyser & DuplicationChecker
        analyser = ResumableDuplicateAnalyser(self.temp_dir)
        self.assertEqual(analyser.num_of_threads, 14)

        dup_widget = DuplicationChecker()
        dup_widget.selected_path = self.temp_dir
        self.assertEqual(dup_widget.max_workers, 14)
        self.assertEqual(dup_widget._duplication_checker.num_of_threads, 14)

        # Dynamically updating max_workers updates underlying analyser
        dup_widget.max_workers = 6
        self.assertEqual(dup_widget._duplication_checker.num_of_threads, 6)

        # 2. FileOrganizer & OrganizerWorker
        org_widget = FileOrganizer()
        self.assertEqual(org_widget.max_workers, 14)

        worker = OrganizerWorker(
            source_dir=self.temp_dir,
            target_dir=self.temp_dir,
            operation="analyze",
        )
        self.assertEqual(worker.max_workers, 14)


if __name__ == "__main__":
    unittest.main()
