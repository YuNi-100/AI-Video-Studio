import os,unittest,tempfile,time,wave,subprocess,sys,json
os.environ['QT_QPA_PLATFORM']='offscreen'
from copy import deepcopy
from pathlib import Path
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from app.features.subtitles.audit import audit_captions
from app.features.subtitles.audit_worker import audio_window
from app.features.subtitles.sequence_audio import render_audio
from app.features.silence.sequence import validate_sequence,sequence_clips

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())

class AuditModelTests(unittest.TestCase):
    def test_reviewed_text_is_unchanged_and_structural_issues_found(self):
        rows=[dict(start=0,end=.2,text='라겸 화이팅',reviewed=True),dict(start=.1,end=1,text='라검 화이팅',reviewed=True),dict(start=1.1,end=2,text='라검 화이팅',reviewed=True)]
        before=deepcopy(rows);findings=audit_captions(rows,3,'라겸')
        reasons=' '.join(reason for f in findings for reason in f['reasons'])
        for expected in ('표시 시간이 짧음','읽는 속도','시간 겹침','같은 문장','표기 확인'):self.assertIn(expected,reasons)
        self.assertEqual(rows,before);self.assertTrue(all(r['reviewed'] for r in rows))

    def test_voice_gaps_timing_and_range_are_suggestions(self):
        rows=[dict(start=0,end=3,text='수정한 문장',reviewed=True)]
        findings=audit_captions(rows,8,speech=[(.8,1.5),(4,6)])
        self.assertTrue(any('일찍' in ' '.join(f['reasons']) for f in findings))
        self.assertTrue(any('오래' in ' '.join(f['reasons']) for f in findings))
        missing=next(f for f in findings if f['index'] is None);self.assertEqual((missing['start'],missing['end']),(4,6))
        scoped=audit_captions(rows,8,speech=[(.8,1.5),(4,6)],start=4.5,end=5.5)
        self.assertEqual([(r['start'],r['end']) for r in scoped],[(4.5,5.5)])

    def test_no_audio_claim_without_audio_check_and_outside_video(self):
        self.assertEqual(audit_captions([dict(start=0,end=1,text='좋아요',reviewed=True)],2),[])
        issue=audit_captions([dict(start=4,end=5,text='뒤 자막')],3)
        self.assertIn('작업본 길이를 넘는 자막',issue[0]['reasons'])

    def test_audio_window_keeps_edit_time_source_offsets_and_gaps(self):
        seq=validate_sequence(dict(id='x',name='작업',source=SOURCE,duration=7.188,ranges=[],clips=[dict(track='audio',start=1,end=3,at=4,group='a')]))
        result=audio_window(seq,5,7)
        self.assertEqual([(c['at'],c['start'],c['end']) for c in sequence_clips(result)],[(0,2,3)])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'window.wav';render_audio(result,path,extent_seconds=2)
            with wave.open(str(path)) as audio:self.assertEqual(audio.getnframes(),32000)

    def test_offline_vad_detects_speech_without_transcribing(self):
        seq=validate_sequence(dict(id='x',name='작업',source=SOURCE,duration=7.188,ranges=[[0,7.188]]))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'speech.wav';render_audio(seq,path)
            # Match production: keep the VAD native runtime outside the Qt UI
            # process, including when the entire test suite shares one app.
            raw=subprocess.check_output([sys.executable,'-c','import json,sys; from app.features.subtitles.audit_worker import speech_ranges; print(json.dumps(speech_ranges(sys.argv[1])))',str(path)],timeout=20)
            ranges=json.loads(raw)
            self.assertTrue(ranges);self.assertTrue(all(0<=a<b<=7.3 for a,b in ranges))


class AuditUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        if cls.app.style().objectName().lower()!='fusion':cls.app.setStyle('Fusion')
        if cls.app.styleSheet()!=STYLE:cls.app.setStyleSheet(STYLE)
        cls.app.processEvents();QTest.qWait(30)

    def setUp(self):
        from app.ui.main_window import MainWindow
        self.w=MainWindow();self.w.show();self.w.activateWindow();QTest.qWait(30)
        w=self.w;w.media.add_files([SOURCE]);end=time.monotonic()+8
        while not w.preview.ready and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(w.preview.ready)
        w.project.subtitles[SOURCE]=[dict(start=.2,end=.4,text='라겸 화이팅',reviewed=True),dict(start=.35,end=1.2,text='라검 화이팅',reviewed=True)]
        w.subtitle_panel.terms.setText('라겸');w.create_edit_sequence(SOURCE,[(0,7)],7.188)
        w.open_subtitle_audit();self.d=w.audit_dialog

    def tearDown(self):
        self.d.reject()
        if hasattr(self.w,'recheck_dialog'):self.w.recheck_dialog.reject()
        self.w.dirty=False
        for doc in self.w.documents:doc['dirty']=False
        self.w.close();QTest.qWait(30)

    def wait(self):
        end=time.monotonic()+30
        while self.d.process and time.monotonic()<end:QTest.qWait(20)
        self.assertIsNone(self.d.process,self.d.status.text())

    def test_final_check_does_not_change_corrections_or_history(self):
        w=self.w;before=deepcopy(w.project);history=len(w.project_undo)
        self.d.audio.setChecked(False);self.d.begin();self.wait()
        self.assertTrue(self.d.findings,self.d.status.text())
        self.assertEqual(w.project,before);self.assertEqual(len(w.project_undo),history)
        self.assertNotIn('체크한 후보만 적용',[b.text() for b in self.d.findChildren(QPushButton)])
        self.d.table.setCurrentCell(0,0);self.d.recognize_selected()
        self.assertIn('구간 재인식',w.recheck_dialog.windowTitle())
        self.assertEqual(w.recheck_dialog.scope.currentIndex(),1)
        self.assertEqual(w.project,before)

    def test_real_audio_audit_and_main_editor_navigation(self):
        before=deepcopy(self.w.project);self.d.begin();self.wait()
        self.assertTrue(self.d.report['audio_checked'],self.d.status.text())
        self.assertEqual(self.w.project,before)
        i=next(i for i,f in enumerate(self.d.findings) if f['index'] is not None)
        self.d.table.setCurrentCell(i,0);self.d.edit_selected()
        self.assertFalse(self.d.isVisible());self.assertEqual(self.w.subtitle_panel.tabs.currentIndex(),1)
        self.assertEqual(self.w.project,before)

    def test_changed_work_discards_results_and_range_is_respected(self):
        d=self.d;d.audio.setChecked(False);d.scope.setCurrentIndex(1);d.start.setValue(.3);d.end.setValue(.8)
        d.begin();self.w.active_sequence()['name']='점검 중 이름 변경';self.wait()
        self.assertEqual(d.findings,[]);self.assertIn('바뀌어',d.status.text())
        d.prepare();d.scope.setCurrentIndex(1);d.start.setValue(2);d.end.setValue(3);d.begin();self.wait()
        self.assertEqual(d.findings,[])

    def test_close_during_check_preserves_project_and_cleans_temporary_audio(self):
        before=deepcopy(self.w.project);self.d.begin();path=Path(self.d.work.name)
        self.d.reject();QTest.qWait(30)
        self.assertIsNone(self.d.process);self.assertFalse(path.exists());self.assertEqual(self.w.project,before)
