"""把原创配乐的有音高事件保存为标准MIDI，便于编辑旋律与和声。"""
from pathlib import Path
import json,struct

ROOT=Path(__file__).resolve().parent
score=json.loads((ROOT/'score_manifest.json').read_text(encoding='utf-8'))
PPQ=480
beat=60/score['bpm']

def variable(value):
    out=[value&127];value>>=7
    while value:out.insert(0,(value&127)|128);value>>=7
    return bytes(out)

def track(events):
    body=bytearray();previous=0
    for tick,payload in sorted(events,key=lambda x:x[0]):
        body+=variable(tick-previous)+payload;previous=tick
    body+=b'\x00\xff\x2f\x00'
    return b'MTrk'+struct.pack('>I',len(body))+body

tempo=round(60_000_000/score['bpm'])
tracks=[track([(0,b'\xff\x51\x03'+tempo.to_bytes(3,'big')),(0,b'\xff\x58\x04\x04\x02\x18\x08')])]
count=0
for channel,(name,instruments,program) in enumerate([('Warm pads',{'pad'},89),('Glass theme',{'glass_motif','sparse_motif','chapter_chime'},9),('Bass pulse',{'bass'},38)]):
    events=[(0,b'\xff\x03'+variable(len(name))+name.encode()),(0,bytes([0xc0+channel,program]))]
    for event in score['events']:
        if event['instrument'] not in instruments or event['midi'] is None:continue
        start=round(event['at']/beat*PPQ);end=round(min(score['duration'],event['at']+event['duration'])/beat*PPQ)
        velocity=max(22,min(112,round(event['gain']/.065*96)))
        events.append((start,bytes([0x90+channel,int(event['midi']),velocity])))
        events.append((max(start+1,end),bytes([0x80+channel,int(event['midi']),0])));count+=1
    tracks.append(track(events))
raw=b'MThd'+struct.pack('>IHHH',6,1,len(tracks),PPQ)+b''.join(tracks)
(ROOT/'score.mid').write_bytes(raw)
assert raw[:4]==b'MThd' and struct.unpack('>HHH',raw[8:14])==(1,4,480)
print(json.dumps({'tracks':len(tracks),'pitched_events':count,'bytes':len(raw),'note':'MIDI保留旋律和和声时序；自制音色、噪声转场和混音以源程序及成片为准。'},ensure_ascii=False))
