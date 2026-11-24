# Feature Implementation Plan: Organize Media by Year and Month

We have introduced a feature to organize family photos and videos into a structured folder hierarchy (`YYYY/MM/` and `No_Date/`) based on their capture dates, prioritizing filename patterns, with embedded SQLite cataloging (`.db/album.db`) and collision safety.

---

## 1. Audit of Current State

### 1.1. Completed Well (`[COMPLETED]`)
- [x] **Smart Date Extraction (`date_extractor.py`)**: Prioritizes filename patterns over EXIF/video container metadata; routes unresolved files to `<target>/No_Date/`.
- [x] **SQLite Catalog & Disk Pre-Checks (`organizer_db.py`)**: Embedded SQLite catalog at `<target_dir>/.db/album.db` (`organized_files`, `organizer_sessions`, `organizer_log`), catalog actuality verification, and pre-copy disk capacity checks (`check_disk_space`).
- [x] **Conflict Resolution & Safety Invariant (`file_organizer_engine.py`)**: Never deletes or overwrites user files; disambiguates collisions with `_copyN` suffixes and compares Blake2b hashes.
- [x] **Core GUI Layout (`file_organizer.py` & `file_organizer_ui.py`)**: Source/Target folder pickers, New Organization vs Self-Organization modes, Copy vs Move radio controls, preview table, and enabled tab in `MainWindow`.

### 1.2. Refactored & Optimized (`[COMPLETED]`)
- [x] **Eliminate `VideoFileClip` (`ffmpeg`) invocation on non-video files in `video_utils.is_file_a_video()`**: Avoid spawning OS subprocesses for `.jpg`/`.png` files; add `get_video_resolution_fast()` via OpenCV and ensure `cap.release()` / `clip.close()` in `finally` blocks.
- [x] **Single-pass Image Metadata Inspection (`image_utils.py`, `date_extractor.py`)**: Replace 5–7 repeated file opens per photo with single-pass Pillow header inspection (`inspect_image_fast`) and direct Pillow EXIF Sub-IFD (`0x8769`) parsing.
- [x] **Parallelize Single-Threaded Loops in `FileOrganizerEngine`**: Replace sequential loops in `scan_and_plan()` and `execute_plan()` with `ThreadPoolExecutor(max_workers=...)` and reuse already-analyzed plans.
- [x] **Replace Hardcoded 200 Threads in `ResumableDuplicateAnalyser`**: Read `worker_threads` dynamically from `AppSettings`.

---

## 2. Step-by-Step Implementation Roadmap (Incremental Commits)

### Step 1: Application Settings (`.settings/settings.json`) & `Tools -> Settings...` Dialog — `[COMPLETED]`
- [x] Create `src/family_album_lib/app_settings.py` (`AppSettings`):
  - Store settings in `<app_dir>/.settings/settings.json` (next to executable or project root).
  - On first launch, detect logical CPU cores (`os.cpu_count()`) and set default `worker_threads = cpu_cores * 2`, immediately creating `.settings/settings.json`.
  - Persist `worker_threads` and `last_selected_directory`.
- [x] Create `src/family_album/gui/dialogs/settings_dialog.py` (`SettingsDialog`):
  - Display detected CPU cores and recommended thread count (`cores × 2`).
  - Provide SpinBox + Slider for `worker_threads` (`1..256`) and reset button.
  - Display/edit `last_selected_directory`.
- [x] Integrate into `MainWindow`, `DirectoryView`, `DuplicationChecker`, and `FileOrganizer`:
  - Add `Tools -> Settings...` menu item (`Ctrl+,`).
  - Restore `last_selected_directory` in `DirectoryView` on startup and update on directory selection.
  - Pass `AppSettings.worker_threads` to both `ResumableDuplicateAnalyser` and `FileOrganizer` / `OrganizerWorker`.
- [x] Add unit tests in `tests/test_app_settings.py` (5 passed).

### Step 2: Metadata Extraction Performance Optimization — `[COMPLETED]`
- [x] Optimize `video_utils.py` (`has_video_extension`, `is_file_a_video` with fast Pillow animated GIF check, `get_video_resolution_fast`, proper `cap.release()` / `clip.close()` resource cleanup).
- [x] Optimize `image_utils.py` (`has_image_extension`, `inspect_image_fast`, context-managed Pillow open) and `date_extractor.py` (`extract_date_from_pil_exif` via Pillow Sub-IFD `0x8769` + `exifread` fallback with `details=False`).
- [x] Add thread-safety (`check_same_thread=False` and `RLock`) to `OrganizerDatabase` (`organizer_db.py`).
- [x] Verify and expand unit tests (`test_video_utils.py`, `test_image_utils.py`, `test_date_extractor.py`, `test_organizer_db.py`).

### Step 3: Multithreaded Analysis & Organization Pipeline (`ThreadPoolExecutor`) — `[COMPLETED]`
- [x] Refactor `FileOrganizerEngine.scan_and_plan()` to analyze files concurrently using `ThreadPoolExecutor(max_workers=...)` with single-pass `_inspect_single_file()` and throttled progress callbacks.
- [x] Refactor `FileOrganizerEngine.execute_plan()` to hash and copy/move files concurrently using `ThreadPoolExecutor(max_workers=...)` with atomic `_reserve_unique_destination()` + `collision_lock` around filename collision disambiguation.
- [x] Reuse existing preview plan (`existing_plan`) when starting organization from UI and optimize large table rendering / progress updates in `FileOrganizer`.
- [x] Add 4 unit tests for multithreaded execution, collision stress testing, plan reuse, and MoviePy bypass in `test_file_organizer_engine.py` (54 passed).

### Step 4: Memento Pattern for File Organizer (Pause / Save State / Resume) — `[COMPLETED]`
- [x] Create `src/family_album_lib/organizer_memento.py` (`OrganizerStatus`, `OrganizerMemento`, `OrganizerSaveManager`) supporting both `analyze` and `organize` phases with `verify_location()`.
- [x] Add `to_dict()` / `from_dict()` serialization to `MediaDateResult`, `OrganizePlanItem`, and `OrganizeStats`; add resumable `existing_items`, `initial_stats`, and `paused` signal to `FileOrganizerEngine` / `OrganizerWorker`.
- [x] Add `Save State` and `Resume` buttons to `FileOrganizer` widget and support pausing/saving/resuming from the exact checkpoint for both analysis and organization.
- [x] Add 5 unit tests in `tests/test_organizer_memento.py` (59 passed total).

### Step 5: Configurable Minimum Valid Date (`2000-01-01`) & Filesystem `Last Modified` Fallback — `[COMPLETED]`
- [x] Add `min_valid_date` (`"2000-01-01"` default) to `AppSettings` (`.settings/settings.json`) and a `QDateEdit` selector + reset button to `SettingsDialog` (`Tools -> Settings...`).
- [x] Enforce `min_valid_date` across all date sources in `date_extractor.py` to reject bogus `1970`/`1980` epoch dates from Google Photos animations/collages and ZIP archives.
- [x] Enable OS filesystem timestamp fallback (`extract_date_from_filesystem` using earliest valid `st_mtime`/`st_ctime`/`st_birthtime`, rejecting pre-`min_valid_date` `st_mtime` placeholders) in `FileOrganizerEngine._inspect_single_file()` as Priority #3 before routing to `No_Date/`.
- [x] Add unit tests in `test_app_settings.py`, `test_date_extractor.py`, and `test_file_organizer_engine.py` with generated JPEG (bogus 1970/1980 EXIF + valid Last Modified) and generated AVI video (63 passed).

### Step 6: Multithreaded Resumable Duplicate Verification (`ResumableDuplicatesVerifier`) — `[COMPLETED]`
- [x] Created `src/family_album_lib/resumable_duplicates_verifier.py` (`ResumableDuplicatesVerifier`), modeled after `ResumableDuplicateAnalyser`:
  - Uses `ThreadPoolExecutor(max_workers=AppSettings.worker_threads)` to verify only detected duplicate groups (comparing exact byte sizes of original vs. candidate duplicates).
  - Supports cooperative pause/stop, progress/log callbacks, and Memento state save/restore so verification can be resumed even after restarting the app on another day.
  - Excludes any size mismatches into `mismatched_files` with `WARNING` logs to protect against hash collisions.
- [x] Extended `DuplicationCheckMemento` (`duplication_memento.py`) with `DuplicationStage` and a `stage` field (`"hashing"` default for backward compatibility, or `"verifying"`), preserving full Stage 1 results (`files_hashes`, `processed_files`, `files_count`, `subdirectories_count`) alongside Stage 2 verification checkpoint fields (`verified_duplicates`, `verified_originals`, `mismatched_files`) so resuming after an app restart retains all Stage 1 data without re-hashing.
- [x] Added a single new **`Verify Duplicates`** button to `DuplicationChecker` (`duplication_checker.py`); reused existing `Stop / Pause`, `Save State`, and `Resume Check` buttons by dispatching internally based on the active/saved stage (`hashing` vs `verifying`).
- [x] Added 6 unit & GUI integration tests in `tests/test_duplicates_verifier.py` covering multithreaded size verification, simulated hash collisions, and pause/save/resume across sessions (69 passed total).

### Step 7: Final Polish & Repository Hygiene — `[NEXT]`
- [ ] Use `is_valid_database()` and invoke `verify_catalog_actuality()` during Self-Organization with log/status summary.
- [ ] Update `docs/organizer_diagram.md` and `README.md`.
- [ ] Remove unused `src/family_album/gui/dataframe_model.py` and add `saves/`, `tests/saves/`, `*.db` to `.gitignore`.

---

## 3. Postponed Backlog
- **Undo / Rollback Functionality** — `[POSTPONED FOR LATER]`
