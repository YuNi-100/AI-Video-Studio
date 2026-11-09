import os,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication,QTableWidget,QTableWidgetItem
from PySide6.QtTest import QTest
from app.ui.apply_checkbox import ApplyCheckDelegate

class RecheckCheckboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyle('Fusion');cls.app.setStyleSheet(STYLE)

    def test_cell_click_space_and_protected_row(self):
        table=QTableWidget(2,1);table.setItemDelegateForColumn(0,ApplyCheckDelegate(table))
        for row in range(2):
            item=QTableWidgetItem();item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|(Qt.ItemFlag.ItemIsUserCheckable if row==0 else Qt.ItemFlag.NoItemFlags));item.setCheckState(Qt.CheckState.Unchecked)
            table.setItem(row,0,item);table.setRowHeight(row,70)
        table.show();QTest.qWait(20)
        try:
            item=table.item(0,0);point=table.visualItemRect(item).center()
            QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=point)
            self.assertEqual(item.checkState(),Qt.CheckState.Checked)
            QTest.keyClick(table,Qt.Key.Key_Space);self.assertEqual(item.checkState(),Qt.CheckState.Unchecked)
            protected=table.item(1,0)
            QTest.mouseClick(table.viewport(),Qt.MouseButton.LeftButton,pos=table.visualItemRect(protected).center())
            self.assertEqual(protected.checkState(),Qt.CheckState.Unchecked)
        finally:table.close();table.deleteLater();QTest.qWait(20)
