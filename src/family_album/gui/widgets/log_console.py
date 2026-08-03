from typing import Optional

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtGui import QTextCursor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QFrame
)

from src.family_album_lib.create_logger import LogEntry, LogLevel, logger_signals


class LogConsoleWidget(QWidget):
    """
    Console log widget containing a QPlainTextEdit inside a collapsible container.
    Displays formatted LogEntry records (INFO, WARNING, ERROR, CRITICAL) with colors
    and emojis, while filtering out DEBUG messages (which go exclusively to log file).
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("LogConsoleWidget")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(2)

        # Header bar
        self.header_frame = QFrame(self)
        self.header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(6, 4, 6, 4)
        self.header_layout.setSpacing(8)

        self.lbl_title = QLabel("📋 <b>Application Console Logs</b>", self.header_frame)
        self.lbl_title.setTextFormat(Qt.TextFormat.RichText)
        self.header_layout.addWidget(self.lbl_title)

        self.lbl_info = QLabel(
            "<span style='color: #7F8C8D; font-size: 11px;'>"
            "(Console: INFO, WARNING, ERROR | File: ALL incl. DEBUG)"
            "</span>",
            self.header_frame
        )
        self.lbl_info.setTextFormat(Qt.TextFormat.RichText)
        self.header_layout.addWidget(self.lbl_info)

        self.header_layout.addStretch()

        self.btn_clear = QPushButton("🗑️ Clear Console", self.header_frame)
        self.btn_clear.setToolTip("Clear all entries from console view")
        self.btn_clear.clicked.connect(self.clear_console)
        self.header_layout.addWidget(self.btn_clear)

        self.btn_toggle = QPushButton("▼ Toggle Console", self.header_frame)
        self.btn_toggle.setToolTip("Expand or collapse console log area")
        self.btn_toggle.clicked.connect(self.toggle_console)
        self.header_layout.addWidget(self.btn_toggle)

        self._layout.addWidget(self.header_frame)

        # QPlainTextEdit log console
        self.console_edit = QPlainTextEdit(self)
        self.console_edit.setReadOnly(True)
        self.console_edit.setMaximumBlockCount(1000)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.console_edit.setFont(font)
        self._layout.addWidget(self.console_edit)

        # Connect global logger signal dispatcher
        logger_signals.log_entry_emitted.connect(self.append_log_entry)

    @pyqtSlot(object)
    def append_log_entry(self, entry: LogEntry) -> None:
        """Appends LogEntry to QPlainTextEdit if level >= INFO (skips DEBUG)."""
        if not isinstance(entry, LogEntry):
            return

        # Do NOT log DEBUG messages in GUI console
        if entry.level == LogLevel.DEBUG:
            return

        self.console_edit.appendHtml(entry.to_html())
        self.console_edit.moveCursor(QTextCursor.MoveOperation.End)

    def clear_console(self) -> None:
        self.console_edit.clear()

    def toggle_console(self) -> None:
        parent_splitter = self.parentWidget()
        if isinstance(parent_splitter, QtWidgets.QSplitter):
            sizes = parent_splitter.sizes()
            if len(sizes) == 2:
                if sizes[1] > 30:
                    parent_splitter.setSizes([sizes[0] + sizes[1], 0])
                    self.btn_toggle.setText("▲ Expand Console")
                else:
                    parent_splitter.setSizes([sizes[0] - 150, 150])
                    self.btn_toggle.setText("▼ Collapse Console")
        else:
            is_visible = self.console_edit.isVisible()
            self.console_edit.setVisible(not is_visible)
            self.btn_toggle.setText("▲ Expand Console" if is_visible else "▼ Collapse Console")
