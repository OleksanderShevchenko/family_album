import json
import os.path
import shutil
import sys

from PyQt6 import QtWidgets, uic, QtGui
from PyQt6.QtCore import pyqtSignal, QStringListModel, Qt, QItemSelectionModel
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QVBoxLayout, QDialog, QMessageBox, QLabel, QMainWindow, QMenu, QListView

from family_album.gui.widgets.py_ui.duplication_checker_ui import Ui_Form
from src.family_album.utility_functions.image_utils import is_image_file
from src.family_album_lib.resumable_duplicate_analyser import ResumableDuplicateAnalyser
from src.family_album_lib.duplication_memento import (
    DuplicationSaveManager,
    DuplicationCheckStatus
)


class DuplicationChecker(QtWidgets.QWidget, Ui_Form):
    ItemSelected = pyqtSignal(str)
    AnalysisStarted = pyqtSignal(str)
    ProgressUpdated = pyqtSignal(int, int)
    AnalysisFinished = pyqtSignal(str)
    LogEventEmitted = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self._parent: QMainWindow = parent
        self.setupUi(self)

        self._save_manager: DuplicationSaveManager = DuplicationSaveManager("saves")

        # Create control buttons for state management
        self.pbStop = QtWidgets.QPushButton("Stop / Pause", parent=self)
        self.pbStop.setToolTip("Stop or pause the active duplicate check process")
        self.pbStop.clicked.connect(self.evt_stop_duplication)

        self.pbSaveState = QtWidgets.QPushButton("Save State", parent=self)
        self.pbSaveState.setToolTip("Save current check progress to 'saves' folder")
        self.pbSaveState.clicked.connect(self.evt_save_state)

        self.pbResume = QtWidgets.QPushButton("Resume Check", parent=self)
        self.pbResume.setToolTip("Resume check from saved state")
        self.pbResume.clicked.connect(self.evt_resume_duplication)

        # Insert new control buttons into the layout
        self.horizontalLayout.insertWidget(2, self.pbStop)
        self.horizontalLayout.insertWidget(3, self.pbSaveState)
        self.horizontalLayout.insertWidget(4, self.pbResume)

        # Connect thread-safe PyQt signals for GUI thread updates
        self.AnalysisStarted.connect(self._on_analysis_started)
        self.ProgressUpdated.connect(self._on_progress_updated)
        self.AnalysisFinished.connect(self._on_analysis_finished)
        self.LogEventEmitted.connect(self._on_log_event)

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
        self.lst_duplications.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.lst_duplications.customContextMenuRequested.connect(self.evt_show_context_menu)

        self._duplication_checker: ResumableDuplicateAnalyser = None
        self._update_button_states()

    @property
    def selected_path(self) -> str:
        return self._selected_path

    @selected_path.setter
    def selected_path(self, new_path: str) -> None:
        if os.path.isdir(new_path):
            norm_path = os.path.normpath(new_path)
            self._selected_path = norm_path
            self.lblFName.setText(norm_path)
            self._duplication_checker = ResumableDuplicateAnalyser(norm_path,
                                                                   self.AnalysisStarted.emit,
                                                                   self.ProgressUpdated.emit,
                                                                   self.LogEventEmitted.emit,
                                                                   self.AnalysisFinished.emit)

            if self._save_manager.has_save(norm_path):
                memento = self._save_manager.load_memento(norm_path)
                checked_count = len(memento.processed_files) if memento else 0
                total_count = memento.files_count if memento else 0
                self.lblInfo.setText(
                    f"Saved state found for this directory ({checked_count}/{total_count} files checked). "
                    f"Click 'Resume Check' to continue or 'Check for duplicate' to start fresh."
                )
            else:
                self.lblInfo.setText("<>")
        else:
            self._selected_path = ""
            self.lblFName.setText("<>")
            self.lblInfo.setText("<>")
            self._duplication_checker = None

        self.files_hash = {}
        self.duplications = {}
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))
        self._update_button_states()

    def _on_analysis_started(self, msg: str) -> None:
        if hasattr(self._parent, 'evt_start_analysis'):
            self._parent.evt_start_analysis(msg)

    def _on_progress_updated(self, finished: int, total: int) -> None:
        if hasattr(self._parent, 'evt_update_progress'):
            self._parent.evt_update_progress(finished, total)

    def _on_analysis_finished(self, msg: str) -> None:
        if hasattr(self._parent, 'evt_finish_analysis'):
            self._parent.evt_finish_analysis(msg)

    def _on_log_event(self, msg: str) -> None:
        if hasattr(self._parent, 'log_event'):
            self._parent.log_event(msg)

    def _update_button_states(self, is_running: bool = False) -> None:
        has_path = bool(self.selected_path and os.path.isdir(self.selected_path))
        has_save = has_path and self._save_manager.has_save(self.selected_path)
        status = self._duplication_checker.status if self._duplication_checker else DuplicationCheckStatus.IDLE

        if is_running or status == DuplicationCheckStatus.RUNNING:
            self.pbAnalyze.setEnabled(False)
            self.pbCheckDuplications.setEnabled(False)
            self.pbStop.setEnabled(True)
            self.pbSaveState.setEnabled(False)
            self.pbResume.setEnabled(False)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        elif status == DuplicationCheckStatus.PAUSED:
            self.pbAnalyze.setEnabled(has_path)
            self.pbCheckDuplications.setEnabled(has_path)
            self.pbStop.setEnabled(False)
            self.pbSaveState.setEnabled(True)
            self.pbResume.setEnabled(has_save)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        else:  # IDLE or COMPLETED
            self.pbAnalyze.setEnabled(has_path)
            self.pbCheckDuplications.setEnabled(has_path)
            self.pbStop.setEnabled(False)
            self.pbSaveState.setEnabled(False)
            self.pbResume.setEnabled(has_save)
            has_dups = bool(self.duplications)
            self.pbDumpDuplications.setEnabled(has_dups)
            self.pbMove.setEnabled(has_dups)

    def evt_check_duplication(self) -> None:
        if not self.selected_path or not self._duplication_checker:
            return

        if self._save_manager.has_save(self.selected_path):
            reply = QMessageBox.question(
                self,
                "Saved State Detected",
                "A saved check state exists for this directory.\n\n"
                "Would you like to resume from the saved state?\n"
                "Choose 'Yes' to resume, 'No' to start a fresh check, or 'Cancel'.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.evt_resume_duplication()
                return
            elif reply == QMessageBox.StandardButton.Cancel:
                return
            else:
                self._save_manager.delete_save(self.selected_path)

        self.files_hash = {}
        self.duplications = {}
        self._duplication_checker.reset()
        try:
            self._update_button_states(is_running=True)
            self._duplication_checker.start_analysis_thread(run_in_background=True)
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self.LogEventEmitted.emit(m)
            self._update_button_states(is_running=False)

    def evt_stop_duplication(self) -> None:
        if self._duplication_checker:
            self._duplication_checker.stop_analysis()
            msg = "Duplicate check process was paused by user."
            self.lblInfo.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._update_button_states()

    def evt_save_state(self) -> None:
        if not self._duplication_checker or not self.selected_path:
            self.__show_message("No active location to save state for.")
            return
        try:
            memento = self._duplication_checker.create_memento()
            saved_path = self._save_manager.save_memento(memento)
            msg = f"Check state successfully saved to '{saved_path}'"
            self.lblInfo.setText(msg)
            self.__show_message(msg)
            self.LogEventEmitted.emit(msg)
            self._update_button_states()
        except Exception as err:
            m = f"Error saving state: {err}"
            print(m)
            self.__show_message(m)
            self.LogEventEmitted.emit(m)

    def evt_resume_duplication(self) -> None:
        if not self.selected_path or not self._duplication_checker:
            return

        if not self._save_manager.has_save(self.selected_path):
            self.__show_message("No saved state found for current location.")
            return

        memento = self._save_manager.load_memento(self.selected_path)
        if not memento:
            self.__show_message("Failed to load saved state.")
            return

        is_valid, reason = self._save_manager.verify_location(memento)
        if not is_valid:
            reply = QMessageBox.warning(
                self,
                "Location Verification Failed",
                f"The saved check state cannot be verified securely:\n\n{reason}\n\n"
                "Would you like to delete the invalid save and start checking from scratch?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_manager.delete_save(self.selected_path)
                self.evt_check_duplication()
            return

        try:
            self._duplication_checker.restore_memento(memento)
            self._update_button_states(is_running=True)
            msg = f"Resuming duplicate check from saved state ({len(memento.processed_files)}/{memento.files_count} checked)..."
            self.lblInfo.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._duplication_checker.start_analysis_thread(run_in_background=True)
        except Exception as err:
            m = f"Error resuming state: {err}"
            print(m)
            self.__show_message(m)
            self.LogEventEmitted.emit(m)
            self._update_button_states()

    def populate_duplications(self) -> None:
        self.files_hash = {}
        self.duplications = {}
        try:
            self.duplications = self._duplication_checker.duplicate_files
            self.files_hash = self._duplication_checker.files_hashes
            if self._save_manager and self.selected_path:
                self._save_manager.delete_save(self.selected_path)
            self.__populate_files()
        except Exception as err:
            m = f"Error occur: {err}"
            print(m)
            self.__show_message(m)
            self.LogEventEmitted.emit(m)
        finally:
            self._update_button_states()

    def __populate_files(self):
        original_files = list(self.duplications.keys())
        if len(original_files) > 0:
            model = QStringListModel(original_files)
            self.lst_original_files.setModel(model)
            self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)
            if len(self.duplications) > 0:
                duplicated_files_count = sum([len(item) for item in self.duplications.values()])
                files_with_duplicates_count = len(self.duplications)
                message = (f"Totally were found {files_with_duplicates_count} files with duplicates. " +
                           f"Total number of duplicate files are - {duplicated_files_count}")
                self.ItemSelected.emit(message)
                self.__show_message(message)
                self.LogEventEmitted.emit(message)
        else:
            message = "No duplication files found"
            self.__show_message(message)
            self.LogEventEmitted.emit(message)
        self._update_button_states()

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
            self.LogEventEmitted.emit(m)
        finally:
            self.pbAnalyze.setEnabled(True)

    def evt_original_file_selected(self, current, previous) -> None:
        selected_file = current.data()
        duplication_files = self.duplications.get(selected_file, [])
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
            self.LogEventEmitted.emit(m)

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
                        self.LogEventEmitted.emit(m)
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
            self.LogEventEmitted.emit(m)
        finally:
            message = f"Totally moved {count_moved} files to '{target_dir}'"
            self.ItemSelected.emit(message)
            self.__show_message(message)
            self.LogEventEmitted.emit(message)
            self.files_hash = {}
            self.duplications = {}
            self._update_button_states()

    def evt_show_context_menu(self, pos):
        index = self.lst_duplications.indexAt(pos)
        if index.isValid():  # Check if an item is selected
            item_text = self.lst_duplications.model().data(index, Qt.ItemDataRole.DisplayRole)
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

    def __switch_original_with_duplicate(self, original_file, duplicate_file) -> None:
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
            self.LogEventEmitted.emit(m)

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
            self.LogEventEmitted.emit(m)


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
