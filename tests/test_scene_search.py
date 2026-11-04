import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import unittest
import tempfile
from pathlib import Path
from app.core.project import Project
from app.features.scene_search import search_edits, validate_tags
from app.features.silence.sequence import validate_sequence, combine_sequences, move_clips
from app.storage.project_store import save_project, load_project

SOURCE = str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())


class SearchTests(unittest.TestCase):
    def project(self):
        p = Project()
        p.media_paths = [SOURCE]
        p.subtitles[SOURCE] = [dict(start=2.2, end=2.5, text='Hello 장면')]
        p.edit_sequences = [validate_sequence(dict(id='a', name='편집', source=SOURCE, duration=7.188, ranges=[[2,3]]))]
        return p

    def test_search_uses_rendered_time_and_repeats(self):
        p = self.project()
        p.edit_sequences = [combine_sequences(p.edit_sequences*2, p.subtitles)]
        rows = search_edits(p, 'HELLO')
        self.assertEqual([r['start'] for r in rows], [.2, 1.2])
        self.assertEqual(search_edits(p, '없는 말'), [])

    def test_mixed_sources_and_independent_captions(self):
        p = self.project()
        other = str(Path(SOURCE).with_name('other.mp4'))
        s = p.edit_sequences[0]
        s = combine_sequences([s, dict(s, source=other)], {SOURCE:p.subtitles[SOURCE], other:[dict(start=2.1,end=2.8,text='다른 영상')]})
        p.edit_sequences = [s]
        self.assertEqual(search_edits(p, '다른')[0]['start'], 1.1)
        s['timeline_captions'] = [dict(start=4,end=5,text='독립 배치')]
        self.assertEqual(search_edits(p, '독립')[0]['start'], 4)
        self.assertEqual(search_edits(p, '다른'), [])

    def test_tags_roundtrip_fixed_time_and_combine(self):
        p = self.project()
        p.edit_sequences[0] = validate_sequence(dict(p.edit_sequences[0],scene_tags=[dict(name='골 장면',start=.1,end=.8)]))
        moved = move_clips(p.edit_sequences[0], {0}, 2000)
        self.assertEqual(moved['scene_tags'], p.edit_sequences[0]['scene_tags'])
        combined = combine_sequences(p.edit_sequences*2, p.subtitles)
        self.assertEqual([r['start'] for r in combined['scene_tags']], [.1,1.1])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.avsp'
            save_project(p,path)
            loaded=load_project(path)
            self.assertEqual(search_edits(loaded,'골','tags')[0]['start'],.1)

    def test_invalid_tags(self):
        for row in [dict(name='',start=0,end=1),dict(name='가',start=1,end=1),dict(name='가',start=float('nan'),end=2),dict(name='가',start=True,end=2)]:
            with self.assertRaises(ValueError):validate_tags([row])


class SearchUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyleSheet(STYLE)

    def test_tag_history_and_result_navigation(self):
        from app.ui.main_window import MainWindow
        from PySide6.QtTest import QTest
        import time
        w=MainWindow()
        try:
            w.media.add_files([SOURCE])
            deadline=time.monotonic()+8
            while not w.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
            self.assertTrue(w.preview.ready)
            w.project.subtitles[SOURCE]=[dict(start=2.2,end=2.5,text='찾을 대사')]
            w.create_edit_sequence(SOURCE,[(2,3)],7.188)
            w.open_scene_search()
            d=w.scene_search
            d.query.setText('대사');d.refresh()
            self.assertEqual(d.results.topLevelItemCount(),1)
            if os.environ.get('STUDIO_TEST_PREVIEW'):
                d.grab().save(os.environ['STUDIO_TEST_PREVIEW'])
            self.assertTrue(d.navigate(d.results.topLevelItem(0)))
            self.assertEqual(w.timeline.canvas.position,200)
            key=w.active_edit_id
            w.close_edit_sequence(w.timeline.sequence_tabs.currentIndex())
            self.assertIsNone(w.active_sequence())
            d.refresh()
            self.assertTrue(d.navigate(d.results.topLevelItem(0)))
            self.assertEqual(w.active_edit_id,key)
            self.assertEqual(w.timeline.canvas.position,200)
            d.tag_name.setText('핵심');d.start.setValue(.1);d.end.setValue(.7);d.add_tag()
            self.assertEqual(w.active_sequence()['scene_tags'][0]['name'],'핵심')
            w.change_sequence_history(False)
            self.assertNotIn('scene_tags',w.active_sequence())
            w.change_sequence_history(True)
            self.assertEqual(w.active_sequence()['scene_tags'][0]['name'],'핵심')
            d.query.setText('핵심');d.refresh();d.results.setCurrentItem(d.results.topLevelItem(0));d.remove_tag()
            self.assertEqual(len(w.active_sequence()['scene_tags']),0)
        finally:
            w.dirty=False
            for doc in w.documents:doc['dirty']=False
            w.close()
            QTest.qWait(20)
