__author__ = "Oleksander Shevchenko"
__contact__ = "alexcad777@meta.ua"
__license__ = """Mit license"""

import sys
import os
import time
import tomllib

# Ensure project root / bundle directory is on sys.path so 'src' package is importable when run directly or via PyInstaller
if getattr(sys, 'frozen', False):
    _bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath("."))
else:
    _this_dir = os.path.dirname(__file__)
    _bundle_dir = os.path.abspath(os.path.join(_this_dir, os.pardir, os.pardir))

if _bundle_dir not in sys.path:
    sys.path.insert(0, _bundle_dir)

from src.family_album.gui.application import create_app, show_splash, run


def get_project_metadata():
    """Dynamically retrieves application name and version from pyproject.toml."""
    pyproject_path = os.path.join(_bundle_dir, "pyproject.toml")
    name = "Family Album"
    version = "0.1.0"
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                poetry_data = data.get("tool", {}).get("poetry", {})
                raw_name = poetry_data.get("name", "family-album")
                name = raw_name.replace("-", " ").title()
                version = poetry_data.get("version", "0.1.0")
        except Exception:
            pass
    return name, version


tool_name, tool_version = get_project_metadata()
__version__ = tool_version


def trap_exc_during_debug(*args):
    # when app raises uncaught exception, print info
    print(args)


def run_main(arguments):
    create_app()
    show_splash(tool_name, tool_version)
    time.sleep(1)
    run(tool_name, tool_version)


if __name__ == '__main__':
    run_main(sys.argv)
