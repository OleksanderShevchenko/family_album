import asyncio
import json
import os.path
import shutil
import sys
from os import path
from PyQt6 import QtWidgets, uic, QtGui
from PyQt6.QtCore import pyqtSignal, QStringListModel, Qt, QItemSelectionModel
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QVBoxLayout, QDialog, QMessageBox, QLabel, QMainWindow, QMenu, QListView

from src.family_album.utility_functions.image_utils import is_image_file
from src.family_album_lib.duplicate_file_analyser import DuplicateFileAnalyser


class DuplicationChecker(QtWidgets.QWidget):
    ItemSelected = pyqtSignal(str)

    def __init__(self, parent):
        self._parent: QMainWindow = parent
        super(DuplicationChecker, self).__init__(parent)
        uic.loadUi(path.dirname(__file__) + '/py_ui/duplication_checker_ui.ui', self)
        self._selected_path: str = ""
        self.files_hash: dict = {}
        self.duplications: dict = {}
        self.lblFName.setText("<>")
        self.lblInfo.setText("<>")
        self.lblOriginalImage.setText("<>")
        self.lblDuplicatedImage.setText("<>")
        self.pbCheckDuplications.clicked.connect(self.evt_check_duplication)
        self.pbAnalyze.clicked.connect(self.evt_analyze_selected)
        self.pbDumpDuplications.clicked.connect(self.evt_dump_duplication)
        self.pbMove.clicked.connect(self.evt_move_duplications)
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))
        self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)
        self.lst_duplications.selectionModel().currentChanged.connect(self.evt_duplicated_file_selected)
        self.lst_duplications.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)  # Important
        self.lst_duplications.customContextMenuRequested.connect(self.evt_show_context_menu)
        self.pbAnalyze.setEnabled(False)
        self.pbCheckDuplications.setEnabled(False)
        self.pbDumpDuplications.setEnabled(False)
        self.pbMove.setEnabled(False)
        self._duplication_checker: DuplicateFileAnalyser = None

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
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
            self._duplication_checker = DuplicateFileAnalyser(new_path)
            self._duplication_checker.start_analysis = self._parent.evt_start_analysis
            self._duplication_checker.update_progress = self._parent.evt_update_progress
            self._duplication_checker.log_event = self._parent.log_event
        else:
            self._selected_path = ""
            self.lblFName.setText("<>")
            self.lblInfo.setText("<>")
            self.pbAnalyze.setEnabled(False)
            self.pbCheckDuplications.setEnabled(False)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
            self._duplication_checker = None
        self.files_hash: dict = {}
        self.duplications: dict = {}
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))

    def evt_check_duplication(self):
        self.files_hash = {}
        self.duplications = {}
        try:
            self.pbCheckDuplications.setEnabled(False)
            self.update()
            self._duplication_checker.start_analysis_thread()

        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        finally:
            self.pbCheckDuplications.setEnabled(True)

    def populate_duplications(self) -> None:
        self.files_hash = {}
        self.duplications = {}
        try:
            self.duplications = self._duplication_checker.duplicate_files
            self.files_hash = self._duplication_checker.files_hashes
            self.__populate_files()
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)

    def __populate_files(self):
        original_files = list(self.duplications.keys())
        if len(original_files) > 0:
            model = QStringListModel(original_files)
            self.lst_original_files.setModel(model)
            self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)
            if len(self.duplications) > 0:
                self.pbDumpDuplications.setEnabled(True)
                self.pbMove.setEnabled(True)
                duplicated_files_count = sum([len(item) for item in self.duplications.values()])
                files_with_duplicates_count = len(self.duplications)
                message = (f"Totally were found {files_with_duplicates_count} files with duplicates. " +
                           f"Total number of duplicate files are - {duplicated_files_count}")
                self.ItemSelected.emit(message)
                self.__show_message(message)
                self._parent.log_event(message)
        else:
            message = "No duplication files found"
            self.__show_message(message)
            self._parent.log_event(message)

    @staticmethod
    def __show_message(message: str) -> None:
        pass


    def evt_analyze_selected(self):
        try:
            self.pbAnalyze.setEnabled(False)
            file_count = self._duplication_checker.files_count_in_directory
            dir_count = self._duplication_checker.subdirectories_count_in_directory
            message = f'Selected directory totally has got {file_count} files and {dir_count} sub-directories'
            self.lblInfo.setText(message)
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)
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
        if is_image_file(selected_file):
            self.__show_image(self.lblOriginalImage, selected_file, True)
        else:
            self.lblOriginalImage.setText("<>")

    def evt_duplicated_file_selected(self, current, previous) -> None:
        selected_file = current.data()
        if is_image_file(selected_file):
            self.__show_image(self.lblDuplicatedImage, selected_file)
        else:
            self.lblDuplicatedImage.setText("<>")

    def evt_dump_duplication(self) -> None:
        if not self.duplications:
            self.__show_message("Duplication files are not defined!")
            return
        try:
            dump_file = os.path.join(self.selected_path, "duplicate_files_analysis_result.json")
            data_to_store = {}
            data_to_store["hash_data"] = self.files_hash
            data_to_store["duplication_data"] = self.duplications
            with open(dump_file, 'w') as fp:
                json.dump(data_to_store, fp)
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)

    def evt_move_duplications(self) -> None:
        if not self.duplications:
            self.__show_message("Duplication files are not defined!")
            return
        try:
            target_dir = os.path.join(self.selected_path, "duplications")
            if not os.path.isdir(target_dir):
                os.mkdir(target_dir)
            protocol = {}
            count_moved = 0
            for original_file, duplicated_files in self.duplications.items():
                for file in duplicated_files:
                    target_file = os.path.join(target_dir, os.path.basename(file))
                    if os.path.isfile(target_file):
                        i = 1
                        while os.path.isfile(target_file):
                            dir_name = os.path.dirname(target_file)
                            file_name, extention = os.path.splitext(os.path.basename(target_file))
                            target_file = os.path.join(dir_name, f"{file_name}_copy{i}{extention}")
                            i += 1
                    try:
                        shutil.move(file, target_file)
                        count_moved += 1
                    except Exception as err:
                        m = (f"Could not move file '{file}' into the directory '{target_dir}'! \n" +
                             f"Error: {err}")
                        print(m)
                        self.__show_message(m)
                        self._parent.log_event(m)
                    else:
                        protocol[f'Move_#{count_moved}'] = {}
                        protocol[f'Move_#{count_moved}']["original"] = original_file
                        protocol[f'Move_#{count_moved}']["moved_from"] = file
                        protocol[f'Move_#{count_moved}']["moved_to"] = target_file
            # save protocol
            protocol_file_name = os.path.join(target_dir, "protocol_of_moving_duplications.json")
            with open(protocol_file_name, 'w') as fp:
                json.dump(protocol, fp, indent=2, ensure_ascii=False)
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)
        finally:
            message = f"Totally moved {count_moved} files to '{target_dir}'"
            self.ItemSelected.emit(message)
            self.__show_message(message)
            self._parent.log_event(message)
            self.files_hash = {}
            self.duplications = {}
            self.pbMove.setEnabled(False)
            self.pbDumpDuplications.setEnabled(False)

    def evt_show_context_menu(self, pos):
        index = self.lst_duplications.indexAt(pos)
        if index.isValid():  # Check if an item is selected
            item_text = self.lst_duplications.model().data(index, Qt.ItemDataRole.DisplayRole)  # Get the text

            menu = QMenu(self)
            # Example actions:
            open_action = QAction("Set original", self)
            open_action.triggered.connect(lambda: self._set_original(item_text))  # Pass the index
            menu.addAction(open_action)

            menu.exec(self.lst_duplications.viewport().mapToGlobal(pos))  # Show the menu at the cursor position

    def _set_original(self, duplicate_file: str) -> None:
        selected_original_indexes = self.lst_original_files.selectionModel().selectedIndexes()

        if selected_original_indexes:
            # Get the first selected index (assuming single selection mode)
            selected_index = selected_original_indexes[0]
            original_file = self.lst_original_files.model().data(selected_index, Qt.ItemDataRole.DisplayRole)
            self.__switch_original_with_duplicate(original_file, duplicate_file)
            self.__populate_files()
            self.__select_new_row(self.lst_original_files, duplicate_file)
            try:
                self.__select_new_row(self.lst_duplications, original_file)
            except Exception:
                pass

        print(duplicate_file)

    def __switch_original_with_duplicate(self,original_file, duplicate_file) -> None:
        if original_file in self.duplications.keys() and duplicate_file not in self.duplications.keys():
            duplication_list: list = self.duplications[original_file]
            duplication_list.append(original_file)
            self.duplications.pop(original_file)
            duplication_list.remove(duplicate_file)
            self.duplications[duplicate_file] = duplication_list
        else:
            m = f"Error switching original and duplication files - duplicate files in originals or original is absent."
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)

    def __select_new_row(self, list_widget: QListView, target_text: str) -> None:
        """Selects the row in a QListView that contains the specified text."""

        model = list_widget.model()
        if model is None:
            return  # No model, nothing to select

        for row in range(model.rowCount()):
            index = model.index(row, 0)  # Assuming single-column list
            item_text = model.data(index, Qt.ItemDataRole.DisplayRole)

            if item_text == target_text:
                selection_model = list_widget.selectionModel()
                selection_model.setCurrentIndex(index, QItemSelectionModel.Select)
                break  # Stop after the first match is found

    def __show_image(self, label: QLabel, image_file_name: str, display_in_statusbar: bool = False) -> None:
        try:
            pix_map = QtGui.QPixmap(image_file_name)
            resolution = f"{pix_map.width()} x {pix_map.height()}"
            w: int = min(label.maximumWidth(), pix_map.width())
            h: int = min(label.maximumHeight(), pix_map.height())
            pix_map = pix_map.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio)
            label.setPixmap(pix_map)
            label.setScaledContents(True)
            label.show()
            if display_in_statusbar:
                self.ItemSelected.emit(f"Selected file - {image_file_name} has resolution {resolution}")
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self._parent.log_event(m)


if __name__ == "__main__":
    _app = QtWidgets.QApplication(sys.argv)
    dialog = QDialog()
    dir_viewer = DuplicationChecker(dialog)
    layout1 = QVBoxLayout()
    # insert input widget to this layout
    layout1.addWidget(dir_viewer)
    dialog.setLayout(layout1)
    dialog.show()
    _app.exec()
