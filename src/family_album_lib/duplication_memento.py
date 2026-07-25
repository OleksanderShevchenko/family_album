import os
import json
import time
import hashlib
from enum import Enum
from typing import Dict, List, Optional, Tuple


class DuplicationCheckStatus(Enum):
    """
    Enum representing the current state of duplicate checking process.
    """
    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"


class DuplicationCheckMemento:
    """
    Memento pattern: Encapsulates and freezes the state of duplicate file checking
    for a location at a specific point in time.
    """

    def __init__(
        self,
        directory: str,
        files_count: int,
        subdirectories_count: int,
        processed_files: Dict[str, str],
        files_hashes: Dict[str, List[str]],
        timestamp: Optional[float] = None
    ) -> None:
        self.directory = os.path.normpath(directory)
        self.files_count = files_count
        self.subdirectories_count = subdirectories_count
        # Normalize all file paths to prevent slash mismatch (e.g. '/' vs '\')
        self.processed_files = {os.path.normpath(k): v for k, v in processed_files.items()}
        self.files_hashes = {k: [os.path.normpath(f) for f in v] for k, v in files_hashes.items()}
        self.timestamp = timestamp if timestamp is not None else time.time()

    def to_dict(self) -> dict:
        return {
            "directory": self.directory,
            "files_count": self.files_count,
            "subdirectories_count": self.subdirectories_count,
            "processed_files": self.processed_files,
            "files_hashes": self.files_hashes,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DuplicationCheckMemento":
        return cls(
            directory=data["directory"],
            files_count=data["files_count"],
            subdirectories_count=data["subdirectories_count"],
            processed_files=data.get("processed_files", {}),
            files_hashes=data.get("files_hashes", {}),
            timestamp=data.get("timestamp", 0.0)
        )


class DuplicationSaveManager:
    """
    Caretaker in the Memento pattern: Responsible for saving, loading, and verifying
    memento files stored in the 'saves' directory.
    """

    def __init__(self, saves_dir: str = "saves") -> None:
        self.saves_dir = os.path.normpath(saves_dir)
        os.makedirs(self.saves_dir, exist_ok=True)

    def _get_save_filename(self, directory: str) -> str:
        norm_path = os.path.normpath(directory).lower()
        path_hash = hashlib.sha256(norm_path.encode('utf-8')).hexdigest()[:16]
        return f"save_{path_hash}.json"

    def get_save_filepath(self, directory: str) -> str:
        return os.path.normpath(os.path.join(self.saves_dir, self._get_save_filename(directory)))

    def has_save(self, directory: str) -> bool:
        return os.path.isfile(self.get_save_filepath(directory))

    def save_memento(self, memento: DuplicationCheckMemento) -> str:
        save_file = self.get_save_filepath(memento.directory)
        with open(save_file, 'w', encoding='utf-8') as f:
            json.dump(memento.to_dict(), f, indent=2, ensure_ascii=False)
        return save_file

    def load_memento(self, directory: str) -> Optional[DuplicationCheckMemento]:
        save_file = self.get_save_filepath(directory)
        if not os.path.isfile(save_file):
            return None
        with open(save_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return DuplicationCheckMemento.from_dict(data)

    def delete_save(self, directory: str) -> None:
        save_file = self.get_save_filepath(directory)
        if os.path.isfile(save_file):
            try:
                os.remove(save_file)
            except Exception as e:
                print(f"Error removing save file {save_file}: {e}")

    def verify_location(self, memento: DuplicationCheckMemento) -> Tuple[bool, str]:
        target_dir = os.path.normpath(memento.directory)
        if not os.path.isdir(target_dir):
            return False, f"Target directory '{target_dir}' no longer exists."

        current_files_count = sum(len(files) for _, _, files in os.walk(target_dir))
        current_subdirs_count = sum(len(dirs) for _, dirs, _ in os.walk(target_dir))

        if current_files_count != memento.files_count:
            return False, (
                f"File count mismatch for '{target_dir}'. "
                f"Saved: {memento.files_count}, Current: {current_files_count}."
            )

        if current_subdirs_count != memento.subdirectories_count:
            return False, (
                f"Subdirectory count mismatch for '{target_dir}'. "
                f"Saved: {memento.subdirectories_count}, Current: {current_subdirs_count}."
            )

        missing_files = [f for f in memento.processed_files.keys() if not os.path.isfile(f)]
        if missing_files:
            return False, f"{len(missing_files)} previously checked files are missing from disk."

        return True, "Location integrity verified."
