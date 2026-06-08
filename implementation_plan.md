# Feature Implementation Plan: Organize Media by Year and Month

We are aiming to introduce a robust, production-ready feature to organize family photos and videos into a structured folder hierarchy (`YYYY/MM/`) based on their metadata creation dates (e.g., EXIF data). 

Currently, there are backend stubs/methods (like `organize_directory_by_year_month` and EXIF readers) present in the codebase. However, they execute synchronously, which freezes the GUI, lack a dedicated target directory selection, and don't provide advanced features like dry-runs, undo actions, or user-guided conflict resolution. 

As a Senior Developer/Architect, I have broken down the future development into the following actionable tasks:

## Proposed Architecture and Tasks

### 1. Asynchronous Execution (Worker Threads)
**Problem:** The current implementation processes files in the main UI thread. For directories with thousands of large media files, this will freeze the PyQt6 GUI.
**Tasks:**
- [ ] Create a `QThread` subclass (e.g., `FileOrganizerWorker`) to encapsulate the file moving and analysis logic.
- [ ] Implement PyQT signals (`pyqtSignal`) in the worker to emit real-time progress (`progress_updated`, `file_moved`, `error_occurred`, `finished`).
- [ ] Refactor `src/family_album/gui/widgets/file_organizer.py` to offload the heavy lifting to this worker thread.

### 2. GUI Enhancements & User Controls
**Problem:** Users cannot select a separate destination folder, leaving the feature to default to the source folder. There's also no visual progress representation specific to the organizing task.
**Tasks:**
- [ ] Update `file_organizer_ui.ui` (or construct it programmatically) to include a "Target Directory" selector alongside the source directory selector.
- [ ] Add a visual "Dry Run" toggle (checkbox) so users can preview where files *will* go without actually moving them.
- [ ] Connect the worker's progress signals to the `main_window.py` progress bar to provide a smooth, continuous progress update.

### 3. Advanced Conflict Resolution
**Problem:** Currently, file conflicts are handled simply by appending `_copyN` to the filename.
**Tasks:**
- [ ] Implement an intelligent conflict strategy: Before appending `_copyN`, perform a fast Blake2b hash comparison. If the files are identical (true duplicates), safely delete or skip the source file rather than duplicating it.
- [ ] If files have the same name but different content, utilize the `_copyN` logic or prompt the user via a UI dialog ("Replace", "Skip", "Keep Both").

### 4. Undo / Rollback Functionality
**Problem:** Moving thousands of files is a destructive action to the directory structure. If a user makes a mistake (e.g., selects the wrong target root), it is difficult to revert.
**Tasks:**
- [ ] Implement a `Journaling System`. During organization, write a lightweight `history.json` or update the SQLite database with the `original_path` and `new_path` of each moved file.
- [ ] Create an "Undo Last Organization" button in the GUI that parses the journal and safely restores files to their original directories.

### 5. Enhanced Metadata Extraction Fallbacks
**Problem:** Some files may lack standard EXIF data or have corrupted metadata.
**Tasks:**
- [ ] Audit `image_utils.py` and `video_utils.py`. Ensure that if `exifread` or `OpenCV` fail to read creation dates, the system gracefully falls back to the OS-level file creation/modification dates.
- [ ] Create an "Unknown Date" default folder (e.g., `TargetRoot/Unknown_Date/`) to neatly store files that completely lack any temporal metadata, instead of skipping them entirely.

---

## User Review Required

> [!IMPORTANT]
> Please review this architectural plan. Because you requested me to act as the Architect and define the tasks *without starting implementation*, I will pause here. 

## Open Questions

> [!QUESTION] 
> 1. Do you agree with adding an SQLite / JSON-based **Undo** feature, or is that out of scope for the MVP (Minimum Viable Product)?
> 2. For identical duplicate files found during organization, should we automatically delete the duplicate, or keep it under the `_copyN` naming convention?

## Verification Plan

- **Automated Tests:** Add `pytest` test cases to verify the Worker thread logic without invoking the UI, test metadata extraction on dummy files, and test the conflict resolution hash checking.
- **Manual Verification:** Open the GUI, select a folder with 50+ mixed media files, set a separate target directory, trigger the organization, and ensure the UI remains responsive and the Progress Bar fills accurately.
