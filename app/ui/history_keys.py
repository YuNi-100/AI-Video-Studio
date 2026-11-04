"""Undo/redo keys scoped to this window, with native text buffers kept separate."""
import weakref
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QApplication, QLineEdit, QTextEdit, QPlainTextEdit


class HistoryKeys(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window = weakref.ref(window)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self,watched,event):
        if event.type() not in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress):
            return False
        window = self.window()
        if window is None or not window.isVisible() or QApplication.activeWindow() is not window:
            return False
        if QApplication.activeModalWidget() or QApplication.activePopupWidget():
            return False
        if event.key() != Qt.Key.Key_Z:
            return False
        modifiers = event.modifiers()
        if modifiers not in (Qt.KeyboardModifier.ControlModifier,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):
            return False
        focus = QApplication.focusWidget()
        text = None
        while focus is not None and focus is not window:
            if isinstance(focus,(QLineEdit,QTextEdit,QPlainTextEdit)):
                text = focus
                break
            focus = focus.parentWidget()
        event.accept()
        if event.type() == QEvent.Type.ShortcutOverride or event.isAutoRepeat():
            return True
        redo = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        if text is not None:
            if not text.isReadOnly():
                text.redo() if redo else text.undo()
        elif redo:
            window.redo_subtitle()
        else:
            window.undo_subtitle()
        return True
