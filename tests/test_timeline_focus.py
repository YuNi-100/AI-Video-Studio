import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QPushButton
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.features.silence.sequence import sequence_clips

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())
CTRL=Qt.KeyboardModifier.ControlModifier


class TimelineFocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.activateWindow();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([SOURCE]);end=time.monotonic()+8
        while not self.w.preview.ready and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(self.w.preview.ready)
        self.w.create_edit_sequence(SOURCE,[(0,7)],7.188)

    def tearDown(self):
        self.w.project_name.setText(self.w.project.name)
        self.w.dirty=False
        for doc in self.w.documents:doc['dirty']=False
        self.w.close();QTest.qWait(20)

    def click_timeline(self):
        c=self.w.timeline.canvas
        x=round(95+500/c.span*(c.width()-107))
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPoint(x,47))
        self.assertTrue(self.w.timeline_focus.active)
        self.assertTrue(self.w.timeline.keyboard_border.isVisible())

    def test_one_click_keeps_keyboard_target_after_mouse_moves(self):
        w=self.w;c=w.timeline.canvas;self.click_timeline()
        QTest.mouseMove(w.media.project_tree.viewport(),QPoint(10,10))
        self.assertTrue(w.timeline_focus.active)
        w.seek_transport(2000)
        QTest.keyClick(c,Qt.Key.Key_Right)
        self.assertEqual(w.transport_position_value(),3000)
        QTest.keyClick(c,Qt.Key.Key_Left)
        self.assertEqual(w.transport_position_value(),2000)
        QTest.keyClick(c,Qt.Key.Key_Right,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(w.transport_position_value(),7000)
        QTest.keyClick(c,Qt.Key.Key_Left,Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(w.transport_position_value(),2000)
        with patch.object(w,'toggle_transport') as toggle:
            QTest.keyClick(c,Qt.Key.Key_Space);self.assertEqual(toggle.call_count,1)
        QTest.keyClick(c,Qt.Key.Key_K,CTRL)
        self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        self.assertEqual(w.project.library_items[0]['source'],SOURCE)

    def test_input_click_and_hover_do_not_trigger_timeline_commands(self):
        w=self.w;self.click_timeline()
        name=w.project_name;QTest.mouseClick(name,Qt.MouseButton.LeftButton)
        name.setText('abcd');name.setCursorPosition(2)
        self.assertFalse(w.timeline_focus.active)
        self.assertTrue(w.timeline.keyboard_border.isHidden())
        position=w.transport_position_value()
        QTest.mouseMove(w.timeline.canvas,QPoint(200,50))
        self.assertFalse(w.timeline_focus.active)
        with patch.object(w,'request_timeline_split') as split,patch.object(w,'toggle_transport') as toggle:
            QTest.keyClick(name,Qt.Key.Key_Right)
            self.assertEqual(name.cursorPosition(),3)
            QTest.keyClick(name,Qt.Key.Key_Left,Qt.KeyboardModifier.ShiftModifier)
            self.assertEqual(name.selectedText(),'c')
            QTest.keyClick(name,Qt.Key.Key_Backspace)
            self.assertEqual(name.text(),'abd')
            QTest.keyClick(name,Qt.Key.Key_K,CTRL)
            QTest.keyClick(name,Qt.Key.Key_Space)
            split.assert_not_called();toggle.assert_not_called()
        self.assertEqual(w.transport_position_value(),position)
        self.assertEqual(len(sequence_clips(w.active_sequence())),2)

    def test_list_click_keeps_list_keys_and_delete_target(self):
        w=self.w;self.click_timeline()
        tree=w.timeline.sequence_tree
        item=tree.topLevelItem(0)
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,pos=tree.visualItemRect(item).center())
        self.assertFalse(w.timeline_focus.active)
        with patch.object(w,'request_timeline_split') as split,patch.object(w,'toggle_transport') as toggle,patch.object(w,'seek_transport') as seek:
            QTest.keyClick(tree,Qt.Key.Key_K,CTRL)
            QTest.keyClick(tree,Qt.Key.Key_Space)
            QTest.keyClick(tree,Qt.Key.Key_Right)
            split.assert_not_called();toggle.assert_not_called();seek.assert_not_called()
        with patch.object(w,'delete_sequence_clip') as cut_delete:
            QTest.keyClick(tree,Qt.Key.Key_Delete)
            cut_delete.assert_not_called()
        self.assertEqual(w.project.edit_sequences,[])
        self.assertTrue(Path(SOURCE).is_file())

    def test_outside_nonfocus_label_click_disables_stale_canvas_focus(self):
        w=self.w;c=w.timeline.canvas;self.click_timeline()
        QTest.mouseClick(w.mode_label,Qt.MouseButton.LeftButton)
        self.assertFalse(w.timeline_focus.active)
        with patch.object(w,'request_timeline_split') as split,patch.object(w,'toggle_transport') as toggle:
            QTest.keyClick(c,Qt.Key.Key_Delete)
            QTest.keyClick(c,Qt.Key.Key_K,CTRL)
            QTest.keyClick(c,Qt.Key.Key_Space)
            split.assert_not_called();toggle.assert_not_called()
        self.assertEqual(len(sequence_clips(w.active_sequence())),2)

    def test_timeline_toolbar_focus_routes_space_and_split_once(self):
        w=self.w;self.click_timeline();w.timeline.undo.setFocus()
        self.assertTrue(w.timeline_focus.active)
        with patch.object(w,'toggle_transport') as toggle,patch.object(w,'undo_subtitle') as undo:
            QTest.keyClick(w.timeline.undo,Qt.Key.Key_Space)
            self.assertEqual(toggle.call_count,1);undo.assert_not_called()
        with patch.object(w,'request_timeline_split') as split:
            QTest.keyClick(w.timeline.undo,Qt.Key.Key_K,CTRL)
            self.assertEqual(split.call_count,1)

    def test_dialog_does_not_receive_timeline_delete_or_split(self):
        w=self.w;self.click_timeline()
        dialog=QDialog(w);layout=QVBoxLayout(dialog);button=QPushButton('확인',dialog);layout.addWidget(button)
        dialog.show();dialog.activateWindow();button.setFocus();QTest.qWait(20)
        self.assertFalse(w.timeline_focus.active)
        with patch.object(w,'request_timeline_split') as split:
            QTest.keyClick(button,Qt.Key.Key_Delete);QTest.keyClick(button,Qt.Key.Key_K,CTRL)
            split.assert_not_called()
        self.assertEqual(len(sequence_clips(w.active_sequence())),2)
        dialog.close();w.activateWindow()

    def test_border_tracks_resize_and_does_not_intercept_cut_clicks(self):
        w=self.w;self.click_timeline()
        for size in ((1180,780),(1480,940)):
            w.resize(*size);QTest.qWait(30)
            border=w.timeline.keyboard_border
            self.assertTrue(border.isVisible())
            self.assertTrue(border.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            self.assertLessEqual(border.geometry().right(),w.timeline.width())
            self.assertLessEqual(border.geometry().bottom(),w.timeline.height())
            self.click_timeline()
            self.assertEqual(w.timeline.canvas.selected_keys,{0,1})
        if os.environ.get('STUDIO_FOCUS_PREVIEW'):w.grab().save(os.environ['STUDIO_FOCUS_PREVIEW'])
