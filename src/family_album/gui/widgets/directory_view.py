import sys
from os import path
from PyQt6 import QtWidgets, uic, QtCore, QtGui
from PyQt6.QtCore import QDir, pyqtSignal
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import QTreeView, QVBoxLayout, QHBoxLayout, QDialog


class DirectoryView(QtWidgets.QWidget):
    ItemSelected = pyqtSignal(str)

    def __init__(self, parent):
        super(DirectoryView, self).__init__(parent)
        uic.loadUi(path.dirname(__file__) + '/py_ui/directory_view.ui', self)

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
    def on_treeView_clicked(self, index):
        indexItem = self.dir_model.index(index.row(), 0, index.parent())
        filePath = self.dir_model.filePath(indexItem)
        self.ItemSelected.emit(filePath)


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
