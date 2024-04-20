import os.path
import sys
from os import path
from PyQt5 import QtWidgets, uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QStandardItemModel
from PyQt5.QtWidgets import QVBoxLayout, QDialog, QMessageBox

from src.gui.dataframe_model import DataFrameModel
from src.utility_functions.analyze_directory import analyze_directory
from src.utility_functions.database_manager import DatabaseManager
from src.utility_functions.database_settings import DatabaseSettings
from src.utility_functions.get_files_and_subdirs_count import get_files_and_subdirs_count


class FileOrganizer(QtWidgets.QWidget):
    _DB_FOLDER = 'data'
    _DB_FILE = 'my_album.db'

    ItemSelected = pyqtSignal(str)

    def __init__(self, parent):
        super(FileOrganizer, self).__init__(parent)
        uic.loadUi(path.dirname(__file__) + '/py_ui/file_organizer_ui.ui', self)
        self._selected_path: str = ""
        self.lbl_folder_selected.setText("<>")
        self.lbl_info.setText("<>")
        self.pb_analyze.clicked.connect(self.evt_analyze_selected)
        self.pb_organize.clicked.connect(self.evt_organize_files)
        self.pb_analyze.setEnabled(False)
        self.pb_organize.setEnabled(False)
        self.tbl_file_data.setSortingEnabled(True)
        self.tbl_file_data.horizontalHeader().setSectionsMovable(True)
        self.__connect_to_database()

    @property
    def selected_path(self) -> str:
        return self._selected_path

    @selected_path.setter
    def selected_path(self, new_path: str) -> None:
        if os.path.isdir(new_path):
            self._selected_path = new_path
            self.lbl_folder_selected.setText(new_path)
            self.pb_analyze.setEnabled(True)
            self.pb_organize.setEnabled(True)
        else:
            self._selected_path = ""
            self.lbl_folder_selected.setText("<>")
            self.lbl_info.setText("<>")
            self.pb_analyze.setEnabled(False)
            self.pb_organize.setEnabled(False)
        self.lbl_info.setText("<>")
        self.tbl_file_data.setModel(QStandardItemModel())

    def evt_organize_files(self):
        try:
            ...
        except Exception as err:
            print(f"Error occur: {err}")
            self.__show_message(f"Error occur: {err}")
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        finally:
            self.pb_organize.setEnabled(True)

    def __show_message(self, message: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Files organizer")
        msg.setText(message)
        msg.setIcon(QMessageBox.Warning)
        msg.exec_()

    def evt_analyze_selected(self):
        try:
            if os.path.isdir(self._selected_path):
                self.pb_analyze.setEnabled(False)
                file_count, dir_count = get_files_and_subdirs_count(self._selected_path)
                message = f'Selected directory totally has got {file_count} files and {dir_count} sub-directories'
                self.lbl_info.setText(message)
                data_frame = analyze_directory(self._selected_path)
                df_model = DataFrameModel(data_frame)
                self.tbl_file_data.setModel(df_model)
        except Exception as err:
            print(f"Error occur: {err}")
            self.__show_message(f"Error occur: {err}")
        finally:
            self.pb_analyze.setEnabled(True)

    def __connect_to_database(self) -> None:  # for sqlite
        working_dir = os.path.abspath(os.getcwd())
        database_path = os.path.join(working_dir, *os.path.split(self._DB_FOLDER))
        database_file = os.path.join(database_path, self._DB_FILE)
        if not os.path.isdir(database_path):
            os.mkdir(database_path)
        self.__db_settings = DatabaseSettings(
            database_type="sqlite",
            host="",
            port=0,
            username="",
            password="",
            database_name=database_file
        )
        self.database: DatabaseManager = DatabaseManager(self.__db_settings)
        self.database.connect()


if __name__ == "__main__":
    _app = QtWidgets.QApplication(sys.argv)
    dialog = QDialog()
    dir_viewer = FileOrganizer(dialog)
    layout1 = QVBoxLayout()
    # insert input widget to this layout
    layout1.addWidget(dir_viewer)
    dialog.setLayout(layout1)
    dialog.show()
    _app.exec_()
