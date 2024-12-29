import sys
import os
import time

from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5 import QtWidgets

_splash = None
_app = None
_image_path = os.path.dirname(__file__) + os.sep + 'images'


def create_app():
    global _app
    _app = QtWidgets.QApplication(sys.argv)


def show_splash(name, version):
    global _splash
    # Create splash screed
    splash_pix = QtGui.QPixmap(_image_path + '/splashscreen.png')
    _splash = QtWidgets.QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    _splash.showMessage(name + ' v' + version + ' is loading. Please wait...', Qt.AlignHCenter |
                        Qt.AlignBottom, Qt.black)
    _splash.show()


def run(name, version):
    global _app
    global _splash
    if _app is None:
        raise Exception('Call create_app first')
    from src.family_album.gui.main_window import MainWindow as Main_Window
    # Create QT application
    QtWidgets.QApplication.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
    QtWidgets.QApplication.setWindowIcon(QtGui.QIcon(_image_path + '/icon.png'))

    # Create main window
    window = Main_Window(name, version)
    window.show()
    if _splash is not None:
        time.sleep(1)
        _splash.finish(window)
    sys.exit(_app.exec_())