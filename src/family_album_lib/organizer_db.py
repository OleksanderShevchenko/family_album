"""
Catalog database management module for the Media File Organizer.

This module provides the OrganizerDatabase class, which manages an embedded SQLite
database located inside `<target_dir>/.db/album.db`. The database tracks:
- All organized files (original path, target path, file hash, size, capture date, source).
- Sessions of organization (mode, start/end timestamps, counters).
- Detailed audit logs of all actions (copied, moved, skipped, error).
- Actuality verification (checking if cataloged files still exist on disk).
- Thread-safe concurrent access via `check_same_thread=False` and `threading.RLock`.
"""

import os
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any


class OrganizerDatabase:
    """
    Manages the SQLite media catalog stored inside `<target_dir>/.db/album.db`.

    Provides thread-safe transactional database operations, automatic table/index
    schema creation, actuality verification of cataloged files against disk state,
    and session logging.

    Attributes:
        DB_FOLDER_NAME (str): Subdirectory name housing the catalog ('.db').
        DB_FILE_NAME (str): Database file name ('album.db').
        target_dir (str): Absolute filesystem path to the managed media root.
        db_dir (str): Absolute path to the `<target_dir>/.db` directory.
        db_path (str): Absolute path to the `<target_dir>/.db/album.db` file.
    """
    DB_FOLDER_NAME = ".db"
    DB_FILE_NAME = "album.db"

    def __init__(self, target_dir: str):
        """
        Initialize the database connection and ensure schema creation.

        Args:
            target_dir (str): Root destination directory where media files and the `.db/` folder reside.
        """
        self.target_dir = os.path.abspath(target_dir)
        self.db_dir = os.path.join(self.target_dir, self.DB_FOLDER_NAME)
        self.db_path = os.path.join(self.db_dir, self.DB_FILE_NAME)
        self._lock = threading.RLock()
        self._ensure_dir()
        self._conn: Optional[sqlite3.Connection] = None
        self.init_schema()

    def _ensure_dir(self) -> None:
        """Create the `.db` hidden directory if it does not already exist."""
        if not os.path.isdir(self.db_dir):
            os.makedirs(self.db_dir, exist_ok=True)

    @classmethod
    def get_db_path(cls, target_dir: str) -> str:
        """
        Compute the expected database file path for a given root directory.

        Args:
            target_dir (str): Root directory path.

        Returns:
            str: Full path to `<target_dir>/.db/album.db`.
        """
        return os.path.join(os.path.abspath(target_dir), cls.DB_FOLDER_NAME, cls.DB_FILE_NAME)

    @classmethod
    def has_database(cls, target_dir: str) -> bool:
        """
        Check if an organizer database file exists inside `<target_dir>/.db/`.

        Args:
            target_dir (str): Root directory to inspect.

        Returns:
            bool: True if `<target_dir>/.db/album.db` exists, False otherwise.
        """
        if not target_dir or not os.path.isdir(target_dir):
            return False
        db_path = cls.get_db_path(target_dir)
        return os.path.isfile(db_path)

    @classmethod
    def is_valid_database(cls, target_dir: str) -> bool:
        """
        Verify that the database file exists and conforms to the organizer schema.

        Args:
            target_dir (str): Root directory to verify.

        Returns:
            bool: True if the database contains all required tables, False otherwise.
        """
        if not cls.has_database(target_dir):
            return False
        db_path = cls.get_db_path(target_dir)
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
            required_tables = {"organized_files", "organizer_sessions", "organizer_log"}
            return required_tables.issubset(tables)
        except Exception:
            return False

    def get_connection(self) -> sqlite3.Connection:
        """
        Retrieve or open the active SQLite connection with `check_same_thread=False`
        and `row_factory` set to `sqlite3.Row`.

        Returns:
            sqlite3.Connection: Active thread-safe database connection.
        """
        with self._lock:
            if self._conn is None:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
            return self._conn

    def close(self) -> None:
        """Close the active database connection if open."""
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def __enter__(self):
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point closing connection."""
        self.close()

    def init_schema(self) -> None:
        """
        Initialize the SQLite schema creating tables and indexes if they do not exist.

        Tables created:
            - `organized_files`: Catalogs every processed photo/video.
            - `organizer_sessions`: Tracks executions of organization runs.
            - `organizer_log`: Detailed audit logs of file actions.
        """
        with self._lock:
            conn = self.get_connection()
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS organized_files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_name TEXT NOT NULL,
                        original_path TEXT NOT NULL,
                        organized_path TEXT NOT NULL UNIQUE,
                        file_size INTEGER NOT NULL,
                        file_hash TEXT NOT NULL,
                        date_taken TEXT,
                        date_source TEXT DEFAULT 'none',
                        is_video INTEGER NOT NULL DEFAULT 0,
                        resolution TEXT DEFAULT '',
                        maker TEXT DEFAULT '',
                        organized_at TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'organized'
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_org_hash ON organized_files(file_hash)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_org_path ON organized_files(organized_path)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_org_date ON organized_files(date_taken)")

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS organizer_sessions (
                        session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        start_time TEXT NOT NULL,
                        end_time TEXT,
                        source_dir TEXT NOT NULL,
                        target_dir TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        total_processed INTEGER DEFAULT 0,
                        files_organized INTEGER DEFAULT 0,
                        files_skipped INTEGER DEFAULT 0,
                        files_errors INTEGER DEFAULT 0
                    )
                """)

                conn.execute("""
                    CREATE TABLE IF NOT EXISTS organizer_log (
                        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER,
                        file_path TEXT NOT NULL,
                        action TEXT NOT NULL,
                        message TEXT DEFAULT '',
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES organizer_sessions (session_id)
                    )
                """)

    def start_session(
        self,
        source_dir: str,
        target_dir: str,
        mode: str,
        action_type: str
    ) -> int:
        """
        Record the commencement of an organization session.

        Args:
            source_dir (str): Origin directory scanned for files.
            target_dir (str): Destination directory where files are organized.
            mode (str): 'new_organization' or 'self_organization'.
            action_type (str): 'copy' or 'move'.

        Returns:
            int: The unique identifier `session_id` of the newly created session.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            conn = self.get_connection()
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO organizer_sessions (start_time, source_dir, target_dir, mode, action_type)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (now_str, os.path.abspath(source_dir), os.path.abspath(target_dir), mode, action_type)
                )
                return cursor.lastrowid

    def finish_session(
        self,
        session_id: int,
        total_processed: int,
        files_organized: int,
        files_skipped: int,
        files_errors: int
    ) -> None:
        """
        Record the completion and summary statistics for an organization session.

        Args:
            session_id (int): Session identifier returned by `start_session`.
            total_processed (int): Total number of files evaluated.
            files_organized (int): Number of files successfully moved or copied.
            files_skipped (int): Number of duplicate or bypassed files.
            files_errors (int): Number of files that encountered errors.
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            conn = self.get_connection()
            with conn:
                conn.execute(
                    """
                    UPDATE organizer_sessions
                    SET end_time = ?, total_processed = ?, files_organized = ?, files_skipped = ?, files_errors = ?
                    WHERE session_id = ?
                    """,
                    (now_str, total_processed, files_organized, files_skipped, files_errors, session_id)
                )

    def log_action(
        self,
        session_id: Optional[int],
        file_path: str,
        action: str,
        message: str = ""
    ) -> None:
        """
        Append an audit entry into `organizer_log`.

        Args:
            session_id (Optional[int]): Associated session identifier, if any.
            file_path (str): Path of the file being acted upon.
            action (str): Action descriptor ('copied', 'moved', 'skipped', 'error', 'verified').
            message (str, optional): Descriptive details or error explanation. Defaults to "".
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._lock:
            conn = self.get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO organizer_log (session_id, file_path, action, message, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, file_path, action, message, now_str)
                )

    def record_organized_file(
        self,
        file_name: str,
        original_path: str,
        organized_path: str,
        file_size: int,
        file_hash: str,
        date_taken: Optional[datetime],
        date_source: str,
        is_video: bool,
        resolution: str = "",
        maker: str = "",
        status: str = "organized"
    ) -> None:
        """
        Insert or update a catalog record in `organized_files`.

        Args:
            file_name (str): Basename of the file.
            original_path (str): Origin file path prior to organization.
            organized_path (str): Final target path in the organized hierarchy.
            file_size (int): Size of the file in bytes.
            file_hash (str): Cryptographic checksum (Blake2b) of file contents.
            date_taken (Optional[datetime]): Deduced creation/taken timestamp.
            date_source (str): Identifier of date origin ('filename', 'exif', etc.).
            is_video (bool): True if video file, False otherwise.
            resolution (str, optional): Pixel resolution string (e.g. '1920x1080'). Defaults to "".
            maker (str, optional): Camera or device manufacturer. Defaults to "".
            status (str, optional): Status tag ('organized', 'duplicate', etc.). Defaults to "organized".
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dt_str = date_taken.strftime("%Y-%m-%d %H:%M:%S") if date_taken else None
        with self._lock:
            conn = self.get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO organized_files
                    (file_name, original_path, organized_path, file_size, file_hash, date_taken, date_source,
                     is_video, resolution, maker, organized_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(organized_path) DO UPDATE SET
                        original_path = excluded.original_path,
                        file_size = excluded.file_size,
                        file_hash = excluded.file_hash,
                        date_taken = excluded.date_taken,
                        date_source = excluded.date_source,
                        is_video = excluded.is_video,
                        resolution = excluded.resolution,
                        maker = excluded.maker,
                        organized_at = excluded.organized_at,
                        status = excluded.status
                    """,
                    (file_name, original_path, organized_path, file_size, file_hash, dt_str, date_source,
                     1 if is_video else 0, resolution, maker, now_str, status)
                )

    def find_by_hash(self, file_hash: str) -> Optional[dict]:
        """
        Search for an existing catalog record matching the specified file hash.

        Args:
            file_hash (str): Blake2b checksum to locate.

        Returns:
            Optional[dict]: Dictionary representation of the matching record, or None if not found.
        """
        with self._lock:
            conn = self.get_connection()
            cursor = conn.execute("SELECT * FROM organized_files WHERE file_hash = ? LIMIT 1", (file_hash,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def find_by_organized_path(self, organized_path: str) -> Optional[dict]:
        """
        Search for an existing catalog record matching the specified destination path.

        Args:
            organized_path (str): Target path to locate.

        Returns:
            Optional[dict]: Dictionary representation of the matching record, or None if not found.
        """
        with self._lock:
            conn = self.get_connection()
            cursor = conn.execute("SELECT * FROM organized_files WHERE organized_path = ? LIMIT 1", (organized_path,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_organized_files(self) -> List[dict]:
        """
        Retrieve all file records from `organized_files`.

        Returns:
            List[dict]: List of all records as dictionaries.
        """
        with self._lock:
            conn = self.get_connection()
            cursor = conn.execute("SELECT * FROM organized_files")
            return [dict(row) for row in cursor.fetchall()]

    def count_organized_files(self) -> int:
        """
        Count total number of entries recorded in `organized_files`.

        Returns:
            int: Total record count.
        """
        with self._lock:
            conn = self.get_connection()
            cursor = conn.execute("SELECT COUNT(*) FROM organized_files")
            return cursor.fetchone()[0]

    def verify_catalog_actuality(self) -> Dict[str, Any]:
        """
        Validates all cataloged records against actual disk contents.

        Checks:
        1. Whether the file still exists at `organized_path`.
        2. Whether the file size matches the database entry.

        Updates record status in the database to 'missing', 'modified', or 'organized'.

        Returns:
            Dict[str, Any]: Verification summary statistics containing:
                - 'total_records': Total files cataloged.
                - 'valid_count': Files verified intact on disk.
                - 'missing_count': Files recorded in DB but missing from disk.
                - 'modified_count': Files on disk whose sizes differ from DB.
                - 'missing_files': List of filesystem paths that could not be found.
        """
        with self._lock:
            conn = self.get_connection()
            all_records = self.get_all_organized_files()

            valid_count = 0
            missing_count = 0
            modified_count = 0
            missing_files = []

            with conn:
                for rec in all_records:
                    file_path = rec["organized_path"]
                    record_id = rec["id"]
                    if not os.path.isfile(file_path):
                        missing_count += 1
                        missing_files.append(file_path)
                        conn.execute("UPDATE organized_files SET status = 'missing' WHERE id = ?", (record_id,))
                    else:
                        try:
                            curr_size = os.path.getsize(file_path)
                            if curr_size != rec["file_size"]:
                                modified_count += 1
                                conn.execute("UPDATE organized_files SET status = 'modified' WHERE id = ?", (record_id,))
                            else:
                                valid_count += 1
                                if rec["status"] != "organized":
                                    conn.execute("UPDATE organized_files SET status = 'organized' WHERE id = ?", (record_id,))
                        except OSError:
                            missing_count += 1
                            missing_files.append(file_path)
                            conn.execute("UPDATE organized_files SET status = 'missing' WHERE id = ?", (record_id,))

            return {
                "total_records": len(all_records),
                "valid_count": valid_count,
                "missing_count": missing_count,
                "modified_count": modified_count,
                "missing_files": missing_files,
            }
