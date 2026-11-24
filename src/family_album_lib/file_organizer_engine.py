"""
Domain engine and background worker for organizing media files by date.

This module provides the core business logic for the File Organizer feature:
- Multithreaded per-file scanning via `ThreadPoolExecutor` using `AppSettings.worker_threads`.
- Fast single-pass Pillow image inspection (size, camera maker, EXIF date in one header open)
  and OpenCV video resolution lookup (avoiding MoviePy/FFmpeg unless needed for date fallback).
- Generating a structured execution plan targeting `<target>/YYYY/MM` or `<target>/No_Date`.
- Performing disk capacity pre-checks before copy operations.
- Multithreaded safe copying or moving of files with atomic collision disambiguation (`_copyN`)
  and Blake2b hashing.
- Invariant safety: never deletes or overwrites files.
- Reusing pre-analyzed plans when transitioning from preview to organization.
- Threaded execution via PyQt6 QThread (`OrganizerWorker`) with throttled real-time UI signals.
- Thread-safe transactional recording in SQLite catalog (`.db/album.db`).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set, Tuple

from PIL import Image
from PyQt6.QtCore import QThread, pyqtSignal

from src.family_album.utility_functions.date_extractor import (
    extract_date_from_exif,
    extract_date_from_filename,
    extract_date_from_filesystem,
    extract_date_from_pil_exif,
    extract_date_from_video,
    MediaDateResult,
)
from src.family_album.utility_functions.image_utils import (
    has_image_extension,
    is_image_file,
)
from src.family_album.utility_functions.video_utils import (
    get_video_resolution_fast,
    has_video_extension,
    is_file_a_video,
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

    def to_dict(self) -> dict:
        """Serialize OrganizePlanItem to a JSON-compatible dictionary."""
        return {
            "file_path": os.path.normpath(self.file_path),
            "file_name": self.file_name,
            "file_size": self.file_size,
            "date_result": self.date_result.to_dict(),
            "destination_dir": os.path.normpath(self.destination_dir),
            "target_path": os.path.normpath(self.target_path),
            "is_video": self.is_video,
            "is_image": self.is_image,
            "resolution": self.resolution,
            "maker": self.maker,
            "action_type": self.action_type,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrganizePlanItem":
        """Reconstruct an OrganizePlanItem from a dictionary."""
        return cls(
            file_path=os.path.normpath(data["file_path"]),
            file_name=data["file_name"],
            file_size=int(data.get("file_size", 0)),
            date_result=MediaDateResult.from_dict(data.get("date_result", {})),
            destination_dir=os.path.normpath(data["destination_dir"]),
            target_path=os.path.normpath(data["target_path"]),
            is_video=bool(data.get("is_video", False)),
            is_image=bool(data.get("is_image", False)),
            resolution=str(data.get("resolution", "")),
            maker=str(data.get("maker", "")),
            action_type=str(data.get("action_type", "copy")),
            status=str(data.get("status", "pending")),
        )


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

    def to_dict(self) -> dict:
        """Serialize OrganizeStats into a JSON-compatible dictionary."""
        return {
            "total_scanned": self.total_scanned,
            "total_processed": self.total_processed,
            "moved": self.moved,
            "copied": self.copied,
            "skipped": self.skipped,
            "errors": self.errors,
            "total_bytes": self.total_bytes,
            "details": list(self.details),
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "OrganizeStats":
        """Reconstruct OrganizeStats from a dictionary."""
        if not data:
            return cls()
        return cls(
            total_scanned=int(data.get("total_scanned", 0)),
            total_processed=int(data.get("total_processed", 0)),
            moved=int(data.get("moved", 0)),
            copied=int(data.get("copied", 0)),
            skipped=int(data.get("skipped", 0)),
            errors=int(data.get("errors", 0)),
            total_bytes=int(data.get("total_bytes", 0)),
            details=list(data.get("details", [])),
        )


def calculate_file_hash(file_path: str, chunk_size: int = 131072) -> str:
    """
    Compute the Blake2b cryptographic hash of a file reading in chunks.

    Args:
        file_path (str): Path to file to hash.
        chunk_size (int): Number of bytes read per chunk (default 128 KB).

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


def _norm_key(path: str) -> str:
    """Return case-normalized absolute path key for thread-safe path reservation."""
    return os.path.normcase(os.path.abspath(path))


def _reserve_unique_destination(
    dst_dir: str,
    base_name: str,
    reserved_paths: Optional[Set[str]] = None,
) -> str:
    """
    Find and atomically reserve an unused destination path inside `dst_dir`.
    Must be invoked while holding `collision_lock` when used across threads.

    Args:
        dst_dir (str): Destination directory path.
        base_name (str): Desired filename with extension.
        reserved_paths (Optional[Set[str]]): Shared set of already reserved normalized paths.

    Returns:
        str: Guaranteed unique destination file path (suffixed with `_copyN` if needed).
    """
    dst = os.path.join(dst_dir, base_name)
    key = _norm_key(dst)
    is_taken = os.path.exists(dst) or (reserved_paths is not None and key in reserved_paths)

    if is_taken:
        name, ext = os.path.splitext(base_name)
        i = 1
        while True:
            candidate = os.path.join(dst_dir, f"{name}_copy{i}{ext}")
            cand_key = _norm_key(candidate)
            if not os.path.exists(candidate) and (reserved_paths is None or cand_key not in reserved_paths):
                dst = candidate
                key = cand_key
                break
            i += 1

    if reserved_paths is not None:
        reserved_paths.add(key)
    return dst


def safe_copy_file(
    src: str,
    dst_dir: str,
    src_hash: Optional[str] = None,
    reserved_paths: Optional[Set[str]] = None,
    collision_lock: Optional[threading.Lock] = None,
) -> Tuple[bool, str, str]:
    """
    Safely copy a source file to destination directory without overwriting or deleting.
    Thread-safe when provided with shared `reserved_paths` and `collision_lock`.

    Behavior:
    - If source and destination paths are identical, skips operation.
    - If a file with the target name exists on disk, compares content hashes:
      - If identical content, skips copying to prevent duplicates.
      - If content differs, reserves a unique `_copy1`, `_copy2`, ... filename.
    - Preserves file metadata and timestamps using `shutil.copy2` outside the lock.

    Args:
        src (str): Absolute path to source file.
        dst_dir (str): Target folder where file will be copied.
        src_hash (Optional[str]): Pre-computed Blake2b hash of `src` to avoid rehashing.
        reserved_paths (Optional[Set[str]]): Shared set of reserved target paths across worker threads.
        collision_lock (Optional[threading.Lock]): Lock protecting atomic filename reservation.

    Returns:
        Tuple[bool, str, str]: (success_flag, final_destination_path, status_detail_message).
    """
    ensure_directory(dst_dir)
    base_name = os.path.basename(src)
    default_dst = os.path.join(dst_dir, base_name)

    if _norm_key(src) == _norm_key(default_dst):
        return False, default_dst, "identical_source_and_destination"

    # Check if an identical file already exists at default_dst on disk
    if os.path.exists(default_dst):
        try:
            computed_src_hash = src_hash or calculate_file_hash(src)
            if computed_src_hash == calculate_file_hash(default_dst):
                return False, default_dst, "identical_file_already_at_destination"
        except Exception:
            pass

    if collision_lock is not None:
        with collision_lock:
            dst = _reserve_unique_destination(dst_dir, base_name, reserved_paths)
    else:
        dst = _reserve_unique_destination(dst_dir, base_name, reserved_paths)

    shutil.copy2(src, dst)
    return True, dst, "copied"


def safe_move_file(
    src: str,
    dst_dir: str,
    reserved_paths: Optional[Set[str]] = None,
    collision_lock: Optional[threading.Lock] = None,
) -> Tuple[bool, str, str]:
    """
    Safely move a source file to destination directory without deleting or overwriting.
    Thread-safe when provided with shared `reserved_paths` and `collision_lock`.

    Behavior:
    - If source and destination paths are identical, skips operation.
    - If destination filename already exists on disk or is reserved by another thread,
      always disambiguates with `_copy1`, `_copy2`, etc. (source is NEVER deleted or overwritten).
    - Moves file using `shutil.move` outside the lock.

    Args:
        src (str): Absolute path to source file.
        dst_dir (str): Target folder where file will be moved.
        reserved_paths (Optional[Set[str]]): Shared set of reserved target paths across worker threads.
        collision_lock (Optional[threading.Lock]): Lock protecting atomic filename reservation.

    Returns:
        Tuple[bool, str, str]: (success_flag, final_destination_path, status_detail_message).
    """
    ensure_directory(dst_dir)
    base_name = os.path.basename(src)
    default_dst = os.path.join(dst_dir, base_name)

    if _norm_key(src) == _norm_key(default_dst):
        return False, default_dst, "identical_source_and_destination"

    if collision_lock is not None:
        with collision_lock:
            dst = _reserve_unique_destination(dst_dir, base_name, reserved_paths)
    else:
        dst = _reserve_unique_destination(dst_dir, base_name, reserved_paths)

    shutil.move(src, dst)
    return True, dst, "moved"


class FileOrganizerEngine:
    """
    Core domain engine for constructing organization plans and executing media transfers.

    Encapsulates all logic for:
    - Scanning candidate source directories (with exclusion of `.db` and `.git`).
    - Parallel single-pass per-file inspection via `ThreadPoolExecutor`.
    - Determining sibling target directories (`<source>_organized`).
    - Building preview plans mapping files to `<target>/YYYY/MM` or `<target>/No_Date`.
    - Executing plans in parallel with atomic collision safety and writing audit records to `album.db`.
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
    def _inspect_single_file(
        full_path: str,
        target_abs: str,
        action_type: str,
        prefer_filename: bool = True,
        min_date: Optional[datetime] = None,
    ) -> OrganizePlanItem:
        """
        Inspect a single candidate file in one optimized pass (designed to run inside
        a `ThreadPoolExecutor` worker thread).

        Date resolution priority (all dates validated against `min_date` / `AppSettings.min_valid_date`):
        1. Filename pattern parsing (zero disk I/O).
        2. Embedded media metadata (single-pass Pillow EXIF Sub-IFD for images;
           container `creation_time` for videos only when filename lacked a date).
        3. Operating system filesystem timestamps (`extract_date_from_filesystem`:
           earliest valid `Last Modified` / `Created`, rejecting 1970/1980 epochs).
        4. Unresolved (`No_Date/`) when no valid date >= `min_date` exists.

        Args:
            full_path (str): Absolute path to the candidate file.
            target_abs (str): Absolute destination root directory.
            action_type (str): Planned transfer method ('copy' or 'move').
            prefer_filename (bool): Whether filename date parsing takes priority.
            min_date (Optional[datetime]): Optional lower bound override for valid dates
                (defaults to `AppSettings.instance().min_valid_datetime`).

        Returns:
            OrganizePlanItem: Constructed plan item for the file.
        """
        effective_min_date = min_date if min_date is not None else AppSettings.instance().min_valid_datetime
        fname = os.path.basename(full_path)
        try:
            fsize = os.path.getsize(full_path)
        except OSError:
            fsize = 0

        date_res: Optional[MediaDateResult] = None

        # 1. Priority 1: Filename date parsing (zero disk I/O)
        if prefer_filename:
            fn_date = extract_date_from_filename(fname, min_date=effective_min_date)
            if fn_date:
                date_res = MediaDateResult(
                    date=fn_date,
                    source="filename",
                    detail=f"Extracted from name: {fname}",
                )

        is_vid = False
        is_img = False
        resolution = ""
        maker = ""

        lower_path = full_path.lower()
        is_gif = lower_path.endswith(".gif")

        # 2. Fast media type classification & single-pass metadata inspection
        if has_video_extension(full_path) or is_gif:
            is_vid = is_file_a_video(full_path)
            if is_vid:
                resolution = get_video_resolution_fast(full_path)
                if date_res is None:
                    v_date = extract_date_from_video(full_path, min_date=effective_min_date)
                    if v_date:
                        date_res = MediaDateResult(
                            date=v_date,
                            source="video_metadata",
                            detail="Extracted from video metadata",
                        )

        if not is_vid and (has_image_extension(full_path) or is_gif):
            # Single Pillow open for is_image + resolution + maker + EXIF date!
            try:
                with Image.open(full_path) as img:
                    is_img = True
                    w, h = img.size
                    if w and h:
                        resolution = f"{w}x{h}"
                    try:
                        exif = img.getexif()
                        if exif:
                            if 271 in exif:
                                maker = str(exif[271]).strip()
                            if date_res is None:
                                pil_dt = extract_date_from_pil_exif(exif, min_date=effective_min_date)
                                if pil_dt:
                                    date_res = MediaDateResult(
                                        date=pil_dt,
                                        source="exif",
                                        detail="Extracted from EXIF DateTimeOriginal",
                                    )
                    except Exception:
                        pass
            except Exception:
                # Fallback verification for unusual image formats (e.g. OpenCV-readable)
                if is_image_file(full_path):
                    is_img = True

            # Only invoke lightweight exifread fallback if Pillow did not find an EXIF date
            if is_img and date_res is None:
                exif_dt = extract_date_from_exif(full_path, min_date=effective_min_date)
                if exif_dt:
                    date_res = MediaDateResult(
                        date=exif_dt,
                        source="exif",
                        detail="Extracted from EXIF DateTimeOriginal",
                    )

        # 3. Filename fallback if prefer_filename was False
        if not prefer_filename and date_res is None:
            fn_date = extract_date_from_filename(fname, min_date=effective_min_date)
            if fn_date:
                date_res = MediaDateResult(
                    date=fn_date,
                    source="filename",
                    detail=f"Extracted from name: {fname}",
                )

        # 4. Priority 3: Operating System Filesystem Fallback (Last Modified / Created)
        if date_res is None:
            fs_date = extract_date_from_filesystem(full_path, min_date=effective_min_date)
            if fs_date:
                date_res = MediaDateResult(
                    date=fs_date,
                    source="filesystem",
                    detail="Extracted from file system (Last Modified)",
                )

        # 5. Unresolved date -> No_Date
        if date_res is None:
            date_res = MediaDateResult(
                date=None,
                source="none",
                detail="No valid creation date found in filename, metadata, or filesystem",
            )

        if date_res.has_date:
            dest_subdir = os.path.join(target_abs, date_res.year_folder, date_res.month_folder)
        else:
            dest_subdir = os.path.join(target_abs, "No_Date")

        target_file_path = os.path.join(dest_subdir, fname)

        return OrganizePlanItem(
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
            action_type=action_type,
        )

    @staticmethod
    def scan_and_plan(
        source_dir: str,
        target_dir: str,
        mode: str = "new_organization",
        action_type: str = "copy",
        prefer_filename: bool = True,
        cancel_event: Optional[threading.Event] = None,
        progress_cb: Optional[Callable[[int, int], None]] = None,
        max_workers: int = 0,
        existing_items: Optional[Dict[str, OrganizePlanItem]] = None,
        total_files_out: Optional[List[int]] = None,
    ) -> List[OrganizePlanItem]:
        """
        Scan source directory in parallel using `ThreadPoolExecutor` and construct
        an actionable organization plan.

        Supports Memento resumption via `existing_items`: files whose normalized path is
        already present in `existing_items` are reused immediately without disk I/O.

        Args:
            source_dir (str): Root folder to scan.
            target_dir (str): Destination media archive root.
            mode (str): Organization mode ('new_organization' or 'self_organization').
            action_type (str): Scheduled transfer method ('copy' or 'move').
            prefer_filename (bool): If True, prioritized date patterns embedded in filename.
            cancel_event (Optional[threading.Event]): Cooperative cancellation event flag.
            progress_cb (Optional[Callable[[int, int], None]]): Callback reporting (current, total).
            max_workers (int): Number of parallel worker threads (defaults to AppSettings.worker_threads).
            existing_items (Optional[Dict[str, OrganizePlanItem]]): Previously analyzed items keyed by
                normalized file path (used when resuming an interrupted analysis).
            total_files_out (Optional[List[int]]): Optional single-element sink list updated with
                total candidate files discovered in `source_dir`.

        Returns:
            List[OrganizePlanItem]: Array of prepared items scheduled for organization.
        """
        plan: List[OrganizePlanItem] = []
        if not os.path.isdir(source_dir):
            return plan

        source_abs = os.path.abspath(source_dir)
        target_abs = os.path.abspath(target_dir)

        norm_existing: Dict[str, OrganizePlanItem] = {}
        if existing_items:
            for k, v in existing_items.items():
                norm_existing[os.path.normcase(os.path.normpath(os.path.abspath(k)))] = v

        # First pass: collect all candidate files
        all_candidate_files: List[str] = []
        for dirpath, dirnames, filenames in os.walk(source_abs):
            if cancel_event and cancel_event.is_set():
                return list(existing_items.values()) if existing_items else plan

            # Skip .db and .git directories
            dirnames[:] = [d for d in dirnames if d != OrganizerDatabase.DB_FOLDER_NAME and d != ".git"]

            # If self-organizing, skip already organized folders matching YYYY/MM or No_Date
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
        if total_files_out is not None:
            total_files_out.clear()
            total_files_out.append(total_files)

        if total_files == 0:
            return plan

        results_by_idx: dict[int, OrganizePlanItem] = {}
        to_inspect: List[Tuple[int, str]] = []

        for idx, fpath in enumerate(all_candidate_files):
            norm_key = os.path.normcase(os.path.normpath(os.path.abspath(fpath)))
            if norm_key in norm_existing:
                cached = norm_existing[norm_key]
                cached.action_type = action_type
                results_by_idx[idx] = cached
            else:
                to_inspect.append((idx, fpath))

        completed = len(results_by_idx)
        last_report_time = 0.0

        if progress_cb and completed > 0:
            progress_cb(completed, total_files)
            last_report_time = time.monotonic()

        if to_inspect:
            workers = max_workers if max_workers > 0 else AppSettings.instance().worker_threads
            workers = max(1, min(workers, len(to_inspect)))

            def _worker_task(index: int, path: str) -> Tuple[int, Optional[OrganizePlanItem]]:
                if cancel_event and cancel_event.is_set():
                    return index, None
                item = FileOrganizerEngine._inspect_single_file(
                    full_path=path,
                    target_abs=target_abs,
                    action_type=action_type,
                    prefer_filename=prefer_filename,
                )
                return index, item

            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(_worker_task, idx, fpath)
                    for idx, fpath in to_inspect
                ]

                for future in as_completed(futures):
                    if cancel_event and cancel_event.is_set():
                        for f in futures:
                            f.cancel()
                        break

                    try:
                        idx, item = future.result()
                        if item is not None:
                            results_by_idx[idx] = item
                    except Exception:
                        pass

                    completed += 1
                    if progress_cb:
                        now = time.monotonic()
                        if completed == total_files or (now - last_report_time) >= 0.05:
                            progress_cb(completed, total_files)
                            last_report_time = now

        # Preserve deterministic ordering matching directory traversal
        plan = [results_by_idx[i] for i in sorted(results_by_idx.keys())]
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
        max_workers: int = 0,
        initial_stats: Optional[OrganizeStats] = None,
    ) -> OrganizeStats:
        """
        Execute the organization plan in parallel using `ThreadPoolExecutor` and
        record transactions into the thread-safe SQLite database.

        Supports Memento resumption: skips items whose status is already 'organized'
        or 'skipped' and continues accumulating metrics from `initial_stats` if provided.

        Args:
            plan (List[OrganizePlanItem]): List of items to process.
            target_dir (str): Target destination root.
            mode (str): Organization mode ('new_organization' or 'self_organization').
            action_type (str): Transfer method ('copy' or 'move').
            cancel_event (Optional[threading.Event]): Cooperative cancellation token.
            progress_cb (Optional[Callable[[int, int], None]]): Callback for (completed_count, total_count).
            status_cb (Optional[Callable[[str], None]]): Callback for high-level status messages.
            log_cb (Optional[Callable[[str], None]]): Callback for detailed log output.
            max_workers (int): Number of parallel worker threads (defaults to AppSettings.worker_threads).
            initial_stats (Optional[OrganizeStats]): Previously accumulated stats when resuming a paused run.

        Returns:
            OrganizeStats: Summary statistics of the completed or paused run.

        Raises:
            InsufficientDiskSpaceError: When copying and available disk space is less than required.
        """
        if initial_stats is not None:
            stats = OrganizeStats(
                total_scanned=max(len(plan), initial_stats.total_scanned),
                total_processed=initial_stats.total_processed,
                moved=initial_stats.moved,
                copied=initial_stats.copied,
                skipped=initial_stats.skipped,
                errors=initial_stats.errors,
                total_bytes=initial_stats.total_bytes,
                details=list(initial_stats.details),
            )
        else:
            stats = OrganizeStats()
            stats.total_scanned = len(plan)
        target_abs = os.path.abspath(target_dir)

        pending_items = [item for item in plan if item.status not in ("organized", "skipped")]

        # 1. Disk space check if action_type is copy
        if action_type == "copy":
            total_bytes_needed = sum(item.file_size for item in pending_items)
            has_space, req, free = check_disk_space(target_abs, total_bytes_needed)
            if not has_space:
                raise InsufficientDiskSpaceError(req, free)

        # 2. Initialize thread-safe database in target/.db/album.db
        db = OrganizerDatabase(target_abs)
        source_dir = os.path.dirname(plan[0].file_path) if plan else target_abs
        session_id = db.start_session(
            source_dir=source_dir,
            target_dir=target_abs,
            mode=mode,
            action_type=action_type
        )

        # Pre-create destination folders to minimize os.makedirs contention across threads
        unique_dest_dirs = {item.destination_dir for item in pending_items}
        for d in unique_dest_dirs:
            ensure_directory(d)

        total_items = len(plan)
        already_done = total_items - len(pending_items)
        completed_count = already_done

        workers = max_workers if max_workers > 0 else AppSettings.instance().worker_threads
        workers = max(1, min(workers, max(1, len(pending_items))))

        collision_lock = threading.Lock()
        stats_lock = threading.Lock()
        reserved_paths: Set[str] = set()
        last_report_time = [0.0]

        def _process_item(item: OrganizePlanItem) -> None:
            nonlocal completed_count
            if cancel_event and cancel_event.is_set():
                return

            src_path = item.file_path
            dst_dir = item.destination_dir

            try:
                f_hash = calculate_file_hash(src_path)
            except Exception:
                f_hash = ""

            try:
                if action_type == "copy":
                    success, final_dst, detail = safe_copy_file(
                        src_path,
                        dst_dir,
                        src_hash=f_hash,
                        reserved_paths=reserved_paths,
                        collision_lock=collision_lock,
                    )
                    if success:
                        item.status = "organized"
                        item.target_path = final_dst
                        db.log_action(session_id, src_path, "copied", f"Copied to {final_dst}")
                        with stats_lock:
                            stats.total_processed += 1
                            stats.copied += 1
                            stats.total_bytes += item.file_size
                    else:
                        item.status = "skipped"
                        db.log_action(session_id, src_path, "skipped", detail)
                        with stats_lock:
                            stats.total_processed += 1
                            stats.skipped += 1
                else:  # move
                    success, final_dst, detail = safe_move_file(
                        src_path,
                        dst_dir,
                        reserved_paths=reserved_paths,
                        collision_lock=collision_lock,
                    )
                    if success:
                        item.status = "organized"
                        item.target_path = final_dst
                        db.log_action(session_id, src_path, "moved", f"Moved to {final_dst}")
                        with stats_lock:
                            stats.total_processed += 1
                            stats.moved += 1
                            stats.total_bytes += item.file_size
                    else:
                        item.status = "skipped"
                        db.log_action(session_id, src_path, "skipped", detail)
                        with stats_lock:
                            stats.total_processed += 1
                            stats.skipped += 1

                # Thread-safe record in DB
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

                verb = "Copied" if action_type == "copy" else "Moved"
                if item.status == "skipped":
                    verb = "Skipped"
                msg = f"{verb}: {item.file_name} -> {os.path.relpath(item.target_path, target_abs)}"

                with stats_lock:
                    completed_count += 1
                    curr = completed_count
                    now = time.monotonic()
                    should_emit_ui = (curr == total_items) or ((now - last_report_time[0]) >= 0.05)
                    if should_emit_ui:
                        last_report_time[0] = now

                if should_emit_ui:
                    if status_cb:
                        status_cb(msg)
                    if progress_cb:
                        progress_cb(curr, total_items)
                if log_cb:
                    log_cb(msg)

            except Exception as err:
                err_msg = f"Error processing {src_path}: {err}"
                item.status = "error"
                db.log_action(session_id, src_path, "error", str(err))
                with stats_lock:
                    stats.total_processed += 1
                    stats.errors += 1
                    stats.details.append(err_msg)
                    completed_count += 1
                    curr = completed_count
                if log_cb:
                    log_cb(err_msg)
                if progress_cb:
                    progress_cb(curr, total_items)

        try:
            if pending_items:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = [executor.submit(_process_item, item) for item in pending_items]
                    for future in as_completed(futures):
                        if cancel_event and cancel_event.is_set():
                            for f in futures:
                                f.cancel()
                            if status_cb:
                                status_cb("Organization stopped by user.")
                            break
                        try:
                            future.result()
                        except Exception:
                            pass
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
    PyQt6 background worker thread for non-blocking parallel analysis and organization execution.

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
    paused = pyqtSignal(str, list, object, int)  # phase, plan, stats, total_files
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        source_dir: str,
        target_dir: str,
        mode: str = "new_organization",
        action_type: str = "copy",
        operation: str = "organize",  # "analyze" or "organize"
        max_workers: int = 0,
        existing_plan: Optional[List[OrganizePlanItem]] = None,
        existing_items: Optional[Dict[str, OrganizePlanItem]] = None,
        initial_stats: Optional[OrganizeStats] = None,
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
            existing_plan (Optional[List[OrganizePlanItem]]): Pre-analyzed plan to reuse during
                'organize' operation without scanning the directory a second time.
            existing_items (Optional[Dict[str, OrganizePlanItem]]): Previously analyzed items keyed by
                normalized file path when resuming an interrupted 'analyze' operation.
            initial_stats (Optional[OrganizeStats]): Previously accumulated stats when resuming
                an interrupted 'organize' operation.
            parent (Optional[QObject]): Parent Qt object.
        """
        super().__init__(parent)
        self.source_dir = source_dir
        self.target_dir = target_dir
        self.mode = mode
        self.action_type = action_type
        self.operation = operation
        self.max_workers = max_workers if max_workers > 0 else AppSettings.instance().worker_threads
        self.existing_plan = existing_plan
        self.existing_items = existing_items
        self.initial_stats = initial_stats
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        """Cooperatively request thread cancellation (pause)."""
        self._cancel_event.set()

    def run(self) -> None:
        """
        Main execution loop in dedicated worker thread.

        Executes parallel analysis or organization based on `self.operation`, supporting
        resumption from Memento state and emitting `paused` when cancelled cooperatively.
        """
        try:
            if self.operation == "analyze":
                self.analysis_started.emit(f"Scanning '{self.source_dir}' ({self.max_workers} threads)...")
                total_sink: List[int] = []
                plan = FileOrganizerEngine.scan_and_plan(
                    source_dir=self.source_dir,
                    target_dir=self.target_dir,
                    mode=self.mode,
                    action_type=self.action_type,
                    cancel_event=self._cancel_event,
                    progress_cb=self.progress_updated.emit,
                    max_workers=self.max_workers,
                    existing_items=self.existing_items,
                    total_files_out=total_sink,
                )
                total_discovered = total_sink[0] if total_sink else len(plan)
                if self._cancel_event.is_set():
                    partial_stats = OrganizeStats(total_scanned=total_discovered)
                    self.paused.emit("analyze", plan, partial_stats, total_discovered)
                    self.status_message.emit(
                        f"Analysis paused ({len(plan)}/{total_discovered} files analyzed). You can save state or resume."
                    )
                else:
                    self.plan_ready.emit(plan)
                    self.status_message.emit(f"Scan complete. Found {len(plan)} files.")
            else:
                self.analysis_started.emit(f"Organizing files to '{self.target_dir}' ({self.max_workers} threads)...")
                total_sink = []
                # 1. Reuse existing preview/resumed plan if available, otherwise scan now
                if self.existing_plan:
                    plan = self.existing_plan
                    total_discovered = len(plan)
                    for item in plan:
                        item.action_type = self.action_type
                else:
                    plan = FileOrganizerEngine.scan_and_plan(
                        source_dir=self.source_dir,
                        target_dir=self.target_dir,
                        mode=self.mode,
                        action_type=self.action_type,
                        cancel_event=self._cancel_event,
                        progress_cb=self.progress_updated.emit,
                        max_workers=self.max_workers,
                        existing_items=self.existing_items,
                        total_files_out=total_sink,
                    )
                    total_discovered = total_sink[0] if total_sink else len(plan)
                    if self._cancel_event.is_set():
                        partial_stats = OrganizeStats(total_scanned=total_discovered)
                        self.paused.emit("analyze", plan, partial_stats, total_discovered)
                        self.status_message.emit(
                            f"Analysis paused ({len(plan)}/{total_discovered} files analyzed). You can save state or resume."
                        )
                        return

                # 2. Execute plan in parallel
                stats = FileOrganizerEngine.execute_plan(
                    plan=plan,
                    target_dir=self.target_dir,
                    mode=self.mode,
                    action_type=self.action_type,
                    cancel_event=self._cancel_event,
                    progress_cb=self.progress_updated.emit,
                    status_cb=self.status_message.emit,
                    log_cb=self.log_event.emit,
                    max_workers=self.max_workers,
                    initial_stats=self.initial_stats,
                )
                if self._cancel_event.is_set():
                    self.paused.emit("organize", plan, stats, total_discovered)
                    done_count = sum(1 for item in plan if item.status in ("organized", "skipped"))
                    self.status_message.emit(
                        f"Organization paused ({done_count}/{total_discovered} files done). You can save state or resume."
                    )
                else:
                    self.finished.emit(stats)

        except InsufficientDiskSpaceError as space_err:
            self.space_error.emit(space_err.required_bytes, space_err.free_bytes)
        except Exception as err:
            self.error_occurred.emit(str(err))
