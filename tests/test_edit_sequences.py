import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.features.silence.sequence import validate_sequence, sequence_layout, sequence_source_ms
from app.core.project import Project
from app.storage.project_store import save_project, load_project
from app.ui.main_window import MainWindow


def sample(source):
    return dict(id='one',name='무음 컷 1',source=source,duration=7.188,ranges=[[0,1],[3,4],[5,6]])


class SequenceModelTests(unittest.TestCase):
    def test_boundary_mapping(self):
        ranges=[(0,1000),(3000,4000),(5000,6000)]
        self.assertEqual(sequence_source_ms(ranges,999),(999,0))
        self.assertEqual(sequence_source_ms(ranges,1000),(3000,1))
        self.assertEqual(sequence_source_ms(ranges,3000),(6000,2))
    def test_layout_and_captions_clipped_and_shifted(self):
        seq=sample('a.mp4')
        captions=[dict(start=.5,end=3.5,text='연결 자막',reviewed=True)]
        blocks,cues,duration=sequence_layout(seq,captions)
        self.assertEqual(duration,3000)
        self.assertEqual(len(blocks),6)
        self.assertEqual([(s['start'],s['end']) for s in cues],[(.5,1),(1,1.5)])
        self.assertEqual(captions[0]['end'],3.5)
    def test_invalid_ranges(self):
        for ranges in ([],[[0,0]],[[0,8]],[[3,4],[2,3]],[[False,1]],[[0,float('nan')]]):
            with self.assertRaises(ValueError):
                validate_sequence(dict(sample('a.mp4'),ranges=ranges))
    def test_portable_save_open_and_legacy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=str(root/'없는 원본.mp4')
            project=Project(media_paths=[source],active_path=source,edit_sequences=[sample(source)])
            destination=root/'sequence.avsp'
            save_project(project,destination)
            self.assertEqual(load_project(destination),project)
            data=json.loads(destination.read_text(encoding='utf-8'))
            self.assertEqual(data['edit_sequences'][0]['source'],'없는 원본.mp4')
            data.pop('edit_sequences')
            destination.write_text(json.dumps(data),encoding='utf-8')
            self.assertEqual(load_project(destination).edit_sequences,[])
    def test_duplicate_and_unknown_source_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source=str(Path(folder)/'a.mp4')
            for sequences in ([sample(source),sample(source)],[sample(str(Path(folder)/'b.mp4'))]):
                with self.assertRaises(ValueError):
                    save_project(Project(media_paths=[source],edit_sequences=sequences),Path(folder)/'x.avsp')


class SequenceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow()
        self.w.show()
        self.w.preview.audio.setMuted(True)
        self.source=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())
        self.w.media.add_files([self.source])
        self.wait(lambda:self.w.preview.ready)
    def tearDown(self):
        self.w.dirty=False
        self.w.close()
        QTest.qWait(30)
    def wait(self,p):
        deadline=time.monotonic()+8
        while not p() and time.monotonic()<deadline:
            QTest.qWait(20)
        self.assertTrue(p())
    def test_create_multiple_tabs_source_preserved_and_restore(self):
        w=self.w
        before=Path(self.source).read_bytes()
        w.project.subtitles[self.source]=[dict(start=.5,end=3.5,text='자막',reviewed=True)]
        original=[dict(row) for row in w.project.subtitles[self.source]]
        w.create_edit_sequence(self.source,[(0,1),(3,4),(5,6)],7.188)
        self.assertEqual(w.timeline.sequence_tabs.count(),2)
        self.assertEqual(w.timeline.sequence_tabs.tabText(1),'무음 컷 1')
        self.assertEqual(w.preview.timeline_duration(),3000)
        self.assertEqual(len(w.timeline.canvas.blocks),6)
        self.assertFalse(w.timeline.scope.isEnabled())
        self.assertTrue(w.subtitle_panel.isEnabled())
        w.seek_transport(1500)
        self.assertEqual(w.preview.timeline_position(),1500)
        self.assertAlmostEqual(w.preview.player.position(),3500,delta=150)
        self.assertAlmostEqual(w.preview.audio_player.position(),3500,delta=150)
        w.create_edit_sequence(self.source,[(1,2),(4,6)],7.188)
        self.assertEqual(w.timeline.sequence_tabs.count(),3)
        w.timeline.sequence_tabs.setCurrentIndex(1)
        self.assertEqual(w.preview.sequence_ranges,[(0,1000),(3000,4000),(5000,6000)])
        w.timeline.sequence_tabs.setCurrentIndex(0)
        self.assertIsNone(w.preview.sequence_ranges)
        self.assertFalse(w.subtitle_panel.isEnabled())
        self.assertEqual(w.project.subtitles[self.source],original)
        self.assertEqual(Path(self.source).read_bytes(),before)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sequence.avsp'
            self.assertTrue(w.save_current(path=path))
            self.assertTrue(w.open_project_path(path))
            self.wait(lambda:w.preview.ready)
            self.assertEqual(w.timeline.sequence_tabs.count(),3)
            w.timeline.sequence_tabs.setCurrentIndex(1)
            self.assertEqual(w.preview.timeline_duration(),3000)
        w.close_edit_sequence(1)
        self.assertIsNone(w.active_sequence())
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),2)
        self.assertEqual(len(w.closed_sequence_ids),1)
    def test_playback_skips_cut_and_scrub_maps(self):
        w=self.w
        w.create_edit_sequence(self.source,[(0,1),(3,4),(5,6)],7.188)
        w.seek_transport(900)
        w.toggle_transport()
        self.wait(lambda:w.preview.timeline_position()>=1200)
        self.assertGreater(w.preview.player.position(),3000)
        w.toggle_transport()
        w.begin_timeline_scrub()
        w.request_timeline_seek(2200)
        w.end_timeline_scrub()
        self.assertEqual(w.preview.timeline_position(),2200)
        self.assertAlmostEqual(w.preview.player.position(),5200,delta=150)
        w.timeline.scope.setCurrentIndex(1)
        self.assertEqual(w.transport_duration_value(),3000)
        w.timeline.sequence_tabs.setCurrentIndex(0)
        w.show_source_subtitles()
        self.assertIsNone(w.preview.sequence_ranges)
    def test_sequence_switches_source_and_missing_source_is_blocked(self):
        w=self.w
        second=str((Path(__file__).parent/'fixtures/테스트 영상.mp4').resolve())
        w.media.add_files([second])
        w.create_edit_sequence(self.source,[(0,1),(3,4)],7.188)
        first_id=w.active_edit_id
        w.create_edit_sequence(second,[(0,1)],3)
        self.wait(lambda:w.preview.ready and str(w.preview.source)==second)
        self.assertEqual(w.preview.timeline_duration(),1000)
        w.timeline.sequence_tabs.setCurrentIndex(1)
        self.wait(lambda:w.preview.ready and str(w.preview.source)==self.source)
        self.assertEqual(w.active_edit_id,first_id)
        self.assertEqual(w.preview.timeline_duration(),2000)
        w.project.edit_sequences[1]['source']=str(Path(self.source).with_name('missing.mp4'))
        w.timeline.sequence_tabs.setCurrentIndex(2)
        self.assertEqual(w.active_edit_id,first_id)
        self.assertEqual(w.timeline.sequence_tabs.currentIndex(),1)
    def test_removing_source_prunes_sequences(self):
        w=self.w
        w.create_edit_sequence(self.source,[(0,1),(3,4)],7.188)
        w.media.remove_selected()
        self.assertEqual(w.project.edit_sequences,[])
        self.assertIsNone(w.active_sequence())
        self.assertEqual(w.timeline.sequence_tabs.count(),1)

if __name__=='__main__':
    unittest.main()
