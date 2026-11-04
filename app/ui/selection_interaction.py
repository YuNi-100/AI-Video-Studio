"""Selection clearing and marquee gestures from timeline panel whitespace."""
import weakref
from PySide6.QtCore import QObject,QEvent,Qt,QPointF
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (QApplication,QWidget,QAbstractButton,QLineEdit,QAbstractSpinBox,
    QComboBox,QAbstractSlider,QAbstractItemView,QTabBar,QMenu,QTextEdit,QPlainTextEdit,QGraphicsView)


class SelectionInteraction(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=weakref.ref(window);self.range_active=False
        QApplication.instance().installEventFilter(self)

    def eventFilter(self,watched,event):
        w=self.window()
        if w is None or not isinstance(watched,QWidget) or watched.window() is not w or QApplication.activeModalWidget():return False
        c=w.timeline.canvas
        if event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Escape:
            if QApplication.activePopupWidget():return False
            c.drag=None;c.preview_blocks=None;c.preview_segments=None;c.selection_origin=None;c.selection_box=None
            self.range_active=False;w.clear_workspace_selection();return False
        if event.type() not in (QEvent.Type.MouseButtonPress,QEvent.Type.MouseMove,QEvent.Type.MouseButtonRelease):return False
        point=QPointF(c.mapFromGlobal(event.globalPosition().toPoint()))
        if self.range_active:
            proxy=QMouseEvent(event.type(),point,event.button(),event.buttons(),event.modifiers())
            if event.type()==QEvent.Type.MouseMove:c.mouseMoveEvent(proxy)
            elif event.type()==QEvent.Type.MouseButtonRelease:
                self.range_active=False;c.mouseReleaseEvent(proxy)
            return True
        if event.type()!=QEvent.Type.MouseButtonPress or event.button()!=Qt.MouseButton.LeftButton:return False
        if watched is c:return False
        node=watched
        controls=(QAbstractButton,QLineEdit,QAbstractSpinBox,QComboBox,QAbstractSlider,QTabBar,QMenu,QTextEdit,QPlainTextEdit,QGraphicsView)
        while node is not None and node is not w:
            if isinstance(node,controls):return False
            if isinstance(node,QAbstractItemView):
                local=node.viewport().mapFromGlobal(event.globalPosition().toPoint())
                if node.indexAt(local).isValid():return False
                w.clear_workspace_selection();return False
            node=node.parentWidget()
        if w.timeline.isAncestorOf(watched) and point.x()>=95 and (point.y()<0 or point.y()>=c.height()):
            c.setFocus();self.range_active=True
            c.start_range_selection(QMouseEvent(event.type(),point,event.button(),event.buttons(),event.modifiers()))
            return True
        w.clear_workspace_selection()
        return False
