"""Small code-native icons keep originals and editing references distinct."""
from functools import lru_cache
from PySide6.QtGui import QIcon,QPixmap,QPainter,QPen,QColor
from PySide6.QtCore import Qt,QRectF,QPointF


@lru_cache(maxsize=4)
def type_icon(kind):
    pixmap=QPixmap(16,16);pixmap.fill(Qt.GlobalColor.transparent)
    painter=QPainter(pixmap);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color={'original':'#aebbd1','asset':'#96b1cd','sequence':'#b39bdc','composition':'#88bcb6'}[kind]
    painter.setPen(QPen(QColor(color),1.2))
    if kind=='original':
        painter.drawRoundedRect(QRectF(2,2,12,12),1,1)
        painter.drawLine(5,2,5,14);painter.drawLine(11,2,11,14)
        for y in (5,10):painter.drawLine(2,y,5,y);painter.drawLine(11,y,14,y)
    elif kind=='asset':
        painter.drawRoundedRect(QRectF(2,3,12,10),1,1)
        painter.drawLine(6,6,10,8);painter.drawLine(10,8,6,10);painter.drawLine(6,10,6,6)
    elif kind=='sequence':
        painter.drawRoundedRect(QRectF(2,4,12,9),1,1)
        painter.drawLine(6,4,6,13);painter.drawLine(10,4,10,13)
    else:
        painter.drawRoundedRect(QRectF(2,2,10,8),1,1)
        painter.drawRoundedRect(QRectF(5,6,9,8),1,1)
    painter.end()
    return QIcon(pixmap)
