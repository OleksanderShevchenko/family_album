# Family Album

Family Album is a Python-based tool with a PyQt6 Graphical User Interface intended to help organize your family photos and videos.

## Features

- **Directory Analysis**: Scans directories to provide statistics on file and folder counts.
- **Duplicate Detection**: Uses Blake2b hashing and multithreading to quickly and accurately identify duplicate files in your albums.
- **Media Organization**: (In Development) Organize images and videos into folders by Year and Month using EXIF and metadata.

## Tech Stack

- **Python**: >= 3.10
- **GUI Framework**: PyQt6
- **Media Processing**: OpenCV (`opencv-python`), `moviepy`, `Pillow`, `exifread`
- **Data Handling**: `pandas`
- **Dependency Management**: Poetry

## How to Run

1. Make sure you have [Poetry](https://python-poetry.org/) installed.
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Activate the virtual environment and run the application:
   ```bash
   poetry run python src/family_album/main.py
   ```
   *Alternatively, create your own virtual environment, install requirements from `requirements.txt` or `pyproject.toml`, and run `main.py` from the `src/` folder.*
