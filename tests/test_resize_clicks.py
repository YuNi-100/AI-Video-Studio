import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QSplitter, QInputDialog
from PySide6.QtTest import QTest, QSignalSpy
from app.ui.main_window import MainWindow
from app.ui.theme import STYLE


class ResizeClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def test_media_selection_rename_and_remove_at_window_coordinates(self):
        window = MainWindow()
        window.show()
        # Window-coordinate events exercise actual hit testing, not button.click().
        try:
            fixture = str((Path(__file__).parent / "fixtures" / "테스트 영상.mp4").resolve())
            other = str(Path(fixture).with_suffix(".mov"))
            split = next(s for s in window.findChildren(QSplitter) if s.count() == 3)
            for width, height in ((1480, 940), (1180, 780), (1280, 820), (1180, 780)):
                window.resize(width, height)
                split.setSizes([1, 1000, 1])
                self.app.processEvents()
                window.media.restore([fixture, other], fixture, {fixture: "긴 이름 " * 24})
                self.app.processEvents()
                listing = window.media.project_tree
                self.assertEqual(listing.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                viewport = listing.viewport()
                rect = listing.visualItemRect(next(item for item in listing.findItems("",Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if item.data(0,Qt.ItemDataRole.UserRole)[0]=="media" and item.data(0,Qt.ItemDataRole.UserRole)[2]==other))
                self.assertGreaterEqual(rect.height(), 27)
                selection_point = viewport.mapTo(window, rect.center())
                QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton, pos=selection_point)
                self.assertEqual(window.media.selected_path(), other)
                rename = window.media.rename_button
                for point in (rename.rect().center(), QPoint(4, rename.height() // 2), QPoint(rename.width() - 5, rename.height() // 2)):
                    mapped = rename.mapTo(window, point)
                    self.assertIs(window.childAt(mapped), rename)
                    with patch.object(QInputDialog, "getText", return_value=("창 축소 확인", True)) as dialog:
                        QTest.mouseClick(window.windowHandle(), Qt.MouseButton.LeftButton, pos=mapped)
                        self.assertEqual(dialog.call_count, 1)
                self.assertEqual(window.media.listing.currentItem().text(), "창 축소 확인")
                remove = window.media.remove_button
                self.assertTrue(window.media.relink_button.isHidden())
                self.assertTrue(remove.isHidden())
                listing.setFocus()
                QTest.keyClick(listing, Qt.Key.Key_Delete)
                self.assertEqual(window.media.paths(), [fixture])
                QTest.keyClick(listing, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
                self.assertEqual(window.media.paths(), [fixture, other])
        finally:
            window.dirty = False
            window.project_name.setText(window.project.name)
            window.close()


if __name__ == "__main__":
    unittest.main()
