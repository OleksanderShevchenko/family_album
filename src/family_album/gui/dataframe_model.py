from typing import Any

import pandas as pd
from PyQt6 import QtCore
from PyQt6.QtCore import QModelIndex
from pandas import DataFrame


class DataFrameModel(QtCore.QAbstractTableModel):
    def __init__(self, df: DataFrame = DataFrame(), parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent=parent)
        self.__dataframe = df

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation,
                   role: int = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        if orientation == QtCore.Qt.Horizontal:
            try:
                return self.__dataframe.columns.tolist()[section]
            except (IndexError):
                return QtCore.QVariant()
        elif orientation == QtCore.Qt.Vertical:
            try:
                return self.__dataframe.index.tolist()[section]
            except (IndexError):
                return QtCore.QVariant()

    def data(self, index: QModelIndex, role: int = QtCore.Qt.DisplayRole):
        if role != QtCore.Qt.DisplayRole:
            return QtCore.QVariant()
        if not index.isValid():
            return QtCore.QVariant()
        return QtCore.QVariant(str(self.__dataframe.iloc[index.row(), index.column()]))

    def setData(self, index: QModelIndex, value: Any, role: int) -> bool:
        row = self.__dataframe.index[index.row()]
        col = self.__dataframe.columns[index.column()]
        if hasattr(value, 'toPyObject'):
            value = value.toPyObject()
        else:
            dtype = self.__dataframe[col].dtype
            if dtype != object:
                value = None if value == '' else dtype.type(value)
        self.__dataframe.set_value(row, col, value)
        return True

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.__dataframe.index)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.__dataframe.columns)

    def sort(self, column: int, order: int):
        column_name = self.__dataframe.columns.tolist()[column]
        self.layoutAboutToBeChanged.emit()
        self.__dataframe.sort_values(column_name, ascending=order == QtCore.Qt.AscendingOrder, inplace=True)
        self.__dataframe.reset_index(inplace=True, drop=True)
        self.layoutChanged.emit()
