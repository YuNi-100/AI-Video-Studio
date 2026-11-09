"""A clearly outlined, centered check box for candidate approval cells."""
from PySide6.QtCore import Qt,QEvent,QRectF,QPointF
from PySide6.QtGui import QColor,QPen,QPolygonF
from PySide6.QtWidgets import QStyledItemDelegate,QStyleOptionViewItem,QStyle,QApplication


class ApplyCheckDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        opt=QStyleOptionViewItem(option);self.initStyleOption(opt,index)
        opt.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        opt.text=''
        style=opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,opt,painter,opt.widget)
        enabled=bool(index.flags() & Qt.ItemFlag.ItemIsUserCheckable)
        checked=index.data(Qt.ItemDataRole.CheckStateRole) in (Qt.CheckState.Checked,Qt.CheckState.Checked.value)
        box=QRectF(option.rect.center().x()-10,option.rect.center().y()-10,21,21)
        painter.save();painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#ceb8ff' if enabled and checked else '#a9b8cf' if enabled else '#536074'),1.5))
        painter.setBrush(QColor('#9567ff' if enabled and checked else '#151e2c' if enabled else '#252b37'))
        painter.drawRoundedRect(box,3,3)
        if checked:
            painter.setPen(QPen(QColor('#ffffff' if enabled else '#8190a8'),2.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
            painter.drawPolyline(QPolygonF([QPointF(box.left()+5,box.top()+10),QPointF(box.left()+9,box.top()+14),QPointF(box.left()+16,box.top()+6)]))
        painter.restore()

    def editorEvent(self,event,model,option,index):
        if not index.flags() & Qt.ItemFlag.ItemIsUserCheckable:return False
        activate=(event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton and option.rect.contains(event.position().toPoint())) or (event.type()==QEvent.Type.KeyPress and event.key()==Qt.Key.Key_Space and not event.isAutoRepeat())
        if activate:
            checked=index.data(Qt.ItemDataRole.CheckStateRole) in (Qt.CheckState.Checked,Qt.CheckState.Checked.value)
            return model.setData(index,(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked).value,Qt.ItemDataRole.CheckStateRole)
        return False
