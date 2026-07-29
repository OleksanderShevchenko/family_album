import os
import shutil
import unittest
from datetime import datetime

from PyQt6.QtWidgets import QApplication
from src.family_album_lib.create_logger import LogEntry, LogLevel, CustomLogger
from src.family_album.gui.widgets.log_console import LogConsoleWidget

_app = QApplication.instance() or QApplication([])


class TestLoggerAndConsole(unittest.TestCase):

    def setUp(self):
        self.logger = CustomLogger("TestApp", "1.0")

    def tearDown(self):
        # Cleanup test log file
        log_path = self.logger.log_file_path
        if os.path.isfile(log_path):
            try:
                os.remove(log_path)
            except Exception:
                pass

    def test_log_entry_attributes(self):
        entry_info = LogEntry("Test info message", LogLevel.INFO)
        self.assertEqual(entry_info.level, LogLevel.INFO)
        self.assertEqual(entry_info.emoji, "🟢")
        self.assertEqual(entry_info.color, "#2ECC71")
        self.assertIn("Test info message", entry_info.to_html())
        self.assertIn("INFO", entry_info.to_file_string())

        entry_err = LogEntry("Test error message", LogLevel.ERROR)
        self.assertEqual(entry_err.emoji, "❌")
        self.assertEqual(entry_err.color, "#E74C3C")

    def test_custom_logger_file_creation(self):
        log_path = self.logger.log_file_path
        self.assertTrue(os.path.isfile(log_path))
        self.assertIn("logs", log_path)
        self.assertIn("TestApp_v1.0_", os.path.basename(log_path))

        self.logger.log_info("Hello log file")
        self.logger.log_debug("Debug line in file")

        with open(log_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertIn("Hello log file", content)
        self.assertIn("Debug line in file", content)

    def test_log_console_widget_filtering(self):
        console = LogConsoleWidget()
        entry_debug = LogEntry("Debug message for file only", LogLevel.DEBUG)
        entry_info = LogEntry("Info message for console", LogLevel.INFO)

        console.append_log_entry(entry_debug)
        console.append_log_entry(entry_info)

        text = console.console_edit.toPlainText()
        self.assertNotIn("Debug message for file only", text)
        self.assertIn("Info message for console", text)


if __name__ == '__main__':
    unittest.main()
