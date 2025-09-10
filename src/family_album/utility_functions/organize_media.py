import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Tuple

from src.family_album.utility_functions.image_utils import is_image_file, get_image_creation_date
from src.family_album.utility_functions.video_utils import is_file_a_video, get_video_creation_date
from src.family_album.utility_functions.file_utils import get_file_creation_date


@dataclass
class OrganizeStats:
    total_processed: int = 0
    moved: int = 0
    skipped: int = 0
    errors: int = 0
    details: List[str] = None

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = []


def ensure_directory(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def safe_move(src: str, dst_dir: str) -> Tuple[bool, str]:
    ensure_directory(dst_dir)
    base_name = os.path.basename(src)
    dst = os.path.join(dst_dir, base_name)
    if os.path.abspath(src) == os.path.abspath(dst):
        return False, dst
    if os.path.exists(dst):
        name, ext = os.path.splitext(base_name)
        i = 1
        while True:
            candidate = os.path.join(dst_dir, f"{name}_copy{i}{ext}")
            if not os.path.exists(candidate):
                dst = candidate
                break
            i += 1
    shutil.move(src, dst)
    return True, dst


def get_media_datetime(file_path: str) -> datetime:
    if is_file_a_video(file_path):
        dt = get_video_creation_date(file_path)
        return dt
    if is_image_file(file_path):
        dt = get_image_creation_date(file_path)
        return dt
    return get_file_creation_date(file_path)


def organize_directory_by_year_month(source_dir: str, target_root: str | None = None,
                                     progress_cb: Callable[[str], None] | None = None) -> OrganizeStats:
    """
    Organize media files from source_dir into target_root/YYYY/MM folders based on creation/taken datetime.

    - If target_root is None, files are reorganized within source_dir into subfolders.
    - Keeps name collisions safe by adding _copyN suffix.
    - Returns stats including moved/skipped/errors and textual details.
    """
    stats = OrganizeStats()
    if not os.path.isdir(source_dir):
        stats.details.append(f"Source directory not found: {source_dir}")
        return stats

    root = target_root or source_dir
    for dirpath, _, filenames in os.walk(source_dir):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            stats.total_processed += 1
            try:
                # Skip our own destination folders to avoid moving already organized media again
                rel = os.path.relpath(dirpath, source_dir)
                if rel != ".":
                    parts = rel.split(os.sep)
                    if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) == 4 and parts[1].isdigit():
                        stats.skipped += 1
                        continue

                dt = get_media_datetime(full_path)
                if not isinstance(dt, datetime):
                    stats.skipped += 1
                    continue
                year = f"{dt.year:04d}"
                month = f"{dt.month:02d}"
                dst_dir = os.path.join(root, year, month)
                moved, dst_path = safe_move(full_path, dst_dir)
                if moved:
                    stats.moved += 1
                    if progress_cb:
                        progress_cb(f"Moved to {dst_path}")
                else:
                    stats.skipped += 1
            except Exception as err:
                stats.errors += 1
                stats.details.append(f"Error processing {full_path}: {err}")
    return stats


