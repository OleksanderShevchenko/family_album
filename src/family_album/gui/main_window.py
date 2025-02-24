__author__ = "Oleksandr Shevchenko"
__copyright__ = "Oleksandr Shevchenko"
__contact__ = "oleksander.shevchenko777@gmail.com"
__version__ = "0.1"
__license__ = """MIT Licence"""

import logging
import os
import time

from PyQt5 import uic, QtWidgets
from PyQt5.QtWidgets import QMainWindow, QVBoxLayout

# from .plot_canvas import PlotCanvas
from src.family_album.gui.widgets.directory_view import DirectoryView
from src.family_album.gui.widgets.duplication_checker import DuplicationChecker
from src.family_album.gui.widgets.file_organizer import FileOrganizer
from src.family_album_lib.create_logger import CustomLogger


class MainWindow(QMainWindow):

    def __init__(self, name: str, version: str):
        super().__init__()
        self._logger = CustomLogger(name, version)
        self._logger.log_debug("\n***** Start new session *****\n")
        try:
            self.window = uic.loadUi(os.path.dirname(__file__) + '/py_ui/main_window.ui', self)
            self.title = name + ' v.' + version
            self._interval = 10_000  # msec interval for show message in status bar
            self.setWindowTitle(self.title)
            self.dir_viewer = DirectoryView(self)
            self.dir_viewer.ItemSelected.connect(self.evt_dir_selected)
            self.duplication_checker = DuplicationChecker(self)
            self.duplication_checker.ItemSelected.connect(self.evt_show_in_statusbar)
            self.file_organizer = FileOrganizer(self)
            self.file_organizer.ItemSelected.connect(self.evt_show_in_statusbar)
            layout1 = QVBoxLayout()
            # insert input widget to this layout
            layout1.addWidget(self.dir_viewer)
            self.directories_space.setLayout(layout1)

            layout2 = QVBoxLayout()
            layout2.addWidget(self.duplication_checker)
            self.files_space.setLayout(layout2)

            layout3 = QVBoxLayout()
            layout3.addWidget(self.file_organizer)
            self.organazing_space.setLayout(layout3)

            self.main_splitter.setStretchFactor(0, 33)
            self.main_splitter.setStretchFactor(1, 67)
            # add progress bar in status bar
            self.progressBar = QtWidgets.QProgressBar()
            self.statusBar().addPermanentWidget(self.progressBar)
            # This is simply to show the bar
            self.progressBar.setGeometry(30, 40, 150, 25)
            self.progressBar.setMinimum(0)
            self.progressBar.setMaximum(100)
            self.progressBar.setValue(0)
            self.progressBar.setVisible(False)
            self.progressBar.setTextVisible(False)
        except Exception as err:
            self._logger.log_error(f"Error on main window initialization: {err}")

    def evt_dir_selected(self, selected_dir: str) -> None:
        if os.path.isdir(selected_dir):
            message = f'Selected directory {selected_dir}.'
            self.statusBar().showMessage(message, self._interval)
            self.duplication_checker.selected_path = selected_dir
            self.file_organizer.selected_path = selected_dir
        elif os.path.isfile(selected_dir):
            message = f'Selected file {selected_dir}.'
            self.statusBar().showMessage(message, self._interval)

    def evt_show_in_statusbar(self, message: str) -> None:
        self.statusBar().showMessage(message, self._interval)

    def evt_start_analysis(self, message: str) -> None:
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)
        self.progressBar.setTextVisible(True)
        self.statusBar().showMessage(message, self._interval)
        self._logger.log_debug(f"Start analysis '{message}'")
        self.update()

    def evt_update_progress(self, finished: int, total: int) -> None:
        progress = int(finished / total * 100)
        current_progress = self.progressBar.value()
        if current_progress < progress <= self.progressBar.maximum():
            self.progressBar.setValue(progress)
            self.statusBar().showMessage(f"Finished {finished} files from {total} total scope of " +
                                         f"files to analyze", self._interval)
            self.update()
        self._logger.log_debug(f"Update progress: done '{finished}' files of totally '{total}' to be analyzed")
        if finished == total:
            time.sleep(1)
            self.evt_finish_analysis("Finish analysis.")

    def evt_finish_analysis(self, message: str) -> None:
        self.progressBar.setValue(0)
        self.progressBar.setVisible(False)
        self.progressBar.setTextVisible(False)
        self.statusBar().showMessage(message, self._interval)
        self._logger.log_debug(f"Finish analysis '{message}'")
        self.duplication_checker.populate_duplications()
        self.update()

    def log_event(self, message: str) -> None:
        if 'error' in message.lower():
            self._logger.log_error(message)
        elif 'warning' in message.lower():
            self._logger.log_warning(message)
        else:
            self._logger.log_info(message)
