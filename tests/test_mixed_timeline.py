import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest,tempfile,time
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication,QStyle
from PySide6.QtTest import QTest
from app.features.silence.sequence import validate_sequence,sequence_clips,sequence_layout,move_clips,move_timeline_items,edit_clip,combine_sequences,splice_sequence,insert_sources
from app.ui.main_window import MainWindow
from app.ui.theme import STYLE
from app.storage.project_store import save_project,load_project

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())

def sample():
    return validate_sequence(dict(id='sample',name='연습',source=SOURCE,duration=7.188,ranges=[[0,1],[2,3],[4,5]]))


class MixedModelTests(unittest.TestCase):
    def test_zero_to_five_cut_at_ten_moves_two_second_caption_to_twelve(self):
        s=validate_sequence(dict(id='example',name='예시',source=SOURCE,duration=20,ranges=[[0,5]]))
        cues=sequence_layout(s,[dict(start=2,end=3,text='예시 자막')])[1]
        r=move_timeline_items(dict(s,timeline_captions=cues),{0,1},{0},10000)
        self.assertEqual([c['at'] for c in r['clips']],[10,10])
        self.assertEqual((r['timeline_captions'][0]['start'],r['timeline_captions'][0]['end']),(12,13))
    def test_overwrite_splits_destination_and_preserves_source_handles(self):
        s=sample();clips=sequence_clips(s)
        # Source A at 0..1, source B at 2..5. A moves into B's middle.
        s=validate_sequence(dict(s,clips=[dict(clips[0]),dict(clips[1]),dict(clips[2],at=2,end=5),dict(clips[3],at=2,end=5)]))
        before=deepcopy(s);r=move_clips(s,{0},3000)
        video=sorted((c for c in r['clips'] if c['track']=='video'),key=lambda c:c['at'])
        self.assertEqual([(c['at'],c['start'],c['end']) for c in video],[(2,2,3),(3,0,1),(4,4,5)])
        self.assertEqual(s,before)
        right=next(i for i,c in enumerate(r['clips']) if c['track']=='video' and c['at']==4)
        moved=move_clips(r,{right},2000)
        right=next(i for i,c in enumerate(moved['clips']) if c['track']=='video' and c['at']==6)
        recovered=edit_clip(moved,right,'start',-1000)
        c=next(c for c in recovered['clips'] if c['track']=='video' and c['at']==5)
        self.assertEqual((c['start'],c['end']),(3,5))
    def test_normal_move_crosses_neighbor_and_shift_moves_followers(self):
        s=sample();r=move_clips(s,{0},4000)
        self.assertEqual(r['clips'][0]['at'],4)
        r=move_clips(s,{0},1000,True)
        self.assertEqual([c['at'] for c in r['clips']],[1,1,2,2,3,3])
    def test_mixed_items_keep_spacing_and_one_bounded_delta(self):
        s=sample();rows=[dict(id='a',start=.2,end=.5,text='가'),dict(id='b',start=1.2,end=1.5,text='나')]
        r=move_timeline_items(s,{0},{0},1000,False,rows)
        self.assertEqual(r['clips'][0]['at'],1)
        self.assertEqual([c['start'] for c in r['timeline_captions']],[1.2,1.2])
        r=move_timeline_items(dict(s,timeline_captions=rows),{2},{0},-1000)
        moved=next(c for c in r['clips'] if c['group']=='pair-1' and c['track']=='video')
        self.assertEqual(moved['at'],.8)
        self.assertEqual(r['timeline_captions'][0]['start'],0)
    def test_caption_shift_and_order_crossing(self):
        rows=[dict(id='a',start=.2,end=.5,text='가'),dict(id='b',start=1.2,end=1.5,text='나')]
        r=move_timeline_items(sample(),set(),{0},2000,False,rows)
        self.assertEqual([c['id'] for c in r['timeline_captions']],['b','a'])
        r=move_timeline_items(sample(),set(),{0},1000,True,rows)
        self.assertEqual([c['start'] for c in r['timeline_captions']],[1.2,2.2])
    def test_combining_inserting_preserves_independent_caption_edits(self):
        s=dict(sample(),timeline_captions=[dict(id='a',start=.2,end=.5,text='편집 자막')])
        r=combine_sequences([s,s])
        self.assertEqual([c['start'] for c in r['timeline_captions']],[.2,3.2])
        r=splice_sequence(s,[s],1000)
        self.assertEqual([c['start'] for c in r['timeline_captions']],[.2,1.2])
        r=insert_sources(s,[(SOURCE,7.188)],0,{SOURCE:[dict(start=1,end=2,text='추가')]})
        self.assertEqual([round(c['start'],3) for c in r['timeline_captions']],[1,7.388])
    def test_invalid_caption_metadata_is_rejected(self):
        for rows in ([dict(start=0,end=604801,text='범위')],[dict(id='a',start=0,end=1,text='가'),dict(id='a',start=1,end=2,text='나')]):
            with self.assertRaises(ValueError):validate_sequence(dict(sample(),timeline_captions=rows))


class MixedUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.app.setStyleSheet(STYLE)
    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([SOURCE]);end=time.monotonic()+8
        while not self.w.preview.ready and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(self.w.preview.ready)
        self.w.project.subtitles[SOURCE]=[dict(start=.2,end=.5,text='첫 자막'),dict(start=2.2,end=2.5,text='둘째 자막'),dict(start=4.2,end=4.5,text='셋째 자막')]
        self.w.create_edit_sequence(SOURCE,[(0,1),(2,3),(4,5)],7.188)
        self.before=Path(SOURCE).read_bytes()
    def tearDown(self):
        self.assertEqual(Path(SOURCE).read_bytes(),self.before)
        self.w.dirty=False
        for d in self.w.documents:d['dirty']=False
        self.w.close();QTest.qWait(20)
    def x(self,ms):
        c=self.w.timeline.canvas;return 95+(ms-c.offset)/c.span*(c.width()-107)
    def gesture(self,start,end,mod=Qt.KeyboardModifier.NoModifier):
        c=self.w.timeline.canvas
        for kind,pos,button,buttons in [(QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)]:
            QApplication.sendEvent(c,QMouseEvent(kind,QPointF(*pos),button,buttons,mod))
    def click(self,ms,y,ctrl=False):
        p=(self.x(ms),y);self.gesture(p,p,Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier)
    def test_ctrl_click_nonadjacent_and_toggle_linked_pair(self):
        c=self.w.timeline.canvas
        self.click(500,47);self.click(2500,47,True)
        self.assertEqual(c.selected_keys,{0,1,4,5})
        self.click(500,47,True)
        self.assertEqual(c.selected_keys,{4,5})
    def test_mixed_selection_drag_history_save_reload(self):
        w=self.w;c=w.timeline.canvas
        self.click(500,47)
        self.assertEqual(c.selected_subtitles,{0})
        self.gesture((self.x(500),47),(self.x(1000),47))
        self.assertAlmostEqual(w.active_sequence()['timeline_captions'][0]['start'],.7,delta=.02)
        self.assertAlmostEqual(sequence_clips(w.active_sequence())[0]['at'],.5,delta=.02)
        self.assertEqual(len(c.selected_keys),2);self.assertEqual(c.selected_subtitles,{0})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mixed.avsp';self.assertTrue(w.save_current(path=path))
            self.assertEqual(load_project(path).edit_sequences[0],w.active_sequence())
        w.undo_subtitle();self.assertEqual(w.active_sequence()['timeline_captions'][0]['start'],.2)
        w.redo_subtitle();self.assertIn('timeline_captions',w.active_sequence())
    def test_subtitle_shift_moves_followers_without_video(self):
        self.gesture((self.x(350),90),(self.x(350),90),Qt.KeyboardModifier.AltModifier)
        self.gesture((self.x(350),90),(self.x(850),90),Qt.KeyboardModifier.ShiftModifier)
        rows=self.w.active_sequence()['timeline_captions']
        self.assertEqual([round(r['start'],1) for r in rows],[.7,1.7,2.7])
        self.assertEqual(sequence_clips(self.w.active_sequence())[0]['at'],0)
    def test_subtitle_selection_survives_crossing_and_delete_undo(self):
        self.gesture((self.x(350),90),(self.x(350),90),Qt.KeyboardModifier.AltModifier)
        self.gesture((self.x(350),90),(self.x(2350),90))
        c=self.w.timeline.canvas
        selected=[c.segments[i] for i in c.selected_subtitles]
        self.assertEqual(len(selected),1);self.assertEqual(selected[0]['text'],'첫 자막')
        QTest.keyClick(c,Qt.Key.Key_Delete)
        self.assertEqual(len(self.w.active_sequence()['timeline_captions']),2)
        self.w.undo_subtitle();self.assertEqual(len(self.w.active_sequence()['timeline_captions']),3)
    def test_selection_starts_below_tracks_and_ctrl_box_adds(self):
        self.assertGreaterEqual(self.w.timeline.canvas.height(),230)
        self.click(500,47)
        self.gesture((self.x(2800),220),(self.x(2200),34),Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.w.timeline.canvas.selected_keys,{0,1,4,5})
    def test_mouse_overwrite_then_recover_source_by_extending_left_edge(self):
        w=self.w;s=w.active_sequence();clips=sequence_clips(s)
        s=validate_sequence(dict(s,clips=[clips[0],clips[1],dict(clips[2],at=2,end=5),dict(clips[3],at=2,end=5)]))
        w.project.edit_sequences[0]=s;w.render_edit_sequence()
        self.gesture((self.x(500),47),(self.x(3500),47))
        video=sorted((c for c in sequence_clips(w.active_sequence()) if c['track']=='video'),key=lambda c:c['at'])
        self.assertEqual([(round(c['at'],1),round(c['start'],1),round(c['end'],1)) for c in video],[(2,2,3),(3,0,1),(4,4,5)])
        self.gesture((self.x(4500),47),(self.x(6500),47))
        self.gesture((self.x(6000)+2,47),(self.x(5000)+2,47))
        restored=next(c for c in sequence_clips(w.active_sequence()) if c['track']=='video' and 4.9<c['at']<5.1)
        self.assertAlmostEqual(restored['start'],3,delta=.04)
        self.assertEqual(restored['end'],5)
    def test_shift_subtitle_from_original_creates_edit(self):
        w=self.w;w.timeline.sequence_tabs.setCurrentIndex(0);QTest.qWait(20)
        self.gesture((self.x(350),90),(self.x(850),90),Qt.KeyboardModifier.ShiftModifier)
        self.assertIsNotNone(w.active_sequence())
        self.assertEqual([round(r['start'],1) for r in w.active_sequence()['timeline_captions']],[.7,2.7,4.7])
    def test_popup_shows_several_rows_at_once(self):
        picker=self.w.project_picker
        picker.blockSignals(True);picker.clear();picker.addItems(['프로젝트 하나','프로젝트 둘','프로젝트 셋']);picker.blockSignals(False)
        picker.showPopup();QTest.qWait(30)
        self.assertFalse(picker.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup,None,picker))
        self.assertGreaterEqual(picker.view().viewport().height(),picker.view().sizeHintForRow(0)*3)
        picker.hidePopup()
    def test_blank_click_clears_timeline_and_bins_together(self):
        w=self.w;c=w.timeline.canvas
        self.click(500,47);w.timeline.sequence_tree.selectAll()
        self.assertTrue(c.selected_keys);self.assertTrue(w.timeline.sequence_tree.selectedItems())
        self.gesture((self.x(3500),210),(self.x(3500),210))
        self.assertFalse(c.selected_keys);self.assertFalse(c.selected_subtitles)
        self.assertFalse(w.timeline.sequence_tree.selectedItems())
        self.click(500,47);w.timeline.sequence_tree.selectAll()
        QTest.mouseClick(w.save_state,Qt.MouseButton.LeftButton)
        self.assertFalse(c.selected_keys);self.assertFalse(w.timeline.sequence_tree.selectedItems())
    def test_escape_and_toolbar_button_does_not_clear_selection(self):
        w=self.w;c=w.timeline.canvas;self.click(500,47)
        QTest.mouseClick(w.project_name,Qt.MouseButton.LeftButton)
        self.assertTrue(c.selected_keys)
        QTest.keyClick(w.project_name,Qt.Key.Key_Escape)
        self.assertFalse(c.selected_keys);self.assertFalse(c.selected_subtitles)
    def test_drag_starts_above_canvas_in_panel_whitespace(self):
        w=self.w;c=w.timeline.canvas;frame=c.parentWidget()
        start=c.mapTo(frame,QPointF(self.x(100),-8).toPoint())
        end=c.mapTo(frame,QPointF(self.x(800),160).toPoint())
        for kind,pos,button,buttons in [(QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)]:
            QApplication.sendEvent(frame,QMouseEvent(kind,QPointF(pos),QPointF(frame.mapToGlobal(pos)),button,buttons,Qt.KeyboardModifier.NoModifier))
        self.assertEqual(c.selected_keys,{0,1});self.assertEqual(c.selected_subtitles,{0})
    def test_drag_starts_below_canvas_in_footer_whitespace(self):
        w=self.w;c=w.timeline.canvas;footer=w.timeline.hint
        start=footer.mapFromGlobal(c.mapToGlobal(QPointF(self.x(100),c.height()+10).toPoint()))
        end=footer.mapFromGlobal(c.mapToGlobal(QPointF(self.x(800),34).toPoint()))
        for kind,pos,button,buttons in [(QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)]:
            QApplication.sendEvent(footer,QMouseEvent(kind,QPointF(pos),QPointF(footer.mapToGlobal(pos)),button,buttons,Qt.KeyboardModifier.NoModifier))
        self.assertEqual(c.selected_keys,{0,1});self.assertEqual(c.selected_subtitles,{0})
    def test_set_move_keeps_relative_caption_offset(self):
        w=self.w;c=w.timeline.canvas;self.click(500,47)
        self.assertEqual(c.selected_subtitles,{0})
        self.gesture((self.x(500),47),(self.x(5500),47))
        rows=sequence_layout(w.active_sequence())[1]
        self.assertAlmostEqual(next(r for r in rows if r['text']=='첫 자막')['start'],5.2,delta=.02)
        w.undo_subtitle();self.assertAlmostEqual(sequence_layout(w.active_sequence(),w.project.subtitles)[1][0]['start'],.2)
    def test_caption_length_edit_survives_later_set_move(self):
        w=self.w;w.select_sequence_clip('subtitle',0)
        w.edit_sequence_clip('subtitle',0,'end',200,False)
        w.select_sequence_clip('video',0);w.edit_sequence_clip('video',0,'move',1000,False)
        row=next(r for r in sequence_layout(w.active_sequence())[1] if r['text']=='첫 자막')
        self.assertAlmostEqual(row['start'],1.2);self.assertAlmostEqual(row['end'],1.7)
    def test_split_crossing_caption_belongs_to_each_piece(self):
        w=self.w;c=w.timeline.canvas
        w.commit_work_subtitles([dict(start=.2,end=.8,text='걸친 자막')]);w.render_edit_sequence()
        self.click(350,47);w.seek_transport(500);w.split_sequence_clip()
        rows=sequence_layout(w.active_sequence())[1]
        self.assertEqual([(r['start'],r['end']) for r in rows],[(.2,.5),(.5,.8)])
        self.assertNotEqual(rows[0]['owner'],rows[1]['owner'])
        self.click(750,47);self.gesture((self.x(750),47),(self.x(3750),47))
        rows=sequence_layout(w.active_sequence())[1]
        self.assertEqual([(round(r['start'],1),round(r['end'],1)) for r in rows],[(.2,.5),(3.5,3.8)])
    def test_alt_video_moves_without_audio_or_caption(self):
        self.gesture((self.x(500),47),(self.x(500),47),Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.w.timeline.canvas.selected_keys,{0})
        self.gesture((self.x(500),47),(self.x(1000),47))
        seq=self.w.active_sequence();clips=sequence_clips(seq)
        self.assertEqual(clips[1]['at'],0)
        self.assertAlmostEqual(sequence_layout(seq)[1][0]['start'],.2,delta=.01)
    def test_alt_click_adds_and_toggles_individual_items(self):
        c=self.w.timeline.canvas
        for ms,y in [(500,47),(1350,90),(2500,133)]:
            p=(self.x(ms),y);self.gesture(p,p,Qt.KeyboardModifier.AltModifier)
        self.assertEqual(c.selected_keys,{0,5});self.assertEqual(c.selected_subtitles,{1})
        p=(self.x(1350),90);self.gesture(p,p,Qt.KeyboardModifier.AltModifier)
        self.assertEqual(c.selected_keys,{0,5});self.assertFalse(c.selected_subtitles)
        p=(self.x(500),47);self.gesture(p,p,Qt.KeyboardModifier.AltModifier)
        self.assertEqual(c.selected_keys,{5})
    def test_alt_mixed_selection_moves_only_selected_items(self):
        c=self.w.timeline.canvas
        for ms,y in [(500,47),(1350,90),(2500,133)]:
            p=(self.x(ms),y);self.gesture(p,p,Qt.KeyboardModifier.AltModifier)
        self.gesture((self.x(500),47),(self.x(1000),47))
        clips=sequence_clips(self.w.active_sequence())
        video=next(r for r in clips if r['track']=='video' and r['group']=='pair-0')
        audio=next(r for r in clips if r['track']=='audio' and r['group']=='pair-0')
        last_audio=next(r for r in clips if r['track']=='audio' and r['group']=='pair-2')
        self.assertAlmostEqual(video['at'],.5,delta=.02);self.assertEqual(audio['at'],0)
        self.assertAlmostEqual(last_audio['at'],2.5,delta=.02)
        cue=next(r for r in c.segments if r['text']=='둘째 자막')
        self.assertAlmostEqual(cue['start'],1.7,delta=.02)
        self.assertEqual(len(c.selected_keys),2);self.assertEqual(len(c.selected_subtitles),1)
    def test_overwrite_preview_marks_destination_without_moving_neighbors(self):
        c=self.w.timeline.canvas
        for kind,pos,button in [(QEvent.Type.MouseButtonPress,(self.x(500),47),Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,(self.x(1500),47),Qt.MouseButton.NoButton)]:
            QApplication.sendEvent(c,QMouseEvent(kind,QPointF(*pos),button,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
        self.assertTrue(c.drag_destinations);self.assertIsNotNone(c.preview_blocks)
        c.grab()  # Exercise the overlay painter while a real move is active.
        QTest.keyClick(c,Qt.Key.Key_Escape)
        self.assertIsNone(c.drag)

if __name__=='__main__':unittest.main()
