import os
from threading import Thread, Event
from typing import Dict, List, Callable, Optional

from src.family_album_lib.duplicate_file_analyser import DuplicateFileAnalyser
from src.family_album_lib.duplication_memento import (
    DuplicationCheckStatus,
    DuplicationCheckMemento
)


class ResumableDuplicateAnalyser(DuplicateFileAnalyser):
    """
    Inherits from DuplicateFileAnalyser and adds Memento-based state saving,
    pausing, resuming, and location verification via hook methods (_should_skip_file and _is_stopped).
    Does NOT duplicate thread execution logic or property proxying.
    """

    _NUM_OPEN_FILES = 200

    def __init__(self,
                 directory: str,
                 start_analysis: Optional[Callable] = None,
                 update_analysis: Optional[Callable] = None,
                 log_event: Optional[Callable] = None,
                 finish_analysis: Optional[Callable] = None,
                 instantly_opened_files: int = 0) -> None:
        norm_dir = os.path.normpath(directory)
        if instantly_opened_files <= 0:
            instantly_opened_files = self._NUM_OPEN_FILES

        super().__init__(
            directory=directory,
            start_analysis=start_analysis,
            update_analysis=update_analysis,
            log_event=log_event,
            instantly_opened_files=instantly_opened_files
        )

        self._processed_files: Dict[str, str] = {}  # full_file_path -> hash_digest
        self._status: DuplicationCheckStatus = DuplicationCheckStatus.IDLE
        self._stop_event = Event()
        self._worker_thread: Optional[Thread] = None

        self.finish_analysis: Optional[Callable] = finish_analysis

    @property
    def processed_files(self) -> Dict[str, str]:
        return self._processed_files

    @property
    def status(self) -> DuplicationCheckStatus:
        return self._status

    def _should_skip_file(self, file_name: str) -> bool:
        """Hook method: skips files that were already processed in a previous/paused session."""
        return file_name in self._processed_files

    def _is_stopped(self) -> bool:
        """Hook method: returns True if stop/pause requested."""
        return self._stop_event.is_set()

    def _should_reset_hashes(self) -> bool:
        """Hook method: reset hashes only when starting a fresh check (processed_files is empty)."""
        return len(self._processed_files) == 0

    def reset(self) -> None:
        self.stop_analysis()
        self.directory = self.directory  # triggers base setter clearing hashes/analysed count
        self._processed_files = {}
        self._status = DuplicationCheckStatus.IDLE

    def create_memento(self) -> DuplicationCheckMemento:
        return DuplicationCheckMemento(
            directory=self.directory,
            files_count=self.files_count_in_directory,
            subdirectories_count=self.subdirectories_count_in_directory,
            processed_files={os.path.normpath(k): v for k, v in self._processed_files.items()},
            files_hashes={k: [os.path.normpath(f) for f in v] for k, v in self.files_hashes.items()}
        )

    def restore_memento(self, memento: DuplicationCheckMemento) -> None:
        self.stop_analysis()
        self.directory = os.path.normpath(memento.directory)
        self._processed_files = {os.path.normpath(k): v for k, v in memento.processed_files.items()}
        super()._files_analysed = len(self._processed_files)  # restore number of analyzed files
        # Restore hashes into base class files_hashes
        base_hashes = self.files_hashes
        base_hashes.clear()
        for k, v in memento.files_hashes.items():
            base_hashes[k] = [os.path.normpath(f) for f in v]

        total_files = self.files_count_in_directory
        if len(self._processed_files) >= total_files and total_files > 0:
            self._status = DuplicationCheckStatus.COMPLETED
        else:
            self._status = DuplicationCheckStatus.PAUSED

    def stop_analysis(self) -> None:
        if self._status == DuplicationCheckStatus.RUNNING:
            self._stop_event.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=2.0)
            self._status = DuplicationCheckStatus.PAUSED

    def start_analysis_thread(self, run_in_background: bool = True) -> None:
        self._stop_event.clear()
        if run_in_background:
            self._worker_thread = Thread(
                target=self._run_resumable_analysis,
                daemon=True
            )
            self._worker_thread.start()
        else:
            self._run_resumable_analysis()

    def _run_resumable_analysis(self) -> None:
        self._status = DuplicationCheckStatus.RUNNING
        # Execute base class multithreaded analysis which uses hooks _should_skip_file & _is_stopped
        super()._find_duplicate_files_multithreaded()

        # Build processed_files map from base files_hashes
        for h, paths in self.files_hashes.items():
            for p in paths:
                self._processed_files[os.path.normpath(p)] = h

        if self._stop_event.is_set():
            self._status = DuplicationCheckStatus.PAUSED
            if isinstance(self._log_event, Callable):
                self._log_event("Duplicate analysis paused by user.")
        else:
            self._status = DuplicationCheckStatus.COMPLETED
            if isinstance(self.finish_analysis, Callable):
                self.finish_analysis("Finish analysis.")
