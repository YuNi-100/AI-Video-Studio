import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import unittest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui.workspace import SubtitlePanel


class SubtitleCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        # End Qt explicitly before Python finalizes native clipboard objects.
        import shiboken6
        cls.app.clipboard().clear()
        cls.app.processEvents()
        import gc
        gc.collect()
        shiboken6.delete(cls.app)
        cls.app = None

    def test_drag_keyboard_and_whole_copy_preserve_results(self):
        panel = SubtitlePanel()
        panel.resize(420, 900)
        panel.show()
        segments = [{"start": 1., "end": 3., "text": "라겸 경희 자막 복사"}]
        panel.show_segments(segments)
        self.app.processEvents()
        view = panel.results
        original = view.toPlainText()
        start = original.index("라겸")
        cursor = view.textCursor()
        cursor.setPosition(start)
        first = view.cursorRect(cursor).center()
        cursor.setPosition(start + 5)
        last = view.cursorRect(cursor).center()
        view.setFocus()
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=first)
        QTest.mouseMove(view.viewport(), last)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=last)
        self.assertTrue(view.textCursor().hasSelection())
        selected = view.textCursor().selectedText()
        QTest.keyClick(view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.app.clipboard().text(), selected)
        self.assertTrue(view.isReadOnly())
        QTest.keyClicks(view, "not editable")
        self.assertEqual(view.toPlainText(), original)
        panel.copy_all.click()
        self.assertEqual(self.app.clipboard().text(), original)
        self.assertIn("00:00:01.000", original)
        panel.show_segments([])
        self.assertFalse(panel.copy_all.isEnabled())
        self.assertEqual(view.toPlainText(), "")
        panel.close()
        import shiboken6
        shiboken6.delete(panel)


if __name__ == "__main__":
    unittest.main()
