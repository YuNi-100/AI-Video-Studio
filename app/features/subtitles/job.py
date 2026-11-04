import importlib.util
import json
import sys
from pathlib import Path
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal
from app.features.subtitles.model import validate_segments


def recognition_installed():
    return all(importlib.util.find_spec(name) is not None for name in ("faster_whisper", "ctranslate2", "av"))


class SubtitleJob(QObject):
    status = Signal(str)
    completed = Signal(str, list)
    failed = Signal(str)
    ended = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.cancelled = False
        self.result = None
        self.run_info = {}
        self.buffer = b""
        self.detail = ""
        self.error_message = ""
        self.source = ""

    @property
    def busy(self):
        return self.process is not None

    def start(self, source, model, language, cache, hotwords="", skip_silence=False, *, worker_module="app.features.subtitles.worker", extra_args=()):
        if self.busy:
            return False
        self.source = str(Path(source).resolve())
        self.stamp = self.source_stamp()
        self.buffer, self.detail, self.result, self.cancelled = b"", "", None, False
        self.error_message = ""
        self.run_info = {}
        process = QProcess(self)
        self.process = process
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        env.insert("HF_HOME", str(Path(cache).parent / "hub"))
        env.insert("HF_XET_CACHE", str(Path(cache).parent / "xet"))
        env.insert("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        process.setProcessEnvironment(env)
        process.setWorkingDirectory(str(Path(__file__).resolve().parents[3]))
        process.setProgram(sys.executable)
        process.setArguments(["-u", "-m", worker_module, "--source", self.source,
                              "--model", model, "--language", language, "--cache", str(cache),
                              "--hotwords", hotwords, "--vad", "on" if skip_silence else "off"] + list(extra_args))
        process.readyReadStandardOutput.connect(self.read_stdout)
        process.readyReadStandardError.connect(self.read_stderr)
        process.finished.connect(self.finish)
        process.errorOccurred.connect(self.process_error)
        process.start()
        return True

    def source_stamp(self):
        stat = Path(self.source).stat()
        return stat.st_size, stat.st_mtime_ns

    def read_stdout(self):
        if self.process is None:
            return
        self.buffer += bytes(self.process.readAllStandardOutput())
        while b"\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\n", 1)
            try:
                self.handle_message(json.loads(raw.decode("utf-8")))
            except (ValueError, TypeError, KeyError) as exc:
                self.detail = f"잘못된 음성 인식 결과: {exc}"
        if len(self.buffer) > 16 * 1024 * 1024:
            self.detail = "자막 결과 크기가 제한을 초과했습니다."
            self.cancel()

    def handle_message(self, message):
        kind = message["type"]
        if kind == "status":
            self.status.emit(message["text"])
        elif kind == "progress":
            self.status.emit(f"실제 인식 결과 {message['count']}개 · {message['seconds']:.1f}초 구간까지 처리")
        elif kind == "done":
            self.result = validate_segments(message["segments"])
            self.run_info = message.get("run", {})
        elif kind == "error":
            self.error_message = message["text"]

    def read_stderr(self):
        if self.process:
            text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
            self.detail = (self.detail + text)[-8000:]

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.failed.emit("음성 인식 작업을 시작하지 못했습니다. Python 실행 환경을 확인하세요.")
            self.cleanup()

    def finish(self, code, exit_status):
        if self.process is None:
            return
        self.read_stdout()
        self.read_stderr()
        try:
            unchanged = self.source_stamp() == self.stamp
        except OSError:
            unchanged = False
        if self.cancelled:
            self.status.emit("취소했습니다. 기존 자막은 유지됩니다.")
        elif not unchanged:
            self.failed.emit("처리 중 원본 파일이 변경되거나 이동했습니다. 다시 연결 후 생성하세요.")
        elif code == 0 and self.result is not None:
            self.completed.emit(self.source, self.result)
        else:
            self.failed.emit("자막 생성 실패 · 인터넷 연결, 모델 다운로드, 음성 트랙을 확인하세요.\n" + (self.error_message or self.detail)[-1500:])
        self.cleanup()

    def cleanup(self):
        process, self.process = self.process, None
        if process:
            process.deleteLater()
        self.ended.emit()

    def cancel(self):
        if self.process:
            self.cancelled = True
            self.process.kill()

    def shutdown(self):
        if self.process:
            self.cancel()
            self.process.waitForFinished(3000)
