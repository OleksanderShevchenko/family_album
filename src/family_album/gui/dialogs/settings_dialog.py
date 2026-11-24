"""
Settings Dialog for the Family Album application.

Allows the user to view and configure application-wide settings stored in
`<app_dir>/.settings/settings.json`, including:
- Number of parallel worker threads for duplicate analysis and media organization.
- Last selected workspace directory restored on application startup.
"""

import os
from typing import Optional

from PyQt6 import QtCore
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QDateEdit,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QSlider,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QWidget,
)

from src.family_album_lib.app_settings import AppSettings


class SettingsDialog(QDialog):
    """
    Modal configuration dialog accessible via `Tools -> Settings...`.

    Provides controls for adjusting parallel worker threads (with CPU core detection
    and recommended defaults) and inspecting/modifying the startup workspace directory.
    """

    def __init__(self, settings: Optional[AppSettings] = None, parent: Optional[QWidget] = None) -> None:
        """
        Initialize the SettingsDialog window.

        Args:
            settings (Optional[AppSettings]): Settings instance to view/edit.
                Defaults to `AppSettings.instance()`.
            parent (Optional[QWidget]): Parent widget or MainWindow.
        """
        super().__init__(parent)
        self._settings = settings or AppSettings.instance()

        self.setWindowTitle("Application Settings")
        self.setMinimumWidth(540)
        self.setModal(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # 1. Parallel Processing / Threading Group
        self.gb_threading = QGroupBox("Parallel Processing (Multithreading)", self)
        threading_layout = QVBoxLayout(self.gb_threading)
        threading_layout.setSpacing(8)

        cpu_cores = self._settings.get_cpu_count()
        recommended = self._settings.calculate_recommended_threads()

        self.lbl_cpu_info = QLabel(
            f"<b>Detected Logical CPU Cores:</b> {cpu_cores} &nbsp;|&nbsp; "
            f"<b>Recommended Threads:</b> {recommended} <i>({cpu_cores} cores × {AppSettings.DEFAULT_THREAD_MULTIPLIER})</i>",
            self.gb_threading,
        )
        self.lbl_cpu_info.setTextFormat(Qt.TextFormat.RichText)
        threading_layout.addWidget(self.lbl_cpu_info)

        controls_row = QHBoxLayout()
        lbl_threads = QLabel("Worker Threads:", self.gb_threading)
        controls_row.addWidget(lbl_threads)

        self.sb_worker_threads = QSpinBox(self.gb_threading)
        self.sb_worker_threads.setRange(AppSettings.MIN_THREADS, AppSettings.MAX_THREADS)
        self.sb_worker_threads.setValue(self._settings.worker_threads)
        self.sb_worker_threads.setFixedWidth(80)
        self.sb_worker_threads.setToolTip("Number of parallel threads used for hashing, scanning, and file organization")
        controls_row.addWidget(self.sb_worker_threads)

        self.sl_worker_threads = QSlider(Qt.Orientation.Horizontal, self.gb_threading)
        self.sl_worker_threads.setRange(AppSettings.MIN_THREADS, AppSettings.MAX_THREADS)
        self.sl_worker_threads.setValue(self._settings.worker_threads)
        controls_row.addWidget(self.sl_worker_threads, stretch=1)

        self.pb_reset_threads = QPushButton(f"Reset ({recommended})", self.gb_threading)
        self.pb_reset_threads.setToolTip("Reset worker thread count to recommended value (CPU cores × 2)")
        controls_row.addWidget(self.pb_reset_threads)

        threading_layout.addLayout(controls_row)

        lbl_thread_hint = QLabel(
            "Controls how many files are analyzed, hashed, or organized in parallel. "
            "Lower values reduce CPU/disk load on home laptops; higher values maximize SSD throughput.",
            self.gb_threading,
        )
        lbl_thread_hint.setWordWrap(True)
        lbl_thread_hint.setStyleSheet("color: #666666; font-size: 11px;")
        threading_layout.addWidget(lbl_thread_hint)

        main_layout.addWidget(self.gb_threading)

        # 2. Media Date Validation Group
        self.gb_date_validation = QGroupBox("Media Date Validation (File Organizer)", self)
        date_layout = QVBoxLayout(self.gb_date_validation)
        date_layout.setSpacing(8)

        date_row = QHBoxLayout()
        lbl_min_date = QLabel("Minimum Valid Date:", self.gb_date_validation)
        date_row.addWidget(lbl_min_date)

        self.de_min_valid_date = QDateEdit(self.gb_date_validation)
        self.de_min_valid_date.setCalendarPopup(True)
        self.de_min_valid_date.setDisplayFormat("yyyy-MM-dd")
        self.de_min_valid_date.setMinimumDate(QDate(1900, 1, 1))
        self.de_min_valid_date.setMaximumDate(QDate.currentDate())
        parsed_qdate = QDate.fromString(self._settings.min_valid_date, "yyyy-MM-dd")
        if not parsed_qdate.isValid():
            parsed_qdate = QDate.fromString(AppSettings.DEFAULT_MIN_VALID_DATE, "yyyy-MM-dd")
        self.de_min_valid_date.setDate(parsed_qdate)
        self.de_min_valid_date.setFixedWidth(130)
        self.de_min_valid_date.setToolTip(
            "Dates earlier than this threshold (e.g., 1970 or 1980 placeholder epochs) will be ignored"
        )
        date_row.addWidget(self.de_min_valid_date)

        self.pb_reset_min_date = QPushButton(
            f"Reset ({AppSettings.DEFAULT_MIN_VALID_DATE})",
            self.gb_date_validation,
        )
        self.pb_reset_min_date.setToolTip(
            f"Reset minimum valid date to default ({AppSettings.DEFAULT_MIN_VALID_DATE})"
        )
        date_row.addWidget(self.pb_reset_min_date)
        date_row.addStretch()

        date_layout.addLayout(date_row)

        lbl_date_hint = QLabel(
            "Rejects bogus placeholder dates (such as 1970-01-01 or 1980-01-01 from Google Photos "
            "animations/collages or ZIP archives) when determining the earliest capture date.",
            self.gb_date_validation,
        )
        lbl_date_hint.setWordWrap(True)
        lbl_date_hint.setStyleSheet("color: #666666; font-size: 11px;")
        date_layout.addWidget(lbl_date_hint)

        main_layout.addWidget(self.gb_date_validation)

        # 3. Startup & Workspace Directory Group
        self.gb_workspace = QGroupBox("Workspace & Session Persistence", self)
        workspace_layout = QVBoxLayout(self.gb_workspace)
        workspace_layout.setSpacing(8)

        lbl_dir = QLabel("Last Selected Directory (restored on startup):", self.gb_workspace)
        workspace_layout.addWidget(lbl_dir)

        dir_row = QHBoxLayout()
        self.le_last_directory = QLineEdit(self._settings.last_selected_directory, self.gb_workspace)
        self.le_last_directory.setPlaceholderText("No directory saved yet")
        dir_row.addWidget(self.le_last_directory, stretch=1)

        self.pb_browse_dir = QPushButton("Browse...", self.gb_workspace)
        self.pb_browse_dir.setFixedWidth(85)
        dir_row.addWidget(self.pb_browse_dir)

        self.pb_clear_dir = QPushButton("Clear", self.gb_workspace)
        self.pb_clear_dir.setFixedWidth(65)
        dir_row.addWidget(self.pb_clear_dir)

        workspace_layout.addLayout(dir_row)

        self.lbl_settings_file = QLabel(
            f"<b>Settings File:</b> <code>{self._settings.settings_path}</code>",
            self.gb_workspace,
        )
        self.lbl_settings_file.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_settings_file.setWordWrap(True)
        self.lbl_settings_file.setStyleSheet("color: #666666; font-size: 11px;")
        workspace_layout.addWidget(self.lbl_settings_file)

        main_layout.addWidget(self.gb_workspace)

        # 3. Dialog Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.pb_save = QPushButton("Save", self)
        self.pb_save.setFixedWidth(100)
        self.pb_save.setDefault(True)
        btn_layout.addWidget(self.pb_save)

        self.pb_cancel = QPushButton("Cancel", self)
        self.pb_cancel.setFixedWidth(100)
        btn_layout.addWidget(self.pb_cancel)

        main_layout.addLayout(btn_layout)

        # Connect signals
        self.sb_worker_threads.valueChanged.connect(self.sl_worker_threads.setValue)
        self.sl_worker_threads.valueChanged.connect(self.sb_worker_threads.setValue)
        self.pb_reset_threads.clicked.connect(lambda: self.sb_worker_threads.setValue(recommended))
        default_qdate = QDate.fromString(AppSettings.DEFAULT_MIN_VALID_DATE, "yyyy-MM-dd")
        self.pb_reset_min_date.clicked.connect(lambda: self.de_min_valid_date.setDate(default_qdate))
        self.pb_browse_dir.clicked.connect(self._evt_browse_dir)
        self.pb_clear_dir.clicked.connect(lambda: self.le_last_directory.setText(""))
        self.pb_save.clicked.connect(self._evt_save)
        self.pb_cancel.clicked.connect(self.reject)

    def _evt_browse_dir(self) -> None:
        """Open directory picker to select startup directory."""
        start_dir = self.le_last_directory.text().strip() or os.getcwd()
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Default / Startup Directory",
            start_dir if os.path.isdir(start_dir) else os.getcwd(),
        )
        if chosen and os.path.isdir(chosen):
            self.le_last_directory.setText(os.path.normpath(chosen))

    def _evt_save(self) -> None:
        """Apply changes to AppSettings, persist to disk, and close dialog."""
        self._settings.worker_threads = self.sb_worker_threads.value()
        self._settings.min_valid_date = self.de_min_valid_date.date().toString("yyyy-MM-dd")
        raw_dir = self.le_last_directory.text().strip()
        self._settings.last_selected_directory = raw_dir if raw_dir else ""
        self._settings.save()
        self.accept()
