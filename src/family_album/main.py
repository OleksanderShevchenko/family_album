__author__ = "Oleksander Shevchenko"
__contact__ = "oleksander.shevchenko777@gmail.com"
__license__ = """Mit license"""
__tool_name__ = "Family Album"

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
                authors = poetry_data.get("authors", "Oleksander_Shevchenko <oleksander.shevchenko777@gmail.com>")[0]
                author_and_contact = authors.split(" ")
                assert len(author_and_contact) == 2, "Incorrect format of authors string"
                author = author_and_contact[0]
                contact = author_and_contact[1]
        except Exception:
            pass
    return name, version, author, contact


tool_name, tool_version, author, contact = get_project_metadata()
__version__ = tool_version
__author__ = author
__contact__ = contact
__tool_name__ = tool_name

def trap_exc_during_debug(*args):
    # when app raises uncaught exception, print info
    print(args)


def run_main(arguments):
    create_app()
    show_splash(__tool_name__, __version__)
    time.sleep(1)
    run(__tool_name__, __version__)


if __name__ == '__main__':
    run_main(sys.argv)
