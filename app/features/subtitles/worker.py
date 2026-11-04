"""Isolated CPU recognition worker. Stdout is UTF-8 JSONL only."""
import argparse
import json
import os
from pathlib import Path
from app.core.media import validate_video
from app.features.subtitles.model import validate_segments, validate_hotwords


def transcribe(source, model_size, language, cache, emit, model_factory=None, hotwords="", skip_silence=False):
    path = validate_video(source)
    hotwords = validate_hotwords(hotwords)
    if type(skip_silence) is not bool:
        raise ValueError("음성 필터 설정이 올바르지 않습니다.")
    if model_size not in ("tiny", "base", "small", "large-v3-turbo") or language not in ("auto", "ko", "en", "ja"):
        raise ValueError("지원되지 않는 모델 또는 언어입니다.")
    if model_factory is None:
        from faster_whisper import WhisperModel
        model_factory = WhisperModel
    emit({"type": "status", "text": "모델 준비 중 · 처음에는 다운로드가 필요합니다."})
    model = model_factory(model_size, device="cpu", compute_type="int8", download_root=str(cache),
                          cpu_threads=max(1, min(8, (os.cpu_count() or 2) - 1)))
    emit({"type": "status", "text": "음성 분석 중 · CPU 처리"})
    segments, info = model.transcribe(str(path), language=None if language == "auto" else language,
                                      beam_size=5, vad_filter=skip_silence, condition_on_previous_text=False,
                                      hotwords=hotwords or None, word_timestamps=True)
    result = []
    duration = float(info.duration)
    for segment in segments:
        words = [w for w in (getattr(segment,"words",None) or []) if getattr(w,"word","").strip()]
        text = segment.text.strip()
        start, end = max(0.0, float(segment.start)), min(duration, float(segment.end))
        if words:
            start = max(0.0,float(words[0].start))
            end = min(duration,float(words[-1].end))
        if text and end > start:
            row = {"start": start, "end": end, "text": text}
            for key in ("avg_logprob", "no_speech_prob"):
                if hasattr(segment, key):
                    row[key] = float(getattr(segment, key))
            result.append(row)
            if len(result) > 50000:
                raise ValueError("자막 수가 프로젝트 제한(50,000개)을 초과했습니다.")
            emit({"type": "progress", "count": len(result), "seconds": end})
    result = validate_segments(result)
    from datetime import datetime, timezone
    emit({"type": "done", "segments": result, "language": info.language,
          "run": {"model": model_size, "language": info.language, "hotwords": hotwords,
                  "skip_silence": skip_silence, "timing": "word-boundaries", "created_at": datetime.now(timezone.utc).isoformat()}})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--hotwords", default="")
    parser.add_argument("--vad", choices=("off", "on"), default="off")
    args = parser.parse_args()
    def emit(value):
        print(json.dumps(value, ensure_ascii=False), flush=True)
    try:
        transcribe(args.source, args.model, args.language, Path(args.cache), emit, hotwords=args.hotwords, skip_silence=args.vad == "on")
        return 0
    except Exception as exc:
        emit({"type": "error", "text": f"{type(exc).__name__}: {exc}"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
