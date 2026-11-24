"""
Module for smart date extraction from media files (photos, videos, documents).

This module implements a priority-based date extraction strategy with configurable
minimum valid date filtering (`AppSettings.min_valid_date`, default `2000-01-01`):
1. Filename pattern parsing (highest priority, immune to filesystem copy/download timestamp distortion).
2. Embedded EXIF tags for images (DateTimeOriginal, DateTimeDigitized, DateTime) via fast Pillow IFD lookup with lightweight exifread fallback.
3. Embedded container metadata for videos (QuickTime / MP4 creation_time) via OpenCV & MoviePy.
4. Operating system filesystem timestamps (`st_mtime` / `Last Modified`, `st_ctime`, `st_birthtime`), taking the earliest valid timestamp and rejecting placeholder epochs (`1970` / `1980`).
5. Unresolved files without any valid date (`>= min_valid_date`) are categorized with `source='none'` for `No_Date/` routing.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import exifread
from PIL import Image

from src.family_album.utility_functions.image_utils import (
    has_image_extension,
    is_image_file,
)
from src.family_album.utility_functions.video_utils import (
    has_video_extension,
    is_file_a_video,
    get_video_metadata,
)
from src.family_album_lib.app_settings import AppSettings


@dataclass(frozen=True)
class MediaDateResult:
    """
    Data container representing the outcome of a media date extraction operation.

    Attributes:
        date (Optional[datetime]): The parsed datetime object, or None if no valid date was detected.
        source (str): Identifier of the date origin:
            - 'filename': Parsed from filename patterns.
            - 'exif': Extracted from image EXIF metadata tags.
            - 'video_metadata': Extracted from video container creation metadata.
            - 'filesystem': Obtained from operating system file timestamps (Last Modified / Created).
            - 'none': No valid date could be determined (routes to No_Date/ directory).
        detail (str): Human-readable information or pattern description regarding detection.
    """
    date: Optional[datetime]
    source: str  # 'filename', 'exif', 'video_metadata', 'filesystem', 'none'
    detail: str = ""

    @property
    def has_date(self) -> bool:
        """
        Check if a valid datetime was identified.

        Returns:
            bool: True if date is not None, False otherwise.
        """
        return self.date is not None

    @property
    def year_folder(self) -> str:
        """
        Produce directory name for the year tier.

        Returns:
            str: 4-digit formatted year string (e.g. '2023'), or 'No_Date' if date is None.
        """
        if self.date:
            return f"{self.date.year:04d}"
        return "No_Date"

    @property
    def month_folder(self) -> str:
        """
        Produce directory name for the month tier.

        Returns:
            str: 2-digit formatted month string (e.g. '05'), or empty string if date is None.
        """
        if self.date:
            return f"{self.date.month:02d}"
        return ""

    def to_dict(self) -> dict:
        """
        Serialize MediaDateResult into a JSON-compatible dictionary.

        Returns:
            dict: Serialized date result dictionary.
        """
        return {
            "date": self.date.strftime("%Y-%m-%d %H:%M:%S") if self.date else None,
            "source": self.source,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MediaDateResult":
        """
        Reconstruct MediaDateResult from a dictionary.

        Args:
            data (dict): Serialized date result dictionary.

        Returns:
            MediaDateResult: Deserialized result object.
        """
        raw_dt = data.get("date")
        dt = datetime.strptime(raw_dt, "%Y-%m-%d %H:%M:%S") if raw_dt else None
        return cls(
            date=dt,
            source=data.get("source", "none"),
            detail=data.get("detail", ""),
        )


# Regex patterns for dates extracted from filename
_FILENAME_PATTERNS = [
    # 1. IMG_20230514_143022 or VID_20230514_143022 or PXL_20230514_143022123 or 20230514_143022
    (
        re.compile(r'(?:^|[\D])(20\d\d|19\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])[_-]([01]\d|2[0-3])([0-5]\d)([0-5]\d)(?:\d{3,6})?(?:$|[\D])'),
        '%Y%m%d%H%M%S',
        'YYYYMMDD_HHMMSS'
    ),
    # 2. 2020-04-12 18.23.01 or 2020-04-12_18-23-01 or 2020-04-12 18:23:01 or Screen Shot 2021-09-15 at 14.30.22
    (
        re.compile(r'(?:^|[\D])(20\d\d|19\d\d)[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])(?:[\s_Tt]+at[\s_Tt]+|[\s_Tt]+)([01]\d|2[0-3])[-_.:]([0-5]\d)[-_.:]([0-5]\d)(?:$|[\D])'),
        '%Y-%m-%d %H:%M:%S',
        'YYYY-MM-DD HH:MM:SS'
    ),
    # 3. Screenshot_2022-01-01-23-59-59 or Screenshot_20220101-235959
    (
        re.compile(r'[Ss]creenshot[-_](20\d\d|19\d\d)[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01])[-_]([01]\d|2[0-3])[-_]?([0-5]\d)[-_]?([0-5]\d)'),
        '%Y%m%d%H%M%S',
        'Screenshot_YYYYMMDD_HHMMSS'
    ),
    # 4. WhatsApp Image 2021-06-25 at 15.30.45 or WhatsApp Video 2021-06-25 at 15.30.45
    (
        re.compile(r'WhatsApp.*?(20\d\d|19\d\d)[-_.](0[1-9]|1[0-2])[-_.](0[1-9]|[12]\d|3[01])\s+at\s+([01]\d|2[0-3])[-_.:]([0-5]\d)[-_.:]([0-5]\d)', re.IGNORECASE),
        '%Y-%m-%d %H:%M:%S',
        'WhatsApp_date_time'
    ),
    # 5. Date only with separators: 2020-04-12 or 2020.04.12 or 2020_04_12
    (
        re.compile(r'(?:^|[\D])(20\d\d|19\d\d)[-_/.](0[1-9]|1[0-2])[-_/.](0[1-9]|[12]\d|3[01])(?:$|[\D])'),
        '%Y-%m-%d',
        'YYYY-MM-DD'
    ),
    # 6. WP_20170308_001 or IMG20230514 or date only compact 8 digits YYYYMMDD
    (
        re.compile(r'(?:^|[A-Za-z_-])(20\d\d|19\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:$|[\D])'),
        '%Y%m%d',
        'YYYYMMDD'
    ),
]


def _resolve_min_date(min_date: Optional[datetime] = None) -> datetime:
    """
    Resolve the effective lower-bound valid datetime.

    Uses the explicitly supplied `min_date` if provided; otherwise queries
    `AppSettings.instance().min_valid_datetime` (default `2000-01-01 00:00:00`).

    Args:
        min_date (Optional[datetime]): Explicit lower bound override, or None.

    Returns:
        datetime: Minimum permissible media creation datetime.
    """
    if min_date is not None:
        return min_date
    return AppSettings.instance().min_valid_datetime


def is_valid_date(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
    min_date: Optional[datetime] = None,
) -> bool:
    """
    Validate that year, month, day, hour, minute, second form a realistic calendar
    datetime within `[min_valid_date, current_year + 1]`.

    Rejects bogus epoch dates (e.g., 1970-01-01 or 1980-01-01 from Google Photos
    animations/collages or ZIP archives) when `min_valid_date` is set to 2000-01-01.

    Args:
        year (int): 4-digit calendar year.
        month (int): Calendar month (1 to 12).
        day (int): Day of the month (1 to 31).
        hour (int, optional): Hour in 24-hour format (0 to 23). Defaults to 0.
        minute (int, optional): Minute (0 to 59). Defaults to 0.
        second (int, optional): Second (0 to 59). Defaults to 0.
        min_date (Optional[datetime], optional): Lower bound override; defaults to
            `AppSettings.instance().min_valid_datetime`.

    Returns:
        bool: True if the values construct a valid calendar datetime within permissible bounds.
    """
    max_year = datetime.now().year + 1
    if year > max_year:
        return False
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= 31):
        return False
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return False
    try:
        dt = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return False

    effective_min = _resolve_min_date(min_date)
    return dt >= effective_min


def extract_date_from_filename(
    filename: str,
    min_date: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Attempts to parse creation datetime directly from a file name string.

    This function scans filenames using an ordered collection of common smartphone,
    camera, screenshot, and messenger timestamp patterns, filtering results against
    `min_date` (default `AppSettings.min_valid_datetime`).

    Args:
        filename (str): The name or full path of the file.
        min_date (Optional[datetime], optional): Lower bound override for valid dates.

    Returns:
        Optional[datetime]: The parsed datetime if a recognized pattern matches and passes calendar
            validation, or None if no valid date could be deduced from the filename.
    """
    base = os.path.basename(filename)
    name_only, _ = os.path.splitext(base)

    # 1. Try regex patterns
    for pattern, fmt, desc in _FILENAME_PATTERNS:
        match = pattern.search(name_only)
        if match:
            groups = match.groups()
            try:
                if len(groups) == 6:
                    year, month, day, hour, minute, second = (int(g) for g in groups)
                    if is_valid_date(year, month, day, hour, minute, second, min_date=min_date):
                        return datetime(year, month, day, hour, minute, second)
                elif len(groups) == 3:
                    year, month, day = (int(g) for g in groups)
                    if is_valid_date(year, month, day, min_date=min_date):
                        return datetime(year, month, day, 0, 0, 0)
            except (ValueError, TypeError):
                continue

    # 2. Try Unix timestamp in milliseconds (13 digits) or seconds (10 digits)
    # E.g., 1684074622000.jpg or 1684074622.jpg
    ts_match = re.search(r'(?:^|[^\d])(1[5-7]\d{8}|1[5-7]\d{11})(?:$|[^\d])', name_only)
    if ts_match:
        try:
            raw_ts = int(ts_match.group(1))
            if len(str(raw_ts)) == 13:
                raw_ts = raw_ts / 1000.0
            dt = datetime.fromtimestamp(raw_ts).replace(microsecond=0)
            if is_valid_date(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, min_date=min_date):
                return dt
        except (ValueError, OSError, OverflowError):
            pass

    return None


def extract_date_from_pil_exif(exif, min_date: Optional[datetime] = None) -> Optional[datetime]:
    """
    Extract earliest valid capture datetime directly from an already-loaded Pillow Exif object.

    Inspects both top-level IFD0 tags (306: DateTime, 36867: DateTimeOriginal,
    36868: DateTimeDigitized, 50971: PreviewDateTime) and the Exif Sub-IFD (`0x8769`),
    rejecting dates earlier than `min_date`.

    Args:
        exif: Pillow `Image.Exif` object obtained via `image.getexif()`.
        min_date (Optional[datetime], optional): Lower bound override for valid dates.

    Returns:
        Optional[datetime]: Earliest valid datetime found, or None.
    """
    if not exif:
        return None

    dates = []
    for tag_id in (36867, 36868, 306, 50971):
        if tag_id in exif:
            dt = _parse_exif_datestring(str(exif[tag_id]).strip(), min_date=min_date)
            if dt:
                dates.append(dt)

    try:
        exif_ifd = exif.get_ifd(0x8769)
        if exif_ifd:
            for tag_id in (36867, 36868, 50971):
                if tag_id in exif_ifd:
                    dt = _parse_exif_datestring(str(exif_ifd[tag_id]).strip(), min_date=min_date)
                    if dt:
                        dates.append(dt)
    except Exception:
        pass

    return min(dates) if dates else None


def extract_date_from_exif(
    file_path: str,
    min_date: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Extracts datetime from image EXIF metadata tags using fast Pillow IFD lookup
    with lightweight fallback to exifread (`details=False`).

    Inspects standard EXIF date tags including DateTimeOriginal, DateTimeDigitized,
    and Image DateTime, selecting the earliest valid capture date >= `min_date`.

    Args:
        file_path (str): Absolute or relative filesystem path to the image file.
        min_date (Optional[datetime], optional): Lower bound override for valid dates.

    Returns:
        Optional[datetime]: The earliest valid EXIF datetime, or None if EXIF is absent or invalid.
    """
    if not os.path.isfile(file_path):
        return None

    # 1. Fast path: Pillow EXIF + Exif Sub-IFD (0x8769)
    try:
        with Image.open(file_path) as image:
            pil_dt = extract_date_from_pil_exif(image.getexif(), min_date=min_date)
            if pil_dt:
                return pil_dt
    except Exception:
        pass

    # 2. Lightweight fallback: Exifread with details=False (skips heavy MakerNote parsing)
    dates = []
    try:
        with open(file_path, 'rb') as f:
            er_tags = exifread.process_file(f, details=False)
        for tag_name in ('EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime'):
            if tag_name in er_tags:
                val = str(er_tags[tag_name]).strip()
                dt = _parse_exif_datestring(val, min_date=min_date)
                if dt:
                    dates.append(dt)
    except Exception:
        pass

    if dates:
        return min(dates)
    return None


def _parse_exif_datestring(
    date_str: str,
    min_date: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Internal helper to parse standard EXIF timestamp string formats and validate bounds.

    Args:
        date_str (str): Raw timestamp string from EXIF (e.g. '2023:05:14 14:30:22').
        min_date (Optional[datetime], optional): Lower bound override for valid dates.

    Returns:
        Optional[datetime]: Parsed datetime object if format matches and passes validation, else None.
    """
    if not date_str or date_str == 'None' or len(date_str) < 10:
        return None
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y:%m:%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            if is_valid_date(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, min_date=min_date):
                return dt
        except ValueError:
            continue
    return None


def extract_date_from_video(
    file_path: str,
    min_date: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Extracts creation datetime from video container metadata.

    Inspects metadata stream tags (such as QuickTime / MP4 creation_time) retrieved
    via MoviePy or OpenCV, validating against `min_date`.

    Args:
        file_path (str): Absolute or relative filesystem path to the video file.
        min_date (Optional[datetime], optional): Lower bound override for valid dates.

    Returns:
        Optional[datetime]: The parsed video creation datetime, or None if absent or invalid.
    """
    if not os.path.isfile(file_path) or not has_video_extension(file_path):
        return None

    try:
        meta = get_video_metadata(file_path)
        if meta and 'infos' in meta and 'metadata' in meta['infos']:
            raw_time = meta['infos']['metadata'].get('creation_time')
            if raw_time:
                clean_str = str(raw_time).strip().split('.')[0].rstrip('Z')
                for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
                    try:
                        dt = datetime.strptime(clean_str, fmt)
                        if is_valid_date(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, min_date=min_date):
                            return dt
                    except ValueError:
                        continue
    except Exception:
        pass

    return None


def extract_date_from_filesystem(
    file_path: str,
    min_date: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Extract the earliest valid operating system file timestamp (`st_mtime`, `st_ctime`,
    and `st_birthtime` when available) for a file.

    Guard against epoch-zeroed archives: if `st_mtime` (Last Modified) is earlier than
    `min_date` (e.g., `1970-01-01` or `1980-01-01` from ZIP/Google Photos placeholders),
    returns None rather than trusting a newer disk copy `st_ctime`.

    Args:
        file_path (str): Path to the file on disk.
        min_date (Optional[datetime], optional): Lower bound override for valid dates.

    Returns:
        Optional[datetime]: Earliest valid OS timestamp (microseconds stripped), or None.
    """
    if not os.path.isfile(file_path):
        return None

    try:
        stat = os.stat(file_path)
    except OSError:
        return None

    # Validate st_mtime (Last Modified) first — if it is an epoch placeholder (< min_date),
    # reject the filesystem fallback so a newer copy st_ctime is not mistakenly used.
    try:
        mtime_dt = datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0)
    except (ValueError, OSError, OverflowError):
        return None

    if not is_valid_date(
        mtime_dt.year, mtime_dt.month, mtime_dt.day,
        mtime_dt.hour, mtime_dt.minute, mtime_dt.second,
        min_date=min_date,
    ):
        return None

    valid_dates = [mtime_dt]

    for attr in ("st_ctime", "st_birthtime"):
        raw_ts = getattr(stat, attr, None)
        if raw_ts is None or raw_ts <= 0:
            continue
        try:
            dt = datetime.fromtimestamp(raw_ts).replace(microsecond=0)
            if is_valid_date(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, min_date=min_date):
                valid_dates.append(dt)
        except (ValueError, OSError, OverflowError):
            continue

    return min(valid_dates)


def extract_media_date(
    file_path: str,
    prefer_filename: bool = True,
    allow_filesystem_fallback: bool = True,
    min_date: Optional[datetime] = None,
) -> MediaDateResult:
    """
    Primary interface for extracting creation datetime for a media file according to priority rules:
    1. Filename pattern parsing (highest priority when `prefer_filename=True`).
    2. Embedded media metadata (EXIF DateTimeOriginal for images, container `creation_time` for videos).
    3. Operating system filesystem timestamps (`Last Modified` / `Created`, when `allow_filesystem_fallback=True`).
    4. When no valid date (`>= min_date`) can be deduced: returns `MediaDateResult(date=None, source='none')`
       for routing into `No_Date/`.

    Args:
        file_path (str): Path to the target media file.
        prefer_filename (bool, optional): If True, filename date parsing takes precedence over EXIF.
            Defaults to True.
        allow_filesystem_fallback (bool, optional): If True, falls back to earliest valid OS timestamp
            (`Last Modified` / `Created`) when filename and media metadata yield no valid date.
            Defaults to True.
        min_date (Optional[datetime], optional): Lower bound override; defaults to
            `AppSettings.instance().min_valid_datetime`.

    Returns:
        MediaDateResult: Immutable result containing the resolved datetime, source tag, and detail string.
    """
    if not os.path.isfile(file_path):
        return MediaDateResult(date=None, source="none", detail="File does not exist")

    filename = os.path.basename(file_path)

    # 1. Primary: Filename Date Parsing (if preferred)
    if prefer_filename:
        fn_date = extract_date_from_filename(filename, min_date=min_date)
        if fn_date:
            return MediaDateResult(date=fn_date, source="filename", detail=f"Extracted from name: {filename}")

    # 2. Embedded metadata: EXIF for images or container metadata for videos
    if has_video_extension(file_path) and is_file_a_video(file_path):
        v_date = extract_date_from_video(file_path, min_date=min_date)
        if v_date:
            return MediaDateResult(date=v_date, source="video_metadata", detail="Extracted from video metadata")
    elif has_image_extension(file_path) or is_image_file(file_path):
        img_date = extract_date_from_exif(file_path, min_date=min_date)
        if img_date:
            return MediaDateResult(date=img_date, source="exif", detail="Extracted from EXIF DateTimeOriginal")

    # 3. Filename Date Parsing (fallback if prefer_filename was False)
    if not prefer_filename:
        fn_date = extract_date_from_filename(filename, min_date=min_date)
        if fn_date:
            return MediaDateResult(date=fn_date, source="filename", detail=f"Extracted from name: {filename}")

    # 4. Operating System Filesystem Fallback (Last Modified / Created)
    if allow_filesystem_fallback:
        fs_date = extract_date_from_filesystem(file_path, min_date=min_date)
        if fs_date:
            return MediaDateResult(
                date=fs_date,
                source="filesystem",
                detail="Extracted from file system (Last Modified)",
            )

    # 5. No reliable date found -> routes to No_Date/
    return MediaDateResult(
        date=None,
        source="none",
        detail="No valid creation date found in filename, metadata, or filesystem"
    )
