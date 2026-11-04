STYLE = """
* { font-family: 'Segoe UI', 'Malgun Gothic'; font-size: 12px; color: #edf0f8; }
QMainWindow, QWidget { background: #0c0f17; }
QFrame#panel { background: #1c2232; border: 1px solid #2a3143; border-radius: 10px; }
QFrame#panel QLabel, QFrame#panel QWidget { background: transparent; }
QLabel#brand { font-size: 17px; font-weight: 700; }
QLabel#heading { font-size: 14px; font-weight: 600; }
QLabel#muted { color: #99a4bb; }
QLabel#badge { color: #c0a8ff; background: #302747; border-radius: 5px; padding: 5px 9px; }
QFrame#panel QLabel#preview { background: #090b12; border: 1px solid #30364a; border-radius: 8px; color: #9ca4ba; font-size: 15px; }
QPushButton { background: #23283a; border: 1px solid #343a50; border-radius: 6px; padding: 9px 13px; }
QPushButton:hover { background: #34314e; border-color: #8b66e8; }
QPushButton:checked { background: #362953; color: #cdb8ff; border-color: #7655c0; }
QPushButton:disabled { color: #747c94; background: #202434; border-color: #2a3043; }
QPushButton#primary { background: #8655df; color: white; border: none; }
QPushButton#primary:disabled { background: #44345f; color: #a495bc; }
QLineEdit, QComboBox { background: #111522; border: 1px solid #343b50; border-radius: 6px; padding: 8px; }
QListWidget { background: #121623; border: 1px dashed #3a4156; border-radius: 8px; padding: 12px; }
QSplitter::handle { background: #0c0f17; }
QSplitter::handle:hover { background: #7750bf; }
QStatusBar { color: #99a4bb; border-top: 1px solid #2a3143; }
QToolTip { background: #302747; color: #eee; border: 1px solid #8655df; }
"""

STYLE += '\nQPushButton { background: #1c2232; border: 1px solid #30394e; border-radius: 6px; }\nQPushButton:checked { background: #2b2342; color: #d3bdff; border: 1px solid #554170; border-bottom: 3px solid #9567ff; }\nQPushButton:disabled, QPushButton#primary:disabled { background: #202636; color: #707d96; border: 1px solid #2c3447; }\nQFrame#panel QLabel#badge { color: #b69bdc; background: #282337; border: none; }\nQLabel#badge { color: #d1baff; background: #302343; }\nQFrame#panel QLabel#preview { background: #080b12; border: 1px solid #364058; }\nQFrame#navPanel, QFrame#mediaPanel { background: #141925; border: 1px solid #252e40; border-radius: 10px; }\nQFrame#navPanel QWidget, QFrame#mediaPanel QWidget { background: transparent; }\nQFrame#navPanel QPushButton { background: #1c2232; border: 1px solid #30394e; }\nQFrame#mediaPanel QListWidget { background: #101521; border: 1px dashed #354057; }\nQLineEdit { background: #141925; border-color: #374258; }\nQSlider::groove:horizontal { height: 4px; background: #30394f; border-radius: 2px; }\nQSlider::sub-page:horizontal { background: #9567ff; border-radius: 2px; }\nQSlider::handle:horizontal { width: 12px; margin: -5px 0; background: #c6aaff; border: 2px solid #9567ff; border-radius: 6px; }\n\nQPushButton#navItem { border: 1px solid #30394e; border-left: 3px solid transparent; padding: 9px 8px; }\nQPushButton#navItem:checked { background: #2b2342; color: #d3bdff; border: 1px solid #554170; border-left: 3px solid #9567ff; }\nQPushButton:enabled:hover { background: #30283f; border-color: #9567ff; }\nQPushButton:enabled:pressed { background: #221c32; }\nQPushButton#primary:enabled { background: #9567ff; color: #ffffff; border: 1px solid #ad89ff; }\nQPushButton#primary:enabled:hover { background: #a47cff; border: 1px solid #c6aaff; }\nQPushButton#primary:enabled:pressed { background: #7847d1; border: 1px solid #9567ff; }\nQPushButton:focus { outline: none; border-color: #c6aaff; }\n'

STYLE += """
QSlider::sub-page:horizontal:disabled { background: #354057; }
QSlider::handle:horizontal:disabled { background: #616d85; border-color: #354057; }
"""

STYLE += """
QListWidget#mediaList { background: #101521; padding: 4px; border: 1px solid #354057; }
QListWidget#mediaList::item { min-height: 30px; padding: 2px 6px; border: 1px solid transparent; border-radius: 4px; }
QListWidget#mediaList::item:selected { background: #362850; color: #f1eaff; border: 1px solid #9567ff; }
QListWidget#mediaList::item:hover:!selected { background: #252d40; }
"""

STYLE += """
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #141925; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #49536a; min-height: 28px; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: #9567ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QProgressBar { background: #242b3d; border: none; border-radius: 2px; }
QProgressBar::chunk { background: #9567ff; border-radius: 2px; }
"""

STYLE += """
QPlainTextEdit#subtitleText { background: #101521; color: #edf0f8; border: 1px solid #354057; border-radius: 6px; padding: 6px; selection-background-color: #7651c2; selection-color: #ffffff; }
QCheckBox::indicator { width: 15px; height: 15px; background: #141925; border: 1px solid #57637b; border-radius: 3px; }
QCheckBox::indicator:checked { background: #9567ff; border-color: #c3a5ff; }
"""

STYLE += """
QTabWidget::pane { border: 0; }
QTabBar::tab { background: #171d2a; color: #99a4bb; padding: 8px 11px; border: 1px solid #30394e; border-radius: 4px; margin-right: 4px; }
QTabBar::tab:selected { background: #302448; color: #e5d5ff; border-bottom: 2px solid #9567ff; }
QTableWidget { background: #101521; border: 1px solid #354057; border-radius: 5px; gridline-color: #293246; selection-background-color: #362850; }
QTableWidget::item { padding: 6px; }
QHeaderView::section { background: #232b3c; color: #b6bfd0; padding: 5px; border: none; }
QDoubleSpinBox { background: #141925; border: 1px solid #354057; border-radius: 5px; padding: 6px; }
"""

STYLE += "QPlainTextEdit#captionEditor { background: #101521; border: 1px solid #354057; border-radius: 5px; padding: 6px; selection-background-color: #7651c2; }"

STYLE += """
QTabBar#sequenceTabs::tab { background: #171d2a; color: #9faabd; border: 1px solid #30394e; border-bottom: 1px solid #30394e; padding: 7px 10px; }
QTabBar#sequenceTabs::tab:selected { background: #273847; color: #e5f5fa; border: 1px solid #7299ac; border-bottom: 1px solid #7299ac; }
QListWidget#sequenceList { padding: 3px; border: 1px solid #30394e; background: #141a26; }
QListWidget#sequenceList::item { padding: 7px 5px; border: 1px solid transparent; border-radius: 4px; }
QListWidget#sequenceList::item:selected { background: #273847; color: #e5f5fa; border: 1px solid #7299ac; }
"""

STYLE += """
QTreeWidget { background: #101521; border: 1px solid #354057; border-radius: 6px; padding: 3px; }
QTreeWidget::item { min-height: 23px; padding: 2px 2px; border-radius: 4px; }
QTreeWidget::item:selected { background: #273847; color: #edf6fa; }
QTreeWidget::item:hover:!selected { background: #252d40; }
QTreeWidget::branch { background: transparent; }
"""

STYLE += """
QFrame#projectHeader { background: transparent; border: none; }
QFrame#projectSeparator { background: #394152; border: none; }
QFrame#headerBoundary { background: #3c4456; border: none; }
QFrame#projectHeader QLabel { background: transparent; border: none; color: #9da7ba; font-family: 'Malgun Gothic'; font-size: 11px; }
QLineEdit#projectName, QComboBox#projectPicker { background: #151b27; color: #e4e9f2; border: 1px solid #424b60; border-radius: 4px; padding: 2px 8px; font-family: 'Malgun Gothic'; font-size: 12px; }
QLineEdit#projectName { border-left: 2px solid #9882cf; }
QLineEdit#projectName:focus, QComboBox#projectPicker:focus { border-color: #a394c9; }
QComboBox#projectPicker::drop-down { width: 22px; border-left: 1px solid #394152; background: transparent; }
"""

from pathlib import Path as _StylePath
_project_arrow=(_StylePath(__file__).parent/'assets'/'chevron-down.svg').as_posix()
STYLE += f"QComboBox#projectPicker::down-arrow {{ image: url('{_project_arrow}'); width: 12px; height: 8px; }}"
