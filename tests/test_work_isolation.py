import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest,tempfile,wave,json
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import numpy as np
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from tests import test_timeline_focus as focus_tests
from tests.test_gap_snap import example,SOURCE
from app.features.silence.sequence import validate_sequence,sequence_clips
from app.features.subtitles.sequence_audio import render_audio
from app.storage.project_store import load_project


class AudioTimelineTests(unittest.TestCase):
    def test_render_uses_audio_cuts_source_ranges_and_silent_gaps(self):
        seq=example();seq['linked']=False
        seq['clips']=[c for c in seq['clips'] if c['track']=='video' or c['at']!=1]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'edit.wav';render_audio(seq,path)
            with wave.open(str(path)) as stream:
                self.assertEqual(stream.getframerate(),16000);self.assertEqual(stream.getnchannels(),1)
                data=np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2')
            self.assertEqual(len(data),4*16000)
            self.assertTrue(np.any(data[:16000]));self.assertFalse(np.any(data[16000:48000]))
            self.assertTrue(np.any(data[48000:]))


class WorkIsolationTests(unittest.TestCase):
    setUpClass=classmethod(focus_tests.TimelineFocusTests.setUpClass.__func__)
    setUp=focus_tests.TimelineFocusTests.setUp
    tearDown=focus_tests.TimelineFocusTests.tearDown
    click_timeline=focus_tests.TimelineFocusTests.click_timeline

    def two_edits(self):
        w=self.w
        w.project.subtitles[SOURCE]=[dict(start=.2,end=.6,text='공통 시작 자막')]
        w.create_edit_sequence(SOURCE,[(0,7)],7.188);first=w.active_edit_id
        w.create_edit_sequence(SOURCE,[(0,7)],7.188);second=w.active_edit_id
        return first,second

    def test_library_click_preserves_work_preview_position_and_pending_caption(self):
        w=self.w;first,second=self.two_edits()
        other=str(Path(SOURCE).with_name("테스트 영상.mov"));w.media.add_files([other]);w.request_timeline_seek(2000)
        w.select_subtitle(0);w.subtitle_panel.editor.text.setPlainText('수정 중')
        rows=deepcopy(w.timeline.canvas.segments);position=w.transport_position_value()
        tree=w.media.project_tree
        item=next(i for i in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if i.data(0,Qt.ItemDataRole.UserRole)[0]=='media' and i.data(0,Qt.ItemDataRole.UserRole)[2]==other)
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,pos=tree.visualItemRect(item).center())
        self.assertEqual(w.active_edit_id,second);self.assertEqual(str(w.preview.source),SOURCE);self.assertEqual(w.timeline.canvas.segments,rows)
        self.assertEqual(w.transport_position_value(),position);self.assertTrue(w.subtitle_panel.editor.pending)
        self.assertEqual(w.subtitle_panel.editor.text.toPlainText(),'수정 중')
        w.subtitle_panel.editor.set_selection(0)

    def test_review_edit_generate_remove_are_local_with_undo_and_reload(self):
        w=self.w;first,second=self.two_edits();source=deepcopy(w.project.subtitles[SOURCE])
        w.select_subtitle(0);editor=w.subtitle_panel.editor;editor.text.setPlainText('두 번째만 수정')
        self.assertTrue(w.apply_subtitle_edit())
        self.assertEqual(w.timeline.canvas.segments[0]['text'],'두 번째만 수정')
        self.assertTrue(w.timeline.canvas.segments[0]['reviewed'])
        w.open_edit_sequence(first);self.assertEqual(w.timeline.canvas.segments[0]['text'],'공통 시작 자막')
        w.open_edit_sequence(second)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'independent.avsp';self.assertTrue(w.save_current(path=path))
            loaded=load_project(path)
            self.assertEqual(next(s for s in loaded.edit_sequences if s['id']==second)['timeline_captions'][0]['text'],'두 번째만 수정')
            self.assertEqual(loaded.subtitles[SOURCE],source)
        w.select_subtitle(0);w.remove_subtitle();self.assertEqual(w.timeline.canvas.segments,[])
        w.undo_subtitle();self.assertEqual(w.timeline.canvas.segments[0]['text'],'두 번째만 수정')
        self.assertEqual(w.project.subtitles[SOURCE],source)

    def test_generation_callback_applies_only_captured_work_and_rejects_stale(self):
        w=self.w;first,second=self.two_edits();source=deepcopy(w.project.subtitles[SOURCE])
        w._work_caption_job=(w.project,second,deepcopy(w.active_sequence()))
        w.subtitles_ready(SOURCE,[dict(start=1,end=2,text='작업본 생성 결과')])
        self.assertEqual(w.active_sequence()['timeline_captions'][0]['text'],'작업본 생성 결과')
        self.assertEqual(w.project.subtitles[SOURCE],source)
        w.open_edit_sequence(first)
        w.subtitles_ready(SOURCE,[dict(start=1,end=2,text='잘못 적용되면 안 됨')])
        self.assertEqual(w.timeline.canvas.segments[0]['text'],'공통 시작 자막')
        w._work_caption_job=None

    def test_recheck_does_not_switch_to_original_and_applies_to_work_only(self):
        w=self.w;first,second=self.two_edits();source=deepcopy(w.project.subtitles[SOURCE])
        w.open_subtitle_recheck();d=w.recheck_dialog
        self.assertEqual(w.active_edit_id,second);self.assertEqual(d.sequence_id,second);self.assertEqual(d.offset,0)
        d.ranges=[[0,1]];d.candidates=[[dict(start=.2,end=.6,text='작업본 재검토 후보')],[]];d.render()
        d.table.item(0,0).setCheckState(Qt.CheckState.Checked);d.apply_selected()
        self.assertEqual(w.timeline.canvas.segments[0]['text'],'작업본 재검토 후보')
        self.assertEqual(w.project.subtitles[SOURCE],source)
        w.undo_subtitle();self.assertEqual(w.timeline.canvas.segments[0]['text'],'공통 시작 자막')
        d.close()

    def test_asset_opens_reusable_independent_work_and_library_preview_is_separate(self):
        w=self.w
        record=dict(id='asset-test',source=SOURCE,name='작업 자료',folder=None)
        w.project.edit_assets.append(record);w.mark_dirty();w.open_asset_work(record)
        key=w.active_edit_id;self.assertTrue(key.startswith('asset-'))
        count=len(w.project.edit_sequences);w.open_asset_work(record)
        self.assertEqual(len(w.project.edit_sequences),count)
        w.preview_library_source(SOURCE)
        self.assertIsNot(w.library_preview.player,w.preview);self.assertEqual(w.active_edit_id,key)
        w.library_preview.close()

    def test_ripple_moves_playhead_to_deleted_cut_start_and_history_restores_both(self):
        w=self.w;c=w.timeline.canvas;seq=example();w.project.edit_sequences=[seq];w.open_edit_sequence(seq['id'])
        self.click_timeline();w.request_timeline_seek(1500)
        QTest.keyClick(c,Qt.Key.Key_Backspace,Qt.KeyboardModifier.AltModifier)
        self.assertEqual(w.transport_position_value(),1000)
        self.assertEqual([r['at'] for r in sequence_clips(w.active_sequence())],[0,0,2,2])
        w.undo_subtitle();self.assertEqual(w.transport_position_value(),1500)
        w.redo_subtitle();self.assertEqual(w.transport_position_value(),1000)

    @unittest.skipUnless(os.environ.get('STUDIO_WHISPER_CACHE'),'offline cache required')
    def test_actual_work_generation_and_recheck_preserve_source(self):
        import time
        w=self.w;w.whisper_cache=Path(os.environ['STUDIO_WHISPER_CACHE'])
        w.subtitle_panel.model.setCurrentIndex(0);w.subtitle_panel.language.setCurrentIndex(2)
        w.project.subtitles[SOURCE]=[dict(start=0,end=1,text='원본 유지')]
        source=deepcopy(w.project.subtitles[SOURCE]);key=w.active_edit_id
        w.generate_subtitles('tiny','en')
        deadline=time.monotonic()+90
        while w.subtitle_job.busy and time.monotonic()<deadline:QTest.qWait(30)
        self.assertFalse(w.subtitle_job.busy);self.assertTrue(w.active_sequence().get('subtitle_run'),w.subtitle_panel.status.text())
        self.assertEqual(w.project.subtitles[SOURCE],source)
        w.open_subtitle_recheck();d=w.recheck_dialog;d.scope.setCurrentIndex(1);d.end.setValue(3);d.begin()
        deadline=time.monotonic()+90
        while w.subtitle_job.busy and time.monotonic()<deadline:QTest.qWait(30)
        self.assertFalse(w.subtitle_job.busy);self.assertIsNotNone(d.candidates,d.status.text())
        self.assertEqual(w.active_edit_id,key);self.assertEqual(w.project.subtitles[SOURCE],source);d.close()
