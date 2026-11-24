import json
import os.path
import shutil
import sys
from typing import List, Optional

import cv2
from PyQt6 import QtWidgets, uic, QtGui, QtCore
from PyQt6.QtCore import pyqtSignal, QStringListModel, Qt, QItemSelectionModel
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QDialog, QMessageBox, QLabel, QMainWindow, QMenu,
    QListView, QPushButton
)

from src.family_album.gui.widgets.py_ui.duplication_checker_ui import Ui_Form
from src.family_album.utility_functions.image_utils import is_image_file
from src.family_album.utility_functions.video_utils import is_file_a_video
from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.resumable_duplicate_analyser import ResumableDuplicateAnalyser
from src.family_album_lib.resumable_duplicates_verifier import ResumableDuplicatesVerifier
from src.family_album_lib.duplication_memento import (
    DuplicationSaveManager,
    DuplicationCheckStatus,
    DuplicationStage,
)


class VideoPlayerWidget(QtWidgets.QWidget):
    """
    Robust OpenCV-based video preview widget. Decodes frames directly via OpenCV,
    bypassing Windows Direct3D11 / WMF codec hardware acceleration errors.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        self.display_label = QLabel(self)
        self.display_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.display_label.setMinimumSize(200, 150)
        self.display_label.setMaximumSize(512, 380)
        self.display_label.setText("<>")
        self._layout.addWidget(self.display_label)

        # Control buttons bar
        self.control_layout = QHBoxLayout()
        self.btn_play = QPushButton("Play", self)
        self.btn_pause = QPushButton("Pause", self)
        self.btn_stop = QPushButton("Stop", self)

        self.btn_play.clicked.connect(self.play)
        self.btn_pause.clicked.connect(self.pause)
        self.btn_stop.clicked.connect(self.stop)

        self.control_layout.addWidget(self.btn_play)
        self.control_layout.addWidget(self.btn_pause)
        self.control_layout.addWidget(self.btn_stop)
        self._layout.addLayout(self.control_layout)

        self._cap: Optional[cv2.VideoCapture] = None
        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._next_frame)
        self._is_paused = False
        self._file_path = ""

    def load_video(self, file_path: str) -> bool:
        self.stop()
        self._file_path = file_path
        self._cap = cv2.VideoCapture(file_path)
        if not self._cap.isOpened():
            self.display_label.setText("Error loading video")
            return False

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        interval = int(1000 / fps) if fps > 0 else 33
        self._timer.setInterval(interval)
        self._is_paused = False
        self._next_frame()
        self._timer.start()
        return True

    def _next_frame(self) -> None:
        if not self._cap or not self._cap.isOpened() or self._is_paused:
            return

        ret, frame = self._cap.read()
        if not ret:
            # Auto-loop video playback
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
            if not ret:
                self.stop()
                return

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_frame.shape
        bytes_per_line = ch * w
        q_img = QtGui.QImage(rgb_frame.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(q_img)

        mw = self.display_label.maximumWidth()
        mh = self.display_label.maximumHeight()
        pixmap = pixmap.scaled(mw, mh, Qt.AspectRatioMode.KeepAspectRatio)
        self.display_label.setPixmap(pixmap)

    def play(self) -> None:
        if self._cap and self._cap.isOpened():
            self._is_paused = False
            if not self._timer.isActive():
                self._timer.start()

    def pause(self) -> None:
        self._is_paused = True

    def stop(self) -> None:
        self._timer.stop()
        self._is_paused = False
        if self._cap:
            self._cap.release()
            self._cap = None
        self.display_label.clear()
        self.display_label.setText("<>")


class DuplicationChecker(QtWidgets.QWidget, Ui_Form):
    ItemSelected = pyqtSignal(str)
    AnalysisStarted = pyqtSignal(str)
    ProgressUpdated = pyqtSignal(int, int)
    AnalysisFinished = pyqtSignal(str)
    VerificationFinished = pyqtSignal(str)
    LogEventEmitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent: QMainWindow = parent
        self.setupUi(self)
        # uic.loadUi(path.dirname(__file__) + '/py_ui/duplication_checker_ui.ui', self)

        self._save_manager: DuplicationSaveManager = DuplicationSaveManager("saves")

        # Create control buttons for state management and Stage 2 verification
        self.pbStop = QtWidgets.QPushButton("Stop / Pause", parent=self)
        self.pbStop.setToolTip("Stop or pause the active duplicate check or verification process")
        self.pbStop.clicked.connect(self.evt_stop_duplication)

        self.pbSaveState = QtWidgets.QPushButton("Save State", parent=self)
        self.pbSaveState.setToolTip("Save current check or verification progress to 'saves' folder")
        self.pbSaveState.clicked.connect(self.evt_save_state)

        self.pbResume = QtWidgets.QPushButton("Resume Check", parent=self)
        self.pbResume.setToolTip("Resume duplicate check or verification from saved/paused state")
        self.pbResume.clicked.connect(self.evt_resume_duplication)

        self.pbVerifyDuplicates = QtWidgets.QPushButton("Verify Duplicates", parent=self)
        self.pbVerifyDuplicates.setToolTip(
            "Verify detected duplicate groups by comparing exact file sizes (Stage 2)"
        )
        self.pbVerifyDuplicates.clicked.connect(self.evt_verify_duplicates)

        # Insert control buttons into the layout
        self.horizontalLayout.insertWidget(2, self.pbStop)
        self.horizontalLayout.insertWidget(3, self.pbSaveState)
        self.horizontalLayout.insertWidget(4, self.pbResume)
        self.horizontalLayout.insertWidget(5, self.pbVerifyDuplicates)

        # Video player components using OpenCV frame renderer
        self._videoPlayerOriginal = VideoPlayerWidget(self)
        self.gridLayout.addWidget(self._videoPlayerOriginal, 3, 0, 1, 1)
        self._videoPlayerOriginal.setVisible(False)

        self._videoPlayerDuplicated = VideoPlayerWidget(self)
        self.gridLayout.addWidget(self._videoPlayerDuplicated, 3, 1, 1, 1)
        self._videoPlayerDuplicated.setVisible(False)

        # Connect thread-safe PyQt signals for GUI thread updates
        self.AnalysisStarted.connect(self._on_analysis_started)
        self.ProgressUpdated.connect(self._on_progress_updated)
        self.AnalysisFinished.connect(self._on_analysis_finished)
        self.VerificationFinished.connect(self._on_verification_finished)
        self.LogEventEmitted.connect(self._on_log_event)

        self._selected_path: str = ""
        self._max_workers: int = AppSettings.instance().worker_threads
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

        self._duplication_checker: Optional[ResumableDuplicateAnalyser] = None
        self._verifier: Optional[ResumableDuplicatesVerifier] = None
        self._active_stage: str = DuplicationStage.HASHING.value
        self._verification_completed: bool = False
        self._last_mismatched_files: List[dict] = []
        self._update_button_states()

    def clear_results(self) -> None:
        """Clears stored duplication hashes, verification state, result lists, and previews."""
        self.files_hash = {}
        self.duplications = {}
        self._verifier = None
        self._active_stage = DuplicationStage.HASHING.value
        self._verification_completed = False
        self._last_mismatched_files = []
        self.lst_original_files.setModel(QStringListModel([]))
        self.lst_duplications.setModel(QStringListModel([]))
        self.lblOriginalImage.clear()
        self.lblOriginalImage.setText("<>")
        self.lblOriginalImage.setVisible(True)
        self.lblDuplicatedImage.clear()
        self.lblDuplicatedImage.setText("<>")
        self.lblDuplicatedImage.setVisible(True)

        if hasattr(self, '_videoPlayerOriginal') and self._videoPlayerOriginal:
            self._videoPlayerOriginal.stop()
            self._videoPlayerOriginal.setVisible(False)

        if hasattr(self, '_videoPlayerDuplicated') and self._videoPlayerDuplicated:
            self._videoPlayerDuplicated.stop()
            self._videoPlayerDuplicated.setVisible(False)

    @property
    def max_workers(self) -> int:
        """Return configured number of worker threads for duplicate analysis and verification."""
        return self._max_workers

    @max_workers.setter
    def max_workers(self, value: int) -> None:
        """Update worker thread count and propagate to active analyser and verifier if present."""
        self._max_workers = max(1, int(value))
        if self._duplication_checker is not None:
            self._duplication_checker.num_of_threads = self._max_workers
        if self._verifier is not None:
            self._verifier.num_of_threads = self._max_workers

    @property
    def selected_path(self) -> str:
        return self._selected_path

    @selected_path.setter
    def selected_path(self, new_path: str) -> None:
        if self._verifier is not None:
            self._verifier.stop_verification()
        if self._duplication_checker is not None:
            self._duplication_checker.stop_analysis()
        self.clear_results()
        if os.path.isdir(new_path):
            norm_path = os.path.normpath(new_path)
            self._selected_path = norm_path
            self.lblFName.setText(norm_path)
            self._duplication_checker = ResumableDuplicateAnalyser(
                norm_path,
                self.AnalysisStarted.emit,
                self.ProgressUpdated.emit,
                self.LogEventEmitted.emit,
                self.AnalysisFinished.emit,
                instantly_opened_files=self._max_workers,
            )

            if self._save_manager.has_save(norm_path):
                memento = self._save_manager.load_memento(norm_path)
                if memento and memento.stage == DuplicationStage.VERIFYING.value:
                    verified_count = len(memento.verified_originals)
                    total_groups = memento.candidate_duplicate_groups_count
                    self.lblInfo.setText(
                        f"Saved verification state found for this directory "
                        f"({verified_count}/{total_groups} duplicate groups verified). "
                        f"Click 'Resume Check' to continue verification or 'Check for duplicate' to start fresh."
                    )
                else:
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

        self._update_button_states()

    def _get_active_status(self) -> DuplicationCheckStatus:
        """Return lifecycle status of whichever stage (hashing or verifying) is currently active."""
        if self._active_stage == DuplicationStage.VERIFYING.value and self._verifier is not None:
            return self._verifier.status
        if self._duplication_checker is not None:
            return self._duplication_checker.status
        return DuplicationCheckStatus.IDLE

    def _on_analysis_started(self, msg: str) -> None:
        if hasattr(self._parent, 'evt_start_analysis'):
            self._parent.evt_start_analysis(msg)

    def _on_progress_updated(self, finished: int, total: int) -> None:
        if self._active_stage == DuplicationStage.VERIFYING.value:
            # Update progress bar directly without invoking MainWindow.evt_finish_analysis
            # (which unconditionally calls populate_duplications for Stage 1).
            if self._parent is not None and hasattr(self._parent, 'progressBar'):
                progress = int(finished / total * 100) if total > 0 else 0
                if self._parent.progressBar.value() < progress <= self._parent.progressBar.maximum():
                    self._parent.progressBar.setValue(progress)
                    msg = f"Verified {finished} of {total} duplicate groups"
                    if hasattr(self._parent, 'statusBar'):
                        self._parent.statusBar().showMessage(
                            msg, getattr(self._parent, '_interval', 3000)
                        )
            return

        if hasattr(self._parent, 'evt_update_progress'):
            self._parent.evt_update_progress(finished, total)

    def _on_analysis_finished(self, msg: str) -> None:
        if self._active_stage != DuplicationStage.HASHING.value:
            return
        if hasattr(self._parent, 'evt_finish_analysis'):
            self._parent.evt_finish_analysis(msg)

    def _on_verification_finished(self, msg: str) -> None:
        """Finalize Stage 2 duplicate verification, update UI lists, and log verification report."""
        if self._parent is not None:
            if hasattr(self._parent, 'dir_viewer') and self._parent.dir_viewer:
                self._parent.dir_viewer.setEnabled(True)
            if hasattr(self._parent, 'progressBar'):
                self._parent.progressBar.setValue(0)
                self._parent.progressBar.setVisible(False)
                self._parent.progressBar.setTextVisible(False)
            if hasattr(self._parent, 'statusBar'):
                self._parent.statusBar().showMessage(
                    msg, getattr(self._parent, '_interval', 3000)
                )

        if self._verifier is not None:
            self.duplications = dict(self._verifier.verified_duplicates)
            if self._verifier.files_hashes:
                self.files_hash = dict(self._verifier.files_hashes)
            self._last_mismatched_files = list(self._verifier.mismatched_files)
            self._verification_completed = True

        if self._save_manager and self.selected_path:
            self._save_manager.delete_save(self.selected_path)

        self._populate_verified_results()
        self._update_button_states()

    def _on_log_event(self, msg: str) -> None:
        if hasattr(self._parent, 'log_event'):
            self._parent.log_event(msg)

    def _update_button_states(self, is_running: bool = False) -> None:
        has_path = bool(self.selected_path and os.path.isdir(self.selected_path))
        has_save = has_path and self._save_manager.has_save(self.selected_path)
        status = self._get_active_status()

        is_active = is_running or status == DuplicationCheckStatus.RUNNING
        if hasattr(self._parent, 'dir_viewer') and self._parent.dir_viewer:
            self._parent.dir_viewer.setEnabled(not is_active)

        if is_active:
            self.pbAnalyze.setEnabled(False)
            self.pbCheckDuplications.setEnabled(False)
            self.pbStop.setEnabled(True)
            self.pbSaveState.setEnabled(False)
            self.pbResume.setEnabled(False)
            self.pbVerifyDuplicates.setEnabled(False)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        elif status == DuplicationCheckStatus.PAUSED:
            self.pbAnalyze.setEnabled(has_path)
            self.pbCheckDuplications.setEnabled(has_path)
            self.pbStop.setEnabled(False)
            self.pbSaveState.setEnabled(True)
            self.pbResume.setEnabled(True)
            self.pbVerifyDuplicates.setEnabled(False)
            self.pbDumpDuplications.setEnabled(False)
            self.pbMove.setEnabled(False)
        else:  # IDLE or COMPLETED
            self.pbAnalyze.setEnabled(has_path)
            self.pbCheckDuplications.setEnabled(has_path)
            self.pbStop.setEnabled(False)
            self.pbSaveState.setEnabled(False)
            self.pbResume.setEnabled(has_save)
            has_dups = bool(self.duplications)
            self.pbVerifyDuplicates.setEnabled(has_dups)
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

        self.clear_results()
        self._active_stage = DuplicationStage.HASHING.value
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

    def evt_verify_duplicates(self) -> None:
        """Start Stage 2 multithreaded byte-size verification over detected duplicate groups."""
        if not self.selected_path or not self.duplications:
            self.__show_message("No duplicate groups available to verify.")
            return

        files_hashes = dict(self.files_hash)
        if not files_hashes and self._duplication_checker is not None:
            files_hashes = dict(self._duplication_checker.files_hashes)

        processed_files = (
            dict(self._duplication_checker.processed_files)
            if self._duplication_checker is not None
            else {p: h for h, paths in files_hashes.items() for p in paths}
        )
        files_count = (
            self._duplication_checker.files_count_in_directory
            if self._duplication_checker is not None
            else len(processed_files)
        )
        subdirs_count = (
            self._duplication_checker.subdirectories_count_in_directory
            if self._duplication_checker is not None
            else 0
        )

        self._active_stage = DuplicationStage.VERIFYING.value
        self._verification_completed = False
        self._last_mismatched_files = []

        self._verifier = ResumableDuplicatesVerifier(
            directory=self.selected_path,
            duplicate_files=self.duplications,
            files_hashes=files_hashes,
            processed_files=processed_files,
            files_count=files_count,
            subdirectories_count=subdirs_count,
            start_verification=self.AnalysisStarted.emit,
            update_progress=self.ProgressUpdated.emit,
            log_event=self.LogEventEmitted.emit,
            finish_verification=self.VerificationFinished.emit,
            max_workers=self._max_workers,
        )

        try:
            self._update_button_states(is_running=True)
            msg = f"Starting Stage 2 duplicate verification for {len(self.duplications)} group(s)..."
            self.lblInfo.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._verifier.start_verification_thread(run_in_background=True)
        except Exception as err:
            m = f"Error starting verification: {err}"
            print(m)
            self.__show_message(m)
            self.LogEventEmitted.emit(m)
            self._update_button_states(is_running=False)

    def evt_stop_duplication(self) -> None:
        if self._active_stage == DuplicationStage.VERIFYING.value and self._verifier is not None:
            self._verifier.stop_verification()
            msg = "Duplicate verification process was paused by user."
            self.lblInfo.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._update_button_states()
            return

        if self._duplication_checker:
            self._duplication_checker.stop_analysis()
            msg = "Duplicate check process was paused by user."
            self.lblInfo.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._update_button_states()

    def evt_save_state(self) -> None:
        if not self.selected_path:
            self.__show_message("No active location to save state for.")
            return

        if self._active_stage == DuplicationStage.VERIFYING.value and self._verifier is not None:
            try:
                memento = self._verifier.create_memento()
                saved_path = self._save_manager.save_memento(memento)
                msg = (
                    f"Verification state successfully saved to '{saved_path}' "
                    f"({len(memento.verified_originals)}/{memento.candidate_duplicate_groups_count} groups verified)"
                )
                self.lblInfo.setText(msg)
                self.__show_message(msg)
                self.LogEventEmitted.emit(msg)
                self._update_button_states()
            except Exception as err:
                m = f"Error saving verification state: {err}"
                print(m)
                self.__show_message(m)
                self.LogEventEmitted.emit(m)
            return

        if not self._duplication_checker:
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

        # Support resuming directly from an in-memory pause even before saving to disk
        if not self._save_manager.has_save(self.selected_path):
            if (
                self._active_stage == DuplicationStage.VERIFYING.value
                and self._verifier is not None
                and self._verifier.status == DuplicationCheckStatus.PAUSED
            ):
                self._update_button_states(is_running=True)
                msg = (
                    f"Resuming duplicate verification "
                    f"({self._verifier.verified_groups_count}/{self._verifier.total_groups_count} groups verified)..."
                )
                self.lblInfo.setText(msg)
                self.LogEventEmitted.emit(msg)
                self._verifier.start_verification_thread(run_in_background=True)
                return

            if self._duplication_checker.status == DuplicationCheckStatus.PAUSED:
                self._update_button_states(is_running=True)
                msg = (
                    f"Resuming duplicate check "
                    f"({len(self._duplication_checker.processed_files)}/{self._duplication_checker.files_count_in_directory} checked)..."
                )
                self.lblInfo.setText(msg)
                self.LogEventEmitted.emit(msg)
                self._duplication_checker.start_analysis_thread(run_in_background=True)
                return

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
            if memento.stage == DuplicationStage.VERIFYING.value:
                # Restore Stage 1 context so hashes, dump, move, and duplicate_directories stay intact
                self._duplication_checker.restore_memento(memento)
                self.files_hash = dict(memento.files_hashes)

                self._active_stage = DuplicationStage.VERIFYING.value
                self._verification_completed = False
                self._verifier = ResumableDuplicatesVerifier(
                    directory=self.selected_path,
                    start_verification=self.AnalysisStarted.emit,
                    update_progress=self.ProgressUpdated.emit,
                    log_event=self.LogEventEmitted.emit,
                    finish_verification=self.VerificationFinished.emit,
                    max_workers=self._max_workers,
                )
                self._verifier.restore_memento(memento)
                self._update_button_states(is_running=True)
                msg = (
                    f"Resuming duplicate verification from saved state "
                    f"({len(memento.verified_originals)}/{memento.candidate_duplicate_groups_count} groups verified)..."
                )
                self.lblInfo.setText(msg)
                self.LogEventEmitted.emit(msg)
                self._verifier.start_verification_thread(run_in_background=True)
            else:
                self._active_stage = DuplicationStage.HASHING.value
                self._verifier = None
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
        if self._active_stage == DuplicationStage.VERIFYING.value:
            return
        self.files_hash = {}
        self.duplications = {}
        self._verification_completed = False
        self._last_mismatched_files = []
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

    def _populate_verified_results(self) -> None:
        """Refresh UI list views and log detailed summary after Stage 2 verification completes."""
        original_files = list(self.duplications.keys())
        verified_groups = len(self.duplications)
        verified_dup_files = sum(len(v) for v in self.duplications.values())
        mismatched_count = len(self._last_mismatched_files)
        failed_count = len(self._verifier.failed_files) if self._verifier else 0
        total_checked_groups = self._verifier.total_groups_count if self._verifier else verified_groups

        self.lst_original_files.setModel(QStringListModel(original_files))
        self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)
        self.lst_duplications.setModel(QStringListModel([]))

        if original_files:
            summary_msg = (
                f"Verification complete ({total_checked_groups} groups checked): "
                f"{verified_groups} verified group(s) ({verified_dup_files} confirmed duplicates), "
                f"{mismatched_count} size mismatch(es) excluded."
            )
            self.ItemSelected.emit(summary_msg)
            self.lblInfo.setText(summary_msg)
        else:
            summary_msg = (
                f"Verification complete ({total_checked_groups} groups checked): "
                f"no confirmed duplicates remain ({mismatched_count} size mismatch(es) excluded)."
            )
            self.lblInfo.setText(summary_msg)

        self._log_verification_summary(
            total_checked_groups,
            verified_groups,
            verified_dup_files,
            mismatched_count,
            failed_count,
        )

    def _log_verification_summary(
        self,
        total_groups: int,
        verified_groups: int,
        verified_dup_files: int,
        mismatched_count: int,
        failed_count: int,
    ) -> None:
        """Emit a structured Stage 2 verification summary report to the log console."""
        lines = [
            "==================================================",
            "✅ DUPLICATE VERIFICATION SUMMARY REPORT (Stage 2)",
            "==================================================",
            f"📁 Target Location: {self.selected_path}",
            f"🔍 Candidate Groups Checked: {total_groups}",
            f"✅ Verified Duplicate Groups: {verified_groups} ({verified_dup_files} confirmed duplicate files)",
            f"⚠️ Size Mismatches Excluded (Potential Collisions): {mismatched_count}",
            f"❌ Unreadable Files: {failed_count}",
        ]
        if self._last_mismatched_files:
            lines.append("--------------------------------------------------")
            lines.append("⚠️ EXCLUDED MISMATCHED CANDIDATES:")
            for item in self._last_mismatched_files:
                lines.append(
                    f"   • Original: '{item['original']}' ({item['original_size']} bytes) "
                    f"vs Candidate: '{item['candidate']}' ({item['candidate_size']} bytes)"
                )
        lines.append("==================================================")
        self.LogEventEmitted.emit("\n".join(lines))

    def __populate_files(self):
        original_files = list(self.duplications.keys())
        total_files = self._duplication_checker.files_count_in_directory if self._duplication_checker else 0
        analysed_files = len(self._duplication_checker.processed_files) if self._duplication_checker else 0
        failed_count = len(self._duplication_checker.failed_files) if self._duplication_checker else 0
        dup_dirs = self._duplication_checker.duplicate_directories if self._duplication_checker else {}
        duplicated_files_count = sum([len(item) for item in self.duplications.values()])
        files_with_duplicates_count = len(self.duplications)

        if len(original_files) > 0:
            model = QStringListModel(original_files)
            self.lst_original_files.setModel(model)
            self.lst_original_files.selectionModel().currentChanged.connect(self.evt_original_file_selected)

            summary_msg = (
                f"Analysed {analysed_files}/{total_files} files (Ignored: {failed_count}). "
                f"Found {files_with_duplicates_count} duplicate groups ({duplicated_files_count} files)"
            )
            if dup_dirs:
                summary_msg += f" and {len(dup_dirs)} duplicate folder(s)."
            else:
                summary_msg += "."

            self.ItemSelected.emit(summary_msg)
            self.lblInfo.setText(summary_msg)
        else:
            message = f"No duplicate files found ({analysed_files}/{total_files} files checked, Ignored: {failed_count})."
            self.lblInfo.setText(message)

        # Log detailed summary report to log console and session log file
        self._log_detailed_summary(analysed_files, total_files, failed_count, files_with_duplicates_count, duplicated_files_count, dup_dirs)
        self._update_button_states()

    def _log_detailed_summary(self, analysed: int, total: int, failed: int, dup_groups: int, dup_files: int, dup_dirs: dict) -> None:
        lines = [
            "==================================================",
            "📊 DUPLICATE ANALYSIS SUMMARY REPORT",
            "==================================================",
            f"📁 Target Location: {self.selected_path}",
            f"📄 Processed Files: {analysed} / {total} total files",
            f"⚠️ Ignored/Unreadable Files: {failed}",
            f"🔍 Duplicate File Groups: {dup_groups} groups ({dup_files} total duplicate files)",
        ]
        if dup_dirs:
            lines.append("--------------------------------------------------")
            lines.append(f"📁 DUPLICATE DIRECTORIES FOUND ({len(dup_dirs)} folder groups):")
            for orig, info in dup_dirs.items():
                f_count = info['file_count']
                total_bytes = info.get('total_size', 0)
                if total_bytes >= 1024 * 1024:
                    size_str = f"{round(total_bytes / (1024 * 1024), 2)} MB"
                else:
                    size_str = f"{round(total_bytes / 1024, 2)} KB"
                for dup in info['duplicates']:
                    lines.append(
                        f"   • Duplicate Folder: '{dup}' is an EXACT DUPLICATE of '{orig}' "
                        f"({f_count} files, total size {size_str})"
                    )
        else:
            lines.append("📁 Duplicate Directories: None detected.")

        lines.append("==================================================")
        full_report = "\n".join(lines)
        self.LogEventEmitted.emit(full_report)

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
        if not selected_file:
            return
        duplication_files = self.duplications.get(selected_file, [])
        if selected_file in duplication_files:
            self.__show_message(f"Selected file {selected_file} is duplicated in list of its duplicates!")
        self.lst_duplications.setModel(QStringListModel(duplication_files))
        self.lst_duplications.selectionModel().currentChanged.connect(self.evt_duplicated_file_selected)

        # Reset duplicate preview when selecting new original file
        self.lblDuplicatedImage.clear()
        self.lblDuplicatedImage.setText("<>")
        self.lblDuplicatedImage.setVisible(True)
        if hasattr(self, '_videoPlayerDuplicated'):
            self._videoPlayerDuplicated.stop()
            self._videoPlayerDuplicated.setVisible(False)

        if is_image_file(selected_file):
            self.lblOriginalImage.setVisible(True)
            if hasattr(self, '_videoPlayerOriginal'):
                self._videoPlayerOriginal.stop()
                self._videoPlayerOriginal.setVisible(False)
            self.__show_image(self.lblOriginalImage, selected_file, True)
        elif is_file_a_video(selected_file):
            self.lblOriginalImage.setVisible(False)
            if hasattr(self, '_videoPlayerOriginal'):
                self._videoPlayerOriginal.setVisible(True)
                self._videoPlayerOriginal.load_video(selected_file)
            self.ItemSelected.emit(f"Selected video file: {selected_file}")
        else:
            self.lblOriginalImage.setVisible(True)
            if hasattr(self, '_videoPlayerOriginal'):
                self._videoPlayerOriginal.stop()
                self._videoPlayerOriginal.setVisible(False)
            self.lblOriginalImage.setText("<>")

    def evt_duplicated_file_selected(self, current, previous) -> None:
        selected_file = current.data()
        if not selected_file:
            return
        if is_image_file(selected_file):
            self.lblDuplicatedImage.setVisible(True)
            if hasattr(self, '_videoPlayerDuplicated'):
                self._videoPlayerDuplicated.stop()
                self._videoPlayerDuplicated.setVisible(False)
            self.__show_image(self.lblDuplicatedImage, selected_file)
        elif is_file_a_video(selected_file):
            self.lblDuplicatedImage.setVisible(False)
            if hasattr(self, '_videoPlayerDuplicated'):
                self._videoPlayerDuplicated.setVisible(True)
                self._videoPlayerDuplicated.load_video(selected_file)
        else:
            self.lblDuplicatedImage.setVisible(True)
            if hasattr(self, '_videoPlayerDuplicated'):
                self._videoPlayerDuplicated.stop()
                self._videoPlayerDuplicated.setVisible(False)
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
            self.clear_results()
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

            # Keep Stage 1 files_hash bucket ordering aligned so Stage 2 mementos reflect the chosen original
            for paths in self.files_hash.values():
                if original_file in paths and duplicate_file in paths:
                    paths.remove(duplicate_file)
                    paths.insert(0, duplicate_file)
                    break
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
