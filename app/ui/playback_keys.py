import weakref
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import (QApplication, QLineEdit, QTextEdit, QPlainTextEdit,
    QAbstractSpinBox, QComboBox, QAbstractItemView, QAbstractSlider, QCheckBox, QRadioButton,QWidget)


class PlaybackKeys(QObject):
    """Window-scoped transport keys, preserving editing and native navigation."""
    def __init__(self, window):
        super().__init__(window)
        self._window = weakref.ref(window)
        self.preview_active=False
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
            if not timeline_active and not self.preview_active and isinstance(focus, (QAbstractItemView, QAbstractSlider)):
                return False
            focus = focus.parentWidget()
        return window.preview.ready

    def eventFilter(self, watched, event):
        window=self.window
        if window is None:return False
        if isinstance(watched,QWidget) and event.type() in (QEvent.Type.MouseButtonPress,QEvent.Type.FocusIn):
            target=watched
            if event.type()==QEvent.Type.MouseButtonPress:
                if event.button()!=Qt.MouseButton.LeftButton:return False
                if watched.window() is window:
                    target=window.childAt(window.mapFromGlobal(event.globalPosition().toPoint())) or watched
            active=target is window.preview or window.preview.isAncestorOf(target)
            self.preview_active=active
            window.preview.frame.setStyleSheet('QFrame#panel { border: 1px solid #aa8ce4; }' if active else '')
            if active and event.type()==QEvent.Type.MouseButtonPress:
                window.preview.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.type()==QEvent.Type.WindowDeactivate and watched is window:
            self.preview_active=False;window.preview.frame.setStyleSheet('')
        if event.type() not in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
            return False
        if not self.available(event):
            return False
        event.accept()
        if event.type() == QEvent.Type.ShortcutOverride:
            return True
        if event.isAutoRepeat() and event.key()==Qt.Key.Key_Space:
            return True
        preview = self.window.preview
        if event.key() == Qt.Key.Key_Space:
            self.window.toggle_transport()
        elif preview.player.isSeekable():
            step=5000 if event.modifiers()==Qt.KeyboardModifier.ShiftModifier else 1000
            delta = -step if event.key() == Qt.Key.Key_Left else step
            position=max(0, min(self.window.transport_duration_value(), self.window.transport_position_value() + delta))
            self.window.request_timeline_seek(position) if self.window.timeline_focus.active else self.window.seek_transport(position)
        return True
