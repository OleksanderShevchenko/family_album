"""
Domain engine and background worker for organizing media files by date.

This module provides the core business logic for the File Organizer feature:
- Scanning source folders for candidate photos and videos.
- Extracting capture dates prioritizing filename patterns over EXIF/video container metadata.
- Generating a structured execution plan targeting `<target>/YYYY/MM` or `<target>/No_Date`.
- Performing disk capacity pre-checks before copy operations.
- Safely copying or moving files with automatic collision disambiguation (`_copyN`).
- Invariant safety: never deletes or overwrites files.
- Threaded execution via PyQt6 QThread (OrganizerWorker) with real-time UI signals.
- Transactional recording in SQLite catalog (`.db/album.db`).
"""

import hashlib
import os
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Tuple, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from src.family_album.utility_functions.date_extractor import (
    extract_media_date,
    MediaDateResult,
)
from src.family_album.utility_functions.image_utils import (
    is_image_file,
    get_image_size,
    get_image_maker,
)
from src.family_album.utility_functions.video_utils import (
    is_file_a_video,
    get_video_metadata,
)
from src.family_album_lib.app_settings import AppSettings
from src.family_album_lib.organizer_db import OrganizerDatabase


class InsufficientDiskSpaceError(Exception):
    """
    Raised when the destination storage device has inadequate free space for copying.

    Attributes:
        required_bytes (int): Total byte count required for all files scheduled to copy.
        free_bytes (int): Available free bytes on destination drive.
    """

    def __init__(self, required_bytes: int, free_bytes: int):
        """
        Initialize the InsufficientDiskSpaceError.

        Args:
            required_bytes (int): Required free disk space in bytes.
            free_bytes (int): Available disk space in bytes.
        """
        super().__init__(
            f"Not enough free disk space: required {required_bytes} bytes, "
            f"available {free_bytes} bytes."
        )
        self.required_bytes = required_bytes
        self.free_bytes = free_bytes


@dataclass
class OrganizePlanItem:
    """
    Represents an individual planned media organization action.

    Attributes:
        file_path (str): Absolute path to the original source file.
        file_name (str): Original filename with extension.
        file_size (int): Size of the file in bytes.
        date_result (MediaDateResult): Extracted capture date, source identifier, and detail.
        destination_dir (str): Computed target folder path (e.g. `<target>/2023/05` or `<target>/No_Date`).
        target_path (str): Intended full destination file path.
        is_video (bool): True if identified as a video format.
        is_image (bool): True if identified as a photo/image format.
        resolution (str): Visual resolution string (e.g. '1920x1080'), if obtainable.
        maker (str): Camera/device manufacturer or model, if extracted from EXIF.
        action_type (str): Transfer method: 'copy' or 'move'.
        status (str): Execution status: 'pending', 'organized', 'skipped', or 'error'.
    """
    file_path: str
    file_name: str
    file_size: int
    date_result: MediaDateResult
    destination_dir: str
    target_path: str
    is_video: bool
    is_image: bool
    resolution: str = ""
    maker: str = ""
    action_type: str = "copy"  # "copy" or "move"
    status: str = "pending"  # "pending", "organized", "skipped", "error"


@dataclass
class OrganizeStats:
    """
    Aggregate metrics and results for an organization batch run.

    Attributes:
        total_scanned (int): Number of candidate media files discovered.
        total_processed (int): Total files processed in execution.
        moved (int): Count of files successfully moved.
        copied (int): Count of files successfully copied.
        skipped (int): Count of files skipped (e.g., identical copy exists).
        errors (int): Count of files encountering errors.
        total_bytes (int): Total bytes transferred.
        details (List[str]): Warning and error message log entries.
    """
    total_scanned: int = 0
    total_processed: int = 0
    moved: int = 0
    copied: int = 0
    skipped: int = 0
    errors: int = 0
    total_bytes: int = 0
    details: List[str] = field(default_factory=list)


def calculate_file_hash(file_path: str, chunk_size: int = 65536) -> str:
    """
    Compute the Blake2b cryptographic hash of a file reading in chunks.

    Args:
        file_path (str): Path to file to hash.
        chunk_size (int): Number of bytes read per chunk (default 64 KB).

    Returns:
        str: Hexadecimal digest string representing the file content hash.
    """
    hasher = hashlib.blake2b()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


def check_disk_space(target_dir: str, required_bytes: int) -> Tuple[bool, int, int]:
    """
    Verify whether the target volume has sufficient free space for an operation.

    Traverses up the directory tree if the specified folder does not yet exist.

    Args:
        target_dir (str): Target directory or prospective path.
        required_bytes (int): Number of bytes needed for the transfer.

    Returns:
        Tuple[bool, int, int]: (has_enough_space, required_bytes, available_free_bytes).
    """
    path_to_check = target_dir
    while not os.path.exists(path_to_check):
        parent = os.path.dirname(path_to_check)
        if parent == path_to_check:
            break
        path_to_check = parent

    free_bytes = shutil.disk_usage(path_to_check).free
    return free_bytes >= required_bytes, required_bytes, free_bytes


def ensure_directory(path: str) -> None:
    """
    Ensure that a directory and all parent directories exist.

    Args:
        path (str): Filesystem path to create if missing.
    """
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def safe_copy_file(src: str, dst_dir: str) -> Tuple[bool, str, str]:
    """
    Safely copy a source file to destination directory without overwriting or deleting.

    Behavior:
    - If source and destination paths are identical, skips operation.
    - If a file with the target name exists, checks content hash:
      - If identical content, skips copying to prevent duplicates.
      - If content differs, suffixes name with `_copy1`, `_copy2`, etc.
    - Preserves file metadata and timestamps using shutil.copy2.

    Args:
        src (str): Absolute path to source file.
        dst_dir (str): Target folder where file will be copied.

    Returns:
        Tuple[bool, str, str]: (success_flag, final_destination_path, status_detail_message).
    """
    ensure_directory(dst_dir)
    base_name = os.path.basename(src)
    dst = os.path.join(dst_dir, base_name)

    if os.path.abspath(src) == os.path.abspath(dst):
        return False, dst, "identical_source_and_destination"

    if os.path.exists(dst):
        # Compare hashes
        try:
            if calculate_file_hash(src) == calculate_file_hash(dst):
                return False, dst, "identical_file_already_at_destination"
        except Exception:
            pass

        # Disambiguate name with _copyN
        name, ext = os.path.splitext(base_name)
        i = 1
        while True:
            candidate = os.path.join(dst_dir, f"{name}_copy{i}{ext}")
            if not os.path.exists(candidate):
                dst = candidate
                break
            i += 1

    shutil.copy2(src, dst)
    return True, dst, "copied"


def safe_move_file(src: str, dst_dir: str) -> Tuple[bool, str, str]:
    """
    Safely move a source file to destination directory without deleting or overwriting.

    Behavior:
    - If source and destination paths are identical, skips operation.
    - If destination filename exists:
      - Checks hash: if identical, disambiguates to preserve copy, ensuring source is never deleted.
      - If different, appends `_copy1`, `_copy2`, etc. until a free filename is found.
    - Moves file using shutil.move.

    Args:
        src (str): Absolute path to source file.
        dst_dir (str): Target folder where file will be moved.

    Returns:
        Tuple[bool, str, str]: (success_flag, final_destination_path, status_detail_message).
    """
    ensure_directory(dst_dir)
    base_name = os.path.basename(src)
    dst = os.path.join(dst_dir, base_name)

    if os.path.abspath(src) == os.path.abspath(dst):
        return False, dst, "identical_source_and_destination"

    if os.path.exists(dst):
        # Compare hashes
        try:
            if calculate_file_hash(src) == calculate_file_hash(dst):
                # An identical file already exists at target!
                # We NEVER delete src, but we preserve it as a copy or leave it
                name, ext = os.path.splitext(base_name)
                i = 1
                while True:
                    candidate = os.path.join(dst_dir, f"{name}_copy{i}{ext}")
                    if not os.path.exists(candidate):
                        dst = candidate
                        break
                    i += 1
        except Exception:
            pass
    else:
        # Check candidate naming
        name, ext = os.path.splitext(base_name)
        i = 1
        while os.path.exists(dst):
            candidate = os.path.join(dst_dir, f"{name}_copy{i}{ext}")
            if not os.path.exists(candidate):
                dst = candidate
                break
            i += 1

    shutil.move(src, dst)
    return True, dst, "moved"


class FileOrganizerEngine:
    """
    Core domain engine for constructing organization plans and executing media transfers.

    Encapsulates all logic for:
    - Scanning candidate source directories (with exclusion of `.db` and `.git`).
    - Determining sibling target directories (`<source>_organized`).
    - Building preview plans mapping files to `<target>/YYYY/MM` or `<target>/No_Date`.
    - Executing plans with copy/move actions and writing audit records to `album.db`.
    """

    @staticmethod
    def get_default_target_dir(source_dir: str) -> str:
        """
        Compute the default sibling target directory `<source>_organized` on the same level.

        Args:
            source_dir (str): Path to the source media directory.

        Returns:
            str: Path to `<source>_organized`.
        """
        norm_source = os.path.normpath(os.path.abspath(source_dir))
        parent_dir = os.path.dirname(norm_source)
        source_name = os.path.basename(norm_source)
        return os.path.join(parent_dir, f"{source_name}_organized")

    @staticmethod
    def scan_and_plan(
        source_dir: str,
        target_dir: str,
        mode: str = "new_organization",
        action_type: str = "copy",
        prefer_filename: bool = True,
        cancel_event: Optional[threading.Event] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        max_workers: int = 0
    ) -> List[OrganizePlanItem]:
        """
        Scan source directory and construct an actionable organization plan.

        Inspects each candidate file to extract creation/taken date (prioritizing filename),
        determines destination subfolder (`YYYY/MM` or `No_Date`), and probes file metadata.
        In self-organization mode, skips already structured subdirectories matching `YYYY/MM`
        or `No_Date`.

        Args:
            source_dir (str): Root folder to scan.
            target_dir (str): Destination media archive root.
            mode (str): Organization mode ('new_organization' or 'self_organization').
            action_type (str): Scheduled transfer method ('copy' or 'move').
            prefer_filename (bool): If True, prioritized date patterns embedded in filename.
            cancel_event (Optional[threading.Event]): Cooperative cancellation event flag.
            progress_cb (Optional[Callable[[int, int], None]]): Callback reporting (current, total).

        Returns:
            List[OrganizePlanItem]: Array of prepared items scheduled for organization.
        """
        plan: List[OrganizePlanItem] = []
        if not os.path.isdir(source_dir):
            return plan

        source_abs = os.path.abspath(source_dir)
        target_abs = os.path.abspath(target_dir)

        # First pass: collect all candidate files
        all_candidate_files = []
        for dirpath, dirnames, filenames in os.walk(source_abs):
            # Skip .db and .git directories
            dirnames[:] = [d for d in dirnames if d != OrganizerDatabase.DB_FOLDER_NAME and d != ".git"]

            # If self-organizing, skip already organized folders matching YYYY/MM
            if mode == "self_organization" and dirpath != source_abs:
                rel = os.path.relpath(dirpath, source_abs)
                parts = rel.split(os.sep)
                if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4 and parts[1].isdigit():
                    continue
                if parts[0] == "No_Date":
                    continue

            for fname in filenames:
                full_path = os.path.join(dirpath, fname)
                all_candidate_files.append(full_path)

        total_files = len(all_candidate_files)

        for idx, full_path in enumerate(all_candidate_files):
            if cancel_event and cancel_event.is_set():
                break

            fname = os.path.basename(full_path)
            try:
                fsize = os.path.getsize(full_path)
            except OSError:
                fsize = 0

            # Date extraction
            date_res = extract_media_date(
                full_path,
                prefer_filename=prefer_filename,
                allow_filesystem_fallback=False
            )

            # Route to YYYY/MM or No_Date
            if date_res.has_date:
                dest_subdir = os.path.join(target_abs, date_res.year_folder, date_res.month_folder)
            else:
                dest_subdir = os.path.join(target_abs, "No_Date")

            target_file_path = os.path.join(dest_subdir, fname)

            # Metadata inspection
            is_vid = is_file_a_video(full_path)
            is_img = False if is_vid else is_image_file(full_path)
            resolution = ""
            maker = ""

            if is_img:
                size_tup = get_image_size(full_path)
                if size_tup:
                    resolution = f"{size_tup[0]}x{size_tup[1]}"
                maker = get_image_maker(full_path)
            elif is_vid:
                meta = get_video_metadata(full_path)
                if meta and "resolution" in meta:
                    resolution = f"{meta['resolution']}"

            item = OrganizePlanItem(
                file_path=full_path,
                file_name=fname,
                file_size=fsize,
                date_result=date_res,
                destination_dir=dest_subdir,
                target_path=target_file_path,
                is_video=is_vid,
                is_image=is_img,
                resolution=resolution,
                maker=maker,
                action_type=action_type
            )
            plan.append(item)

            if progress_cb:
                progress_cb(idx + 1, total_files)

        return plan

    @staticmethod
    def execute_plan(
        plan: List[OrganizePlanItem],
        target_dir: str,
        mode: str = "new_organization",
        action_type: str = "copy",
        cancel_event: Optional[threading.Event] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        status_cb: Optional[Callable[[str], None]] = None,
        log_cb: Optional[Callable[[str], None]] = None,
        max_workers: int = 0
    ) -> OrganizeStats:
        """
        Execute the organization plan and record transactions into the database.

        Preconditions:
        - If action_type is 'copy', verifies free disk capacity before starting.

        Execution loop:
        - Transfers each item safely (moving or copying) with collision handling.
        - Calculates Blake2b hash for database indexing.
        - Emits progress and status callbacks.
        - Closes and commits the session in `<target_dir>/.db/album.db`.

        Args:
            plan (List[OrganizePlanItem]): List of items to process.
            target_dir (str): Target destination root.
            mode (str): Organization mode ('new_organization' or 'self_organization').
            action_type (str): Transfer method ('copy' or 'move').
            cancel_event (Optional[threading.Event]): Cooperative cancellation token.
            progress_cb (Optional[Callable[[int, int], None]]): Callback for (completed_count, total_count).
            status_cb (Optional[Callable[[str], None]]): Callback for high-level status messages.
            log_cb (Optional[Callable[[str], None]]): Callback for detailed log output.

        Returns:
            OrganizeStats: Summary statistics of the completed run.

        Raises:
            InsufficientDiskSpaceError: When copying and available disk space is less than required.
        """
        stats = OrganizeStats()
        stats.total_scanned = len(plan)
        target_abs = os.path.abspath(target_dir)

        # 1. Disk space check if action_type is copy
        if action_type == "copy":
            total_bytes_needed = sum(item.file_size for item in plan)
            has_space, req, free = check_disk_space(target_abs, total_bytes_needed)
            if not has_space:
                raise InsufficientDiskSpaceError(req, free)

        # 2. Initialize database in target/.db/album.db
        db = OrganizerDatabase(target_abs)
        source_dir = os.path.dirname(plan[0].file_path) if plan else target_abs
        session_id = db.start_session(
            source_dir=source_dir,
            target_dir=target_abs,
            mode=mode,
            action_type=action_type
        )

        try:
            for idx, item in enumerate(plan):
                if cancel_event and cancel_event.is_set():
                    if status_cb:
                        status_cb("Organization stopped by user.")
                    break

                stats.total_processed += 1
                src_path = item.file_path
                dst_dir = item.destination_dir

                try:
                    f_hash = calculate_file_hash(src_path)
                except Exception as e:
                    f_hash = ""

                try:
                    if action_type == "copy":
                        success, final_dst, detail = safe_copy_file(src_path, dst_dir)
                        if success:
                            stats.copied += 1
                            stats.total_bytes += item.file_size
                            item.status = "organized"
                            item.target_path = final_dst
                            db.log_action(session_id, src_path, "copied", f"Copied to {final_dst}")
                        else:
                            stats.skipped += 1
                            item.status = "skipped"
                            db.log_action(session_id, src_path, "skipped", detail)
                    else:  # move
                        success, final_dst, detail = safe_move_file(src_path, dst_dir)
                        if success:
                            stats.moved += 1
                            stats.total_bytes += item.file_size
                            item.status = "organized"
                            item.target_path = final_dst
                            db.log_action(session_id, src_path, "moved", f"Moved to {final_dst}")
                        else:
                            stats.skipped += 1
                            item.status = "skipped"
                            db.log_action(session_id, src_path, "skipped", detail)

                    # Record in DB
                    db.record_organized_file(
                        file_name=item.file_name,
                        original_path=src_path,
                        organized_path=item.target_path,
                        file_size=item.file_size,
                        file_hash=f_hash,
                        date_taken=item.date_result.date,
                        date_source=item.date_result.source,
                        is_video=item.is_video,
                        resolution=item.resolution,
                        maker=item.maker,
                        status=item.status
                    )

                    msg = f"{'Copied' if action_type == 'copy' else 'Moved'}: {item.file_name} -> {os.path.relpath(item.target_path, target_abs)}"
                    if status_cb:
                        status_cb(msg)
                    if log_cb:
                        log_cb(msg)

                except Exception as err:
                    stats.errors += 1
                    item.status = "error"
                    err_msg = f"Error processing {src_path}: {err}"
                    stats.details.append(err_msg)
                    db.log_action(session_id, src_path, "error", str(err))
                    if log_cb:
                        log_cb(err_msg)

                if progress_cb:
                    progress_cb(idx + 1, len(plan))

        finally:
            db.finish_session(
                session_id=session_id,
                total_processed=stats.total_processed,
                files_organized=stats.copied + stats.moved,
                files_skipped=stats.skipped,
                files_errors=stats.errors
            )
            db.close()

        return stats


class OrganizerWorker(QThread):
    """
    PyQt6 background worker thread for non-blocking analysis and organization execution.

    Signals:
        analysis_started (str): Emitted when a scan or execution starts with description.
        progress_updated (int, int): Emitted with (current_index, total_count).
        status_message (str): Emitted with single-line status updates for UI labels.
        log_event (str): Emitted with detailed log entries for the application console.
        space_error (int, int): Emitted when disk space is insufficient (required_bytes, free_bytes).
        finished (OrganizeStats): Emitted on completion of organization with result statistics.
        plan_ready (List[OrganizePlanItem]): Emitted after preview analysis with generated plan.
        error_occurred (str): Emitted on unhandled background exceptions.
    """
    analysis_started = pyqtSignal(str)
    progress_updated = pyqtSignal(int, int)
    status_message = pyqtSignal(str)
    log_event = pyqtSignal(str)
    space_error = pyqtSignal(int, int)  # required_bytes, free_bytes
    finished = pyqtSignal(object)  # OrganizeStats
    plan_ready = pyqtSignal(list)  # List[OrganizePlanItem]
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        source_dir: str,
        target_dir: str,
        mode: str = "new_organization",
        action_type: str = "copy",
        operation: str = "organize",  # "analyze" or "organize"
        max_workers: int = 0,
        parent=None
    ):
        """
        Initialize the OrganizerWorker thread.

        Args:
            source_dir (str): Source directory containing media files.
            target_dir (str): Destination media root.
            mode (str): Organization mode ('new_organization' or 'self_organization').
            action_type (str): Transfer method ('copy' or 'move').
            operation (str): Operational mode ('analyze' for preview plan, 'organize' for execution).
            max_workers (int): Number of parallel worker threads (defaults to AppSettings.worker_threads).
            parent (Optional[QObject]): Parent Qt object.
        """
        super().__init__(parent)
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.mode = mode
        self.action_type = action_type
        self.operation = operation
        self.max_workers = max_workers if max_workers > 0 else AppSettings.instance().worker_threads
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Cooperatively request thread cancellation."""
        self._cancel_event.set()

    def run(self) -> None:
        """
        Main execution loop in dedicated worker thread.

        Executes analysis or organization based on `self.operation`, catching errors
        and emitting corresponding Qt signals.
        """
        try:
            if self.operation == "analyze":
                self.analysis_started.emit(f"Scanning '{self.source_dir}'...")
                plan = FileOrganizerEngine.scan_and_plan(
                    source_dir=self.source_dir,
                    target_dir=self.target_dir,
                    mode=self.mode,
                    action_type=self.action_type,
                    cancel_event=self._cancel_event,
                    progress_cb=self.progress_updated.emit,
                    max_workers=self.max_workers
                )
                self.plan_ready.emit(plan)
                self.status_message.emit(f"Scan complete. Found {len(plan)} files.")
            else:
                self.analysis_started.emit(f"Organizing files to '{self.target_dir}'...")
                # 1. Build plan first
                plan = FileOrganizerEngine.scan_and_plan(
                    source_dir=self.source_dir,
                    target_dir=self.target_dir,
                    mode=self.mode,
                    action_type=self.action_type,
                    cancel_event=self._cancel_event,
                    progress_cb=self.progress_updated.emit,
                    max_workers=self.max_workers
                )
                if self._cancel_event.is_set():
                    return

                # 2. Execute plan
                stats = FileOrganizerEngine.execute_plan(
                    plan=plan,
                    target_dir=self.target_dir,
                    mode=self.mode,
                    action_type=self.action_type,
                    cancel_event=self._cancel_event,
                    progress_cb=self.progress_updated.emit,
                    status_cb=self.status_message.emit,
                    log_cb=self.log_event.emit,
                    max_workers=self.max_workers
                )
                self.finished.emit(stats)

        except InsufficientDiskSpaceError as space_err:
            self.space_error.emit(space_err.required_bytes, space_err.free_bytes)
        except Exception as err:
            self.error_occurred.emit(str(err))
