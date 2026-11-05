"""Click/focus-based timeline keyboard ownership, never mouse-hover based."""
import weakref
from PySide6.QtCore import QObject,QEvent,Qt,QPoint
from PySide6.QtWidgets import QApplication,QWidget,QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox,QComboBox


class TimelineFocus(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.owner=weakref.ref(window)
        self.active=False
        self.set_active(False)
        QApplication.instance().installEventFilter(self)

    def set_active(self,active):
        window=self.owner()
        if window is None:return
        self.active=bool(active)
        window.timeline.canvas.keyboard_active=self.active
        window.split_shortcut.setEnabled(self.active)
        window.timeline.keyboard_active=self.active
        window.timeline.update_keyboard_border()

    def editing_widget(self,widget,global_point=None):
        window=self.owner();timeline=window.timeline
        if widget is timeline.canvas or timeline.canvas.isAncestorOf(widget):return True
        if widget in (timeline.undo,timeline.split_button,timeline.delete_button,timeline.begin_edit,timeline.zoom,timeline.scroll):return True
        if widget is not timeline and not timeline.isAncestorOf(widget):return False
        for excluded in (timeline.sequence_tree,timeline.sequence_tabs,timeline.sequence_list):
            if widget is excluded or excluded.isAncestorOf(widget):return False
        if global_point is None:
            global_point=widget.mapToGlobal(widget.rect().center())
        local=timeline.mapFromGlobal(global_point)
        return timeline.rect().contains(local) and local.x()>=timeline.canvas.mapTo(timeline,QPoint(0,0)).x()

    @staticmethod
    def text_input(widget):
        while widget is not None:
            if isinstance(widget,(QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox,QComboBox)):
                return True
            widget=widget.parentWidget()
        return False

    def eventFilter(self,watched,event):
        window=self.owner()
        if window is None or not isinstance(watched,QWidget):return False
        if event.type()==QEvent.Type.WindowDeactivate and watched is window:
            self.set_active(False)
        if event.type()==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
            self.set_active(watched.window() is window and not self.text_input(watched)
                and self.editing_widget(watched,event.globalPosition().toPoint()))
        elif event.type()==QEvent.Type.FocusIn:
            self.set_active(watched.window() is window and not self.text_input(watched) and self.editing_widget(watched))
        if event.type() not in (QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress):return False
        if not self.active or QApplication.activeWindow() is not window or QApplication.activeModalWidget() or QApplication.activePopupWidget():return False
        if not window.timeline.isEnabled() or window.subtitle_job.busy or self.text_input(QApplication.focusWidget()):return False
        key=event.key();mod=event.modifiers()
        command=(key in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and mod in (Qt.KeyboardModifier.NoModifier,Qt.KeyboardModifier.AltModifier)) or (
            key in (Qt.Key.Key_K,Qt.Key.Key_C,Qt.Key.Key_V) and mod==Qt.KeyboardModifier.ControlModifier)
        if not command:return False
        event.accept()
        if event.type()==QEvent.Type.ShortcutOverride or event.isAutoRepeat():return True
        if key==Qt.Key.Key_K:window.request_timeline_split()
        else:window.timeline.canvas.keyPressEvent(event)
        return True
