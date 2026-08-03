import unittest
from PyQt6.QtWidgets import QApplication
from src.family_album.gui.dialogs.about_dialog import AboutDialog

_app = QApplication.instance() or QApplication([])


class TestAboutDialog(unittest.TestCase):

    def test_about_dialog_creation(self):
        dialog = AboutDialog()
        self.assertEqual(dialog.windowTitle(), "About Family Album")
        self.assertTrue(dialog.isModal())


if __name__ == '__main__':
    unittest.main()
