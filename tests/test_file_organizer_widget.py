import os
import shutil
import tempfile
import unittest

from PyQt6.QtWidgets import QApplication

from src.family_album.gui.widgets.file_organizer import FileOrganizer
from src.family_album_lib.organizer_db import OrganizerDatabase

app = QApplication.instance()
if app is None:
    app = QApplication([])


class TestFileOrganizerWidget(unittest.TestCase):

    def setUp(self):
        self.temp_root = tempfile.mkdtemp()
        self.source_dir = os.path.join(self.temp_root, "raw_photos")
        os.makedirs(self.source_dir, exist_ok=True)
        self.widget = FileOrganizer()

    def tearDown(self):
        self.widget.deleteLater()
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_widget_initial_state(self):
        self.assertEqual(self.widget.selected_path, "")
        self.assertEqual(self.widget.target_path, "")
        self.assertFalse(self.widget.pb_analyze.isEnabled())
        self.assertFalse(self.widget.pb_organize.isEnabled())

    def test_set_selected_path_configures_new_organization_mode(self):
        self.widget.selected_path = self.source_dir
        self.assertEqual(self.widget.selected_path, os.path.normpath(self.source_dir))

        # Expected sibling target: <source>_organized
        expected_target = os.path.normpath(os.path.join(self.temp_root, "raw_photos_organized"))
        self.assertEqual(self.widget.target_path, expected_target)

        # Mode should be new organization
        self.assertTrue(self.widget.rb_mode_new.isChecked())
        self.assertTrue(self.widget.rb_action_copy.isChecked())
        self.assertTrue(self.widget.pb_analyze.isEnabled())
        self.assertTrue(self.widget.pb_organize.isEnabled())

    def test_set_selected_path_with_existing_db_activates_self_organization(self):
        # Initialize .db in source directory
        with OrganizerDatabase(self.source_dir) as db:
            pass

        self.widget.selected_path = self.source_dir

        # Mode should automatically be self-organization
        self.assertTrue(self.widget.rb_mode_self.isChecked())
        # Target should be source itself
        self.assertEqual(self.widget.target_path, os.path.normpath(self.source_dir))
        # Copy must be disabled, Move must be checked
        self.assertFalse(self.widget.rb_action_copy.isEnabled())
        self.assertTrue(self.widget.rb_action_move.isChecked())


if __name__ == "__main__":
    unittest.main()
