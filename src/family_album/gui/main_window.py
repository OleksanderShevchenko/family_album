"""
Main window module for the Family Album desktop application.

Coordinates top-level GUI layout, menus, splitters, log console, status bar,
and tabbed workspaces (Duplication Checker and File Organizer).
"""

import os
import time

from PyQt6 import uic, QtWidgets, QtCore
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QMainWindow, QVBoxLayout

from src.family_album.gui.dialogs.about_dialog import AboutDialog
from src.family_album.gui.dialogs.settings_dialog import SettingsDialog
from src.family_album.gui.widgets.directory_view import DirectoryView
from src.family_album.gui.widgets.duplication_checker import DuplicationChecker
from src.family_album.gui.widgets.file_organizer import FileOrganizer
from src.family_album.gui.widgets.log_console import LogConsoleWidget
from src.family_album.gui.py_ui.main_window import Ui_FamilyAlbumUI
from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.create_logger import CustomLogger, LogLevel


class MainWindow(QMainWindow, Ui_FamilyAlbumUI):
    """
    Primary desktop application window hosting the main workspace.

    Integrates:
    - Left sidebar: Directory tree browser (`DirectoryView`).
    - Right work area tabs:
      - Tab 1: Duplicate file analyzer & previewer (`DuplicationChecker`).
      - Tab 2: Media structure organizer by date (`FileOrganizer`).
    - Bottom collapsable logging console (`LogConsoleWidget`).
    - Status bar with animated progress tracking and notifications.
    """

    def __init__(self, name: str, version: str):
        """
        Initialize the main application window, menus, sub-widgets, and splitters.

        Args:
            name (str): Application display name.
            version (str): Application semantic version.
        """
        super().__init__()
        self._logger = CustomLogger(name, version)
        self._logger.log_debug("\n***** Start new session *****\n")
        self._settings = AppSettings.instance()
        try:
            self.setupUi(self)
            # self.window = uic.loadUi(os.path.dirname(__file__) + '/py_ui/main_window.ui', self)

            self.title = name + ' v.' + version
            self._interval = 10_000  # msec interval for show message in status bar
            self.setWindowTitle(self.title)

            # Create Menu Bar with File, Tools, and Help menus
            self.menu_bar = self.menuBar()

            # File Menu
            self.menu_file = self.menu_bar.addMenu("&File")
            self.action_exit = QAction("&Exit", self)
            self.action_exit.setShortcut(QKeySequence("Alt+F4"))
            self.action_exit.setStatusTip("Exit application")
            self.action_exit.triggered.connect(self.close)
            self.menu_file.addAction(self.action_exit)

            # Tools Menu
            self.menu_tools = self.menu_bar.addMenu("&Tools")
            self.action_settings = QAction("&Settings...", self)
            self.action_settings.setShortcut(QKeySequence("Ctrl+,"))
            self.action_settings.setStatusTip("Configure application settings and parallel worker threads")
            self.action_settings.triggered.connect(self.evt_show_settings_dialog)
            self.menu_tools.addAction(self.action_settings)

            # Help Menu
            self.menu_help = self.menu_bar.addMenu("&Help")
            self.action_about = QAction("&About...", self)
            self.action_about.setStatusTip("Show information about Family Album and author")
            self.action_about.triggered.connect(self.evt_show_about_dialog)
            self.menu_help.addAction(self.action_about)

            self.dir_viewer = DirectoryView(self)
            self.dir_viewer.ItemSelected.connect(self.evt_dir_selected)
            self.duplication_checker = DuplicationChecker(self)
            self.duplication_checker.ItemSelected.connect(self.evt_show_in_statusbar)
            self.file_organizer = FileOrganizer(self)
            self.file_organizer.ItemSelected.connect(self.evt_show_in_statusbar)
            self.file_organizer.LogEventEmitted.connect(self.log_event)

            layout1 = QVBoxLayout()
            layout1.addWidget(self.dir_viewer)
            self.directories_space.setLayout(layout1)

            layout2 = QVBoxLayout()
            layout2.addWidget(self.duplication_checker)
            self.files_space.setLayout(layout2)

            layout3 = QVBoxLayout()
            layout3.addWidget(self.file_organizer)
            self.organazing_space.setLayout(layout3)

            self.splitter.setStretchFactor(0, 33)
            self.splitter.setStretchFactor(1, 67)

            # Enable the second tab ("Organize structure")
            self.tabWidget.setTabEnabled(1, True)
            self.tabWidget.setTabToolTip(1, "Organize media files into Year/Month structure")

            # Create vertical splitter separating main content space and log console above status bar
            self.main_vertical_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, parent=self.centralwidget)
            self.verticalLayout_3.removeWidget(self.splitter)
            self.main_vertical_splitter.addWidget(self.splitter)

            self.log_console = LogConsoleWidget(parent=self.main_vertical_splitter)
            self.main_vertical_splitter.addWidget(self.log_console)

            self.verticalLayout_3.addWidget(self.main_vertical_splitter)
            # Default state: collapsed console (or small initial size)
            self.main_vertical_splitter.setSizes([800, 0])

            # Add progress bar in status bar
            self.progressBar = QtWidgets.QProgressBar()
            self.statusBar().addPermanentWidget(self.progressBar)
            self.progressBar.setGeometry(30, 40, 150, 25)
            self.progressBar.setMinimum(0)
            self.progressBar.setMaximum(100)
            self.progressBar.setValue(0)
            self.progressBar.setVisible(False)
            self.progressBar.setTextVisible(False)

            self._logger.log_info(
                f"Session started. Worker threads: {self._settings.worker_threads}. "
                f"Log file: '{self._logger.log_file_path}'"
            )

            # Restore last selected directory if valid on disk
            last_dir = self._settings.last_selected_directory
            if last_dir and os.path.isdir(last_dir):
                self.dir_viewer.select_directory(last_dir)
                self.evt_dir_selected(last_dir)
        except Exception as err:
            self._logger.log_error(f"Error on main window initialization: {err}")

    def evt_show_settings_dialog(self) -> None:
        """
        Display the modal application Settings dialog (`Tools -> Settings...`).

        Propagates updated worker thread count and startup directory to active tools.
        """
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            threads = self._settings.worker_threads
            self.duplication_checker.max_workers = threads
            self.file_organizer.max_workers = threads

            new_dir = self._settings.last_selected_directory
            if new_dir and os.path.isdir(new_dir) and new_dir != self.duplication_checker.selected_path:
                self.dir_viewer.select_directory(new_dir)
                self.evt_dir_selected(new_dir)

            msg = f"Settings updated: worker threads = {threads}."
            self.statusBar().showMessage(msg, self._interval)
            self._logger.log_info(msg)

    def evt_show_about_dialog(self) -> None:
        """Display the modal application About dialog."""
        dialog = AboutDialog(self)
        dialog.exec()

    def evt_dir_selected(self, selected_dir: str) -> None:
        """
        Handle selection of a directory from the DirectoryView tree.

        Propagates selected path to both DuplicationChecker and FileOrganizer widgets
        and persists it in AppSettings (`last_selected_directory`).

        Args:
            selected_dir (str): Filesystem path to selected directory.
        """
        if os.path.isdir(selected_dir):
            norm_dir = os.path.normpath(selected_dir)
            message = f'Selected directory {norm_dir}.'
            self.statusBar().showMessage(message, self._interval)
            self.duplication_checker.selected_path = norm_dir
            self.file_organizer.selected_path = norm_dir
            if self._settings.last_selected_directory != norm_dir:
                self._settings.last_selected_directory = norm_dir
                self._settings.save()
            self._logger.log_info(message)

    def evt_show_in_statusbar(self, message: str) -> None:
        """
        Display a temporary message in the status bar and record it to the logger.

        Args:
            message (str): Text message to display.
        """
        self.statusBar().showMessage(message, self._interval)
        self._logger.log_info(message)

    def evt_start_analysis(self, message: str) -> None:
        """
        Prepare GUI for duplicate analysis: lock directory tree and show progress bar.

        Args:
            message (str): Status notification text.
        """
        if hasattr(self, 'dir_viewer') and self.dir_viewer:
            self.dir_viewer.setEnabled(False)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)
        self.progressBar.setTextVisible(True)
        self.statusBar().showMessage(message, self._interval)
        self._logger.log_info(f"Start analysis '{message}'")
        self.update()

    def evt_update_progress(self, finished: int, total: int) -> None:
        """
        Update the status bar progress bar based on completed file counts.

        Args:
            finished (int): Count of files completed.
            total (int): Total file count.
        """
        progress = int(finished / total * 100) if total > 0 else 0
        current_progress = self.progressBar.value()
        if current_progress < progress <= self.progressBar.maximum():
            self.progressBar.setValue(progress)
            msg = f"Finished {finished} files from {total} total scope of files to analyze"
            self.statusBar().showMessage(msg, self._interval)
        self._logger.log_debug(f"Update progress: done '{finished}' files of totally '{total}' to be analyzed")
        if finished == total:
            time.sleep(0.1)
            self.evt_finish_analysis("Finish analysis.")

    def evt_finish_analysis(self, message: str) -> None:
        """
        Finalize analysis UI: re-enable directory tree, hide progress bar, and display results.

        Args:
            message (str): Completion message.
        """
        if hasattr(self, 'dir_viewer') and self.dir_viewer:
            self.dir_viewer.setEnabled(True)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(False)
        self.progressBar.setTextVisible(False)
        self.statusBar().showMessage(message, self._interval)
        self._logger.log_info(f"Finish analysis '{message}'")
        self.duplication_checker.populate_duplications()
        self.update()

    def log_event(self, message: str) -> None:
        """
        Log an informational event message through the application custom logger.

        Args:
            message (str): Message to log.
        """
        self._logger.log_event(message)
