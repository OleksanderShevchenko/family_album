"""
Memento pattern implementation for the Media File Organizer.

Provides state persistence, pausing, resuming, and location verification for both
the analysis (scanning & plan generation) and execution (copying/moving files)
phases of the File Organizer.
"""

import hashlib
import json
import os
import time
from enum import Enum
from typing import Dict, Optional, Tuple


class OrganizerStatus(Enum):
    """
    Enum representing the current operational state of the File Organizer.
    """
    IDLE = "Idle"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"


class OrganizerMemento:
    """
    Memento pattern: Encapsulates and freezes the state of a media organization
    analysis or execution session for a specific source directory.

    Attributes:
        source_dir (str): Normalized source directory path.
        target_dir (str): Normalized target directory path.
        mode (str): Organization mode ('new_organization' or 'self_organization').
        action_type (str): Transfer action ('copy' or 'move').
        phase (str): Interrupted phase ('analyze' or 'organize').
        files_count (int): Total candidate files discovered in the source directory.
        plan_items (Dict[str, dict]): Mapping of normalized source `file_path` to serialized `OrganizePlanItem` dict.
        stats (dict): Serialized `OrganizeStats` counters accumulated so far.
        timestamp (float): Unix epoch timestamp when the memento was created.
    """

    def __init__(
        self,
        source_dir: str,
        target_dir: str,
        mode: str,
        action_type: str,
        phase: str,
        files_count: int,
        plan_items: Dict[str, dict],
        stats: Optional[dict] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """
        Initialize an OrganizerMemento instance.

        Args:
            source_dir (str): Source directory path.
            target_dir (str): Target directory path.
            mode (str): 'new_organization' or 'self_organization'.
            action_type (str): 'copy' or 'move'.
            phase (str): 'analyze' or 'organize'.
            files_count (int): Total candidate files count in source_dir.
            plan_items (Dict[str, dict]): Serialized plan items keyed by normalized file_path.
            stats (Optional[dict]): Serialized OrganizeStats dictionary.
            timestamp (Optional[float]): Creation timestamp.
        """
        self.source_dir = os.path.normpath(source_dir)
        self.target_dir = os.path.normpath(target_dir)
        self.mode = mode
        self.action_type = action_type
        self.phase = phase  # "analyze" or "organize"
        self.files_count = int(files_count)
        self.plan_items: Dict[str, dict] = {
            os.path.normpath(k): v for k, v in plan_items.items()
        }
        self.stats: dict = stats or {
            "total_scanned": len(self.plan_items),
            "total_processed": 0,
            "moved": 0,
            "copied": 0,
            "skipped": 0,
            "errors": 0,
            "total_bytes": 0,
            "details": [],
        }
        self.timestamp = timestamp if timestamp is not None else time.time()

    @property
    def analyzed_count(self) -> int:
        """Return number of files that have been analyzed and added to the plan."""
        return len(self.plan_items)

    @property
    def organized_count(self) -> int:
        """Return number of planned items already processed (organized or skipped)."""
        return sum(
            1
            for item in self.plan_items.values()
            if item.get("status") in ("organized", "skipped")
        )

    @property
    def pending_count(self) -> int:
        """Return number of planned items still waiting to be organized."""
        return sum(
            1
            for item in self.plan_items.values()
            if item.get("status", "pending") not in ("organized", "skipped")
        )

    def to_dict(self) -> dict:
        """
        Serialize the memento into a JSON-compatible dictionary.

        Returns:
            dict: Serialized state dictionary.
        """
        return {
            "source_dir": self.source_dir,
            "target_dir": self.target_dir,
            "mode": self.mode,
            "action_type": self.action_type,
            "phase": self.phase,
            "files_count": self.files_count,
            "plan_items": self.plan_items,
            "stats": self.stats,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrganizerMemento":
        """
        Reconstruct an OrganizerMemento from a dictionary.

        Args:
            data (dict): Deserialized JSON state dictionary.

        Returns:
            OrganizerMemento: Reconstructed memento object.
        """
        return cls(
            source_dir=data["source_dir"],
            target_dir=data["target_dir"],
            mode=data.get("mode", "new_organization"),
            action_type=data.get("action_type", "copy"),
            phase=data.get("phase", "analyze"),
            files_count=data.get("files_count", 0),
            plan_items=data.get("plan_items", {}),
            stats=data.get("stats"),
            timestamp=data.get("timestamp", 0.0),
        )


class OrganizerSaveManager:
    """
    Caretaker in the Memento pattern: Manages saving, loading, deleting, and
    verifying OrganizerMemento JSON files inside the `saves` directory.
    """

    def __init__(self, saves_dir: str = "saves") -> None:
        """
        Initialize the OrganizerSaveManager.

        Args:
            saves_dir (str): Directory path where memento JSON files are stored.
        """
        self.saves_dir = os.path.normpath(saves_dir)
        os.makedirs(self.saves_dir, exist_ok=True)

    def _get_save_filename(self, source_dir: str) -> str:
        """
        Generate a deterministic save filename from the normalized source directory path.

        Args:
            source_dir (str): Source directory path.

        Returns:
            str: Save filename in the format `organizer_save_<16_char_sha256>.json`.
        """
        norm_path = os.path.normpath(os.path.abspath(source_dir)).lower()
        path_hash = hashlib.sha256(norm_path.encode("utf-8")).hexdigest()[:16]
        return f"organizer_save_{path_hash}.json"

    def get_save_filepath(self, source_dir: str) -> str:
        """
        Compute the full path to the save file for a given source directory.

        Args:
            source_dir (str): Source directory path.

        Returns:
            str: Full path to the JSON save file.
        """
        return os.path.normpath(os.path.join(self.saves_dir, self._get_save_filename(source_dir)))

    def has_save(self, source_dir: str) -> bool:
        """
        Check whether a saved organizer state exists for the specified source directory.

        Args:
            source_dir (str): Source directory path.

        Returns:
            bool: True if a save file exists, False otherwise.
        """
        if not source_dir:
            return False
        return os.path.isfile(self.get_save_filepath(source_dir))

    def save_memento(self, memento: OrganizerMemento) -> str:
        """
        Persist an OrganizerMemento to disk as JSON.

        Args:
            memento (OrganizerMemento): Memento instance to save.

        Returns:
            str: Path to the written save file.
        """
        os.makedirs(self.saves_dir, exist_ok=True)
        save_file = self.get_save_filepath(memento.source_dir)
        with open(save_file, "w", encoding="utf-8") as f:
            json.dump(memento.to_dict(), f, indent=2, ensure_ascii=False)
        return save_file

    def load_memento(self, source_dir: str) -> Optional[OrganizerMemento]:
        """
        Load a saved OrganizerMemento for the given source directory.

        Args:
            source_dir (str): Source directory path.

        Returns:
            Optional[OrganizerMemento]: Loaded memento, or None if not found or invalid.
        """
        save_file = self.get_save_filepath(source_dir)
        if not os.path.isfile(save_file):
            return None
        try:
            with open(save_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return OrganizerMemento.from_dict(data)
        except Exception:
            return None

    def delete_save(self, source_dir: str) -> None:
        """
        Delete the saved memento file for the given source directory if it exists.

        Args:
            source_dir (str): Source directory path.
        """
        if not source_dir:
            return
        save_file = self.get_save_filepath(source_dir)
        if os.path.isfile(save_file):
            try:
                os.remove(save_file)
            except Exception:
                pass

    def verify_location(self, memento: OrganizerMemento) -> Tuple[bool, str]:
        """
        Verify that the source directory and remaining pending files in the memento
        are still valid on disk.

        Note: Files with status 'organized' or 'skipped' are not required to remain
        in `source_dir` because a paused 'move' operation legitimately transfers them
        out of `source_dir` into `target_dir`.

        Args:
            memento (OrganizerMemento): Memento to validate.

        Returns:
            Tuple[bool, str]: (is_valid, status_or_reason_message).
        """
        source_dir = os.path.normpath(memento.source_dir)
        if not os.path.isdir(source_dir):
            return False, f"Source directory '{source_dir}' no longer exists."

        missing_pending = []
        for fpath, item_dict in memento.plan_items.items():
            status = item_dict.get("status", "pending")
            if status == "pending" and not os.path.isfile(fpath):
                missing_pending.append(fpath)

        if missing_pending:
            return (
                False,
                f"{len(missing_pending)} pending file(s) from the saved state are missing from '{source_dir}'.",
            )

        return True, "Location integrity verified."
