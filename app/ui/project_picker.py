"""A regular dropdown list, rather than a platform menu with scroll arrows."""
from PySide6.QtWidgets import QComboBox,QListView,QStyleFactory
from PySide6.QtCore import Qt


class ProjectPicker(QComboBox):
    def __init__(self):
        super().__init__()
        # Fusion uses a list popup (SH_ComboBox_Popup=False). Some platform
        # menu styles instead constrain the popup around the current item.
        self._popup_style=QStyleFactory.create('Fusion')
        self.setStyle(self._popup_style)
        view=QListView()
        view.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(view)
        self.setMaxVisibleItems(10)
        self.setStyleSheet('QComboBox { combobox-popup: 0; } QComboBox QAbstractItemView { background: #151b27; color: #e4e9f2; border: 1px solid #424b60; selection-background-color: #30283f; padding: 2px; } QComboBox QAbstractItemView::item { min-height: 28px; padding: 2px 8px; }')
