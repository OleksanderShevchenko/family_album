# 📸 Family Album

**Family Album** is a modern Python desktop application with a PyQt6 Graphical User Interface designed to help you organize, search, and manage your family photo and video archives efficiently.

---

## ✨ Features

- 💾 **Resumable Duplicate File Analysis**: Uses BLAKE2b cryptographic hashing and multithreading to identify duplicate files rapidly. Supports pausing, saving session state (Memento Pattern), and resuming checks at any time.
- 📁 **Content-Based Folder Duplicate Detection**: Identifies exact duplicate directories by analyzing file content hashes, file count, and total byte size. **Filename-Agnostic**: Detects duplicate folders even if files or subfolders have been renamed.
- 🖼️ 🎥 **Visual Photo & Video Comparison**: Side-by-side media preview for photos and videos using an integrated OpenCV video player (`VideoPlayerWidget`) for smooth playback without codec hardware acceleration errors.
- 📋 **Real-Time Logging Console (`LogConsoleWidget`)**: Embedded collapsible console displaying formatted log records with emojis and palette-safe colors readable in both **Light** and **Dark** desktop themes. Simultaneously logs all events (including `DEBUG`) to session files under `logs/`.
- ℹ️ **Menu Bar & Theme-Adaptive About Dialog**: Features `File -> Exit` (`Alt+F4`), `Help -> About...` modal dialog, and automatic directory tree locking during active analysis to prevent mid-scan conflicts.
- 📁 **Media Organizer**: *(Under Development 🚀)* Automatic organization of photos and videos into structured folders by Year/Month using EXIF and metadata.

---

## 🛠️ Tech Stack

- **Python**: `>= 3.10, < 3.14`
- **GUI Framework**: PyQt6
- **Media & Video Processing**: OpenCV (`opencv-python`), `moviepy`, `Pillow`, `exifread`
- **Data Handling**: `pandas`
- **Packaging**: PyInstaller
- **Dependency Management**: Poetry

---

## 🚀 How to Run

1. Make sure you have [Poetry](https://python-poetry.org/) installed.
2. Install project dependencies:
   ```bash
   poetry install
   ```
3. Run the application:
   ```bash
   poetry run python src/family_album/main.py
   ```

---

## 🧪 Running Tests

The test suite includes 29 unit and integration tests covering duplicate detection, Memento resumption, logger console filtering, OpenCV video playback, and directory duplicate analysis.

Run all tests using pytest:
```bash
poetry run pytest
```

---

## 📦 Building Executable (Windows & Linux)

The project uses **PyInstaller** to build standalone, zero-dependency executable binaries for both Windows and Linux without requiring Python or external libraries installed on target machines.

### Build Executable Command

To build the executable for your current operating system, run:
```bash
poetry run pyinstaller family_album.spec
```

### Build Artifacts

- **Windows**: Generates a single standalone executable `dist/FamilyAlbum.exe`.
- **Linux**: Generates an executable binary `dist/FamilyAlbum` (run `chmod +x dist/FamilyAlbum` if needed, then execute `./dist/FamilyAlbum`).

---

## 📜 License & Author

- **Author**: Oleksandr Shevchenko ([oleksander.shevchenko777@gmail.com](mailto:oleksander.shevchenko777@gmail.com))
- **License**: MIT License
- **Copyright**: © 2026 Oleksandr Shevchenko
