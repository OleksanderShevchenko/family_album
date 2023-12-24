import asyncio
import os.path
import sys
from os import path
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from PyQt5.QtCore import QDir, pyqtSignal, QStringListModel
from PyQt5.QtWidgets import QFileSystemModel, QTreeView, QVBoxLayout, QHBoxLayout, QDialog, QMessageBox

from src.utility_functions.find_duplicate_files_async import find_duplicate_files_async
from src.utility_functions.get_files_and_subdirs_count import get_files_and_subdirs_count


class FileView(QtWidgets.QWidget):
    ItemSelected = pyqtSignal(str)

    def __init__(self, parent):
        super(FileView, self).__init__(parent)
        uic.loadUi(path.dirname(__file__) + '/py_ui/files_view.ui', self)
        self._selected_path: str = ""
        self.files_hash: dict = {}
        self.duplications: dict = {}
        self.lblFName.setText("<>")
        self.lblInfo.setText("<>")
        self.lblOriginalImage.setText("<>")
        self.lblDuplicatedImage.setText("<>")
        self.btnCheckDuplications.clicked.connect(self.evt_check_duplication)
        self.pbAnalyze.clicked.connect(self.evt_analyze_selected)
        self.pbAnalyze.setEnabled(False)
        self.btnCheckDuplications.setEnabled(False)

    @property
    def selected_path(self) -> str:
        return self._selected_path

    @selected_path.setter
    def selected_path(self, new_path: str) -> None:
        if os.path.isdir(new_path):
            self._selected_path = new_path
            self.lblFName.setText(new_path)
            self.pbAnalyze.setEnabled(True)
            self.btnCheckDuplications.setEnabled(True)
        else:
            self._selected_path = ""
            self.lblFName.setText("<>")
            self.lblInfo.setText("<>")
            self.pbAnalyze.setEnabled(False)
            self.btnCheckDuplications.setEnabled(False)
        self.files_hash: dict = {}
        self.duplications: dict = {}
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))

    def evt_check_duplication(self):
        try:
            self.files_hash = asyncio.run(find_duplicate_files_async(self._selected_path))
            self.duplications = {os.path.basename(file[0]): file[1:] for _, file in self.files_hash.items() if len(file) > 1}
            original_files = list(self.duplications.keys())
            if len(original_files) > 0:
                model = QStringListModel(original_files)
                self.lst_original_files.setModel(model)
            else:
                self.__show_message("No duplication files found")
        except Exception as err:
            print(f"Error occur: {err}")
            self.__show_message(f"Error occur: {err}")

    def __show_message(self, message: str) -> None:
        msg = QMessageBox()
        msg.setWindowTitle("Duplication analysis")
        msg.setText(message)
        msg.setIcon(QMessageBox.Warning)
        msg.exec_()

    def evt_analyze_selected(self):
        try:
            self.pbAnalyze.setEnabled(False)
            file_count, dir_count = get_files_and_subdirs_count(self._selected_path)
            message = f'Selected directory totally has got {file_count} files and {dir_count} sub-directories'
            self.lblInfo.setText(message)
        except Exception as err:
            print(f"Error occur: {err}")
            self.__show_message(f"Error occur: {err}")
        finally:
            self.pbAnalyze.setEnabled(True)


if __name__ == "__main__":
    _app = QtWidgets.QApplication(sys.argv)
    dialog = QDialog()
    dir_viewer = FileView(dialog)
    layout1 = QVBoxLayout()
    # insert input widget to this layout
    layout1.addWidget(dir_viewer)
    dialog.setLayout(layout1)
    dialog.show()
    _app.exec_()
