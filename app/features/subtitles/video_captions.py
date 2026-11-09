"""Burn-in layout in displayed video pixels, matching the preview proportions."""
from app.features.subtitles.model import validate_segments


def ass_time(seconds):
    value=round(seconds*100)
    return f'{value//360000}:{value//6000%60:02}:{value//100%60:02}.{value%100:02}'


def write_video_captions(rows,path,width,height):
    rows=validate_segments(rows)
    font=max(8,round(height*.055));padding=max(1,round(height*.012))
    margin_x=round(width*.06)+padding;margin_y=round(height*.07)+padding
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,{font},&H00FFFFFF,&H00FFFFFF,&H46000000,&H46000000,-1,0,0,0,100,100,0,0,3,{padding},0,2,{margin_x},{margin_x},{margin_y},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    events=[]
    for row in rows:
        text=row['text'].replace('\\',r'\\').replace('{',r'\{').replace('}',r'\}').replace('\n',r'\N')
        events.append(f"Dialogue: 0,{ass_time(row['start'])},{ass_time(row['end'])},Default,,0,0,0,,{text}")
    path.write_text(header+'\n'.join(events)+'\n',encoding='utf-8-sig')
