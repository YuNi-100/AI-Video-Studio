import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from PySide6.QtCore import Qt,QSize,QSizeF,QPoint,QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtMultimedia import QVideoFrame,QVideoFrameFormat
from PySide6.QtWidgets import QApplication,QTreeWidgetItem,QStyle,QStyleOptionButton
from PySide6.QtTest import QTest
from app.ui.caption_video import CaptionVideoView
from app.ui.main_window import MainWindow
from app.ui.timeline import Timeline


class PreviewFitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyle('Fusion');cls.app.setStyleSheet(STYLE)

    def frame(self,size,rotation=0,extra=0):
        fmt=QVideoFrameFormat(QSize(*size),QVideoFrameFormat.PixelFormat.Format_RGBA8888)
        enum=type(fmt.rotation());fmt.setRotation(enum(rotation))
        frame=QVideoFrame(fmt);frame.setRotation(enum(extra));return frame

    def assert_fitted(self,view,ratio):
        rect=view.transform().mapRect(view.sceneRect());size=view.viewport().size()
        self.assertAlmostEqual(rect.width()/rect.height(),ratio,places=5)
        self.assertLessEqual(rect.width(),size.width()+1);self.assertLessEqual(rect.height(),size.height()+1)
        self.assertLess(min(abs(rect.width()-size.width()),abs(rect.height()-size.height())),6)

    def test_rotations_and_resolution_switch_fit_visible_area(self):
        view=CaptionVideoView();view.resize(960,300);view.show();QTest.qWait(20)
        try:
            for size,rotation,extra,expected in [((1080,1920),270,0,(1920,1080)),((1080,1920),90,0,(1920,1080)),((1080,1920),0,0,(1080,1920)),((1920,1080),180,0,(1920,1080)),((1080,1920),270,90,(1080,1920))]:
                view.native_size_changed(QSizeF(*size));view.frame_changed(self.frame(size,rotation,extra))
                self.assertEqual(view.video_item.size(),QSizeF(*expected))
                self.assert_fitted(view,expected[0]/expected[1])
            view.resize(400,700);QTest.qWait(20);self.assert_fitted(view,1080/1920)
            old=view.sceneRect();view.frame_changed(QVideoFrame());self.assertEqual(view.sceneRect(),old)
        finally:view.close();view.deleteLater();QTest.qWait(30)

    def test_hidden_view_refits_when_shown_and_caption_stays_inside(self):
        view=CaptionVideoView();view.frame_changed(self.frame((1080,1920),90))
        view.show_caption('아래 자막')
        view.resize(900,400);view.show();QTest.qWait(20)
        try:
            self.assert_fitted(view,16/9)
            self.assertTrue(view.sceneRect().contains(view.caption.sceneBoundingRect()))
        finally:view.close();view.deleteLater();QTest.qWait(30)

    def test_late_native_size_does_not_override_frame_orientation(self):
        view=CaptionVideoView()
        try:
            view.frame_changed(self.frame((1080,1920),270))
            view.native_size_changed(QSizeF(1920,1080))
            self.assertEqual(view.video_item.size(),QSizeF(1920,1080))
            view.frame_changed(QVideoFrame())
            view.native_size_changed(QSizeF(1080,1920))
            self.assertEqual(view.video_item.size(),QSizeF(1920,1080))
            view.reset_frame_geometry();view.frame_changed(self.frame((1080,1920)))
            self.assertEqual(view.video_item.size(),QSizeF(1080,1920))
        finally:view.close();view.deleteLater();QTest.qWait(30)

    @unittest.skipUnless(os.environ.get('STUDIO_NATIVE_PREVIEW_TEST'),'requires real Windows screen pixels')
    def test_rotated_frame_refreshes_left_middle_and_right(self):
        view=CaptionVideoView();view.show();QTest.qWait(30);view.resize(900,360);QTest.qWait(30)
        def solid(r,g,b):
            fmt=QVideoFrameFormat(QSize(180,320),QVideoFrameFormat.PixelFormat.Format_RGBA8888)
            fmt.setRotation(type(fmt.rotation())(270))
            frame=QVideoFrame(fmt)
            self.assertTrue(frame.map(QVideoFrame.MapMode.WriteOnly))
            data=frame.bits(0);data[:frame.mappedBytes(0)]=bytes((r,g,b,255))*(frame.mappedBytes(0)//4)
            frame.unmap();return frame
        try:
            view.videoSink().setVideoFrame(solid(230,30,30));QTest.qWait(100)
            view.videoSink().setVideoFrame(solid(30,40,230));QTest.qWait(100)
            # grabWindow reads the visible pixels; QWidget.grab() would repaint
            # the whole scene and accidentally hide the partial refresh defect.
            pix=view.screen().grabWindow(view.winId());self.assertFalse(pix.isNull())
            img=pix.toImage();ratio=pix.devicePixelRatio()
            rect=view.mapFromScene(view.sceneRect()).boundingRect()
            for fraction in (.15,.5,.85):
                x=round((rect.left()+rect.width()*fraction)*ratio);y=round(rect.center().y()*ratio)
                color=img.pixelColor(x,y)
                self.assertGreater(color.blue(),180,(fraction,color.name()))
                self.assertLess(color.red(),80,(fraction,color.name()))
        finally:view.close();view.deleteLater();QTest.qWait(30)


class CompactTimelineTests(unittest.TestCase):
    setUpClass=classmethod(PreviewFitTests.setUpClass.__func__)

    def wheel(self,widget,x,delta=120,mod=Qt.KeyboardModifier.AltModifier):
        point=QPointF(x,widget.height()/2)
        event=QWheelEvent(point,QPointF(widget.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,delta),Qt.MouseButton.NoButton,mod,Qt.ScrollPhase.NoScrollPhase,False)
        QApplication.sendEvent(widget,event)

    def test_alt_wheel_canvas_keeps_pointer_time_and_slider_synced(self):
        t=Timeline();t.resize(1300,360);t.show();QTest.qWait(20)
        try:
            c=t.canvas;c.duration=120000;t.zoom.setValue(200);c.offset=20000;t.update_scroll()
            x=95+.4*(c.width()-107)
            fraction=(QPointF(x,0).toPoint().x()-95)/(c.width()-107)
            before=c.offset+fraction*c.span
            self.wheel(c,x)
            self.assertGreater(t.zoom.value(),200);self.assertEqual(t.zoom.value(),c.zoom)
            self.assertAlmostEqual(c.offset+fraction*c.span,before,delta=2)
            larger=t.zoom.value();self.wheel(c,x,-120);self.assertLess(t.zoom.value(),larger)
            value=t.zoom.value();self.wheel(c,x,120,Qt.KeyboardModifier.NoModifier);self.assertEqual(t.zoom.value(),value)
            self.wheel(t.zoom,t.zoom.width()/2);self.assertGreater(t.zoom.value(),value)
            t.zoom.setValue(t.zoom.maximum());self.wheel(c,x);self.assertEqual(t.zoom.value(),t.zoom.maximum())
        finally:t.close();t.deleteLater();QTest.qWait(30)

    def test_compact_panel_keeps_three_tracks_and_list_scrollable(self):
        w=MainWindow();w.show();QTest.qWait(30)
        # Realize the native window before sizing, so Windows applies its DPI
        # transition before the layout/drag measurements.
        w.resize(1480,860);QTest.qWait(30)
        try:
            for i in range(70):w.timeline.sequence_tree.addTopLevelItem(QTreeWidgetItem([f'자료 {i}','자료']))
            split=w.workspace_vertical;handle=split.handle(1);point=handle.rect().center()
            low,high=split.getRange(1)
            split.moveSplitter((low+high)//2,1);QTest.qWait(30)
            before=split.sizes()
            QTest.mousePress(handle,Qt.MouseButton.LeftButton,pos=point)
            QTest.mouseMove(handle,point+QPoint(0,500),delay=30)
            QTest.mouseRelease(handle,Qt.MouseButton.LeftButton);QTest.qWait(30)
            self.assertGreater(split.sizes()[0],before[0],(w.size(),w.pos(),split.geometry(),split.getRange(1),w.screen().availableGeometry()))
            c=w.timeline.canvas
            self.assertGreaterEqual(c.height(),189);self.assertLess(c.height(),230)
            hint=w.timeline.hint
            self.assertTrue(hint.parentWidget().contentsRect().contains(hint.geometry()))
            self.assertGreaterEqual(hint.height(),hint.heightForWidth(hint.width()))
            tree=w.timeline.sequence_tree
            self.assertGreater(tree.verticalScrollBar().maximum(),0)
            tree.scrollToBottom();QTest.qWait(10)
            self.assertTrue(tree.viewport().rect().intersects(tree.visualItemRect(tree.topLevelItem(tree.topLevelItemCount()-1))))
        finally:
            w.dirty=False
            for d in w.documents:d['dirty']=False
            w.close();w.deleteLater();QTest.qWait(30)

    def test_library_buttons_text_fits_with_larger_font(self):
        w=MainWindow();w.show();QTest.qWait(30);w.resize(1480,860);QTest.qWait(30)
        try:
            for button in (w.media.new_folder,w.media.rename_button):
                button.setStyleSheet('font-size: 18px; padding: 4px 8px;')
            w.workspace_horizontal.setSizes([300,900,310]);QTest.qWait(20)
            for button in (w.media.new_folder,w.media.rename_button):
                opt=QStyleOptionButton();opt.initFrom(button)
                contents=button.style().subElementRect(QStyle.SubElement.SE_PushButtonContents,opt,button)
                text=button.fontMetrics().boundingRect(button.text())
                self.assertGreaterEqual(contents.height(),text.height(),(button.text(),button.size(),button.minimumSizeHint(),button.minimumSize(),w.size(),w.workspace_vertical.sizes()))
                self.assertGreaterEqual(contents.width(),text.width())
        finally:w.dirty=False;w.close();w.deleteLater();QTest.qWait(30)
