"""
Application settings management module for the Family Album application.

Stores persistent user configuration inside `<app_dir>/.settings/settings.json`.
On first launch (when no settings file exists), automatically detects logical CPU
cores and initializes `worker_threads` to `cpu_cores * 2` (clamped to a safe range)
and persists the configuration file to disk.
"""

import json
import os
import sys
from typing import Optional


def get_default_app_dir() -> str:
    """
    Determine the base application directory next to the executable or project root.

    When running as a frozen PyInstaller executable (`sys.frozen`), returns the
    directory containing the `.exe` file. When running from source, returns the
    repository root directory.

    Returns:
        str: Absolute path to the application root directory.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(this_dir, os.pardir, os.pardir))


class AppSettings:
    """
    Manages persistent application settings stored in `<app_dir>/.settings/settings.json`.

    Attributes:
        SETTINGS_FOLDER_NAME (str): Name of the settings subdirectory ('.settings').
        SETTINGS_FILE_NAME (str): Name of the JSON configuration file ('settings.json').
        DEFAULT_THREAD_MULTIPLIER (int): Multiplier applied to logical CPU cores (2).
        MIN_THREADS (int): Minimum selectable worker thread count (1).
        MAX_THREADS (int): Maximum selectable worker thread count (256).
    """

    SETTINGS_FOLDER_NAME = ".settings"
    SETTINGS_FILE_NAME = "settings.json"
    DEFAULT_THREAD_MULTIPLIER = 2
    MIN_THREADS = 1
    MAX_THREADS = 256

    _instance: Optional["AppSettings"] = None

    def __init__(self, app_dir: Optional[str] = None) -> None:
        """
        Initialize the AppSettings manager and load or create `.settings/settings.json`.

        Args:
            app_dir (Optional[str]): Custom application directory path (used in tests).
                Defaults to `get_default_app_dir()`.
        """
        self.app_dir = os.path.abspath(app_dir) if app_dir else get_default_app_dir()
        self.settings_dir = os.path.join(self.app_dir, self.SETTINGS_FOLDER_NAME)
        self.settings_path = os.path.join(self.settings_dir, self.SETTINGS_FILE_NAME)

        self._worker_threads: int = self.calculate_recommended_threads()
        self._last_selected_directory: str = ""

        self.load()

    @classmethod
    def instance(cls, app_dir: Optional[str] = None) -> "AppSettings":
        """
        Retrieve or create the shared singleton AppSettings instance.

        Args:
            app_dir (Optional[str]): Optional override directory for initialization.

        Returns:
            AppSettings: Singleton settings instance.
        """
        if cls._instance is None or (app_dir is not None and os.path.abspath(app_dir) != cls._instance.app_dir):
            cls._instance = cls(app_dir=app_dir)
        return cls._instance

    @staticmethod
    def get_cpu_count() -> int:
        """
        Return the number of logical CPU cores detected on the host machine.

        Returns:
            int: Logical CPU core count (at least 1).
        """
        return max(1, os.cpu_count() or 4)

    @classmethod
    def calculate_recommended_threads(cls, multiplier: int = DEFAULT_THREAD_MULTIPLIER) -> int:
        """
        Compute the default number of worker threads based on available CPU cores.

        Uses `logical_cores * multiplier` (by default `cores * 2`), clamped between
        `MIN_THREADS` and `MAX_THREADS`.

        Args:
            multiplier (int): Factor by which to multiply logical CPU cores. Defaults to 2.

        Returns:
            int: Recommended worker thread count.
        """
        cores = cls.get_cpu_count()
        recommended = cores * max(1, multiplier)
        return max(cls.MIN_THREADS, min(cls.MAX_THREADS, recommended))

    @property
    def worker_threads(self) -> int:
        """
        Configured number of parallel worker threads for analysis and file operations.

        Returns:
            int: Active worker thread count.
        """
        return self._worker_threads

    @worker_threads.setter
    def worker_threads(self, value: int) -> None:
        """
        Set the number of parallel worker threads (clamped to valid range).

        Args:
            value (int): Desired thread count.
        """
        clamped = max(self.MIN_THREADS, min(self.MAX_THREADS, int(value)))
        self._worker_threads = clamped

    @property
    def last_selected_directory(self) -> str:
        """
        Last directory path selected by the user in the main workspace.

        Returns:
            str: Normalized directory path, or empty string if unset.
        """
        return self._last_selected_directory

    @last_selected_directory.setter
    def last_selected_directory(self, path: str) -> None:
        """
        Update the last selected directory path.

        Args:
            path (str): Filesystem directory path.
        """
        self._last_selected_directory = os.path.normpath(path) if path else ""

    def to_dict(self) -> dict:
        """
        Serialize current settings to a JSON-compatible dictionary.

        Returns:
            dict: Dictionary containing current configuration parameters.
        """
        return {
            "worker_threads": self._worker_threads,
            "cpu_cores_detected": self.get_cpu_count(),
            "recommended_threads": self.calculate_recommended_threads(),
            "last_selected_directory": self._last_selected_directory,
        }

    def load(self) -> None:
        """
        Load settings from `.settings/settings.json` if it exists; otherwise create it
        with default calculated values.
        """
        os.makedirs(self.settings_dir, exist_ok=True)
        if os.path.isfile(self.settings_path):
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "worker_threads" in data:
                    self.worker_threads = int(data["worker_threads"])
                if "last_selected_directory" in data:
                    self.last_selected_directory = str(data["last_selected_directory"] or "")
                return
            except Exception:
                # If file is corrupted, regenerate defaults and save
                pass

        # First run or unreadable file: initialize defaults and persist immediately
        self._worker_threads = self.calculate_recommended_threads()
        self.save()

    def save(self) -> str:
        """
        Persist current settings to `<app_dir>/.settings/settings.json`.

        Returns:
            str: Path to the saved settings file.
        """
        os.makedirs(self.settings_dir, exist_ok=True)
        with open(self.settings_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return self.settings_path
