__author__ = "Oleksander Shevchenko"
__contact__ = "alexcad777@meta.ua"
__version__ = "0.1.0"
__license__ = """Mit license"""

import sys
import time

from src.family_album.gui.application import create_app, show_splash, run


tool_name = 'Family Album tool'
tool_version = __version__


def trap_exc_during_debug(*args):
    # when app raises uncaught exception, print info
    print(args)


def run_main(arguments):
    create_app()
    show_splash(tool_name, tool_version)
    time.sleep(2)
    run(tool_name, tool_version)


if __name__ == '__main__':
    run_main(sys.argv)

