from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QSignalBlocker, QPoint, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF, QBrush
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSlider, QScrollBar, QCheckBox, QComboBox, QPushButton, QTabBar, QToolButton, QListWidget, QSizePolicy, QFrame
from app.ui.components import panel, label
from app.core.media import timecode
from app.ui.project_tree import ProjectTree


class TrackCanvas(QWidget):
    clear_requested = Signal()
    range_selected = Signal(list,list,bool)
    edit_requested = Signal()
    clip_selected = Signal(str,int)
    clip_edited = Signal(str,int,str,int,bool)
    split_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    delete_requested = Signal()
    ripple_delete_requested = Signal()
    gap_selected = Signal(str,int,int)
    seek_requested = Signal(int)
    clip_seek_requested = Signal(int)
    subtitle_selected = Signal(int)
    block_moved = Signal(str, int, int)
    subtitle_resized = Signal(int, int, int)
    scrub_started = Signal()
    scrub_finished = Signal()

    def __init__(self):
        super().__init__()
        self.keyboard_active=False
        self.zoom = 100
        self.duration = 0
        self.position = 0
        self.offset = 0
        self.segments = []
        self.name = ""
        self.blocks = []
        self.sequence_view = False
        self.selected_keys = set()
        self.selected_gap=None
        self.gap_linked=True
        self.gap_probe=None
        self.snap_guide=None
        self.snap_insert=False
        self.edit_blocked=False
        self.selected_clip = None
        self.selected_track = None
        self.preview_blocks = None
        self.preview_segments = None
        self.selection_additive = False
        self.selection_alt = False
        self.individual_selection = False
        self.drag_destinations=[]
        self.edit_preview = None
        self._ripple = False
        self.selection_origin=None
        self.selection_box=None
        self.selected_subtitles=set()
        self.drag = None
        self.navigation = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(230)
        self.setAccessibleName("영상과 자막 타임라인 · 클릭하여 재생 위치 이동")

    @property
    def span(self):
        return max(1000, round(max(10000, self.duration) * 100 / self.zoom))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left, top, row = 95, 30, 43
        width = max(1, self.width() - left - 12)
        major,minor = self.tick_steps()
        first = (self.offset//minor)*minor
        last_label = -1000
        for value in range(first,self.offset+self.span+minor,minor):
            x = left+(value-self.offset)/self.span*width
            if x < left or x > self.width()-12:
                continue
            is_major = value % major == 0
            p.setPen(QColor("#8b97b0" if is_major else "#48536d"))
            p.drawLine(round(x),19 if is_major else 25,round(x),30)
            if is_major:
                label_x = max(left,min(x-37,self.width()-88))
                if label_x-last_label >= 80:
                    p.drawText(QRectF(label_x,0,85,18),self.ruler_time(value,major))
                    last_label = label_x
        for i, (name, color) in enumerate(((("V1  영상" if self.sequence_view else "V1  원본"), "#9567ff"), ("S1  자막", "#d9b969"), ("A1  음성", "#49c5b6"))):
            y = top + i * row
            p.setPen(QColor(color))
            p.drawText(QRectF(0, y, left-5, row), Qt.AlignmentFlag.AlignVCenter, name)
            p.setPen(QPen(QColor("#343b50"), 1, Qt.PenStyle.DashLine))
            p.setBrush(QColor("#131724"))
            p.drawRoundedRect(QRectF(left, y+3, width, row-7), 5, 5)
        p.save()
        p.setClipRect(QRectF(left, top, width, row * 3))
        def x_at(ms):
            return left + (ms-self.offset) / self.span * width
        p.setPen(QPen(QColor("#242b3b"),1))
        for value in range(first,self.offset+self.span+minor,minor):
            x = round(x_at(value))
            p.drawLine(x,top,x,top+row*3)
        overwrite_preview=bool(self.sequence_view and self.drag and self.drag[5]=='move' and self.drag[4] and not self._ripple and not self.snap_insert)
        if self.selected_gap is not None:
            track,a,b=self.selected_gap
            y=top if self.gap_linked or track=='video' else top+(1 if track=='subtitle' else 2)*row
            height=row*3 if self.gap_linked else row
            rect=QRectF(x_at(a),y+3,max(1,x_at(b)-x_at(a)),height-7)
            p.fillRect(rect,QColor(139,212,203,40))
            p.setPen(QPen(QColor('#8bd4cb'),1,Qt.PenStyle.DashLine));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(rect)
        for block in (self.preview_blocks if self.preview_blocks is not None and not overwrite_preview else self.blocks):
            track, start, end, name, key = block
            y = top + (0 if track == "video" else 2)*row
            if not self.sequence_view and self.drag and self.drag[0] == track and self.drag[1] == key:
                delta = self.drag[4]
                start, end = start+delta, end+delta
            rect = QRectF(x_at(start), y+4, max(3, (end-start)/self.span*width), row-9)
            selected=self.sequence_view and (key==self.selected_clip or key in self.selected_keys)
            p.setPen(QPen(QColor("#a5deef" if selected else ("#9567ff" if track == "video" else "#49c5b6")),2 if selected else 1))
            p.setBrush(QColor("#302448" if track == "video" else "#193c3b"))
            p.drawRoundedRect(rect, 4, 4)
            if self.sequence_view and rect.width()>=18:
                for edge in (rect.left()+3,rect.right()-3):
                    p.drawLine(round(edge),round(rect.top()+9),round(edge),round(rect.bottom()-9))
            p.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, name)
        for index, segment in enumerate(self.preview_segments if self.preview_segments is not None else self.segments):
            start, end = segment["start"]*1000, segment["end"]*1000
            if not self.sequence_view and self.drag and self.drag[0] == "subtitle" and self.drag[1] == index:
                if self.drag[5] == "start":
                    start += self.drag[4]
                elif self.drag[5] == "end":
                    end += self.drag[4]
                else:
                    start, end = start+self.drag[4], end+self.drag[4]
            if end < self.offset or start > self.offset + self.span:
                continue
            rect = QRectF(x_at(start), top+row+4, max(3, (end-start)/self.span*width), row-9)
            p.setBrush(QColor("#393327" if not segment.get("reviewed") else "#514329"))
            p.setPen(QPen(QColor("#f7eed5" if index in self.selected_subtitles else "#aa9467" if not segment.get("reviewed") else "#d9b969"),2 if index in self.selected_subtitles else 1))
            p.drawRoundedRect(rect, 3, 3)
            if rect.width() >= 18:
                p.setPen(QColor("#f5e8c9"))
                for edge in (rect.left()+3,rect.right()-3):
                    p.drawLine(round(edge),round(rect.top()+9),round(edge),round(rect.bottom()-9))
            if rect.width() > 35:
                text = p.fontMetrics().elidedText(segment["text"].replace("\n", " "), Qt.TextElideMode.ElideRight, max(1, round(rect.width()-10)))
                p.setPen(QColor("#f5e8c9"))
                p.drawText(rect.adjusted(5, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter, text)
        p.setPen(QColor("#e0c8ff"))
        x = round(x_at(self.position))
        p.drawLine(x, top, x, top+row*3)
        p.restore()
        if self.sequence_view and self.drag and self.drag[4] and self.drag[5]=='move':
            p.save();p.setClipRect(QRectF(left,top,width,row*3))
            for track,start,end,name,key in self.drag_destinations:
                y=top+(0 if track=='video' else 2)*row+4
                target=QRectF(x_at(start),y,max(3,(end-start)/self.span*width),row-9)
                if not self._ripple and not self.snap_insert:
                    for old_track,a,b,_,old_key in self.blocks:
                        if old_track!=track or old_key in self.selected_keys:continue
                        a,b=max(a,start),min(b,end)
                        if a<b:
                            cut=QRectF(x_at(a),y,max(1,(b-a)/self.span*width),row-9)
                            p.fillRect(cut,QColor(230,119,87,75))
                            p.fillRect(cut,QBrush(QColor('#ed997b'),Qt.BrushStyle.BDiagPattern))
                p.setPen(QPen(QColor('#b2e6f0'),2,Qt.PenStyle.DashLine));p.setBrush(QColor(123,210,224,35));p.drawRoundedRect(target,4,4)
            p.restore()
            if self.snap_guide is not None:
                p.setPen(QPen(QColor('#8bd4cb'),2));p.drawLine(round(x_at(self.snap_guide)),top,round(x_at(self.snap_guide)),top+row*3)
            p.setPen(QColor('#8bd4cb' if self.snap_insert else '#b2e6f0' if self._ripple else '#edb095'))
            message='끝 맞춤 · 컷 길이 보존 / 필요한 뒤 컷 밀기' if self.snap_insert else '이동 불가 · 공통 경계로 옮기세요' if self.edit_blocked else '뒤 항목 함께 이동' if self._ripple else '덮어쓰기 · 점선: 놓일 위치 / 빗금: 제거될 부분'
            p.drawText(QRectF(95,167,max(1,self.width()-107),22),message)
        x = round(x_at(self.position))
        if left <= x <= self.width()-12:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#e0c8ff"))
            p.drawPolygon(QPolygonF([QPointF(x-5,20),QPointF(x+5,20),QPointF(x,29)]))
        if self.selected_gap is not None and not self.drag:
            p.setPen(QColor('#8bd4cb'));p.drawText(QRectF(95,167,max(1,self.width()-107),22),'빈칸 선택 · Backspace / Alt+Backspace: 빈칸 닫기')
        if self.selection_box is not None and self.selection_box.width()>3:
            p.setPen(QPen(QColor("#9edbf0"),1,Qt.PenStyle.DashLine))
            p.setBrush(QColor(135,200,230,40))
            p.drawRect(self.selection_box)
        p.end()

    def tick_steps(self):
        target = self.span*100/max(1,self.width()-107)
        candidates = (100,200,500,1000,2000,5000,10000,15000,30000,
                      60000,120000,300000,600000,900000,1800000,3600000,
                      7200000,18000000,36000000,86400000,172800000,604800000)
        major = next((value for value in candidates if value >= target),candidates[-1])
        minor = max(1,major//5)
        if minor/self.span*max(1,self.width()-107) < 8:
            minor = major
        return major,minor

    @staticmethod
    def ruler_time(value,step):
        if step >= 1000:
            return timecode(value)
        return f"{value//60000:02}:{value//1000%60:02}.{value%1000:03}"

    def value_at(self, x):
        return max(0, round(self.offset+(x-95)/max(1,self.width()-107)*self.span))

    def subtitle_hit(self, x, y):
        if not 77 <= y < 107 or not 95 <= x <= self.width()-12:
            return None
        scale = max(1,self.width()-107)/self.span
        for i,segment in enumerate(self.segments):
            left = 95+(segment["start"]*1000-self.offset)*scale
            right = 95+(segment["end"]*1000-self.offset)*scale
            if left-2 <= x <= right+2:
                mode = "move"
                if right-left >= 18:
                    if left >= 95 and abs(x-left) <= 6:
                        mode = "start"
                    elif right <= self.width()-12 and abs(x-right) <= 6:
                        mode = "end"
                return i,mode
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.duration or event.position().x() < 95:
            return
        self.setFocus()
        value = self.value_at(event.position().x())
        self.selected_gap=None
        self.snap_guide=None;self.snap_insert=False;self.edit_blocked=False
        if event.position().y() < 30:
            self.navigation = True
            self.scrub_started.emit()
            self.seek_requested.emit(min(self.duration,value))
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        row = int((event.position().y()-30)//43)
        self._ripple=bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.drag_destinations=[]
        self.selection_additive=bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        self.selection_alt=bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if not self.sequence_view and row in (0,1,2) and (self._ripple or (row==1 and (self.selection_additive or len(self.selected_subtitles)>1))):
            self.edit_requested.emit()
        hit = None
        subtitle = self.subtitle_hit(event.position().x(),event.position().y())
        if subtitle is not None:
            i,mode = subtitle
            segment = self.segments[i]
            hit = ("subtitle",i,round(segment["start"]*1000),mode,round(segment["end"]*1000))
        elif row in (0,2) and 4 <= (event.position().y()-30)%43 <= 34:
            for track,start,end,name,key in self.blocks:
                if track == ("video" if row == 0 else "audio") and start <= value < end:
                    hit = (track,key,start,"move",end)
                    break
        if self.sequence_view:
            if hit:
                track,key,start,mode,end=hit
                width=max(1,self.width()-107)
                left=95+(start-self.offset)/self.span*width
                right=95+(end-self.offset)/self.span*width
                if right-left>=18:
                    if left>=95 and abs(event.position().x()-left)<=6: mode='start'
                    elif right<=self.width()-12 and abs(event.position().x()-right)<=6: mode='end'
                self.drag=[track,key,start,event.position().x(),0,mode,end]
                self.clip_selected.emit(track,key)
                # Ctrl-click toggles selection; do not move a deselected item.
                if (track=='subtitle' and key not in self.selected_subtitles) or (track!='subtitle' and key not in self.selected_keys):self.drag=None
                self.update()
            else:
                self.start_range_selection(event)
            return
        if hit:
            track,key,start,mode,end = hit
            if track=='subtitle':
                if self.selection_additive:
                    if key in self.selected_subtitles:self.selected_subtitles.remove(key)
                    else:self.selected_subtitles.add(key)
                elif key not in self.selected_subtitles:self.selected_subtitles={key}
            self.drag = [track,key,start,event.position().x(),0,mode,end]
            self.setCursor(Qt.CursorShape.SizeHorCursor if mode != "move" else Qt.CursorShape.ClosedHandCursor)
        else:
            self.start_range_selection(event)

    def mouseMoveEvent(self, event):
        if self.selection_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.selection_box=QRectF(self.selection_origin,event.position()).normalized().intersected(QRectF(95,30,max(1,self.width()-107),self.height()-30))
            self.update()
            return
        if self.navigation and event.buttons() & Qt.MouseButton.LeftButton:
            self.seek_requested.emit(min(self.duration,self.value_at(event.position().x())))
            return
        if self.sequence_view and self.drag and event.buttons() & Qt.MouseButton.LeftButton:
            dx=event.position().x()-self.drag[3]
            self.drag[4]=round(dx/max(1,self.width()-107)*self.span) if abs(dx)>=4 else 0
            self._ripple=self._ripple or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if self.edit_preview:
                preview=self.edit_preview(self.drag[1],self.drag[5],self.drag[4],self._ripple,self.drag[0])
                if preview is not None:self.preview_blocks,self.preview_segments=preview
            self.update()
            return
        if self.drag and event.buttons() & Qt.MouseButton.LeftButton:
            dx = event.position().x()-self.drag[3]
            delta = round(dx/max(1,self.width()-107)*self.span) if abs(dx) >= 4 else 0
            start,end,mode = self.drag[2],self.drag[6],self.drag[5]
            minimum = min(100,end-start)
            if mode == "start":
                delta = min(max(delta,-start),end-start-minimum)
            elif mode == "end":
                delta = max(delta,start+minimum-end)
            else:
                delta = max(delta,-start)
            self.drag[4] = delta
            self.update()
            return
        if self.sequence_view:
            subtitle=self.subtitle_hit(event.position().x(),event.position().y())
            if subtitle is not None:
                self.setCursor(Qt.CursorShape.SizeHorCursor if subtitle[1]!='move' else Qt.CursorShape.OpenHandCursor)
                self.setToolTip('자막 양 끝: 길이 조절 · 가운데: 선택 항목 이동 · Ctrl+클릭: 추가/해제 · Shift: 뒤 자막 함께')
                return
            value=self.value_at(event.position().x())
            row=int((event.position().y()-30)//43)
            hovered=next((b for b in self.blocks if b[0]==('video' if row==0 else 'audio' if row==2 else '') and b[1]<=value<b[2]),None)
            edge=False
            if hovered:
                width=max(1,self.width()-107)
                left=95+(hovered[1]-self.offset)/self.span*width
                right=95+(hovered[2]-self.offset)/self.span*width
                edge=right-left>=18 and ((left>=95 and abs(event.position().x()-left)<=6) or (right<=self.width()-12 and abs(event.position().x()-right)<=6))
            self.setCursor(Qt.CursorShape.SizeHorCursor if edge else Qt.CursorShape.OpenHandCursor if hovered else Qt.CursorShape.ArrowCursor)
            self.setToolTip(('컷이 좁습니다. 확대하면 양 끝을 조절할 수 있습니다.' if right-left<18 else '양 끝: 길이 조절 · 가운데: 이동 · Shift: 뒤 컷 함께 이동') if hovered else '컷 사이 공통 빈칸 클릭: 선택 · Backspace: 빈칸 닫기')
            return
        hit = self.subtitle_hit(event.position().x(),event.position().y())
        self.setCursor(Qt.CursorShape.SizeHorCursor if hit and hit[1] != "move" else
                       Qt.CursorShape.OpenHandCursor if hit else Qt.CursorShape.ArrowCursor)
        if hit:
            segment = self.segments[hit[0]]
            pixels = (segment["end"]-segment["start"])*1000/self.span*max(1,self.width()-107)
            self.setToolTip("자막이 좁습니다. 확대하면 양 끝을 조정할 수 있습니다." if pixels < 18 else
                            "양 끝: 시작·종료 조정 · 가운데: 전체 이동")
        else:
            self.setToolTip("시간 눈금 드래그: 재생 위치 이동 · 빈 곳 클릭: 위치 이동")

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.selection_origin is not None:
            box=self.selection_box
            self.selection_origin=None;self.selection_box=None
            if box is not None and box.width()>4 and box.height()>4:
                blocks=[];subtitles=[]
                for track,start,end,name,key in self.blocks:
                    rect=QRectF(95+(start-self.offset)/self.span*(self.width()-107),34 if track=='video' else 120,max(3,(end-start)/self.span*(self.width()-107)),34)
                    if rect.intersects(box):blocks.append((track,key,start,end))
                for i,row in enumerate(self.segments):
                    rect=QRectF(95+(row['start']*1000-self.offset)/self.span*(self.width()-107),77,max(3,(row['end']-row['start'])*1000/self.span*(self.width()-107)),34)
                    if rect.intersects(box):subtitles.append(i)
                self.range_selected.emit(blocks,subtitles,self._selection_additive)
            else:
                value=self.value_at(event.position().x())
                row=int((event.position().y()-30)//43)
                track='video' if row==0 else 'subtitle' if row==1 else 'audio' if row==2 else None
                gap=self.gap_probe(value,track) if self.sequence_view and track and self.gap_probe and not self._selection_additive else None
                if gap:
                    self.gap_selected.emit(track,*gap)
                else:
                    if not self._selection_additive:self.clear_requested.emit()
                    self.seek_requested.emit(min(self.duration,value))
            self.update();return
        if self.navigation:
            self.seek_requested.emit(min(self.duration,self.value_at(event.position().x())))
            self.navigation = None
            self.scrub_finished.emit()
            self.unsetCursor()
            return
        drag,self.drag = self.drag,None
        if not drag:
            return
        track,key,start,x,delta,mode,end = drag
        if self.sequence_view:
            self.preview_blocks=None
            self.preview_segments=None
            if delta:
                self.clip_edited.emit(track,key,mode,delta,self._ripple or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier))
            else:
                self.clip_seek_requested.emit(min(self.duration,self.value_at(event.position().x())))
            self.unsetCursor()
            self.update()
            return
        if delta and mode != "move":
            self.subtitle_resized.emit(key,start+delta if mode == "start" else start,
                                       end+delta if mode == "end" else end)
        elif delta:
            self.block_moved.emit(track,key,start+delta)
        elif track == "subtitle":
            self.subtitle_selected.emit(key)
        else:
            self.seek_requested.emit(min(self.duration,self.value_at(event.position().x())))
        self.unsetCursor()
        self.update()

    def start_range_selection(self,event):
        self.selected_gap=None
        self.snap_guide=None;self.snap_insert=False
        self.selection_origin=QPointF(event.position())
        self.selection_box=QRectF(self.selection_origin,self.selection_origin)
        self._selection_additive=bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)

    def keyPressEvent(self, event):
        if not self.keyboard_active and event.key()!=Qt.Key.Key_Escape:
            super().keyPressEvent(event)
            return
        if not self.drag and not self.navigation and event.modifiers()==Qt.KeyboardModifier.ControlModifier and event.key() in (Qt.Key.Key_C,Qt.Key.Key_V):
            (self.copy_requested if event.key()==Qt.Key.Key_C else self.paste_requested).emit()
            event.accept()
            return
        if event.key()==Qt.Key.Key_Escape and self.selection_origin is not None:
            self.selection_origin=None;self.selection_box=None;self.update();event.accept();return
        if not self.sequence_view and self.selected_subtitles and event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):
            self.delete_requested.emit();event.accept();return
        if self.sequence_view and not self.drag and not self.navigation:
            if event.key()==Qt.Key.Key_Backspace and (event.modifiers()==Qt.KeyboardModifier.AltModifier or (self.selected_gap is not None and event.modifiers()==Qt.KeyboardModifier.NoModifier)):
                self.ripple_delete_requested.emit();event.accept();return
            if self.selected_gap is None and event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and event.modifiers()==Qt.KeyboardModifier.NoModifier:
                self.delete_requested.emit()
                event.accept()
                return
            if event.key()==Qt.Key.Key_K and event.modifiers()==Qt.KeyboardModifier.ControlModifier:
                self.split_requested.emit()
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape and self.navigation:
            self.navigation = None
            self.scrub_finished.emit()
            self.unsetCursor()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape and self.drag:
            self.drag = None
            self.preview_blocks = None
            self.preview_segments = None
            self.unsetCursor()
            self.update()
            event.accept()
        else:
            super().keyPressEvent(event)

    def leaveEvent(self, event):
        if not self.drag and not self.navigation:
            self.unsetCursor()
        super().leaveEvent(event)


class Timeline(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = panel()
        outer.addWidget(frame)
        self.sequence_tabs = QTabBar()
        self.sequence_tabs.setObjectName("sequenceTabs")
        self.sequence_tabs.setDrawBase(False)
        self.sequence_tabs.setExpanding(False)
        self.sequence_tabs.setUsesScrollButtons(True)
        self.sequence_tabs.setTabsClosable(False)
        self.sequence_tabs.addTab("원본")
        self.sequence_tabs.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        self.sequence_tabs.hide()
        layout.addWidget(self.sequence_tabs)
        bar = QHBoxLayout()
        bar.addWidget(label("타임라인", "heading"))
        self.info = label("미디어 없음", "muted")
        bar.addWidget(self.info)
        self.scope = QComboBox()
        self.scope.addItems(["선택 영상 보기", "전체 영상 이어 보기"])
        self.scope.setToolTip("원본 보기 범위입니다. 편집 시퀀스는 왼쪽 목록에서 선택하세요.")
        bar.addWidget(self.scope)
        self.scope.hide()
        self.earlier = QPushButton("앞 순서")
        self.later = QPushButton("뒤 순서")
        bar.addWidget(self.earlier)
        self.earlier.hide()
        bar.addWidget(self.later)
        self.later.hide()
        self.earlier.setToolTip("선택 영상을 미디어 목록에서 앞으로 이동")
        self.later.setToolTip("선택 영상을 미디어 목록에서 뒤로 이동")
        editbar=QHBoxLayout()
        editbar.setSpacing(10)
        self.link = QCheckBox("영상·음성 연결")
        self.link.setChecked(True)
        editbar.addWidget(self.link)
        self.begin_edit=QPushButton("편집 시작")
        self.begin_edit.setToolTip("원본 구성을 복사해 새 편집본에서 편집합니다. Ctrl+K / Shift 드래그로도 시작할 수 있습니다.")
        editbar.addWidget(self.begin_edit)
        self.undo = QPushButton("실행 취소")
        editbar.addWidget(self.undo)
        self.split_button=QPushButton('분할')
        self.split_button.setToolTip('선택 컷을 재생 위치에서 분할 · 타임라인에서 Ctrl+K')
        self.delete_button=QPushButton('삭제')
        self.delete_button.setToolTip('선택 컷만 삭제 · Delete/Backspace · Alt+Backspace: 빈틈 없이 삭제')
        editbar.addWidget(self.split_button)
        editbar.addWidget(self.delete_button)
        self.split_button.hide()
        self.delete_button.hide()
        self.current_edit=label('원본 보기','muted')
        self.current_edit.setAccessibleName('현재 타임라인 편집 대상')
        self.current_edit.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        editbar.addWidget(self.current_edit,1)
        editbar.addStretch()
        editbar.addWidget(label("확대", "muted"))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(50, 10000)
        self.zoom.setValue(100)
        self.zoom.setFixedWidth(120)
        self.zoom.setAccessibleName("타임라인 확대")
        editbar.addWidget(self.zoom)
        self.follow_playhead = True
        self.canvas = TrackCanvas()
        self.canvas.seek_requested.connect(lambda _:setattr(self,"follow_playhead",True))
        self.canvas.clip_seek_requested.connect(lambda _:setattr(self,"follow_playhead",True))
        content=QHBoxLayout()
        sidebar=QVBoxLayout()
        sidebar.addLayout(bar)
        bin_header=QHBoxLayout()
        bin_header.addWidget(label('편집본 목록', 'heading'))
        self.new_folder=QPushButton('새 폴더')
        self.new_folder.setStyleSheet('padding: 4px;')
        bin_header.addWidget(self.new_folder)
        sidebar.addLayout(bin_header)
        self.sequence_list=QListWidget()
        self.sequence_list.setObjectName('sequenceList')
        self.sequence_list.setFixedWidth(155)
        self.sequence_list.setAccessibleName('편집본 목록')
        self.sequence_list.addItem('원본')
        self.sequence_list.currentRowChanged.connect(self.sequence_tabs.setCurrentIndex)
        self.sequence_list.hide()
        self.sequence_tree=ProjectTree()
        self.sequence_tree.setFixedWidth(260)
        sidebar.addWidget(self.sequence_tree,1)
        content.addLayout(sidebar)
        self.editing_panel=QWidget()
        track_layout=QVBoxLayout(self.editing_panel)
        track_layout.setContentsMargins(12,12,12,10)
        track_layout.setSpacing(10)
        track_layout.addLayout(editbar)
        track_layout.addWidget(self.canvas)
        content.addWidget(self.editing_panel,1)
        layout.addLayout(content,1)
        self.scroll = QScrollBar(Qt.Orientation.Horizontal)
        self.scroll.setAccessibleName("타임라인 가로 이동")
        self.scroll.valueChanged.connect(self.scroll_changed)
        track_layout.addWidget(self.scroll)
        self.keyboard_active=False
        self.keyboard_border=QFrame(self)
        self.keyboard_border.setObjectName('timelineKeyboardBorder')
        self.keyboard_border.setStyleSheet('QFrame { background: transparent; border: 1px solid #756887; border-radius: 4px; }')
        self.keyboard_border.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,True)
        self.keyboard_border.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.keyboard_border.hide()
        self.zoom.valueChanged.connect(self.set_zoom)
        self.hint = label("시간 눈금 드래그 → 재생 위치 · 빈 곳 클릭 → 위치 이동 · 자막 양 끝 → 시간 조정", "muted")
        layout.addWidget(self.hint)
        self.update_scroll()

    def update_keyboard_border(self):
        if not hasattr(self,'keyboard_border'):return
        origin=self.editing_panel.mapTo(self,QPoint(0,0))
        self.keyboard_border.setGeometry(origin.x(),origin.y(),self.editing_panel.width(),self.editing_panel.height())
        self.keyboard_border.setVisible(self.keyboard_active)
        if self.keyboard_active:self.keyboard_border.raise_()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        QTimer.singleShot(0,self.update_keyboard_border)

    def add_sequence_close(self,index):
        button=QToolButton()
        button.setText('×')
        button.setFixedSize(20,20)
        button.setToolTip('탭 닫기 · 편집본 목록에는 유지')
        button.setStyleSheet('QToolButton { background: transparent; border: none; color: #aeb8c9; font-size: 17px; padding: 0; } QToolButton:hover { background: #3b465b; color: white; border-radius: 4px; }')
        button.clicked.connect(lambda:self.sequence_tabs.tabCloseRequested.emit(index))
        self.sequence_tabs.setTabButton(index,QTabBar.ButtonPosition.RightSide,button)

    def set_source(self, duration, segments, name, source_duration=None, video=0, audio=0, linked=True):
        self.canvas.selected_gap=None
        self.canvas.snap_guide=None
        self.canvas.snap_insert=False
        self.current_edit.setText('원본 보기'+(' · '+name if name else ''))
        self.current_edit.setToolTip(self.current_edit.text())
        self.canvas.duration = duration
        self.canvas.segments = segments
        self.canvas.name = name
        length = duration if source_duration is None else source_duration
        self.canvas.blocks = [("video",round(video*1000),round(video*1000)+length,name,0),
                              ("audio",round(audio*1000),round(audio*1000)+length,name,0)] if name else []
        with QSignalBlocker(self.link):
            self.link.setChecked(linked)
        self.info.setText(f"자막 {len(segments)}개" if name else "미디어 없음")
        self.update_scroll()
        self.canvas.update()

    def set_position(self, position):
        self.canvas.position = position
        if self.follow_playhead and (position < self.canvas.offset or position > self.canvas.offset + self.canvas.span):
            self.canvas.offset = min(max(0, position-self.canvas.span//4), max(0, self.canvas.duration-self.canvas.span))
            self.update_scroll()
        self.canvas.update()

    def update_scroll(self):
        maximum = max(0, self.canvas.duration-self.canvas.span)
        self.canvas.offset = min(self.canvas.offset, maximum)
        with QSignalBlocker(self.scroll):
            self.scroll.setRange(0, maximum)
            self.scroll.setPageStep(self.canvas.span)
            self.scroll.setValue(self.canvas.offset)
        self.scroll.setVisible(maximum > 0)

    def scroll_changed(self, value):
        self.follow_playhead = False
        self.canvas.offset = value
        self.canvas.update()

    def set_zoom(self, value):
        self.canvas.zoom = value
        self.update_scroll()
        self.canvas.update()
