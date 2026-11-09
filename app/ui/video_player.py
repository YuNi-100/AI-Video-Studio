from pathlib import Path
from PySide6.QtCore import Qt, QUrl, Signal, QTimer, QElapsedTimer
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoFrame
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QSlider, QPushButton, QSizePolicy
from app.ui.caption_video import CaptionVideoView
from app.ui.seek_slider import SeekSlider
from app.features.subtitles.editing import active_text
from app.ui.components import panel, label
from app.features.silence.sequence import sequence_source_ms, track_source_ms
from app.core.media import validate_video, timecode


class VideoPlayer(QWidget):
    loaded = Signal(str, int)
    failed = Signal(str)
    finished = Signal()
    timelinePositionChanged = Signal(int)
    timelineDurationChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._sequence_pending = set()
        self.sequence_tracks = None
        self.sequence_ranges = None
        self._sequence_clip = None
        self.source = None
        self.name_for_path = lambda path: Path(path).name
        self.edit_name = ""
        self.ready = False
        self.subtitles = []
        self.show_subtitles = True
        self.video_offset = self.audio_offset = 0
        self._position = 0
        self._playing = False
        self._syncing = False
        self._anchor = 0
        self._elapsed = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.tick)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = panel()
        self.frame=frame
        outer.addWidget(frame)
        title_row=QHBoxLayout()
        self.status=label("미디어 없음","heading")
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.status.setWordWrap(False)
        title_row.addWidget(self.status,1)
        self.heading=label("영상 미리보기 · 선택 영상 시간","muted")
        self.heading.setWordWrap(False)
        title_row.addWidget(self.heading)
        layout.addLayout(title_row)
        self.stack = QStackedWidget()
        self.empty = label("▷\n\n영상 파일을 불러오세요\nMP4 · MOV", "preview")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video = CaptionVideoView()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video.setMinimumSize(320, 180)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.video)
        layout.addWidget(self.stack, 1)
        self.seek = SeekSlider()
        self.seek.setAccessibleName("타임라인 재생 위치")
        self.seek.setRange(0, 0)
        layout.addWidget(self.seek)
        controls = QHBoxLayout()
        self.clock = label("00:00:00 / 00:00:00", "muted")
        controls.addWidget(self.clock)
        controls.addStretch()
        self.start_button = QPushButton("|◁")
        self.start_button.setToolTip("타임라인 처음으로")
        self.play_button = QPushButton("▶")
        self.play_button.setAccessibleName("재생 또는 일시정지 · Space")
        self.stop_button = QPushButton("■")
        self.stop_button.setToolTip("정지 · 타임라인 처음으로")
        for button in (self.start_button, self.play_button, self.stop_button):
            controls.addWidget(button)
        controls.addStretch()
        controls.addWidget(label("음량", "muted"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(70)
        self.volume.setAccessibleName("재생 음량")
        controls.addWidget(self.volume)
        layout.addLayout(controls)
        self.player = QMediaPlayer(self)
        self.player.sourceChanged.connect(self.video.reset_frame_geometry)
        self.audio_player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.audio_player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video.video_item)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.positionChanged.connect(self.position_changed)
        self.player.mediaStatusChanged.connect(self.media_status)
        self.player.playbackStateChanged.connect(self.playback_state)
        self.player.errorOccurred.connect(self.on_error)
        self.audio_player.durationChanged.connect(self.duration_changed)
        self.audio_player.mediaStatusChanged.connect(self.audio_status)
        self.audio_player.errorOccurred.connect(self.audio_error)
        self.player.seekableChanged.connect(self.update_controls)
        self.player.hasVideoChanged.connect(self.update_controls)
        self.player.hasAudioChanged.connect(self.update_controls)
        self.start_button.clicked.connect(lambda: self.seek_timeline(0))
        self.play_button.clicked.connect(self.toggle_play)
        self.stop_button.clicked.connect(self.stop)
        self.seek.sliderMoved.connect(self.seek_timeline)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        self.update_controls()

    def timeline_position(self):
        return self._position

    def timeline_duration(self):
        if self.sequence_tracks is not None:
            return max((round((c['at']+c['end']-c['start'])*1000) for c in self.sequence_tracks),default=0)
        source_length = max(0, self.player.duration())
        audio_length = max(source_length, self.audio_player.duration()) if self.player.hasAudio() else 0
        caption_end = max((round(s["end"] * 1000) for s in self.subtitles), default=0)
        return max(self.video_offset + source_length, self.audio_offset + audio_length, caption_end)

    def open_video(self, path):
        source = validate_video(path)
        self.shutdown()
        self._sequence_pending = set()
        self.sequence_tracks = None
        self.sequence_ranges = None
        self._sequence_clip = None
        self.ready = False
        self.source = source
        self.video_offset = self.audio_offset = 0
        self._position = 0
        self.empty.setText("영상 불러오는 중…")
        self.stack.setCurrentWidget(self.empty)
        self.status.setText("파일을 확인하고 있습니다.")
        self.player.setVideoOutput(self.video.video_item)
        self.player.setAudioOutput(None)
        self.audio_player.setAudioOutput(self.audio)
        url = QUrl.fromLocalFile(str(source))
        self.player.setSource(url)
        self.audio_player.setSource(url)
        self.update_controls()

    def update_controls(self, *_):
        available = self.ready and self.player.hasVideo()
        self.play_button.setEnabled(available)
        self.stop_button.setEnabled(available)
        self.start_button.setEnabled(available and self.player.isSeekable())
        self.seek.setEnabled(available and self.player.isSeekable())
        self.volume.setEnabled(available and self.player.hasAudio())

    def media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            if not self.player.hasVideo():
                self.on_error(None, "영상 트랙이 없는 파일입니다.")
                return
            self._sequence_pending.discard('video')
            first_load = not self.ready
            self.ready = True
            self.stack.setCurrentWidget(self.video)
            self.status.setText(self.name_for_path(str(self.source)) if self.source else "재생 준비")
            self.update_controls()
            if self.sequence_tracks is not None:
                self.sync_players(force=True)
            self.render_position()
            if first_load and self.source:
                self.loaded.emit(str(self.source), self.player.duration())

    def audio_status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self._sequence_pending.discard('audio')
            if self._playing or self.sequence_tracks is not None:
                self.sync_players(force=True)

    def audio_error(self, error, message):
        self.status.setText("음성 재생 오류 · 영상은 계속 확인할 수 있습니다.")
        self.status.setToolTip(message)

    def duration_changed(self, *_):
        self.seek.setRange(0, min(self.timeline_duration(), 2147483647))
        self.timelineDurationChanged.emit(self.timeline_duration())
        self.render_position()

    def position_changed(self, position):
        # Supports direct source seeking while transport is paused as well.
        if not self._playing and not self._syncing and self.sequence_ranges is None:
            self._position = position + self.video_offset
        self.render_position()

    def refresh_title(self):
        if self.ready and self.audio_player.error()==QMediaPlayer.Error.NoError:
            source=self.player.source().toLocalFile() or str(self.source or "")
            self.status.setText((self.edit_name+" · " if self.edit_name else "")+self.name_for_path(source))
            self.status.setToolTip(source)

    def render_position(self):
        self.refresh_title()
        if not self.seek.isSliderDown():
            self.seek.setValue(self._position)
        self.clock.setText(f"{timecode(self._position)} / {timecode(self.timeline_duration())}")
        relative = self._position-self.video_offset if self.sequence_tracks is None else track_source_ms(self.sequence_tracks,'video',self._position)[0]
        self.video.video_item.setVisible(self.ready and relative is not None and 0 <= relative <= self.player.duration())
        self.video.show_caption(active_text(self.subtitles, self._position), self.show_subtitles)
        self.timelinePositionChanged.emit(self._position)

    def set_sequence_ranges(self, ranges):
        clips,at=[],0
        if ranges is not None:
            for i,(start,end) in enumerate(ranges):
                for track in ('video','audio'):
                    clips.append(dict(track=track,start=start,end=end,at=round(at,3),group=str(i)))
                at=round(at+end-start,3)
        self.set_sequence_clips(None if ranges is None else clips)

    def set_sequence_clips(self, clips):
        if clips == self.sequence_tracks:
            return
        if self._playing:
            self.toggle_play()
        self._sequence_pending = set()
        self.sequence_tracks = None if clips is None else [dict(c) for c in clips]
        self.sequence_ranges = None if clips is None else [(round(c['start']*1000),round(c['end']*1000)) for c in sorted(clips,key=lambda c:c['at']) if c['track']=='video']
        self._sequence_clip = {}
        self._sequence_pending.clear()
        self._position = 0
        if clips is None and self.source and Path(self.player.source().toLocalFile())!=Path(self.source):
            self.open_video(str(self.source))
            return
        self.duration_changed()
        if self.ready:
            self.seek_timeline(0)

    def set_placements(self, video_seconds, audio_seconds):
        self.video_offset = round(video_seconds * 1000)
        self.audio_offset = round(audio_seconds * 1000)
        self.duration_changed()
        if self.ready:
            self.sync_players(force=True)
        self.render_position()

    def seek_timeline(self, position):
        if not self.ready:
            return
        self._position = max(0, min(round(position), self.timeline_duration()))
        self._anchor = self._position
        if self._playing:
            self._elapsed.restart()
        self.sync_players(force=True)
        self.render_position()

    def sync_players(self, force=False):
        self._syncing = True
        try:
            for track,player,offset,enabled in (('video',self.player,self.video_offset,True),
                                                ('audio',self.audio_player,self.audio_offset,self.player.hasAudio())):
                track_force=force
                relative=self._position-offset
                if self.sequence_tracks is not None:
                    relative,index=track_source_ms(self.sequence_tracks,track,self._position)
                    track_force=track_force or self._sequence_clip.get(track)!=index
                    self._sequence_clip[track]=index
                    if index is not None:
                        source=self.sequence_tracks[index].get('source',str(self.source))
                        if Path(player.source().toLocalFile())!=Path(source):
                            self._sequence_pending.add(track)
                            player.setSource(QUrl.fromLocalFile(source))
                            track_force=True
                        if track=='audio':
                            enabled=player.hasAudio()
                duration=player.duration()
                inside=enabled and relative is not None and 0<=relative<duration
                relative=relative if relative is not None else 0
                target = max(0, min(relative, duration))
                if track_force or (inside and abs(player.position() - target) > 200):
                    player.setPosition(target)
                if self._playing and inside and track not in self._sequence_pending:
                    if player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                        player.play()
                elif player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                    player.pause()
        finally:
            self._syncing = False

    def tick(self):
        if self.sequence_tracks is not None and self._sequence_pending:
            self._anchor=self._position
            self._elapsed.restart()
            self.sync_players()
            self.render_position()
            return
        self._position = min(self.timeline_duration(), self._anchor + self._elapsed.elapsed())
        ended = self._position >= self.timeline_duration()
        if ended:
            self._playing = False
            self._timer.stop()
            self.status.setText("재생 완료 · ▶ 또는 Space로 다시 재생")
        self.sync_players()
        self.render_position()
        self.playback_state()
        if ended:
            self.finished.emit()

    def playback_state(self, *_):
        playing = self._playing or self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setText("Ⅱ" if playing else "▶")
        self.play_button.setToolTip("일시정지 · Space" if playing else "재생 · Space")

    def toggle_play(self):
        if not self.ready:
            return
        if self._playing or self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            if self._playing:
                self._position = min(self.timeline_duration(), self._anchor + self._elapsed.elapsed())
            self._playing = False
            self._timer.stop()
            self.player.pause()
            self.audio_player.pause()
        else:
            if self._position >= self.timeline_duration():
                self._position = 0
            self._anchor = self._position
            self._elapsed.start()
            self._playing = True
            self.sync_players(force=True)
            self._timer.start()
        self.render_position()
        self.playback_state()

    def stop(self):
        self._playing = False
        self._timer.stop()
        self._syncing = True
        self.player.stop()
        self.audio_player.stop()
        self._syncing = False
        self.seek_timeline(0)
        self.playback_state()

    def on_error(self, error, message):
        during_playback = self.ready
        self.ready = False
        self._playing = False
        self._timer.stop()
        self.player.stop()
        self.audio_player.stop()
        self.empty.setText("영상 재생 중 오류가 발생했습니다.\n목록에서 영상을 다시 선택해 주세요." if during_playback else
                           "영상을 열 수 없습니다.\n파일 위치와 형식을 확인해 주세요.")
        self.stack.setCurrentWidget(self.empty)
        if "memory" in message.lower() or "allocate" in message.lower():
            self.status.setText("영상 탐색 중 재생 메모리 오류 · 원본 손상 여부와는 별개입니다.")
        else:
            self.status.setText("영상 재생 오류 · 자세한 내용은 이 안내에 마우스를 올려 확인하세요.")
        self.status.setToolTip(message)
        self.update_controls()
        self.failed.emit(message)

    def shutdown(self):
        self._sequence_pending.clear()
        self._playing = False
        self._timer.stop()
        self._syncing = True
        for player in (self.player, self.audio_player):
            player.stop()
            player.setSource(QUrl())
        self.player.setVideoOutput(None)
        self.audio_player.setAudioOutput(None)
        self.video.videoSink().setVideoFrame(QVideoFrame())
        self._position = 0
        self._syncing = False
        self.video.show_caption("")

    def set_subtitles(self, segments):
        self.subtitles = segments
        self.duration_changed()
        self.video.show_caption(active_text(segments, self._position), self.show_subtitles)

    def set_subtitles_visible(self, visible):
        self.show_subtitles = visible
        self.video.show_caption(active_text(self.subtitles, self._position), visible)
