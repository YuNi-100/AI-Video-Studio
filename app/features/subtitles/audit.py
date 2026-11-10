"""Read-only final checks. Findings are suggestions, never replacement text."""
import re
from app.features.subtitles.model import validate_segments,validate_hotwords


def merge_ranges(ranges,gap=0):
    merged=[]
    for a,b in sorted(ranges):
        if b<=a:continue
        if merged and a<=merged[-1][1]+gap:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged


def subtract_ranges(start,end,covered):
    cursor=start;result=[]
    for a,b in covered:
        if b<=cursor:continue
        if a>=end:break
        if a>cursor:result.append((cursor,min(a,end)))
        cursor=max(cursor,b)
    if cursor<end:result.append((cursor,end))
    return result


def one_edit(a,b):
    if a==b or abs(len(a)-len(b))>1:return False
    if len(a)==len(b):return sum(x!=y for x,y in zip(a,b))==1
    short,long=(a,b) if len(a)<len(b) else (b,a)
    return any(long[:i]+long[i+1:]==short for i in range(len(long)))


def audit_captions(rows,duration,terms='',speech=None,start=0,end=None,language='ko'):
    clean=validate_segments(rows);terms=validate_hotwords(terms)
    end=duration if end is None else min(end,duration)
    if not 0<=start<end:raise ValueError('점검할 시간 범위를 확인하세요.')
    findings=[];speech=None if speech is None else merge_ranges(speech,.1)
    names=[n.strip() for n in terms.split(',') if len(n.strip())>=2]
    present={n for n in names if any(n in r['text'] for r in clean)}
    normalized=lambda t:re.sub(r'[\W_]+','',t).casefold()
    previous_end=0
    for i,row in enumerate(clean):
        a,b=row['start'],row['end']
        overlap=previous_end>a+.01;previous_end=max(previous_end,b)
        if (b<=start or a>=end) and not (end==duration and b>duration and a>=start):continue
        reasons=[];span=b-a;text=row['text'];characters=len(re.sub(r'\s+','',text))
        if span<.4:reasons.append('표시 시간이 짧음')
        if characters/span>(20 if language=='en' else 14):reasons.append('읽는 속도 확인')
        if len(text.splitlines())>2 or any(len(line)>42 for line in text.splitlines()):reasons.append('한 화면의 글자 수 확인')
        if span>12:reasons.append('표시 시간이 김')
        if b>duration+.01:reasons.append('작업본 길이를 넘는 자막')
        if overlap:reasons.append('다른 자막과 시간 겹침')
        if i and a-clean[i-1]['end']<.5 and normalized(text)==normalized(clean[i-1]['text']):reasons.append('인접한 같은 문장 확인')
        variants=[]
        for word in re.findall(r'[가-힣A-Za-z]{2,12}',text):
            if any(word.startswith(n) for n in names):continue
            for name in present:
                if word[0]==name[0] and one_edit(name,word):variants.append(f'{word} ↔ {name}')
        if variants:reasons.append('등록 이름·용어 표기 확인: '+', '.join(sorted(set(variants))))
        if speech is not None:
            voiced=[(max(a,x),min(b,y)) for x,y in speech if x<b and y>a]
            if not voiced and span>=.6:reasons.append('말소리 추정 구간과 자막 위치 확인')
            elif voiced:
                if voiced[0][0]-a>.5:reasons.append('말소리보다 일찍 표시되는지 확인')
                if b-voiced[-1][1]>.7:reasons.append('말소리 뒤에 오래 남는지 확인')
        if reasons:findings.append(dict(start=a,end=b,index=i,text=text,reviewed=row.get('reviewed',False),reasons=reasons))
    if speech is not None:
        coverage=merge_ranges([(max(0,r['start']-.15),r['end']+.15) for r in clean])
        for a,b in speech:
            for left,right in subtract_ranges(max(a,start),min(b,end),coverage):
                if right-left>=.6:findings.append(dict(start=round(left,3),end=round(right,3),index=None,text='',reviewed=False,reasons=['말소리 추정 구간에 자막 없음']))
    return sorted(findings,key=lambda r:(r['start'],r['index'] is None))
