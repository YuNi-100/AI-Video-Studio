import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
import time
import tempfile
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.features.subtitles.recheck import plan_ranges, apply_candidates, validate_ranges
from app.features.subtitles.recheck_worker import recognize_ranges
from app.features.subtitles.editing import review_reasons
from app.features.clip_clipboard import copy_sets
from app.features.silence.sequence import validate_sequence, sequence_layout, sequence_clips, splice_sequence
from app.storage.project_store import load_project

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())


def sample():
    return validate_sequence(dict(id='test',name='원본 컷',source=SOURCE,duration=7.188,ranges=[[0,1],[2,3],[4,5]]))


class RecheckModelTests(unittest.TestCase):
    def test_full_and_selected_range_includes_no_caption_regions(self):
        self.assertEqual(plan_ranges('full',65,[]),[[0,30],[30,60],[60,65]])
        self.assertEqual(plan_ranges('range',65,[],start=12,end=46),[[12,42],[42,46]])
        with self.assertRaises(ValueError):plan_ranges('range',65,[],start=4,end=3)

    def test_suspects_use_source_time_and_skip_reviewed(self):
        rows=[dict(start=12,end=13,text='ㅁㅁㅁ'),dict(start=14,end=15,text='Почему',reviewed=True)]
        self.assertEqual(plan_ranges('suspect',20,rows,offset=10),[[2,3]])
        for text in ['ㅁㅁㅁ','왜왜왜왜왜왜','こんにちは']:
            self.assertTrue(review_reasons([dict(start=0,end=1,text=text)])[0])

    def test_apply_preserves_unselected_and_outside_pieces_with_offset(self):
        rows=[dict(start=10,end=15,text='걸친 문장'),dict(start=17,end=18,text='유지',reviewed=True)]
        before=deepcopy(rows)
        result=apply_candidates(rows,[(1,3,[dict(start=1.2,end=2.5,text='새 문장')])],offset=10)
        self.assertEqual([(r['start'],r['end'],r['text']) for r in result],[(10,11,'걸친 문장'),(11.2,12.5,'새 문장'),(13,15,'걸친 문장'),(17,18,'유지')])
        self.assertEqual(rows,before)

    def test_protection_empty_and_invalid_candidates(self):
        rows=[dict(start=0,end=1,text='검수',reviewed=True)]
        with self.assertRaises(ValueError):apply_candidates(rows,[(0,1,[dict(start=0,end=1,text='새')])])
        with self.assertRaises(ValueError):apply_candidates(rows,[(0,1,[])],protect=False)
        with self.assertRaises(ValueError):apply_candidates([],[(0,1,[dict(start=0,end=2,text='초과')])])
        self.assertEqual(apply_candidates(rows,[(0,1,[dict(start=0,end=1,text='새')])],protect=False)[0]['text'],'새')

    def test_worker_adds_context_and_clips_word_times(self):
        import numpy as np
        calls=[]
        class Backend:
            def transcribe(self,audio,**kwargs):
                calls.append((len(audio),kwargs))
                words=[SimpleNamespace(start=0,end=1,word='바깥'),SimpleNamespace(start=2.1,end=2.6,word=' 안쪽')]
                return iter([SimpleNamespace(start=0,end=3,text='바깥 안쪽',words=words)]),None
        rows=recognize_ranges(np.zeros(10*16000),Backend(),[[4,5]],'ko','힌트',False,lambda e:None)
        self.assertEqual(rows[0],[dict(start=4.1,end=4.6,text='안쪽')])
        self.assertEqual(calls[0][0],5*16000)
        self.assertIsNone(calls[1][1]['hotwords'])


class ClipboardModelTests(unittest.TestCase):
    def test_set_audio_video_offset_survives_gap_compaction(self):
        seq=sample();clips=sequence_clips(seq)
        clips[1]['at']=5
        # Only the first set is copied; its own intentional gap must remain.
        seq=validate_sequence(dict(seq,clips=[clips[0],clips[1]]))
        payload=copy_sets(seq,{0})
        self.assertEqual([c['at'] for c in payload['clips']],[0,5])

    def test_selected_sets_pack_gaps_and_freeze_captions(self):
        s=sample();before=deepcopy(s)
        rows={SOURCE:[dict(start=.2,end=.6,text='첫째'),dict(start=4.2,end=4.6,text='셋째')]}
        clip=copy_sets(s,{0,4},subtitles=rows)
        self.assertEqual([c['at'] for c in clip['clips']],[0,0,1,1])
        self.assertEqual([r['start'] for r in clip['timeline_captions']],[.2,1.2])
        self.assertEqual(s,before)
        rows[SOURCE][0]['text']='바뀜'
        self.assertEqual(clip['timeline_captions'][0]['text'],'첫째')

    def test_paste_inside_cut_splits_and_ripples_existing_captions(self):
        target=validate_sequence(dict(sample(),ranges=[[0,5]]))
        target['timeline_captions']=sequence_layout(target,{SOURCE:[dict(start=1,end=4,text='걸친 자막')]})[1]
        payload=copy_sets(sample(),{0})
        result=splice_sequence(target,[payload],2000)
        video=[c for c in result['clips'] if c['track']=='video']
        self.assertEqual([(c['at'],c['start'],c['end']) for c in video],[(0,0,2),(3,2,5),(2,0,1)])
        self.assertEqual([(r['start'],r['end']) for r in result['timeline_captions']],[(1,2),(3,5)])
        again=splice_sequence(result,[payload],6000)
        groups=[c['group'] for c in again['clips'] if c['track']=='video']
        self.assertEqual(len(groups),len(set(groups)))


class WorkflowUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        from app.ui.main_window import MainWindow
        self.w=MainWindow();self.w.show();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([SOURCE])
        deadline=time.monotonic()+8
        while not self.w.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
        self.assertTrue(self.w.preview.ready)

    def tearDown(self):
        self.w.subtitle_job.shutdown()
        self.w.dirty=False
        for d in self.w.documents:d['dirty']=False
        self.w.close();QTest.qWait(20)

    def test_real_keys_copy_create_paste_undo_reload(self):
        w=self.w
        w.project.subtitles[SOURCE]=[dict(start=.2,end=.6,text='연결 자막')]
        w.create_edit_sequence(SOURCE,[(0,1),(2,3),(4,5)],7.188)
        c=w.timeline.canvas;c.selected_keys={0,1,4,5};c.selected_clip=0;c.setFocus()
        QTest.keyClick(c,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(w.clip_clipboard)
        w.new_edit_from_clipboard()
        self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        w.preview.seek_timeline(2000)
        c.setFocus();QTest.keyClick(c,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(sequence_clips(w.active_sequence())),8)
        w.change_sequence_history(False)
        self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        w.change_sequence_history(True)
        self.assertEqual(len(sequence_clips(w.active_sequence())),8)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'copy.avsp';self.assertTrue(w.save_current(path=path))
            self.assertEqual(next(s for s in load_project(path).edit_sequences if s['id']==w.active_edit_id),w.active_sequence())

    def test_candidate_results_do_not_overwrite_until_checked_and_stale_guard(self):
        w=self.w
        w.project.subtitles[SOURCE]=[dict(start=0,end=1,text='기존')]
        w.show_source_subtitles(force=True)
        w.create_edit_sequence(SOURCE,[(0,7)],7.188)
        w.open_subtitle_recheck();d=w.recheck_dialog
        d.ranges=[[0,1]];d.running=True
        w.subtitle_job.run_info={'alternate':[dict(start=.1,end=.9,text='힌트 제외')]}
        w.subtitles_ready(SOURCE,[dict(start=.1,end=.9,text='기본 후보')]);w.subtitle_finished()
        self.assertEqual(w.active_sequence()['timeline_captions'][0]['text'],'기존')
        if os.environ.get('STUDIO_RECHECK_PREVIEW'):d.grab().save(os.environ['STUDIO_RECHECK_PREVIEW'])
        d.table.cellWidget(0,4).setCurrentIndex(1)
        d.table.item(0,0).setCheckState(Qt.CheckState.Checked)
        d.apply_selected()
        self.assertEqual(w.active_sequence()['timeline_captions'][0]['text'],'힌트 제외')
        w.undo_subtitle();self.assertEqual(w.active_sequence()['timeline_captions'][0]['text'],'기존')
        w.redo_subtitle();self.assertEqual(w.active_sequence()['timeline_captions'][0]['text'],'힌트 제외')
        d.prepare();d.ranges=[[0,1]];d.running=True
        w.subtitles_ready(SOURCE,[dict(start=.1,end=.9,text='미적용')]);w.subtitle_finished()
        d.table.item(0,0).setCheckState(Qt.CheckState.Checked)
        w.active_sequence()['timeline_captions'][0]['text']='외부 수정'
        d.apply_selected();self.assertEqual(w.active_sequence()['timeline_captions'][0]['text'],'외부 수정')

    def test_two_a_clips_plus_one_b_clip_with_captions(self):
        w=self.w
        other=str((Path(__file__).parent/'fixtures/테스트 영상.mp4').resolve())
        w.project.subtitles[SOURCE]=[dict(start=.2,end=.6,text='A 자막')]
        w.create_edit_sequence(SOURCE,[(0,1),(2,3),(4,5)],7.188)
        w.timeline.canvas.selected_keys={0,4};w.copy_timeline_sets();w.new_edit_from_clipboard()
        final=w.active_edit_id
        w.media.add_files([other])
        deadline=time.monotonic()+8
        while not w.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
        w.project.subtitles[other]=[dict(start=2.2,end=2.6,text='B 자막')]
        w.create_edit_sequence(other,[(2,3)],3)
        w.timeline.canvas.selected_keys={0};w.copy_timeline_sets()
        w.open_edit_sequence(final)
        deadline=time.monotonic()+8
        while not w.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
        w.preview.seek_timeline(2000);w.paste_timeline_sets()
        seq=w.active_sequence()
        video=[c for c in seq['clips'] if c['track']=='video']
        self.assertEqual(sorted((c['at'],c['source']) for c in video),[(0,SOURCE),(1,SOURCE),(2,other)])
        self.assertEqual([r['text'] for r in seq['timeline_captions']],['A 자막','B 자막'])

    def test_cancelled_job_retains_captions_and_removes_request(self):
        w=self.w
        w.project.subtitles[SOURCE]=[dict(start=0,end=1,text='원래 자막')]
        w.create_edit_sequence(SOURCE,[(0,7)],7.188);w.open_subtitle_recheck();d=w.recheck_dialog
        with patch.object(w.subtitle_job,'start',return_value=True):d.begin()
        path=d.request_path
        self.assertTrue(path.exists())
        d.reject();self.assertTrue(d.isVisible())
        w.subtitle_finished()
        self.assertFalse(path.exists())
        self.assertEqual(w.project.subtitles[SOURCE][0]['text'],'원래 자막')

    @unittest.skipUnless(os.environ.get('STUDIO_WHISPER_CACHE'),'offline cache required')
    def test_real_review_job_preserves_original(self):
        w=self.w
        w.whisper_cache=Path(os.environ['STUDIO_WHISPER_CACHE'])
        w.subtitle_panel.model.setCurrentIndex(0)
        w.subtitle_panel.language.setCurrentIndex(2)
        w.project.subtitles[SOURCE]=[dict(start=0,end=1,text='보존')]
        w.create_edit_sequence(SOURCE,[(0,7)],7.188)
        w.select_subtitle(0)
        w.open_subtitle_recheck();d=w.recheck_dialog
        d.use_selection()
        self.assertEqual((d.start.value(),d.end.value()),(0,1))
        d.scope.setCurrentIndex(1);d.start.setValue(0);d.end.setValue(4)
        d.begin();request=d.request_path
        deadline=time.monotonic()+90
        while w.subtitle_job.busy and time.monotonic()<deadline:QTest.qWait(30)
        self.assertFalse(w.subtitle_job.busy,d.status.text())
        self.assertIsNotNone(d.candidates,d.status.text())
        self.assertEqual(w.project.subtitles[SOURCE][0]['text'],'보존')
        self.assertFalse(request.exists())
