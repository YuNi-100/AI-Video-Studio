"""Search rendered edit time, never confuse it with source media time."""
import math
import unicodedata
import hashlib
from app.features.silence.sequence import sequence_layout


def validate_tags(rows):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('장면 태그 목록이 올바르지 않습니다.')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('장면 태그가 올바르지 않습니다.')
        name = row.get('name')
        a, b = row.get('start'), row.get('end')
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise ValueError('태그 이름은 1~80자로 입력하세요.')
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (a, b)) or not 0 <= a < b <= 604800:
            raise ValueError('태그 시작·종료 시간을 확인하세요.')
        result.append(dict(name=name.strip(), start=float(a), end=float(b)))
    return result


def search_edits(project, query='', kind='all', sequence_id=None):
    normalize = lambda s: unicodedata.normalize('NFKC', s).casefold()
    needle = normalize(query.strip())
    offsets = {p: v['video'] for p, v in project.media_placements.items()}
    results = []
    for seq in project.edit_sequences:
        if sequence_id is not None and seq['id']!=sequence_id:continue
        if kind != 'tags' and (not seq.get('parent_id') or sequence_id is not None):
            for index, cue in enumerate(sequence_layout(seq, project.subtitles, offsets)[1]):
                if needle in normalize(cue['text']):
                    results.append(dict(sequence=seq['id'], name=seq['name'], kind='대사', start=cue['start'], end=cue['end'], text=cue['text'],caption_index=index,cue_id=cue.get('id'),key_sequence=seq.get('parent_id',seq['id'])))
        if kind != 'captions':
            for index, tag in enumerate(seq.get('scene_tags', [])):
                if needle in normalize(tag['name']):
                    results.append(dict(sequence=seq['id'], name=seq['name'], kind='태그', start=tag['start'], end=tag['end'], text=tag['name'], tag_index=index))
    for row in results:
        identity=row.get('cue_id') or repr((row['kind'],row['start'],row['end'],row['text']))
        row['key']=row.get('key_sequence',row['sequence'])+':'+hashlib.sha256(identity.encode('utf-8')).hexdigest()
        row['folder']=project.search_locations.get(row['key'])
    return sorted(results, key=lambda r: (r['name'], r['start'], r['kind']))


def timestamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'
