import os,time,tempfile,subprocess,json,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from unittest.mock import patch
import av
import numpy as np
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from app.ui.video_export_dialog import VideoExportDialog
from app.features.silence.video_export import probe_sources,render_dimensions

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())

class ExportOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.temp=tempfile.TemporaryDirectory();root=Path(cls.temp.name)
        portrait=root/'portrait.mp4';cls.rotated=root/'rotated.mp4'
        subprocess.run(['ffmpeg','-v','error','-i',SOURCE,'-t','0.6','-vf','scale=180:320','-c:v','libx264','-c:a','aac','-y',str(portrait)],check=True)
        subprocess.run(['ffmpeg','-v','error','-display_rotation','90','-i',str(portrait),'-c','copy','-y',str(cls.rotated)],check=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def setUp(self):
        self.out=tempfile.TemporaryDirectory()
        self.seq=dict(id='export',name='출력 확인',source=str(self.rotated),duration=.6,ranges=[[0,.6]])
        self.rows=[dict(start=.1,end=.5,text='테스트 자막')]
        self.d=VideoExportDialog(self.seq,self.rows)

    def tearDown(self):
        self.d.reject();self.d.deleteLater();QTest.qWait(40);self.out.cleanup()

    def wait(self):
        end=time.monotonic()+30
        while self.d.process and time.monotonic()<end:QTest.qWait(20)
        self.assertIsNone(self.d.process,self.d.status.text())

    def frame(self,path):
        with av.open(str(path)) as c:
            frames=list(c.decode(video=0));return frames[len(frames)//2].to_ndarray(format='rgb24')

    def test_four_caption_audio_combinations_and_rotation(self):
        _,meta=probe_sources(self.seq);self.assertEqual(render_dimensions(self.seq,meta)[:2],(320,180))
        before=self.rotated.read_bytes();images={}
        for captions in (False,True):
            for audio in (False,True):
                self.d.include.setChecked(captions);self.d.audio_include.setChecked(audio)
                target=Path(self.out.name)/f'{captions}-{audio}.mp4'
                self.assertTrue(self.d.start_output(target));self.wait();self.assertTrue(target.is_file(),self.d.status.text())
                info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(target)]))
                video=next(s for s in info['streams'] if s['codec_type']=='video')
                self.assertEqual((video['width'],video['height']),(320,180))
                self.assertEqual(any(s['codec_type']=='audio' for s in info['streams']),audio)
                with av.open(str(target)) as c:self.assertEqual(next(c.decode(video=0)).rotation,0)
                images[captions,audio]=self.frame(target)
        difference=np.max(np.abs(images[True,False].astype(int)-images[False,False].astype(int)),axis=2)
        self.assertGreater(np.count_nonzero(difference[125:170]>25),50)
        self.assertLess(np.count_nonzero(difference[:90]>25),30)
        self.assertEqual(before,self.rotated.read_bytes())

    def test_subtitles_only_without_ffmpeg_and_existing_preserved(self):
        self.d.include.setChecked(False)
        target=Path(self.out.name)/'only.srt'
        with patch('app.ui.video_export_dialog.shutil.which',return_value=None):self.assertTrue(self.d.save_subtitles(target))
        contents=target.read_bytes();self.assertIn('테스트 자막',contents.decode('utf-8-sig'))
        self.assertIn('00:00:00,100 --> 00:00:00,500',contents.decode('utf-8-sig'))
        self.assertFalse(self.d.save_subtitles(target));self.assertEqual(target.read_bytes(),contents)

    def test_no_cancellation_button_and_result_links(self):
        self.assertNotIn('작업 취소',[b.text() for b in self.d.findChildren(QPushButton)])
        target=Path(self.out.name)/'saved.srt';self.assertTrue(self.d.save_subtitles(target))
        with patch('app.ui.video_export_dialog.QDesktopServices.openUrl') as opened:
            self.d.open_file.click();self.assertEqual(Path(opened.call_args.args[0].toLocalFile()),target)
            self.d.open_folder.click();self.assertEqual(Path(opened.call_args.args[0].toLocalFile()),target.parent)
        empty=VideoExportDialog(self.seq,[])
        try:
            self.assertFalse(empty.include.isEnabled());self.assertFalse(empty.subtitles_save.isEnabled())
            self.assertTrue(empty.audio_include.isChecked())
        finally:empty.close();empty.deleteLater();QTest.qWait(20)
