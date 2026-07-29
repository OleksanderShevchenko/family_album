# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

project_root = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(project_root, 'src', 'family_album', 'gui', 'images'), os.path.join('src', 'family_album', 'gui', 'images')),
    (os.path.join(project_root, 'src', 'family_album', 'gui', 'py_ui'), os.path.join('src', 'family_album', 'gui', 'py_ui')),
    (os.path.join(project_root, 'pyproject.toml'), '.'),
]

datas += copy_metadata('imageio')
datas += copy_metadata('moviepy')
datas += copy_metadata('imageio_ffmpeg')

icon_path = os.path.join(project_root, 'src', 'family_album', 'gui', 'images', 'icon.png')
icon_file = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    [os.path.join(project_root, 'src', 'family_album', 'main.py')],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'cv2',
        'exifread',
        'geopy',
        'moviepy',
        'moviepy.audio.fx',
        'imageio',
        'imageio_ffmpeg',
        'PIL',
        'pandas',
        'sqlite3',
        'tomllib',
        'importlib.metadata'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FamilyAlbum' if not sys.platform.startswith('win') else 'FamilyAlbum.exe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
