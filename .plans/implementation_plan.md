# Feature Implementation Plan: Organize Media by Year and Month

We have introduced a robust, production-ready feature to organize family photos and videos into a structured folder hierarchy (`YYYY/MM/` and `No_Date/`) based on their metadata creation dates, prioritizing filename capture patterns, with embedded SQLite cataloging (`.db/album.db`) and collision safety.

---

## Architecture and Task Status

### 1. Asynchronous Execution (Worker Threads) — [COMPLETED]
**Problem:** Processing files in the main UI thread freezes the PyQt6 GUI for large archives.
**Status:** Completed.
- [x] Created `QThread` subclass `OrganizerWorker` in `src/family_album_lib/file_organizer_engine.py`.
- [x] Implemented PyQt signals (`analysis_started`, `progress_updated`, `status_message`, `log_event`, `space_error`, `plan_ready`, `finished`, `error_occurred`).
- [x] Refactored `src/family_album/gui/widgets/file_organizer.py` to offload analysis and organization to `OrganizerWorker`.
- [x] Added non-blocking cooperative cancellation via `cancel()` event flag and UI "Stop" button.

### 2. GUI Enhancements & User Controls — [COMPLETED]
**Problem:** Need flexible source/target selection, mode switching, visual plan preview, and real-time progress.
**Status:** Completed.
- [x] Updated `file_organizer_ui.ui` and generated `file_organizer_ui.py` with:
  - Source directory picker.
  - Target directory picker (auto-detects sibling `<source>_organized`).
  - Mode selector: "New Organization" vs "Self-Organization" (in-place).
  - Action selector: "Copy" (default with disk space pre-check) vs "Move".
  - Database status indicator (`.db/album.db`).
  - Multi-column QTableView displaying planned items (`tbl_file_data`).
  - Progress bar and status feedback labels.
- [x] Implemented "Analyze / Preview" mode: constructs plan and populates table without touching files.
- [x] Unlocked and enabled "Organize structure" tab in `main_window.py`.

### 3. Advanced Conflict Resolution & Invariant Safety — [COMPLETED]
**Problem:** Moving/copying files must never delete or overwrite existing media on name collisions.
**Status:** Completed.
- [x] Implemented Blake2b cryptographic hashing (`calculate_file_hash`) for content comparison.
- [x] Added `safe_copy_file` and `safe_move_file`:
  - If content is identical, skips duplicate without deleting source.
  - If content differs or file exists, disambiguates target with `_copyN` suffixes.
- [x] Core invariant: files are **never deleted or overwritten**.

### 4. Smart Date Extraction (Filename Priority + EXIF/Video Metadata + Fallbacks) — [COMPLETED]
**Problem:** Downloaded or messenger photos lose OS filesystem dates; filenames often preserve original capture times.
**Status:** Completed.
- [x] Created `src/family_album/utility_functions/date_extractor.py`:
  - Regex patterns for camera filenames (`IMG_...`, `VID_...`, `PXL_...`, `Screenshot_...`, `WhatsApp...`, etc.).
  - Range validation for dates ($1980 \le \text{year} \le \text{current\_year} + 1$).
  - Fallback to EXIF DateTimeOriginal / video container `creation_time`.
  - Unresolved files route safely to `<target>/No_Date/` instead of failing.

### 5. SQLite Catalog & Disk Space Pre-Checks — [COMPLETED]
**Problem:** Need structured tracking of organized files and protection against running out of disk space during Copy.
**Status:** Completed.
- [x] Created `src/family_album_lib/organizer_db.py`:
  - Embedded SQLite database at `<target_dir>/.db/album.db`.
  - Tables: `organized_files` (pairs `original_path` -> `organized_path`, hash, size, date, source), `organizer_sessions`, `organizer_log`.
  - Actuality verification (`verify_actuality`) to detect deleted/altered files.
- [x] Pre-flight disk space validation (`check_disk_space`):
  - Calculates total bytes needed for copy.
  - Warns user and offers interactive switch to "Move" if storage is insufficient.

---

## Future Roadmap / Backlog (Postponed)

### 6. Undo / Rollback Functionality — [POSTPONED FOR LATER]
**Goal:** Allow users to safely revert the last organization run and restore files to their previous locations.
**Current Status:** Postponed to a future release.
**Foundation Ready:** The SQLite catalog already records every session with complete `(original_path, organized_path)` records in `<target>/.db/album.db`.
**Tasks for future implementation:**
- [ ] Add `rollback_session(session_id)` to `OrganizerDatabase` and `FileOrganizerEngine`.
- [ ] Add an "Undo Last Organization" button in `FileOrganizer` GUI.
- [ ] Implement safe reverse move (`organized_path` -> `original_path`) with validation that original directories exist or are recreated.
- [ ] Add automated pytest suite verifying rollback functionality.

---

## Verification & Test Results

- **Automated Tests:** 50 of 50 test cases passing across all suites (`poetry run pytest`):
  - `test_date_extractor.py` (8 passed)
  - `test_organizer_db.py` (4 passed)
  - `test_file_organizer_engine.py` (6 passed)
  - `test_file_organizer_widget.py` (3 passed)
  - `test_image_utils.py` (4 passed)
  - `test_video_utils.py` (2 passed)
  - `test_duplicate_directory_analysis.py` (3 passed)
  - `test_duplicate_file_analyser_resume.py` (1 passed)
  - `test_duplication_checker_widget.py` (3 passed)
  - `test_duplication_memento.py` (4 passed)
  - `test_database_manager.py` (5 passed)
  - `test_find_duplication.py` (3 passed)
  - `test_logger_and_console.py` (3 passed)
  - `test_about_dialog.py` (1 passed)
