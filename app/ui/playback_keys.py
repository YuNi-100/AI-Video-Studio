import weakref
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import (QApplication, QLineEdit, QTextEdit, QPlainTextEdit,
    QAbstractSpinBox, QComboBox, QAbstractItemView, QAbstractSlider, QCheckBox, QRadioButton)


class PlaybackKeys(QObject):
    """Window-scoped transport keys, preserving editing and native navigation."""
    def __init__(self, window):
        super().__init__(window)
        self._window = weakref.ref(window)
        QApplication.instance().installEventFilter(self)

    @property
    def window(self):
        return self._window()

    def available(self, event):
        window = self.window
        if window is None:
            return False
        if not window.isVisible() or QApplication.activeWindow() is not window:
            return False
        if QApplication.activeModalWidget() or QApplication.activePopupWidget():
            return False
        if event.key() not in (Qt.Key.Key_Space, Qt.Key.Key_Left, Qt.Key.Key_Right):
            return False
        allowed=(Qt.KeyboardModifier.NoModifier,Qt.KeyboardModifier.ShiftModifier) if event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right) else (Qt.KeyboardModifier.NoModifier,)
        if event.modifiers() not in allowed:
            return False
        focus = QApplication.focusWidget()
        timeline_active=bool(getattr(window,"timeline_focus",None) and window.timeline_focus.active)
        if not timeline_active and focus is not window.preview and not (focus and window.preview.isAncestorOf(focus)):
            return False
        while focus is not None and focus is not window:
            if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox)) or (not timeline_active and isinstance(focus,(QCheckBox,QRadioButton))):
                return False
            if not timeline_active and isinstance(focus, (QAbstractItemView, QAbstractSlider)):
                return False
            focus = focus.parentWidget()
        return window.preview.ready

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            return False
        if not self.available(event):
            return False
        event.accept()
        if event.type() == QEvent.Type.ShortcutOverride:
            return True
        if event.isAutoRepeat():
            return True
        preview = self.window.preview
        if event.key() == Qt.Key.Key_Space:
            self.window.toggle_transport()
        elif preview.player.isSeekable():
            step=5000 if event.modifiers()==Qt.KeyboardModifier.ShiftModifier else 1000
            delta = -step if event.key() == Qt.Key.Key_Left else step
            self.window.seek_transport(max(0, min(self.window.transport_duration_value(), self.window.transport_position_value() + delta)))
        return True
