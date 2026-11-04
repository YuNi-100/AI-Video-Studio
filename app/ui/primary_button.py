from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton, QGraphicsDropShadowEffect


class PrimaryButton(QPushButton):
    """Readiness is controlled by the feature, never by the visual effect."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("primary")
        self.glow = QGraphicsDropShadowEffect(self)
        self.glow.setOffset(0, 0)
        self.glow.setBlurRadius(16)
        self.glow.setColor(QColor(149, 103, 255, 65))
        self.setGraphicsEffect(self.glow)
        self.glow.setEnabled(self.isEnabled())

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.EnabledChange and hasattr(self, "glow"):
            self.glow.setEnabled(self.isEnabled())
