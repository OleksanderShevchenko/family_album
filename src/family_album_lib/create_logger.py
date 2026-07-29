from datetime import datetime
from enum import Enum
from logging import Logger, DEBUG, Formatter, FileHandler
import os
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal


class LogLevel(Enum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class LogEntry:
    """
    Represents a single log event with timestamp, text, log level, color, and emoji.
    Colors are chosen to be clear and readable in both Light and Dark OS desktop themes.
    """

    LEVEL_MAP = {
        LogLevel.DEBUG: {"emoji": "🔍", "color": "#95A5A6", "name": "DEBUG"},
        LogLevel.INFO: {"emoji": "🟢", "color": "#2ECC71", "name": "INFO"},
        LogLevel.WARNING: {"emoji": "⚠️", "color": "#E67E22", "name": "WARNING"},
        LogLevel.ERROR: {"emoji": "❌", "color": "#E74C3C", "name": "ERROR"},
        LogLevel.CRITICAL: {"emoji": "🚨", "color": "#E74C3C", "name": "CRITICAL"},
    }

    def __init__(self, text: str, level: LogLevel = LogLevel.INFO, timestamp: Optional[datetime] = None):
        self.text = text
        self.level = level
        self.timestamp = timestamp or datetime.now()
        meta = self.LEVEL_MAP.get(level, self.LEVEL_MAP[LogLevel.INFO])
        self.emoji = meta["emoji"]
        self.color = meta["color"]
        self.level_name = meta["name"]

    @property
    def formatted_timestamp(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    def to_html(self) -> str:
        escaped_text = (
            self.text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>")
        )
        return (
            f"<span style='color: {self.color}; font-family: monospace, Consolas, Courier, sans-serif; font-size: 12px;'>"
            f"<b>[{self.formatted_timestamp}] {self.emoji} [{self.level_name}]</b> {escaped_text}"
            f"</span>"
        )

    def to_file_string(self) -> str:
        return f"{self.formatted_timestamp} - {self.level_name} - {self.text}"

    def __str__(self) -> str:
        return self.to_file_string()


class LoggerSignalDispatcher(QObject):
    """Qt Signal dispatcher to safely emit log entries across threads to GUI components."""
    log_entry_emitted = pyqtSignal(object)


# Global signal dispatcher instance
logger_signals = LoggerSignalDispatcher()


class CustomLogger(Logger):

    def __init__(self, app_name: str, version: str, log_level: int = DEBUG) -> None:
        super().__init__(app_name, log_level)
        self.__app_name = app_name
        self.__version = version
        self.__log_level = log_level
        self.__log_file_path = ""
        self.__setup_logger()

    @property
    def log_file_path(self) -> str:
        return self.__log_file_path

    def __setup_logger(self) -> None:
        # Create 'logs' directory alongside the application
        app_dir = os.path.abspath(os.getcwd())
        log_dir = os.path.join(app_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

        # Unique session log filename: AppName_vVersion_YYYY-MM-DD_HH-MM-SS.log
        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_app_name = self.__app_name.replace(" ", "_")
        log_filename = f"{safe_app_name}_v{self.__version}_{timestamp_str}.log"
        self.__log_file_path = os.path.join(log_dir, log_filename)

        # File Handler (logs ALL levels including DEBUG)
        file_handler = FileHandler(self.__log_file_path, encoding='utf-8')
        file_handler.setLevel(self.__log_level)

        formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        self.addHandler(file_handler)

    def dispatch_entry(self, text: str, level: LogLevel) -> LogEntry:
        entry = LogEntry(text, level)
        # Log to file via logging.Logger base
        self.log(level.value, text)
        # Emit signal to GUI log console
        logger_signals.log_entry_emitted.emit(entry)
        return entry

    def log_debug(self, message: str) -> LogEntry:
        return self.dispatch_entry(message, LogLevel.DEBUG)

    def log_info(self, message: str) -> LogEntry:
        return self.dispatch_entry(message, LogLevel.INFO)

    def log_warning(self, message: str) -> LogEntry:
        return self.dispatch_entry(message, LogLevel.WARNING)

    def log_error(self, message: str) -> LogEntry:
        return self.dispatch_entry(message, LogLevel.ERROR)

    def log_critical(self, message: str) -> LogEntry:
        return self.dispatch_entry(message, LogLevel.CRITICAL)

    def log_event(self, message: str, level: Optional[LogLevel] = None) -> LogEntry:
        """Parses level from string content if level is omitted, ensuring backwards compatibility."""
        if level is None:
            msg_lower = message.lower()
            if 'error' in msg_lower or 'fail' in msg_lower or 'cannot' in msg_lower:
                level = LogLevel.ERROR
            elif 'warning' in msg_lower or 'warn' in msg_lower:
                level = LogLevel.WARNING
            elif 'debug' in msg_lower:
                level = LogLevel.DEBUG
            else:
                level = LogLevel.INFO
        return self.dispatch_entry(message, level)
