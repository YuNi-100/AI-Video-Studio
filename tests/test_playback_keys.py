import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow


class PlaybackKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_transport_keys_and_text_input(self):
        window = MainWindow()
        window.show()
        window.activateWindow()
        window.preview.ready = True
        window.preview.setFocus()
        self.app.processEvents()
        try:
            with patch.object(window.preview, "toggle_play") as toggle:
                QTest.keyClick(window.preview, Qt.Key.Key_Space)
                self.assertEqual(toggle.call_count, 1)
                window.project_name.setFocus()
                window.project_name.setText("name")
                QTest.keyClick(window.project_name, Qt.Key.Key_Space)
                self.assertEqual(toggle.call_count, 1)
                self.assertIn(" ", window.project_name.text())
            window.preview.setFocus()
            with patch.object(window.preview.player, "isSeekable", return_value=True), patch.object(window, "transport_duration_value", return_value=20000), patch.object(window, "transport_position_value", return_value=8000), patch.object(window, "seek_transport") as seek:
                QTest.keyClick(window.preview, Qt.Key.Key_Left)
                seek.assert_called_with(7000)
                QTest.keyClick(window.preview, Qt.Key.Key_Right)
                seek.assert_called_with(9000)
                QTest.keyClick(window.preview, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
                seek.assert_called_with(3000)
                QTest.keyClick(window.preview, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
                seek.assert_called_with(13000)
            with patch.object(window.preview.player, "isSeekable", return_value=True), patch.object(window, "transport_duration_value", return_value=20000), patch.object(window, "transport_position_value", return_value=1000), patch.object(window, "seek_transport") as seek:
                QTest.keyClick(window.preview, Qt.Key.Key_Left)
                seek.assert_called_with(0)
            with patch.object(window.preview.player, "isSeekable", return_value=True), patch.object(window, "transport_duration_value", return_value=20000), patch.object(window, "transport_position_value", return_value=19000), patch.object(window, "seek_transport") as seek:
                QTest.keyClick(window.preview, Qt.Key.Key_Right)
                seek.assert_called_with(20000)
                window.subtitle_panel.terms.setFocus()
                QTest.keyClick(window.subtitle_panel.terms, Qt.Key.Key_Left)
                self.assertEqual(seek.call_count, 1)
        finally:
            window.project_name.setText(window.project.name)
            window.dirty = False
            window.close()


if __name__ == "__main__":
    unittest.main()
