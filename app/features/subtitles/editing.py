from copy import deepcopy
import math
import re
from app.features.subtitles.model import validate_segments


def edit_segment(segments, index, start, end, text, duration=None):
    if not 0 <= index < len(segments):
        raise ValueError("수정할 자막을 선택하세요.")
    if type(start) not in (int, float) or type(end) not in (int, float) or not math.isfinite(start) or not math.isfinite(end):
        raise ValueError("시간은 유효한 숫자여야 합니다.")
    if duration is not None and end > duration + .001:
        raise ValueError("종료 시간이 영상 길이를 넘습니다.")
    result = deepcopy(segments)
    result[index] = {**result[index], "start": round(start, 3), "end": round(end, 3), "text": text.strip(), "reviewed": True}
    entry = result[index]
    result.sort(key=lambda s: s["start"])
    new_index = next(i for i, item in enumerate(result) if item is entry)
    return validate_segments(result), new_index


def active_text(segments, position_ms):
    now = position_ms / 1000
    return "\n".join(s["text"] for s in segments if s["start"] <= now < s["end"])


def review_reasons(segments, language="ko"):
    flags = [[] for _ in segments]
    normalized = [re.sub(r"[\W_]+", "", s["text"]) for s in segments]
    for i, segment in enumerate(segments):
        text = segment["text"]
        if len(text) > 160:
            flags[i].append("긴 문장")
        if segment["end"] - segment["start"] > 12:
            flags[i].append("긴 표시 시간")
        if language == "ko" and re.search(r"[A-Za-z\u0400-\u04ff\u0600-\u06ff\u3040-\u30ff\u4e00-\u9fff]", text):
            flags[i].append("외국어 확인")
        if len(re.findall(r"[\u3130-\u318f]", text)) >= 3:
            flags[i].append("해독 어려운 문자")
        if re.search(r"([^\W_])\1{4,}", re.sub(r"\s+", "", text)):
            flags[i].append("같은 글자 반복")
        if re.search(r"(.{2,20}?)\1{3,}", re.sub(r"\s+", "", text)):
            flags[i].append("문장 내부 반복")
        if segment.get("avg_logprob", 0) < -1 or segment.get("no_speech_prob", 0) > .6:
            flags[i].append("인식 신뢰 확인")
        if i and segment["start"] < segments[i-1]["end"]:
            flags[i].append("시간 겹침")
    start = 0
    while start < len(normalized):
        end = start + 1
        while end < len(normalized) and normalized[end] == normalized[start]:
            end += 1
        if end - start >= 3 and len(normalized[start]) >= 2:
            for i in range(start, end):
                flags[i].append("연속 반복")
        start = end
    return flags
