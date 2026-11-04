"""Local silence detection and source-time cut planning."""
import math
import re


def candidates_from_log(log, duration, padding=.15):
    """Keep a small sound-side margin; never select candidates automatically."""
    rows, start = [], None
    for kind, value in re.findall(r'silence_(start|end):\s*([0-9.eE+\-]+)', log):
        number = float(value)
        if not math.isfinite(number):
            continue
        if kind == 'start':
            start = max(0., number)
        elif start is not None:
            end = min(duration, number)
            if end - start > 2 * padding:
                rows.append((round(start + padding, 3), round(end - padding, 3)))
            start = None
    if start is not None and duration - start > 2 * padding:
        rows.append((round(start + padding, 3), round(duration - padding, 3)))
    return rows


def retained_ranges(duration, cuts):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('영상 길이를 확인할 수 없습니다.')
    merged = []
    for start, end in sorted(cuts):
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= duration:
            raise ValueError('제외 구간의 시간이 올바르지 않습니다.')
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    kept, cursor = [], 0.
    for start, end in merged:
        if start > cursor:
            kept.append((cursor, start))
        cursor = end
    if cursor < duration:
        kept.append((cursor, duration))
    if not kept:
        raise ValueError('영상 전체를 제외할 수 없습니다.')
    return kept

