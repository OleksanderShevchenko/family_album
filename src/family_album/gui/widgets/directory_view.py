"""
Directory tree browser widget for the Family Album application.

Displays the local filesystem folder hierarchy using QFileSystemModel and QTreeView,
allowing users to select a directory and programmatically restoring the last selected
directory on application startup.
"""

import os
import sys
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import QDir, pyqtSignal
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import QVBoxLayout, QDialog

from src.family_album.gui.widgets.py_ui.directory_view import Ui_Form


class DirectoryView(QtWidgets.QWidget, Ui_Form):
    """
    Left-pane filesystem directory tree browser.

    Signals:
        ItemSelected (str): Emitted with the selected directory path when a node is clicked.
    """
    ItemSelected = pyqtSignal(str)

    def __init__(self, parent=None):
        """
        Initialize the DirectoryView widget and configure the QFileSystemModel.

        Args:
            parent (Optional[QtWidgets.QWidget]): Parent widget or MainWindow.
        """
        super().__init__(parent)
        self.setupUi(self)

        self.dir_model = QFileSystemModel()
        self.dir_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
        self.dir_model.setRootPath(self.dir_model.myComputer())
        self.indexRoot = self.dir_model.index(self.dir_model.rootPath())
        self.directory_tree.setModel(self.dir_model)
        self.directory_tree.setRootIndex(self.indexRoot)
        self.directory_tree.clicked.connect(self.on_treeView_clicked)
        self.directory_tree.setColumnWidth(0, 200)
        # Hide the second column ('size') as far as we do not show files
        self.directory_tree.hideColumn(1)
        # Sort directories by name in ascending order
        self.directory_tree.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        # Set the width for better visual presentation of directory names
        self.directory_tree.setColumnWidth(0, 400)

    @QtCore.pyqtSlot(QtCore.QModelIndex)
    def on_treeView_clicked(self, index: QtCore.QModelIndex) -> None:
        """
        Handle user clicks on a directory node in the tree view.

        Args:
            index (QtCore.QModelIndex): Clicked model index.
        """
        indexItem = self.dir_model.index(index.row(), 0, index.parent())
        filePath = self.dir_model.filePath(indexItem)
        self.ItemSelected.emit(filePath)

    def select_directory(self, directory_path: str) -> bool:
        """
        Programmatically expand, scroll to, and select a directory path in the tree view.

        Args:
            directory_path (str): Filesystem directory path to select.

        Returns:
            bool: True if the directory exists and was selected, False otherwise.
        """
        if not directory_path or not os.path.isdir(directory_path):
            return False
        norm_path = os.path.normpath(directory_path)
        index = self.dir_model.index(norm_path)
        if not index.isValid():
            return False

        # Expand all parent nodes up to root
        parent_idx = index.parent()
        while parent_idx.isValid():
            self.directory_tree.expand(parent_idx)
            parent_idx = parent_idx.parent()

        self.directory_tree.setCurrentIndex(index)
        self.directory_tree.scrollTo(index, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter)
        return True


if __name__ == "__main__":
    _app = QtWidgets.QApplication(sys.argv)
    dialog = QDialog()
    dir_viewer = DirectoryView(dialog)
    layout1 = QVBoxLayout()
    # insert input widget to this layout
    layout1.addWidget(dir_viewer)
    dialog.setLayout(layout1)
    dialog.show()
    _app.exec()
