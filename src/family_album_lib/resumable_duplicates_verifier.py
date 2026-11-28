"""
Stage 2 Duplicate Verification engine with multithreading and Memento-based pause/resume.

Verifies ONLY candidate duplicate groups detected during Stage 1 (Blake2b hashing)
by comparing exact file byte sizes (`os.path.getsize`) between each original file and
its candidate duplicates. Any candidate whose byte size differs from the original is
flagged as a potential hash collision, excluded from the verified duplicates mapping,
and logged as a warning.

Supports pausing, saving state (including full Stage 1 results) to disk via
`DuplicationCheckMemento(stage="verifying")`, and resuming even after restarting the
application on another day.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event, Lock, Thread
from typing import Callable, Dict, List, Optional, Tuple

from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.duplication_memento import (
    DuplicationCheckMemento,
    DuplicationCheckStatus,
    DuplicationStage,
)


class ResumableDuplicatesVerifier:
    """
    Multithreaded, pausable, and resumable Stage 2 duplicate verifier.

    Modeled after `ResumableDuplicateAnalyser`, this class verifies only the
    duplicate file groups produced by Stage 1 hashing by comparing exact file sizes
    on disk (`os.path.getsize`). It preserves complete Stage 1 results inside its
    memento so that saving and resuming across sessions never loses Stage 1 hash data.
    """

    def __init__(
        self,
        directory: str,
        duplicate_files: Optional[Dict[str, List[str]]] = None,
        files_hashes: Optional[Dict[str, List[str]]] = None,
        processed_files: Optional[Dict[str, str]] = None,
        files_count: int = 0,
        subdirectories_count: int = 0,
        start_verification: Optional[Callable[[str], None]] = None,
        update_progress: Optional[Callable[[int, int], None]] = None,
        log_event: Optional[Callable[[str], None]] = None,
        finish_verification: Optional[Callable[[str], None]] = None,
        max_workers: int = 0,
    ) -> None:
        """
        Initialize the Stage 2 duplicate verifier.

        Args:
            directory: Root directory being checked.
            duplicate_files: Mapping `{original_path: [candidate_dup_paths]}` from Stage 1.
            files_hashes: Complete Stage 1 `{hash_digest: [file_paths]}` mapping to preserve in mementos.
            processed_files: Complete Stage 1 `{file_path: hash_digest}` mapping to preserve in mementos.
            files_count: Total file count in `directory` from Stage 1 (used for location verification).
            subdirectories_count: Total subdirectory count in `directory` from Stage 1.
            start_verification: Optional callback invoked when verification starts `(msg: str)`.
            update_progress: Optional callback invoked after each group `(verified_count: int, total_groups: int)`.
            log_event: Optional callback for logging warnings and status events `(msg: str)`.
            finish_verification: Optional callback invoked when verification completes `(msg: str)`.
            max_workers: Number of worker threads; defaults to `AppSettings.instance().worker_threads` if <= 0.
        """
        self._directory: str = os.path.normpath(directory) if directory else ""
        if max_workers <= 0:
            max_workers = AppSettings.instance().worker_threads
        self._num_of_threads: int = max(1, int(max_workers))

        # Normalize Stage 1 results to preserve across save/resume cycles
        self._files_hashes: Dict[str, List[str]] = self._normalize_hash_paths(files_hashes)

        if processed_files:
            self._processed_files: Dict[str, str] = {
                os.path.normpath(p): h for p, h in processed_files.items()
            }
        else:
            self._processed_files = {
                p: h for h, paths in self._files_hashes.items() for p in paths
            }
        self._files_count: int = int(files_count)
        self._subdirectories_count: int = int(subdirectories_count)

        # Candidate duplicate groups to verify
        if duplicate_files is not None:
            self._candidate_duplicates: Dict[str, List[str]] = {
                os.path.normpath(orig): [os.path.normpath(d) for d in dups]
                for orig, dups in duplicate_files.items()
                if dups
            }
        else:
            self._candidate_duplicates = self._build_candidates_from_hashes(self._files_hashes)

        # Stage 2 verification state
        self._verified_originals: List[str] = []
        self._verified_originals_set: set = set()
        self._verified_duplicates: Dict[str, List[str]] = {}
        self._mismatched_files: List[dict] = []
        self._failed_files: List[Tuple[str, str]] = []

        # Callbacks
        self._start_verification: Optional[Callable[[str], None]] = start_verification
        self._update_progress: Optional[Callable[[int, int], None]] = update_progress
        self._log_event: Optional[Callable[[str], None]] = log_event
        self._finish_verification: Optional[Callable[[str], None]] = finish_verification

        # Threading & lifecycle
        self._status: DuplicationCheckStatus = DuplicationCheckStatus.IDLE
        self._stop_event: Event = Event()
        self._lock: Lock = Lock()
        self._worker_thread: Optional[Thread] = None

    @staticmethod
    def _normalize_hash_paths(files_hashes: dict[str, list[str]] | None) -> dict[str, list[str]]:
        """Normalize all file paths in a Stage 1 `{hash_digest: [file_paths]}` mapping."""
        return {
            h: [os.path.normpath(p) for p in paths]
            for h, paths in (files_hashes or {}).items()
        }

    @staticmethod
    def _build_candidates_from_hashes(files_hashes: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Derive `{original_path: [candidate_dup_paths]}` mapping from Stage 1 `files_hashes`."""
        candidates: Dict[str, List[str]] = {}
        for paths in files_hashes.values():
            if len(paths) > 1:
                candidates[os.path.normpath(paths[0])] = [os.path.normpath(p) for p in paths[1:]]
        return candidates

    @property
    def directory(self) -> str:
        """Return normalized target directory path."""
        return self._directory

    @property
    def num_of_threads(self) -> int:
        """Return configured worker thread count."""
        return self._num_of_threads

    @num_of_threads.setter
    def num_of_threads(self, value: int) -> None:
        """Set worker thread count (must be a positive integer)."""
        if not isinstance(value, int) or value <= 0:
            raise ValueError("The number of threads must be a positive integer!")
        self._num_of_threads = value

    @property
    def status(self) -> DuplicationCheckStatus:
        """Return current verification lifecycle status."""
        return self._status

    @property
    def candidate_duplicates(self) -> Dict[str, List[str]]:
        """Return candidate duplicate groups from Stage 1."""
        return dict(self._candidate_duplicates)

    @property
    def verified_duplicates(self) -> Dict[str, List[str]]:
        """Return duplicate groups confirmed to have matching exact file sizes."""
        return dict(self._verified_duplicates)

    @property
    def verified_originals(self) -> List[str]:
        """Return list of original file paths whose duplicate groups have been verified."""
        return list(self._verified_originals)

    @property
    def mismatched_files(self) -> List[dict]:
        """Return list of candidate duplicates rejected due to file size mismatch."""
        return list(self._mismatched_files)

    @property
    def failed_files(self) -> List[Tuple[str, str]]:
        """Return list of `(file_path, error_message)` pairs that failed OS size lookup."""
        return list(self._failed_files)

    @property
    def total_groups_count(self) -> int:
        """Return total number of candidate duplicate groups to verify."""
        return len(self._candidate_duplicates)

    @property
    def verified_groups_count(self) -> int:
        """Return number of candidate duplicate groups verified so far."""
        return len(self._verified_originals)

    @property
    def files_hashes(self) -> Dict[str, List[str]]:
        """Return preserved Stage 1 `files_hashes` mapping."""
        return self._files_hashes

    @property
    def processed_files(self) -> Dict[str, str]:
        """Return preserved Stage 1 `processed_files` mapping."""
        return self._processed_files

    @property
    def files_count(self) -> int:
        """Return preserved Stage 1 total file count."""
        return self._files_count

    @property
    def subdirectories_count(self) -> int:
        """Return preserved Stage 1 total subdirectory count."""
        return self._subdirectories_count

    def reset(self) -> None:
        """Reset Stage 2 verification progress while keeping Stage 1 candidate data intact."""
        self.stop_verification()
        with self._lock:
            self._verified_originals = []
            self._verified_originals_set = set()
            self._verified_duplicates = {}
            self._mismatched_files = []
            self._failed_files = []
        self._status = DuplicationCheckStatus.IDLE

    def create_memento(self) -> DuplicationCheckMemento:
        """
        Capture current Stage 2 verification state AND full Stage 1 results into a memento.

        Returns:
            DuplicationCheckMemento with `stage == "verifying"`.
        """
        with self._lock:
            return DuplicationCheckMemento(
                directory=self._directory,
                files_count=self._files_count,
                subdirectories_count=self._subdirectories_count,
                processed_files=dict(self._processed_files),
                files_hashes={h: list(paths) for h, paths in self._files_hashes.items()},
                stage=DuplicationStage.VERIFYING.value,
                verified_originals=list(self._verified_originals),
                verified_duplicates={orig: list(dups) for orig, dups in self._verified_duplicates.items()},
                mismatched_files=list(self._mismatched_files),
            )

    def restore_memento(self, memento: DuplicationCheckMemento) -> None:
        """
        Restore both Stage 1 context and Stage 2 verification progress from a memento.

        Args:
            memento: Previously saved `DuplicationCheckMemento` (typically `stage == "verifying"`).
        """
        self.stop_verification()
        with self._lock:
            self._directory = os.path.normpath(memento.directory)
            self._files_count = memento.files_count
            self._subdirectories_count = memento.subdirectories_count
            self._processed_files = {os.path.normpath(k): v for k, v in memento.processed_files.items()}
            self._files_hashes = self._normalize_hash_paths(memento.files_hashes)
            if self._files_hashes:
                self._candidate_duplicates = self._build_candidates_from_hashes(self._files_hashes)

            self._verified_originals = [os.path.normpath(p) for p in memento.verified_originals]
            self._verified_originals_set = set(self._verified_originals)
            self._verified_duplicates = {
                os.path.normpath(orig): [os.path.normpath(d) for d in dups]
                for orig, dups in memento.verified_duplicates.items()
            }
            self._mismatched_files = list(memento.mismatched_files)
            self._failed_files = []

            total_groups = len(self._candidate_duplicates)
            if total_groups > 0 and len(self._verified_originals_set) >= total_groups:
                self._status = DuplicationCheckStatus.COMPLETED
            else:
                self._status = DuplicationCheckStatus.PAUSED

    def stop_verification(self) -> None:
        """Request cooperative pause/stop of the running verification thread."""
        if self._status == DuplicationCheckStatus.RUNNING:
            self._stop_event.set()
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=5.0)
            if self._status != DuplicationCheckStatus.COMPLETED:
                self._status = DuplicationCheckStatus.PAUSED

    def start_verification_thread(self, run_in_background: bool = True) -> None:
        """
        Start or resume Stage 2 duplicate verification.

        Args:
            run_in_background: If True, executes in a background daemon thread;
                otherwise runs synchronously on the calling thread.
        """
        self._stop_event.clear()
        if run_in_background:
            self._worker_thread = Thread(
                target=self._run_verification,
                daemon=True,
            )
            self._worker_thread.start()
        else:
            self._run_verification()

    def _verify_single_group(
        self,
        original_path: str,
        candidate_paths: List[str],
    ) -> Optional[Tuple[str, List[str], List[dict], List[Tuple[str, str]]]]:
        """
        Verify a single duplicate group by comparing byte sizes against the original.

        Returns `None` if stop/pause was requested before verification began so the
        group remains pending for a future resume.
        """
        if self._stop_event.is_set():
            return None

        confirmed_dups: List[str] = []
        group_mismatches: List[dict] = []
        group_failed: List[Tuple[str, str]] = []

        try:
            orig_size = os.path.getsize(original_path)
        except OSError as err:
            err_msg = str(err)
            group_failed.append((original_path, err_msg))
            if callable(self._log_event):
                self._log_event(
                    f"WARNING: Could not read size of original file '{original_path}': {err_msg}"
                )
            return original_path, confirmed_dups, group_mismatches, group_failed

        for cand in candidate_paths:
            if self._stop_event.is_set():
                return None

            try:
                cand_size = os.path.getsize(cand)
            except OSError as err:
                err_msg = str(err)
                group_failed.append((cand, err_msg))
                if callable(self._log_event):
                    self._log_event(
                        f"WARNING: Could not read size of candidate duplicate '{cand}': {err_msg}"
                    )
                continue

            if cand_size == orig_size:
                confirmed_dups.append(cand)
            else:
                mismatch_info = {
                    "original": original_path,
                    "candidate": cand,
                    "original_size": orig_size,
                    "candidate_size": cand_size,
                    "reason": "size_mismatch",
                }
                group_mismatches.append(mismatch_info)
                if callable(self._log_event):
                    self._log_event(
                        f"WARNING: Possible hash collision! File size mismatch between "
                        f"'{original_path}' ({orig_size} bytes) and '{cand}' ({cand_size} bytes). "
                        f"Candidate excluded from duplicates."
                    )

        return original_path, confirmed_dups, group_mismatches, group_failed

    def _run_verification(self) -> None:
        """Execute multithreaded byte-size verification over all unverified duplicate groups."""
        self._status = DuplicationCheckStatus.RUNNING

        with self._lock:
            total_groups = len(self._candidate_duplicates)
            pending_items = [
                (orig, list(dups))
                for orig, dups in self._candidate_duplicates.items()
                if orig not in self._verified_originals_set
            ]

        if callable(self._start_verification):
            self._start_verification(
                f"Verifying {len(pending_items)} duplicate group(s) (total {total_groups})..."
            )

        if not pending_items:
            if callable(self._update_progress) and total_groups > 0:
                self._update_progress(total_groups, total_groups)
            self._status = DuplicationCheckStatus.COMPLETED
            if callable(self._finish_verification):
                self._finish_verification("Duplicate verification completed.")
            return

        with ThreadPoolExecutor(max_workers=self._num_of_threads) as executor:
            futures = [
                executor.submit(self._verify_single_group, orig, dups)
                for orig, dups in pending_items
            ]

            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    orig, confirmed_dups, group_mismatches, group_failed = result
                    with self._lock:
                        if orig not in self._verified_originals_set:
                            self._verified_originals.append(orig)
                            self._verified_originals_set.add(orig)
                        if confirmed_dups:
                            self._verified_duplicates[orig] = confirmed_dups
                        if group_mismatches:
                            self._mismatched_files.extend(group_mismatches)
                        if group_failed:
                            self._failed_files.extend(group_failed)
                        verified_count = len(self._verified_originals)

                    if callable(self._update_progress):
                        self._update_progress(verified_count, total_groups)

                if self._stop_event.is_set():
                    for pending_future in futures:
                        pending_future.cancel()
                    break

        with self._lock:
            all_done = len(self._verified_originals_set) >= total_groups

        if self._stop_event.is_set() and not all_done:
            self._status = DuplicationCheckStatus.PAUSED
            if callable(self._log_event):
                self._log_event("Duplicate verification paused by user.")
        else:
            self._status = DuplicationCheckStatus.COMPLETED
            if callable(self._finish_verification):
                self._finish_verification("Duplicate verification completed.")
