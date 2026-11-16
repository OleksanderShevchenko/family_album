"""
File Organizer GUI widget for the Family Album application.

This module provides the FileOrganizer widget, which integrates into the main application
interface to offer interactive photo and video archive organization:
- Folder browsing for source and target media repositories.
- Mode selection: New Organization (into `<source>_organized/`) or Self-Organization (in-place).
- Action selection: Copy (default for new organization) or Move (mandatory for self-organization).
- Pre-organization analysis and plan inspection in a responsive QTableView.
- Disk capacity validation before copy operations, prompting switch to Move if space is low.
- Asynchronous threaded execution via OrganizerWorker with live progress and status bars.
"""

import os
from typing import Optional, List

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QMessageBox, QFileDialog

from src.family_album.gui.widgets.py_ui.file_organizer_ui import Ui_Form
from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.organizer_db import OrganizerDatabase
from src.family_album_lib.file_organizer_engine import (
    FileOrganizerEngine,
    OrganizerWorker,
    OrganizePlanItem,
    OrganizeStats,
    check_disk_space,
)


class FileOrganizer(QtWidgets.QWidget, Ui_Form):
    """
    Main widget for configuring, previewing, and executing media file organization.

    Connects user interface controls to the backend FileOrganizerEngine and displays
    results in a multi-column table model with real-time progress indicators.

    Signals:
        ItemSelected (str): Emitted to notify parent/main window of current operation or status message.
        AnalysisStarted (str): Emitted when a background scan or batch job starts.
        ProgressUpdated (int, int): Emitted with (current, total) counts during processing.
        AnalysisFinished (str): Emitted upon completion of an analysis or organization run.
        LogEventEmitted (str): Emitted with diagnostic or audit log lines for the application log console.
    """
    ItemSelected = pyqtSignal(str)
    AnalysisStarted = pyqtSignal(str)
    ProgressUpdated = pyqtSignal(int, int)
    AnalysisFinished = pyqtSignal(str)
    LogEventEmitted = pyqtSignal(str)

    def __init__(self, parent=None):
        """
        Initialize the FileOrganizer widget.

        Args:
            parent (Optional[QtWidgets.QWidget]): Parent widget or MainWindow instance.
        """
        super().__init__(parent)
        self._parent = parent
        self.setupUi(self)

        self._selected_path: str = ""
        self._target_path: str = ""
        self._worker: Optional[OrganizerWorker] = None
        self._current_plan: List[OrganizePlanItem] = []
        self._max_workers: int = AppSettings.instance().worker_threads

        # Connect UI controls
        self.pb_browse_source.clicked.connect(self.evt_browse_source)
        self.pb_browse_target.clicked.connect(self.evt_browse_target)
        self.rb_mode_new.toggled.connect(self.evt_mode_changed)
        self.rb_mode_self.toggled.connect(self.evt_mode_changed)

        self.pb_analyze.clicked.connect(self.evt_analyze_selected)
        self.pb_organize.clicked.connect(self.evt_organize_files)
        self.pb_stop.clicked.connect(self.evt_stop_operation)

        # Initial UI states
        self.lbl_folder_selected.setText("<>")
        self.lbl_target_selected.setText("<>")
        self.lbl_info.setText("<>")
        self.lbl_db_status.setText("Database: Not initialized")
        self.progressBar.setVisible(False)
        self.pb_analyze.setEnabled(False)
        self.pb_organize.setEnabled(False)
        self.pb_stop.setEnabled(False)

        # Table configuration
        self.tbl_file_data.setSortingEnabled(True)
        self.tbl_file_data.horizontalHeader().setSectionsMovable(True)
        self.tbl_file_data.setModel(QStandardItemModel())

    @property
    def max_workers(self) -> int:
        """
        Configured number of parallel worker threads for organizer operations.

        Returns:
            int: Worker thread count.
        """
        return self._max_workers

    @max_workers.setter
    def max_workers(self, value: int) -> None:
        """
        Update the number of parallel worker threads.

        Args:
            value (int): New thread count (> 0).
        """
        self._max_workers = max(1, int(value))

    @property
    def selected_path(self) -> str:
        """
        Current source directory path chosen for organization.

        Returns:
            str: Normalized filesystem path to source directory, or empty string.
        """
        return self._selected_path

    @selected_path.setter
    def selected_path(self, new_path: str) -> None:
        """
        Set and configure a new source directory.

        Automatically inspects directory for existing `.db/album.db`, adjusts default
        destination and organization mode, enables action buttons, and resets table data.

        Args:
            new_path (str): Target directory path.
        """
        if new_path and os.path.isdir(new_path):
            norm_path = os.path.normpath(new_path)
            self._selected_path = norm_path
            self.lbl_folder_selected.setText(norm_path)
            self._detect_and_configure_target(norm_path)
            self.pb_analyze.setEnabled(True)
            self.pb_organize.setEnabled(True)
        else:
            self._selected_path = ""
            self._target_path = ""
            self.lbl_folder_selected.setText("<>")
            self.lbl_target_selected.setText("<>")
            self.lbl_info.setText("<>")
            self.lbl_db_status.setText("Database: Not initialized")
            self.pb_analyze.setEnabled(False)
            self.pb_organize.setEnabled(False)

        self._current_plan = []
        self.tbl_file_data.setModel(QStandardItemModel())

    @property
    def target_path(self) -> str:
        """
        Current destination directory where organized files will be placed.

        Returns:
            str: Normalized destination path.
        """
        return self._target_path

    @target_path.setter
    def target_path(self, new_target: str) -> None:
        """
        Update destination directory path and update UI label.

        Args:
            new_target (str): New destination path.
        """
        self._target_path = os.path.normpath(new_target) if new_target else ""
        self.lbl_target_selected.setText(self._target_path or "<>")

    def _detect_and_configure_target(self, source_path: str) -> None:
        """
        Inspect source path to detect existing organizer catalog (`.db/album.db`).

        If a database is found, automatically enables Self-Organization mode (Move only).
        Otherwise, selects New Organization targeting `<source>_organized/` (Copy by default).

        Args:
            source_path (str): Source directory to inspect.
        """
        has_db = OrganizerDatabase.has_database(source_path)
        if has_db:
            # Self-organization mode detected!
            self.rb_mode_self.setChecked(True)
            self.target_path = source_path
            self.lbl_db_status.setText("Database: Found (.db/album.db) - Self-organization active")
            self.lbl_db_status.setStyleSheet("color: #007700; font-weight: bold; font-size: 11px;")
            self.rb_action_copy.setEnabled(False)
            self.rb_action_move.setChecked(True)
            self.lbl_action_hint.setText("Self-organization reorganizes files in-place (Move only)")
        else:
            # New organization mode
            self.rb_mode_new.setChecked(True)
            default_target = FileOrganizerEngine.get_default_target_dir(source_path)
            self.target_path = default_target
            self.lbl_db_status.setText("Database: Will be created in target/.db/album.db")
            self.lbl_db_status.setStyleSheet("color: #555555; font-size: 11px;")
            self.rb_action_copy.setEnabled(True)
            self.rb_action_copy.setChecked(True)
            self.lbl_action_hint.setText("Checks disk space before copying")

    def evt_mode_changed(self) -> None:
        """
        Handle radio button toggle between 'New Organization' and 'Self-Organization' modes.

        Adjusts target directory, enables/disables target browsing and Copy radio button.
        """
        if not self._selected_path:
            return

        if self.rb_mode_self.isChecked():
            self.target_path = self._selected_path
            self.pb_browse_target.setEnabled(False)
            self.rb_action_copy.setEnabled(False)
            self.rb_action_move.setChecked(True)
            self.lbl_action_hint.setText("Self-organization reorganizes files in-place (Move only)")
        else:
            default_target = FileOrganizerEngine.get_default_target_dir(self._selected_path)
            self.target_path = default_target
            self.pb_browse_target.setEnabled(True)
            self.rb_action_copy.setEnabled(True)
            self.lbl_action_hint.setText("Checks disk space before copying")

    def evt_browse_source(self) -> None:
        """Open system directory picker to select source folder for organization."""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Source Directory to Organize",
            self._selected_path or os.getcwd()
        )
        if chosen and os.path.isdir(chosen):
            self.selected_path = chosen

    def evt_browse_target(self) -> None:
        """Open system directory picker to select target folder (new organization mode only)."""
        if self.rb_mode_self.isChecked():
            return
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Target Directory for Organized Files",
            self._target_path or os.getcwd()
        )
        if chosen:
            self.target_path = chosen

    def get_action_type(self) -> str:
        """
        Determine selected action type from UI controls.

        Returns:
            str: 'move' if move radio button is checked, otherwise 'copy'.
        """
        return "move" if self.rb_action_move.isChecked() else "copy"

    def get_mode(self) -> str:
        """
        Determine selected organization mode from UI controls.

        Returns:
            str: 'self_organization' if self-organization radio button is checked, else 'new_organization'.
        """
        return "self_organization" if self.rb_mode_self.isChecked() else "new_organization"

    def evt_analyze_selected(self) -> None:
        """
        Initiate background scanning and preview plan generation for the selected folder.

        Spawns an OrganizerWorker with operation='analyze' and binds progress/result signals.
        """
        if not self._selected_path or not os.path.isdir(self._selected_path):
            self.__show_warning("Please select a valid source directory first.")
            return

        self._set_running_state(True)
        self.lbl_info.setText("Analyzing files in directory...")
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

        mode = self.get_mode()
        action = self.get_action_type()

        self._worker = OrganizerWorker(
            source_dir=self._selected_path,
            target_dir=self._target_path,
            mode=mode,
            action_type=action,
            operation="analyze",
            max_workers=self._max_workers,
            parent=self
        )
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.plan_ready.connect(self._on_plan_ready)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.finished.connect(lambda _: self._set_running_state(False))
        self._worker.start()

    def _on_plan_ready(self, plan: List[OrganizePlanItem]) -> None:
        """
        Handle completion of background analysis and display the generated plan.

        Args:
            plan (List[OrganizePlanItem]): List of planned media items with detected dates and targets.
        """
        self._current_plan = plan
        self._populate_plan_table(plan)
        msg = f"Analysis complete: {len(plan)} files discovered and planned."
        self.lbl_info.setText(msg)
        self.ItemSelected.emit(msg)
        self.LogEventEmitted.emit(msg)
        self._set_running_state(False)

    def _populate_plan_table(self, plan: List[OrganizePlanItem]) -> None:
        """
        Populate the QTableView with columns describing planned organization actions.

        Columns:
        1. File Name (with full path tooltip)
        2. Date Detected (formatted YYYY-MM-DD HH:MM:SS or 'No Date')
        3. Date Source (Filename, EXIF Metadata, Video Metadata, or None)
        4. Target Folder (relative to target root)
        5. Size (formatted in KB)
        6. Type (Video, Image, or Other)
        7. Resolution (width x height)

        Args:
            plan (List[OrganizePlanItem]): Items to display.
        """
        headers = [
            "File Name",
            "Date Detected",
            "Date Source",
            "Target Folder (YYYY/MM)",
            "Size (KB)",
            "Type",
            "Resolution"
        ]
        model = QStandardItemModel(len(plan), len(headers))
        model.setHorizontalHeaderLabels(headers)

        for row_idx, item in enumerate(plan):
            item_name = QStandardItem(item.file_name)
            item_name.setToolTip(item.file_path)

            date_str = item.date_result.date.strftime("%Y-%m-%d %H:%M:%S") if item.date_result.date else "No Date"
            item_date = QStandardItem(date_str)

            # Date source label
            src_display = {
                "filename": "Filename (Name)",
                "exif": "EXIF Metadata",
                "video_metadata": "Video Metadata",
                "filesystem": "File System",
                "none": "None (No_Date)"
            }.get(item.date_result.source, item.date_result.source)
            item_source = QStandardItem(src_display)

            # Target relative folder
            target_rel = os.path.relpath(item.destination_dir, self._target_path) if self._target_path else item.destination_dir
            item_target = QStandardItem(target_rel)

            size_kb = f"{round(item.file_size / 1024, 1):,}"
            item_size = QStandardItem(size_kb)
            item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            type_str = "Video" if item.is_video else ("Image" if item.is_image else "Other")
            item_type = QStandardItem(type_str)

            item_res = QStandardItem(item.resolution or "-")

            model.setItem(row_idx, 0, item_name)
            model.setItem(row_idx, 1, item_date)
            model.setItem(row_idx, 2, item_source)
            model.setItem(row_idx, 3, item_target)
            model.setItem(row_idx, 4, item_size)
            model.setItem(row_idx, 5, item_type)
            model.setItem(row_idx, 6, item_res)

        self.tbl_file_data.setModel(model)
        self.tbl_file_data.resizeColumnsToContents()

    def evt_organize_files(self) -> None:
        """
        Validate preconditions and trigger background organization execution.

        Checks available disk capacity before copying. If disk space is insufficient,
        prompts the user with an interactive dialog offering to switch to Move action.
        """
        if not self._selected_path or not os.path.isdir(self._selected_path):
            self.__show_warning("Please select a valid source directory first.")
            return

        mode = self.get_mode()
        action = self.get_action_type()

        # Check disk space if copying
        if action == "copy" and mode == "new_organization":
            # Estimate size
            total_size = sum(item.file_size for item in self._current_plan) if self._current_plan else 0
            if total_size > 0:
                has_space, req, free = check_disk_space(self._target_path, total_size)
                if not has_space:
                    req_mb = round(req / (1024 * 1024), 1)
                    free_mb = round(free / (1024 * 1024), 1)
                    reply = QMessageBox.question(
                        self,
                        "Insufficient Disk Space for Copy",
                        f"There is not enough free space on the destination drive to copy files:\n\n"
                        f"• Required space: {req_mb} MB\n"
                        f"• Available space: {free_mb} MB\n\n"
                        f"Would you like to switch to Move (transfer files without keeping copies) instead?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        self.rb_action_move.setChecked(True)
                        action = "move"
                    else:
                        return

        # Start organization worker
        self._set_running_state(True)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

        self._worker = OrganizerWorker(
            source_dir=self._selected_path,
            target_dir=self._target_path,
            mode=mode,
            action_type=action,
            operation="organize",
            max_workers=self._max_workers,
            parent=self
        )
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.log_event.connect(self._on_log_event)
        self._worker.space_error.connect(self._on_space_error)
        self._worker.finished.connect(self._on_organize_finished)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.start()

    def evt_stop_operation(self) -> None:
        """Cooperatively stop any running background worker thread."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.lbl_info.setText("Stopping operation...")
            self.pb_stop.setEnabled(False)

    def _on_progress_updated(self, current: int, total: int) -> None:
        """
        Update progress bar and parent window progress indicators.

        Args:
            current (int): Number of items processed so far.
            total (int): Total number of items in scope.
        """
        pct = int(current / total * 100) if total > 0 else 0
        self.progressBar.setValue(pct)
        if hasattr(self._parent, 'evt_update_progress'):
            self._parent.evt_update_progress(current, total)

    def _on_status_message(self, msg: str) -> None:
        """
        Display status message in info label and emit status signal.

        Args:
            msg (str): Message to display.
        """
        self.lbl_info.setText(msg)
        self.ItemSelected.emit(msg)

    def _on_log_event(self, msg: str) -> None:
        """
        Relay log message to the log console and parent window.

        Args:
            msg (str): Formatted log event message.
        """
        self.LogEventEmitted.emit(msg)
        if hasattr(self._parent, 'log_event'):
            self._parent.log_event(msg)

    def _on_space_error(self, required: int, free: int) -> None:
        """
        Handle InsufficientDiskSpaceError emitted from the worker thread.

        Prompts the user to switch to Move action and retry immediately.

        Args:
            required (int): Bytes required for the operation.
            free (int): Free bytes currently available.
        """
        self._set_running_state(False)
        req_mb = round(required / (1024 * 1024), 1)
        free_mb = round(free / (1024 * 1024), 1)
        reply = QMessageBox.question(
            self,
            "Insufficient Disk Space",
            f"Not enough disk space to complete copying!\n\n"
            f"Required: {req_mb} MB, Available: {free_mb} MB\n\n"
            f"Would you like to execute organization by Moving files instead?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.rb_action_move.setChecked(True)
            self.evt_organize_files()

    def _on_organize_finished(self, stats: OrganizeStats) -> None:
        """
        Handle successful completion of an organization run.

        Displays summary dialog, updates database status indicator, and re-enables controls.

        Args:
            stats (OrganizeStats): Metrics and counters from the completed run.
        """
        self._set_running_state(False)
        self.progressBar.setValue(100)

        # Generate summary report
        summary = (
            f"Organization complete! Processed: {stats.total_processed}, "
            f"Organized: {stats.moved + stats.copied} (Moved: {stats.moved}, Copied: {stats.copied}), "
            f"Skipped: {stats.skipped}, Errors: {stats.errors}"
        )
        self.lbl_info.setText(summary)
        self.ItemSelected.emit(summary)
        self.LogEventEmitted.emit(summary)

        # Detailed summary dialog
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Organization Finished")
        msg_box.setText(summary)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()

        # Update database status label
        self._detect_and_configure_target(self._target_path)

    def _on_worker_error(self, err_msg: str) -> None:
        """
        Display error dialog upon background worker unhandled exception.

        Args:
            err_msg (str): Error message string.
        """
        self._set_running_state(False)
        self.__show_warning(f"Error during organization: {err_msg}")
        self.LogEventEmitted.emit(f"Error: {err_msg}")

    def _set_running_state(self, running: bool) -> None:
        """
        Toggle UI widget enabled/disabled states based on active execution.

        Args:
            running (bool): True if background task is active, False otherwise.
        """
        self.pb_analyze.setEnabled(not running)
        self.pb_organize.setEnabled(not running)
        self.pb_stop.setEnabled(running)
        self.pb_browse_source.setEnabled(not running)
        self.pb_browse_target.setEnabled(not running and not self.rb_mode_self.isChecked())
        self.gb_mode.setEnabled(not running)
        self.gb_action.setEnabled(not running and not self.rb_mode_self.isChecked())

    def __show_warning(self, message: str) -> None:
        """
        Display an informational modal warning dialog.

        Args:
            message (str): Text to show in the warning box.
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("File Organizer")
        msg.setText(message)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.exec()
