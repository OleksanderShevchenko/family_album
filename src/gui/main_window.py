__author__ = "Oleksandr Shevchenko"
__copyright__ = "Oleksandr Shevchenko"
__contact__ = "oleksander.shevchenko777@gmail.com"
__version__ = "0.1"
__license__ = """MIT Licence"""
import os
from PyQt5 import uic
from PyQt5.QtWidgets import QMainWindow, QVBoxLayout

# from .plot_canvas import PlotCanvas
from src.gui.widgets.directory_view import DirectoryView
from src.gui.widgets.duplication_checker import DuplicationChecker
from src.gui.widgets.file_organizer import FileOrganizer


class MainWindow(QMainWindow):

    def __init__(self, name: str, version: str):
        super().__init__()
        self.window = uic.loadUi(os.path.dirname(__file__) + '/py_ui/main_window.ui', self)
        self.title = name + ' v.' + version
        self._interval = 10000  # msec
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
