import os
import shutil
import tempfile
import sys
import unittest
from PyQt6.QtWidgets import QApplication, QMainWindow

# Ensure QApplication instance exists for GUI tests
app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)

from src.family_album.gui.widgets.duplication_checker import DuplicationChecker
from src.family_album_lib.duplication_memento import DuplicationCheckMemento


class MockMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.log_messages = []

    def evt_start_analysis(self, msg: str):
        pass

    def evt_update_progress(self, finished: int, total: int):
        pass

    def evt_finish_analysis(self, msg: str):
        pass

    def log_event(self, msg: str):
        self.log_messages.append(msg)


class TestDuplicationCheckerWidget(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.mock_parent = MockMainWindow()
        self.widget = DuplicationChecker(self.mock_parent)

        # Set up dummy folder & files
        self.f1 = os.path.join(self.temp_dir, "test1.jpg")
        with open(self.f1, "w") as f:
            f.write("test content")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_widget_initial_button_states(self):
        self.assertFalse(self.widget.pbAnalyze.isEnabled())
        self.assertFalse(self.widget.pbCheckDuplications.isEnabled())
        self.assertFalse(self.widget.pbStop.isEnabled())
        self.assertFalse(self.widget.pbSaveState.isEnabled())
        self.assertFalse(self.widget.pbResume.isEnabled())

    def test_widget_path_selected_and_save_detection(self):
        self.widget.selected_path = self.temp_dir

        self.assertTrue(self.widget.pbAnalyze.isEnabled())
        self.assertTrue(self.widget.pbCheckDuplications.isEnabled())
        self.assertFalse(self.widget.pbStop.isEnabled())
        self.assertFalse(self.widget.pbSaveState.isEnabled())
        self.assertFalse(self.widget.pbResume.isEnabled())

        # Create a memento save manually for this directory
        memento = DuplicationCheckMemento(
            directory=self.temp_dir,
            files_count=1,
            subdirectories_count=0,
            processed_files={self.f1: "hash123"},
            files_hashes={"hash123": [self.f1]}
        )
        self.widget._save_manager.save_memento(memento)

        # Re-set selected path to trigger save detection
        self.widget.selected_path = self.temp_dir
        self.assertTrue(self.widget.pbResume.isEnabled())
        self.assertIn("Saved state found", self.widget.lblInfo.text())

    def test_widget_save_state_and_resume_events(self):
        self.widget.selected_path = self.temp_dir
        self.widget._duplication_checker._find_duplicate_files_multithreaded()

        # Trigger save state
        self.widget.evt_save_state()
        self.assertTrue(self.widget._save_manager.has_save(self.temp_dir))

        # Reset checker and test resume
        self.widget.selected_path = self.temp_dir
        self.assertTrue(self.widget.pbResume.isEnabled())

        # Trigger resume event
        self.widget.evt_resume_duplication()
        self.assertIn("Resuming duplicate check", self.widget.lblInfo.text())


if __name__ == '__main__':
    unittest.main()
