"""
Module for smart date extraction from media files (photos, videos, documents).

This module implements a priority-based date extraction strategy:
1. Filename pattern parsing (highest priority, immune to filesystem copy/download timestamp distortion).
2. Embedded EXIF tags for images (DateTimeOriginal, DateTimeDigitized, DateTime) via Pillow & exifread.
3. Embedded container metadata for videos (QuickTime / MP4 creation_time) via OpenCV & MoviePy.
4. Optional filesystem creation / modification timestamps (fallback).
5. Unresolved files without reliable dates are categorized with source='none' for 'No_Date/' routing.
"""

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from src.family_album.utility_functions.image_utils import (
    is_image_file,
    _get_image_info,
    _get_image_info_pil,
)
from src.family_album.utility_functions.video_utils import (
    is_file_a_video,
    get_video_metadata,
)


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
            - 'filesystem': Obtained from operating system file timestamps.
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


def is_valid_date(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> bool:
    """
    Validate that year, month, day, hour, minute, second form a realistic past/present calendar datetime.

    Args:
        year (int): 4-digit calendar year (must be between 1970 and current_year + 1).
        month (int): Calendar month (1 to 12).
        day (int): Day of the month (1 to 31).
        hour (int, optional): Hour in 24-hour format (0 to 23). Defaults to 0.
        minute (int, optional): Minute (0 to 59). Defaults to 0.
        second (int, optional): Second (0 to 59). Defaults to 0.

    Returns:
        bool: True if the values construct a valid calendar datetime within permissible bounds, False otherwise.
    """
    current_year = datetime.now().year + 1
    if not (1970 <= year <= current_year):
        return False
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= 31):
        return False
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        return False
    try:
        datetime(year, month, day, hour, minute, second)
        return True
    except ValueError:
        return False


def extract_date_from_filename(filename: str) -> Optional[datetime]:
    """
    Attempts to parse creation datetime directly from a file name string.

    This function scans filenames using an ordered collection of common smartphone,
    camera, screenshot, and messenger timestamp patterns.

    Args:
        filename (str): The name or full path of the file.

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
                    if is_valid_date(year, month, day, hour, minute, second):
                        return datetime(year, month, day, hour, minute, second)
                elif len(groups) == 3:
                    year, month, day = (int(g) for g in groups)
                    if is_valid_date(year, month, day):
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
            dt = datetime.fromtimestamp(raw_ts)
            current_year = datetime.now().year + 1
            if 1990 <= dt.year <= current_year:
                return dt
        except (ValueError, OSError, OverflowError):
            pass

    return None


def extract_date_from_exif(file_path: str) -> Optional[datetime]:
    """
    Extracts datetime from image EXIF metadata tags using Pillow and exifread.

    Inspects standard EXIF date tags including DateTimeOriginal, DateTimeDigitized,
    and Image DateTime, selecting the earliest valid capture date.

    Args:
        file_path (str): Absolute or relative filesystem path to the image file.

    Returns:
        Optional[datetime]: The earliest valid EXIF datetime, or None if EXIF is absent or unparseable.
    """
    if not os.path.isfile(file_path):
        return None

    dates = []

    # 1. Check Pillow EXIF
    try:
        pil_exif = _get_image_info_pil(file_path)
        # 306: DateTime, 36867: DateTimeOriginal, 36868: DateTimeDigitized, 50971: PreviewDateTime
        for tag_id in (36867, 36868, 306, 50971):
            if tag_id in pil_exif:
                val = str(pil_exif[tag_id]).strip()
                dt = _parse_exif_datestring(val)
                if dt:
                    dates.append(dt)
    except Exception:
        pass

    # 2. Check Exifread tags
    try:
        er_tags = _get_image_info(file_path)
        for tag_name in ('EXIF DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime'):
            if tag_name in er_tags:
                val = str(er_tags[tag_name]).strip()
                dt = _parse_exif_datestring(val)
                if dt:
                    dates.append(dt)
    except Exception:
        pass

    if dates:
        return min(dates)
    return None


def _parse_exif_datestring(date_str: str) -> Optional[datetime]:
    """
    Internal helper to parse standard EXIF timestamp string formats.

    Args:
        date_str (str): Raw timestamp string from EXIF (e.g. '2023:05:14 14:30:22').

    Returns:
        Optional[datetime]: Parsed datetime object if format matches, otherwise None.
    """
    if not date_str or date_str == 'None' or len(date_str) < 10:
        return None
    for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y:%m:%d %H:%M', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(date_str[:19], fmt)
            if is_valid_date(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second):
                return dt
        except ValueError:
            continue
    return None


def extract_date_from_video(file_path: str) -> Optional[datetime]:
    """
    Extracts creation datetime from video container metadata.

    Inspects metadata stream tags (such as QuickTime / MP4 creation_time) retrieved
    via MoviePy or OpenCV.

    Args:
        file_path (str): Absolute or relative filesystem path to the video file.

    Returns:
        Optional[datetime]: The parsed video creation datetime, or None if metadata is absent.
    """
    if not os.path.isfile(file_path):
        return None

    try:
        meta = get_video_metadata(file_path)
        if meta and 'infos' in meta and 'metadata' in meta['infos']:
            raw_time = meta['infos']['metadata'].get('creation_time')
            if raw_time:
                for fmt in ('%Y:%m:%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
                    try:
                        clean_str = str(raw_time).strip()
                        if '.' in clean_str:
                            clean_str = clean_str.split('.')[0]
                        dt = datetime.strptime(clean_str, fmt)
                        if is_valid_date(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second):
                            return dt
                    except ValueError:
                        continue
    except Exception:
        pass

    return None


def extract_media_date(
    file_path: str,
    prefer_filename: bool = True,
    allow_filesystem_fallback: bool = False
) -> MediaDateResult:
    """
    Primary interface for extracting creation datetime for a media file according to priority rules:
    1. Filename pattern parsing (highest priority when prefer_filename=True, immune to copy/download distortion).
    2. Embedded media metadata (EXIF DateTimeOriginal for images, container creation_time for videos).
    3. Optional operating system filesystem timestamps (if allow_filesystem_fallback=True).
    4. When no valid date can be deduced: returns a MediaDateResult with date=None and source='none'
       (intended to route the file into a dedicated 'No_Date/' subfolder).

    Args:
        file_path (str): Path to the target media file.
        prefer_filename (bool, optional): If True, filename date parsing takes precedence over EXIF.
            Defaults to True.
        allow_filesystem_fallback (bool, optional): If True, falls back to min(ctime, mtime) if all
            metadata and name parsing fails. Defaults to False.

    Returns:
        MediaDateResult: Immutable result containing the resolved datetime, source tag, and detail string.
    """
    if not os.path.isfile(file_path):
        return MediaDateResult(date=None, source="none", detail="File does not exist")

    filename = os.path.basename(file_path)

    # 1. Primary: Filename Date Parsing (if preferred)
    if prefer_filename:
        fn_date = extract_date_from_filename(filename)
        if fn_date:
            return MediaDateResult(date=fn_date, source="filename", detail=f"Extracted from name: {filename}")

    # 2. Embedded metadata: EXIF for images or container metadata for videos
    if is_file_a_video(file_path):
        v_date = extract_date_from_video(file_path)
        if v_date:
            return MediaDateResult(date=v_date, source="video_metadata", detail="Extracted from video metadata")
    elif is_image_file(file_path):
        img_date = extract_date_from_exif(file_path)
        if img_date:
            return MediaDateResult(date=img_date, source="exif", detail="Extracted from EXIF DateTimeOriginal")

    # 3. Filename Date Parsing (fallback if prefer_filename was False)
    if not prefer_filename:
        fn_date = extract_date_from_filename(filename)
        if fn_date:
            return MediaDateResult(date=fn_date, source="filename", detail=f"Extracted from name: {filename}")

    # 4. Optional Filesystem Fallback
    if allow_filesystem_fallback:
        try:
            stat = os.stat(file_path)
            candidate_times = [stat.st_mtime]
            if hasattr(stat, 'st_ctime'):
                candidate_times.append(stat.st_ctime)
            earliest = min(candidate_times)
            dt = datetime.fromtimestamp(earliest)
            if is_valid_date(dt.year, dt.month, dt.day):
                return MediaDateResult(date=dt, source="filesystem", detail="Filesystem timestamp")
        except Exception:
            pass

    # 5. No reliable date found -> routes to No_Date/
    return MediaDateResult(
        date=None,
        source="none",
        detail="No creation date found in filename or metadata"
    )
