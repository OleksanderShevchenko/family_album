import asyncio
import os.path
import sys
from os import path
from PyQt5 import QtWidgets, uic, QtCore, QtGui
from PyQt5.QtCore import QDir, pyqtSignal, QStringListModel, Qt
from PyQt5.QtWidgets import QFileSystemModel, QTreeView, QVBoxLayout, QHBoxLayout, QDialog, QMessageBox, QLabel

from src.utility_functions.find_duplicate_files_async import find_duplicate_files_async
from src.utility_functions.get_files_and_subdirs_count import get_files_and_subdirs_count
from src.utility_functions.is_file_image_pil import is_file_a_picture


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
        self.pbCheckDuplications.clicked.connect(self.evt_check_duplication)
        self.pbAnalyze.clicked.connect(self.evt_analyze_selected)
        self.pbMove.clicked.connect(self.evt_move_duplications)
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))
        self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)
        self.lst_duplications.selectionModel().currentChanged.connect(self.evt_duplicated_file_selected)
        self.pbAnalyze.setEnabled(False)
        self.pbCheckDuplications.setEnabled(False)
        self.pbMove.setEnabled(False)

    @property
    def selected_path(self) -> str:
        return self._selected_path

    @selected_path.setter
    def selected_path(self, new_path: str) -> None:
        if os.path.isdir(new_path):
            self._selected_path = new_path
            self.lblFName.setText(new_path)
            self.pbAnalyze.setEnabled(True)
            self.pbCheckDuplications.setEnabled(True)
            self.pbMove.setEnabled(False)
        else:
            self._selected_path = ""
            self.lblFName.setText("<>")
            self.lblInfo.setText("<>")
            self.pbAnalyze.setEnabled(False)
            self.pbCheckDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        self.files_hash: dict = {}
        self.duplications: dict = {}
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))


    def evt_check_duplication(self):
        try:
            self.pbCheckDuplications.setEnabled(False)
            self.files_hash = asyncio.run(find_duplicate_files_async(self._selected_path))
            self.duplications = {file[0]: file[1:] for _, file in self.files_hash.items()
                                 if len(file) > 1}
            original_files = list(self.duplications.keys())
            if len(original_files) > 0:
                model = QStringListModel(original_files)
                self.lst_original_files.setModel(model)
                self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)
            else:
                self.__show_message("No duplication files found")
            if len(self.duplications) > 0:
                self.pbMove.setEnabled(True)
        except Exception as err:
            print(f"Error occur: {err}")
            self.__show_message(f"Error occur: {err}")
            self.pbMove.setEnabled(False)
        finally:
            self.pbCheckDuplications.setEnabled(True)

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

    def evt_original_file_selected(self, current, previous) -> None:
        selected_file = current.data()
        duplication_files = self.duplications[selected_file]
        if selected_file in duplication_files:
            self.__show_message(f"Selected file {selected_file} is duplicated in list of its duplicates!")
        self.lst_duplications.setModel(QStringListModel(duplication_files))
        self.lst_duplications.selectionModel().currentChanged.connect(self.evt_duplicated_file_selected)
        self.lblDuplicatedImage.setText("<>")
        if is_file_a_picture(selected_file):
            self.__show_image(self.lblOriginalImage, selected_file)
        else:
            self.lblOriginalImage.setText("<>")

    def evt_duplicated_file_selected(self, current, previous) -> None:
        selected_file = current.data()
        if is_file_a_picture(selected_file):
            self.__show_image(self.lblDuplicatedImage, selected_file)
        else:
            self.lblDuplicatedImage.setText("<>")

    def evt_move_duplications(self) -> None:
        if not self.duplications:
            self.__show_message("Duplication files are not defined!")
            return

    def __show_image(self, label: QLabel, image_file_name: str) -> None:
        pix_map = QtGui.QPixmap(image_file_name)
        w: int = min(label.maximumWidth(), pix_map.width())
        h: int = min(label.maximumHeight(), pix_map.height())
        pix_map.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label.setPixmap(pix_map)
        label.show()


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
