import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import unittest
from PySide6.QtWidgets import QApplication, QPushButton
from app.ui.main_window import MainWindow
from app.core.project import Project
from app.ui.theme import STYLE

class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.dirty = False
        self.window.project_name.setText(self.window.project.name)
        self.window.close()

    def test_actions_disabled_without_media(self):
        for text in ("✦  자동 자막 생성", "SRT 출력", "▶"):
            button = next(b for b in self.window.findChildren(QPushButton) if b.text() == text)
            self.assertFalse(button.isEnabled(), text)

    def test_session_name_and_validation(self):
        self.window.project_name.setText("  새 프로젝트  ")
        self.window.rename_project()
        self.assertEqual(self.window.project.name, "새 프로젝트")
        self.window.project_name.setText("   ")
        self.window.rename_project()
        self.assertEqual(self.window.project_name.text(), "새 프로젝트")
        self.assertFalse(Project().rename("a" * 81))

    def test_tab_and_zoom(self):
        self.window.activate_tab("자막")
        self.assertEqual(self.window.tabs.checkedButton().text(), "자막")
        self.window.timeline.zoom.setValue(175)
        self.assertEqual(self.window.timeline.canvas.zoom, 175)

    def test_minimum_layout(self):
        self.window.resize(1180, 780)
        self.app.processEvents()
        self.assertEqual(self.window.width(), 1180)
        self.assertLessEqual(self.window.centralWidget().minimumSizeHint().width(), 1180)
        self.assertGreater(self.window.timeline.canvas.width(), 300)

class VisualStateTests(unittest.TestCase):
    setUpClass = StudioTests.__dict__["setUpClass"]
    setUp = StudioTests.setUp
    tearDown = StudioTests.tearDown

    def test_top_tabs_and_resizable_panels(self):
        from PySide6.QtWidgets import QSplitter, QFrame
        self.assertIsNone(self.window.findChild(QFrame, "navPanel"))
        self.assertFalse(any(b.objectName() == "navItem" for b in self.window.findChildren(QPushButton)))
        for name in ("미디어", "자막", "AI 도구", "편집", "내보내기"):
            self.window.activate_tab(name)
            self.assertEqual(self.window.tabs.checkedButton().text(), name)
        split = next(s for s in self.window.findChildren(QSplitter) if s.count() == 3)
        self.assertEqual(split.count(), 3)
        before = split.sizes()
        split.moveSplitter(before[0] + 35, 1)
        self.app.processEvents()
        self.assertNotEqual(before, split.sizes())

    def test_primary_glow_tracks_readiness(self):
        from app.ui.primary_button import PrimaryButton
        button = PrimaryButton("테스트 전용")
        self.assertTrue(button.glow.isEnabled())
        button.setEnabled(False)
        self.assertFalse(button.glow.isEnabled())
        button.setEnabled(True)
        self.assertTrue(button.glow.isEnabled())
        actual = self.window.findChild(PrimaryButton)
        self.assertFalse(actual.isEnabled())
        self.assertFalse(actual.glow.isEnabled())

if __name__ == "__main__":
    unittest.main()
