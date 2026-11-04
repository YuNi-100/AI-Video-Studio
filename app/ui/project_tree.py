"""Collapsible project trees and local-video drag payloads."""
import json
from PySide6.QtCore import Qt,QMimeData,QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QTreeWidget,QAbstractItemView


class ProjectTree(QTreeWidget):
    def __init__(self,media=False):
        super().__init__()
        self._fold_click=False
        self.media_tree=media
        self.setHeaderHidden(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRootIsDecorated(False)
        self.itemExpanded.connect(lambda item:self.disclosure(item,True))
        self.itemCollapsed.connect(lambda item:self.disclosure(item,False))
        self.setIndentation(14 if media else 24)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setExpandsOnDoubleClick(False)
        self.setColumnCount(2)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0,self.header().ResizeMode.Stretch)
        self.setColumnWidth(1,54)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setMinimumHeight(90)
        self.setAccessibleName('미디어 보관함' if media else '편집본 목록')
        self.setObjectName('projectMediaTree' if media else 'projectSequenceTree')

    def disclosure(self,item,expanded):
        data=item.data(0,Qt.ItemDataRole.UserRole)
        if data and data[0] in ('folder','project'):
            text=item.text(0)
            if text.startswith(('▾  ','▸  ')):text=text[3:]
            item.setText(0,('▾  ' if expanded else '▸  ')+text)

    def mousePressEvent(self,event):
        self._fold_click=False
        item=self.itemAt(event.position().toPoint())
        if item and item.data(0,Qt.ItemDataRole.UserRole) and item.data(0,Qt.ItemDataRole.UserRole)[0] in ('folder','project') and event.button()==Qt.MouseButton.LeftButton and event.position().x()<self.visualItemRect(item).left()+23:
            self._fold_click=True
            item.setExpanded(not item.isExpanded())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if self._fold_click:
            self._fold_click=False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and self.currentItem():
            self.itemClicked.emit(self.currentItem(),0)
            event.accept()
            return
        super().keyPressEvent(event)

    def startDrag(self,actions):
        urls=[];payload=[]
        for item in self.selectedItems():
            data=item.data(0,Qt.ItemDataRole.UserRole)
            if data:payload.append(data)
            if data and data[0]=='media':
                urls.append(QUrl.fromLocalFile(data[2]))
        if payload:
            mime=QMimeData();mime.setUrls(urls)
            mime.setData('application/x-studio-organizer',json.dumps(payload).encode('utf-8'))
            drag=QDrag(self);drag.setMimeData(mime)
            drag.exec(Qt.DropAction.CopyAction)
