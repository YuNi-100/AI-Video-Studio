"""Source-time recheck plans and explicit, reversible caption replacement."""
import math
from copy import deepcopy
from app.features.subtitles.model import validate_segments
from app.features.subtitles.editing import review_reasons


def validate_ranges(ranges, duration):
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 25000:
        raise ValueError('재검토할 구간이 없습니다.')
    clean = []
    previous = 0
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError('재검토 구간이 올바르지 않습니다.')
        a, b = pair
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in pair) or not previous <= a < b <= duration + .001:
            raise ValueError('재검토 시간은 원본 길이 안에서 겹치지 않게 지정하세요.')
        clean.append([round(a, 3), round(b, 3)])
        previous = b
    return clean


def plan_ranges(mode, duration, rows, offset=0, start=0, end=0, language='ko'):
    if not math.isfinite(duration) or not 0 < duration <= 604800:
        raise ValueError('영상 길이를 확인할 수 없습니다.')
    if mode == 'full':
        intervals = [[0, duration]]
    elif mode == 'range':
        intervals = validate_ranges([[start, end]], duration)
    elif mode == 'suspect':
        intervals = []
        for row, flags in zip(rows, review_reasons(rows, language)):
            if not flags or row.get('reviewed'):
                continue
            a, b = max(0, row['start']-offset), min(duration, row['end']-offset)
            if a < b:
                if intervals and a <= intervals[-1][1]:
                    intervals[-1][1] = max(b, intervals[-1][1])
                else:
                    intervals.append([a, b])
    else:
        raise ValueError('재검토 범위를 선택하세요.')
    chunks = []
    for a, b in intervals:
        while a < b:
            right = round(min(b, a+30), 3)
            if right <= a:
                break
            chunks.append([round(a, 3), right])
            a = right
    return validate_ranges(chunks, duration)


def overlaps(row, a, b):
    return row['start'] < b and row['end'] > a


def apply_candidates(original, replacements, offset=0, protect=True):
    """Only chosen intervals change; preserve all outside pieces and metadata."""
    result = deepcopy(original)
    previous = 0
    for a, b, candidate in sorted(replacements, key=lambda r:r[0]):
        if not 0 <= a < b <= 604800 or a < previous:
            raise ValueError('적용 구간이 겹치거나 올바르지 않습니다.')
        previous = b
        left, right = round(a+offset, 3), round(b+offset, 3)
        if protect and any(r.get('reviewed') and overlaps(r, left, right) for r in original):
            raise ValueError('검수 완료 자막이 포함된 구간입니다. 보호 설정을 확인하세요.')
        clean = validate_segments(candidate)
        if not clean:
            raise ValueError('새 후보가 비어 있습니다. 기존 자막은 유지합니다.')
        if any(r['start'] < a-.001 or r['end'] > b+.001 for r in clean):
            raise ValueError('새 후보 시간이 적용 구간을 벗어났습니다.')
        retained = []
        for row in result:
            if not overlaps(row, left, right):
                retained.append(row)
            else:
                if row['start'] < left:
                    retained.append(dict(row, end=left))
                if row['end'] > right:
                    retained.append(dict(row, start=right))
        retained.extend(dict(r, start=round(r['start']+offset, 3), end=round(r['end']+offset, 3), reviewed=True) for r in clean)
        result = sorted(retained, key=lambda r:r['start'])
    return validate_segments(result)
