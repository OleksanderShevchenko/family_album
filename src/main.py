__author__ = "Oleksander Shevchenko"
__contact__ = "alexcad777@meta.ua"
__version__ = "0.1"
__license__ = """<SOME LICENSE TEXT HERE>"""

import sys
import time

from PyQt5.QtWidgets import QApplication

from src.gui.main_window import MainWindow

#
# import sys
# import time
#
# from PyQt5.QtWidgets import QApplication
#
# from widgets.data_source import DataSource
# from gui.main_window import MainWindow
# from gui.plot_canvas import PlotCanvas

# set name and current version of the tool


tool_name = 'Family Album tool'
tool_version = '0.0.1'
from src.gui.application import create_app, show_splash, run


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

