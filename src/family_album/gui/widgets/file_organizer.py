"""
File Organizer GUI widget for the Family Album application.

This module provides the FileOrganizer widget, which integrates into the main application
interface to offer interactive photo and video archive organization:
- Folder browsing for source and target media repositories.
- Mode selection: New Organization (into `<source>_organized/`) or Self-Organization (in-place).
- Action selection: Copy (default for new organization) or Move (mandatory for self-organization).
- Pre-organization parallel analysis and plan inspection in a responsive QTableView.
- Disk capacity validation before copy operations, prompting switch to Move if space is low.
- Asynchronous multithreaded execution via OrganizerWorker with live progress and status bars.
- Memento-based state pausing, saving (`saves/organizer_save_*.json`), and resuming for
  both the analysis and organization phases.
"""

import os
from typing import Dict, Optional, List

from PyQt6 import QtWidgets
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QMessageBox, QFileDialog

from src.family_album.gui.widgets.py_ui.file_organizer_ui import Ui_Form
from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.organizer_db import OrganizerDatabase
from src.family_album_lib.organizer_memento import (
    OrganizerMemento,
    OrganizerSaveManager,
    OrganizerStatus,
)
from src.family_album_lib.file_organizer_engine import (
    FileOrganizerEngine,
    OrganizerWorker,
    OrganizePlanItem,
    OrganizeStats,
    check_disk_space,
)


class FileOrganizer(QtWidgets.QWidget, Ui_Form):
    """
    Main widget for configuring, previewing, pausing/resuming, and executing media
    file organization.

    Connects user interface controls to the multithreaded FileOrganizerEngine and
    OrganizerSaveManager (Memento pattern), displaying results in a multi-column
    table model with real-time progress indicators.

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

    def __init__(self, parent=None, saves_dir: str = "saves"):
        """
        Initialize the FileOrganizer widget.

        Args:
            parent (Optional[QtWidgets.QWidget]): Parent widget or MainWindow instance.
            saves_dir (str): Directory where Memento state JSON files are stored.
        """
        super().__init__(parent)
        self._parent = parent
        self.setupUi(self)

        self._selected_path: str = ""
        self._target_path: str = ""
        self._worker: Optional[OrganizerWorker] = None
        self._current_plan: List[OrganizePlanItem] = []
        self._plan_context: Optional[tuple] = None  # (source_dir, target_dir, mode)
        self._max_workers: int = AppSettings.instance().worker_threads

        # Memento state tracking
        self._save_manager: OrganizerSaveManager = OrganizerSaveManager(saves_dir)
        self._status: OrganizerStatus = OrganizerStatus.IDLE
        self._paused_phase: str = ""  # "analyze" or "organize"
        self._total_discovered_files: int = 0
        self._accumulated_stats: OrganizeStats = OrganizeStats()

        # Enhance button bar with Memento Save State & Resume buttons (mirrors DuplicationChecker)
        self.pb_stop.setText("Stop / Pause")
        self.pb_stop.setToolTip("Pause the active analysis or organization process")

        self.pb_save_state = QtWidgets.QPushButton("Save State", parent=self)
        self.pb_save_state.setToolTip("Save paused analysis or organization progress to disk")
        self.pb_save_state.setEnabled(False)
        self.pb_save_state.clicked.connect(self.evt_save_state)

        self.pb_resume = QtWidgets.QPushButton("Resume", parent=self)
        self.pb_resume.setToolTip("Resume paused or previously saved analysis / organization")
        self.pb_resume.setEnabled(False)
        self.pb_resume.clicked.connect(self.evt_resume_operation)

        # Insert Save State & Resume right after pb_stop (index 3 and 4, before the spacer)
        self.horizontalLayout_buttons.insertWidget(3, self.pb_save_state)
        self.horizontalLayout_buttons.insertWidget(4, self.pb_resume)

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

        # Table configuration
        self.tbl_file_data.setSortingEnabled(True)
        self.tbl_file_data.horizontalHeader().setSectionsMovable(True)
        self.tbl_file_data.setModel(QStandardItemModel())

        self._update_button_states(is_running=False)

    @property
    def status(self) -> OrganizerStatus:
        """Current operational status of the organizer widget."""
        return self._status

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

        Automatically inspects directory for existing `.db/album.db` and any saved
        Memento state, adjusts default destination and organization mode, updates
        action buttons, and resets table data.

        Args:
            new_path (str): Target directory path.
        """
        self._current_plan = []
        self._plan_context = None
        self._status = OrganizerStatus.IDLE
        self._paused_phase = ""
        self._total_discovered_files = 0
        self._accumulated_stats = OrganizeStats()
        self.tbl_file_data.setModel(QStandardItemModel())

        if new_path and os.path.isdir(new_path):
            norm_path = os.path.normpath(new_path)
            self._selected_path = norm_path
            self.lbl_folder_selected.setText(norm_path)
            self._detect_and_configure_target(norm_path)

            if self._save_manager.has_save(norm_path):
                memento = self._save_manager.load_memento(norm_path)
                if memento:
                    if memento.phase == "organize":
                        self.lbl_info.setText(
                            f"Saved organization state found ({memento.organized_count}/{memento.files_count} files done). "
                            f"Click 'Resume' to continue from checkpoint."
                        )
                    else:
                        self.lbl_info.setText(
                            f"Saved analysis state found ({memento.analyzed_count}/{memento.files_count} files analyzed). "
                            f"Click 'Resume' to continue from checkpoint."
                        )
            else:
                self.lbl_info.setText("<>")
        else:
            self._selected_path = ""
            self._target_path = ""
            self.lbl_folder_selected.setText("<>")
            self.lbl_target_selected.setText("<>")
            self.lbl_info.setText("<>")
            self.lbl_db_status.setText("Database: Not initialized")

        self._update_button_states(is_running=False)

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
            self.rb_mode_self.setChecked(True)
            self.target_path = source_path
            self.lbl_db_status.setText("Database: Found (.db/album.db) - Self-organization active")
            self.lbl_db_status.setStyleSheet("color: #007700; font-weight: bold; font-size: 11px;")
            self.rb_action_copy.setEnabled(False)
            self.rb_action_move.setChecked(True)
            self.lbl_action_hint.setText("Self-organization reorganizes files in-place (Move only)")
        else:
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

    def create_memento(self) -> OrganizerMemento:
        """
        Freeze the current paused/in-progress organizer state into an OrganizerMemento.

        Returns:
            OrganizerMemento: Snapshot containing plan items, phase, mode, action, and stats.
        """
        plan_map: Dict[str, dict] = {
            os.path.normpath(item.file_path): item.to_dict()
            for item in self._current_plan
        }
        phase = self._paused_phase or "analyze"
        total_files = max(self._total_discovered_files, len(self._current_plan))
        return OrganizerMemento(
            source_dir=self._selected_path,
            target_dir=self._target_path,
            mode=self.get_mode(),
            action_type=self.get_action_type(),
            phase=phase,
            files_count=total_files,
            plan_items=plan_map,
            stats=self._accumulated_stats.to_dict(),
        )

    def restore_memento(self, memento: OrganizerMemento) -> None:
        """
        Restore widget state, UI mode/action selectors, plan items, and stats from a memento.

        Args:
            memento (OrganizerMemento): Loaded memento snapshot.
        """
        self._selected_path = os.path.normpath(memento.source_dir)
        self.lbl_folder_selected.setText(self._selected_path)

        if memento.mode == "self_organization":
            self.rb_mode_self.setChecked(True)
        else:
            self.rb_mode_new.setChecked(True)

        self.target_path = memento.target_dir

        if memento.action_type == "move":
            self.rb_action_move.setChecked(True)
        else:
            self.rb_action_copy.setChecked(True)

        self._current_plan = [
            OrganizePlanItem.from_dict(item_dict)
            for item_dict in memento.plan_items.values()
        ]
        self._plan_context = (self._selected_path, self._target_path, memento.mode)
        self._paused_phase = memento.phase
        self._total_discovered_files = max(memento.files_count, len(self._current_plan))
        self._accumulated_stats = OrganizeStats.from_dict(memento.stats)
        self._status = OrganizerStatus.PAUSED

        self._populate_plan_table(self._current_plan)
        self._update_button_states(is_running=False)

    def _prompt_saved_state_if_exists(self) -> Optional[str]:
        """
        Check whether a saved Memento exists for the current directory and prompt the user.

        Returns:
            Optional[str]: 'resume' to resume saved state, 'fresh' to start fresh (after deleting save),
                'cancel' to abort, or None if no saved state exists.
        """
        if not self._selected_path or not self._save_manager.has_save(self._selected_path):
            return None

        reply = QMessageBox.question(
            self,
            "Saved Organizer State Detected",
            "A saved organizer checkpoint exists for this directory.\n\n"
            "Would you like to resume from the saved checkpoint?\n"
            "Choose 'Yes' to resume, 'No' to start fresh, or 'Cancel'.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            return "resume"
        if reply == QMessageBox.StandardButton.Cancel:
            return "cancel"
        self._save_manager.delete_save(self._selected_path)
        return "fresh"

    def evt_analyze_selected(self) -> None:
        """
        Initiate background parallel scanning and preview plan generation for the selected folder.

        Prompts to resume if a saved checkpoint exists for the selected directory.
        """
        if not self._selected_path or not os.path.isdir(self._selected_path):
            self.__show_warning("Please select a valid source directory first.")
            return

        choice = self._prompt_saved_state_if_exists()
        if choice == "resume":
            self.evt_resume_operation()
            return
        if choice == "cancel":
            return

        self._paused_phase = ""
        self._accumulated_stats = OrganizeStats()
        self._start_analyze_worker(existing_items=None)

    def _start_analyze_worker(self, existing_items: Optional[Dict[str, OrganizePlanItem]]) -> None:
        """Launch OrganizerWorker in 'analyze' mode, optionally resuming from `existing_items`."""
        self._status = OrganizerStatus.RUNNING
        self._update_button_states(is_running=True)
        self.lbl_info.setText(
            "Resuming analysis from checkpoint..." if existing_items else "Analyzing files in directory..."
        )
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
            existing_items=existing_items,
            parent=self,
        )
        self._worker.analysis_started.connect(self._on_status_message)
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.plan_ready.connect(self._on_plan_ready)
        self._worker.paused.connect(self._on_worker_paused)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.start()

    def _on_plan_ready(self, plan: List[OrganizePlanItem]) -> None:
        """
        Handle completion of background analysis and display the generated plan.

        Args:
            plan (List[OrganizePlanItem]): List of planned media items with detected dates and targets.
        """
        self._current_plan = plan
        self._total_discovered_files = len(plan)
        self._plan_context = (self._selected_path, self._target_path, self.get_mode())
        self._status = OrganizerStatus.COMPLETED
        self._paused_phase = ""

        # Clean up any analyze-phase save file now that full plan is complete
        if self._selected_path and self._save_manager.has_save(self._selected_path):
            saved = self._save_manager.load_memento(self._selected_path)
            if saved and saved.phase == "analyze":
                self._save_manager.delete_save(self._selected_path)

        self._populate_plan_table(plan)
        msg = f"Analysis complete: {len(plan)} files discovered and planned ({self._max_workers} threads)."
        self.lbl_info.setText(msg)
        self.ItemSelected.emit(msg)
        self.LogEventEmitted.emit(msg)
        self._update_button_states(is_running=False)

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

        src_labels = {
            "filename": "Filename (Name)",
            "exif": "EXIF Metadata",
            "video_metadata": "Video Metadata",
            "filesystem": "File System",
            "none": "None (No_Date)",
        }

        for row_idx, item in enumerate(plan):
            item_name = QStandardItem(item.file_name)
            item_name.setToolTip(item.file_path)

            date_str = item.date_result.date.strftime("%Y-%m-%d %H:%M:%S") if item.date_result.date else "No Date"
            item_date = QStandardItem(date_str)

            src_display = src_labels.get(item.date_result.source, item.date_result.source)
            item_source = QStandardItem(src_display)

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

        self.tbl_file_data.setSortingEnabled(False)
        self.tbl_file_data.setModel(model)
        if len(plan) <= 500:
            self.tbl_file_data.resizeColumnsToContents()
        else:
            default_widths = (240, 145, 130, 140, 90, 70, 100)
            for col_idx, width in enumerate(default_widths):
                self.tbl_file_data.setColumnWidth(col_idx, width)
        self.tbl_file_data.setSortingEnabled(True)

    def _get_reusable_plan(self, mode: str) -> Optional[List[OrganizePlanItem]]:
        """
        Return the cached preview plan if it matches the active source, target, and mode
        and still contains pending items.

        Args:
            mode (str): Active organization mode.

        Returns:
            Optional[List[OrganizePlanItem]]: Reusable plan list, or None if a fresh scan is required.
        """
        current_ctx = (self._selected_path, self._target_path, mode)
        if self._current_plan and self._plan_context == current_ctx:
            if any(item.status not in ("organized", "skipped") for item in self._current_plan):
                return self._current_plan
        return None

    def evt_organize_files(self) -> None:
        """
        Validate preconditions and trigger parallel background organization execution.

        Prompts to resume if a saved checkpoint exists. Reuses an already-analyzed
        preview plan when available, and checks available disk capacity before copying.
        """
        if not self._selected_path or not os.path.isdir(self._selected_path):
            self.__show_warning("Please select a valid source directory first.")
            return

        choice = self._prompt_saved_state_if_exists()
        if choice == "resume":
            self.evt_resume_operation()
            return
        if choice == "cancel":
            return

        mode = self.get_mode()
        reusable_plan = self._get_reusable_plan(mode)
        self._start_organize_worker(existing_plan=reusable_plan, initial_stats=None)

    def _start_organize_worker(
        self,
        existing_plan: Optional[List[OrganizePlanItem]],
        initial_stats: Optional[OrganizeStats],
    ) -> None:
        """Validate disk space (for Copy) and launch OrganizerWorker in 'organize' mode."""
        mode = self.get_mode()
        action = self.get_action_type()

        # Check disk space if copying
        if action == "copy" and mode == "new_organization":
            pending_bytes = (
                sum(item.file_size for item in existing_plan if item.status not in ("organized", "skipped"))
                if existing_plan
                else 0
            )
            if pending_bytes > 0:
                has_space, req, free = check_disk_space(self._target_path, pending_bytes)
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

        self._status = OrganizerStatus.RUNNING
        self._update_button_states(is_running=True)
        self.progressBar.setValue(0)
        self.progressBar.setVisible(True)

        self._worker = OrganizerWorker(
            source_dir=self._selected_path,
            target_dir=self._target_path,
            mode=mode,
            action_type=action,
            operation="organize",
            max_workers=self._max_workers,
            existing_plan=existing_plan,
            initial_stats=initial_stats,
            parent=self,
        )
        self._worker.analysis_started.connect(self._on_status_message)
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.status_message.connect(self._on_status_message)
        self._worker.log_event.connect(self._on_log_event)
        self._worker.space_error.connect(self._on_space_error)
        self._worker.paused.connect(self._on_worker_paused)
        self._worker.finished.connect(self._on_organize_finished)
        self._worker.error_occurred.connect(self._on_worker_error)
        self._worker.start()

    def evt_stop_operation(self) -> None:
        """Cooperatively pause any running background worker thread, preserving progress."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.lbl_info.setText("Pausing operation...")
            self.pb_stop.setEnabled(False)

    def _on_worker_paused(
        self,
        phase: str,
        plan: List[OrganizePlanItem],
        stats: OrganizeStats,
        total_files: int,
    ) -> None:
        """
        Handle cooperative pause emitted by OrganizerWorker.

        Freezes partial plan and stats in memory, updates the preview table, and
        enables 'Save State' and 'Resume' controls.

        Args:
            phase (str): Interrupted phase ('analyze' or 'organize').
            plan (List[OrganizePlanItem]): Plan items collected/updated up to the pause point.
            stats (OrganizeStats): Partial execution statistics accumulated so far.
            total_files (int): Total candidate files discovered in the source directory.
        """
        self._status = OrganizerStatus.PAUSED
        self._paused_phase = phase
        self._current_plan = plan
        self._plan_context = (self._selected_path, self._target_path, self.get_mode())
        self._accumulated_stats = stats
        self._total_discovered_files = max(total_files, len(plan))

        self._populate_plan_table(plan)

        if phase == "organize":
            done_count = sum(1 for item in plan if item.status in ("organized", "skipped"))
            msg = (
                f"Organization paused ({done_count}/{self._total_discovered_files} files done). "
                f"Click 'Save State' to persist checkpoint or 'Resume' to continue."
            )
        else:
            msg = (
                f"Analysis paused ({len(plan)}/{self._total_discovered_files} files analyzed). "
                f"Click 'Save State' to persist checkpoint or 'Resume' to continue."
            )

        self.lbl_info.setText(msg)
        self.ItemSelected.emit(msg)
        self.LogEventEmitted.emit(msg)
        self._update_button_states(is_running=False)

    def evt_save_state(self) -> None:
        """Save the current paused analysis or organization state via OrganizerSaveManager."""
        if not self._selected_path or self._status != OrganizerStatus.PAUSED:
            self.__show_warning("No paused operation to save state for.")
            return
        try:
            memento = self.create_memento()
            saved_path = self._save_manager.save_memento(memento)
            msg = f"Organizer state ({memento.phase}) successfully saved to '{saved_path}'."
            self.lbl_info.setText(msg)
            self.ItemSelected.emit(msg)
            self.LogEventEmitted.emit(msg)
            self._update_button_states(is_running=False)
        except Exception as err:
            err_msg = f"Error saving organizer state: {err}"
            self.__show_warning(err_msg)
            self.LogEventEmitted.emit(err_msg)

    def evt_resume_operation(self) -> None:
        """
        Resume a paused or saved analysis / organization operation from its exact checkpoint.

        If a saved file exists on disk and the widget is not currently holding an in-memory
        paused state, loads the memento and validates location integrity via `verify_location()`.
        """
        if not self._selected_path or not os.path.isdir(self._selected_path):
            self.__show_warning("Please select a valid source directory first.")
            return

        # Load from disk if not already paused in memory
        if self._status != OrganizerStatus.PAUSED:
            if not self._save_manager.has_save(self._selected_path):
                self.__show_warning("No saved organizer state found for the current directory.")
                return

            memento = self._save_manager.load_memento(self._selected_path)
            if not memento:
                self.__show_warning("Failed to load saved organizer state.")
                return

            is_valid, reason = self._save_manager.verify_location(memento)
            if not is_valid:
                reply = QMessageBox.warning(
                    self,
                    "Location Verification Failed",
                    f"The saved organizer state cannot be verified:\n\n{reason}\n\n"
                    "Would you like to delete the invalid save and start fresh?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._save_manager.delete_save(self._selected_path)
                    self._update_button_states(is_running=False)
                return

            self.restore_memento(memento)

        phase = self._paused_phase or "analyze"
        if phase == "organize":
            done_count = sum(1 for item in self._current_plan if item.status in ("organized", "skipped"))
            msg = f"Resuming organization from checkpoint ({done_count}/{len(self._current_plan)} files done)..."
            self.lbl_info.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._start_organize_worker(
                existing_plan=self._current_plan,
                initial_stats=self._accumulated_stats,
            )
        else:
            existing_map = {
                os.path.normpath(item.file_path): item
                for item in self._current_plan
            }
            msg = f"Resuming analysis from checkpoint ({len(existing_map)}/{self._total_discovered_files} files analyzed)..."
            self.lbl_info.setText(msg)
            self.LogEventEmitted.emit(msg)
            self._start_analyze_worker(existing_items=existing_map)

    def _on_progress_updated(self, current: int, total: int) -> None:
        """
        Update the widget progress bar and status label without flooding logs.

        Args:
            current (int): Number of items processed so far.
            total (int): Total number of items in scope.
        """
        pct = int(current / total * 100) if total > 0 else 0
        self.progressBar.setValue(pct)
        self.lbl_info.setText(f"Processing {current:,} / {total:,} files ({pct}%)...")

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
        Relay log message to the application log console via signal.

        Args:
            msg (str): Formatted log event message.
        """
        self.LogEventEmitted.emit(msg)

    def _on_space_error(self, required: int, free: int) -> None:
        """
        Handle InsufficientDiskSpaceError emitted from the worker thread.

        Prompts the user to switch to Move action and retry immediately.

        Args:
            required (int): Bytes required for the operation.
            free (int): Free bytes currently available.
        """
        self._status = OrganizerStatus.IDLE
        self._update_button_states(is_running=False)
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

        Deletes any saved checkpoint, displays summary dialog, updates database
        status indicator, and re-enables controls.

        Args:
            stats (OrganizeStats): Metrics and counters from the completed run.
        """
        self._status = OrganizerStatus.COMPLETED
        self._paused_phase = ""
        self._plan_context = None
        self._accumulated_stats = stats

        # Clean up saved Memento file after successful completion
        if self._selected_path:
            self._save_manager.delete_save(self._selected_path)

        self._update_button_states(is_running=False)
        self.progressBar.setValue(100)

        summary = (
            f"Organization complete! Processed: {stats.total_processed}, "
            f"Organized: {stats.moved + stats.copied} (Moved: {stats.moved}, Copied: {stats.copied}), "
            f"Skipped: {stats.skipped}, Errors: {stats.errors}"
        )
        self.lbl_info.setText(summary)
        self.ItemSelected.emit(summary)
        self.LogEventEmitted.emit(summary)

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Organization Finished")
        msg_box.setText(summary)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.exec()

        self._detect_and_configure_target(self._target_path)

    def _on_worker_error(self, err_msg: str) -> None:
        """
        Display error dialog upon background worker unhandled exception.

        Args:
            err_msg (str): Error message string.
        """
        self._status = OrganizerStatus.IDLE
        self._update_button_states(is_running=False)
        self.__show_warning(f"Error during organization: {err_msg}")
        self.LogEventEmitted.emit(f"Error: {err_msg}")

    def _update_button_states(self, is_running: bool = False) -> None:
        """
        Toggle UI widget enabled/disabled states based on active status and saved state.

        Args:
            is_running (bool): True if background task is currently active, False otherwise.
        """
        has_path = bool(self._selected_path and os.path.isdir(self._selected_path))
        has_save = has_path and self._save_manager.has_save(self._selected_path)
        active = is_running or self._status == OrganizerStatus.RUNNING
        is_paused = (not active) and (self._status == OrganizerStatus.PAUSED)

        if hasattr(self._parent, "dir_viewer") and self._parent.dir_viewer:
            self._parent.dir_viewer.setEnabled(not active)

        self.pb_analyze.setEnabled(has_path and not active)
        self.pb_organize.setEnabled(has_path and not active)
        self.pb_stop.setEnabled(active)
        self.pb_save_state.setEnabled(has_path and is_paused)
        self.pb_resume.setEnabled(has_path and not active and (is_paused or has_save))

        self.pb_browse_source.setEnabled(not active)
        self.pb_browse_target.setEnabled(not active and not self.rb_mode_self.isChecked())
        self.gb_mode.setEnabled(not active)
        self.gb_action.setEnabled(not active and not self.rb_mode_self.isChecked())

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
