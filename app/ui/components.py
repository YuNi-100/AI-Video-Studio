from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QPushButton

def label(text, kind=None):
    item = QLabel(text)
    if kind:
        item.setObjectName(kind)
    item.setWordWrap(True)
    return item

def panel():
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    return frame, layout

def pending(text, reason):
    button = QPushButton(text)
    button.setEnabled(False)
    button.setToolTip(reason)
    button.setAccessibleDescription(reason)
    return button
