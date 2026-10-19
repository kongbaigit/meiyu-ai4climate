"""为原生动画创作并合成配乐，保留音符、旁白和混音的可复现记录。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import os
import shutil
from math import gcd
from pathlib import Path
import subprocess
import wave

import numpy as np
from scipy.signal import resample_poly

ROOT=Path(__file__).resolve().parent
SR=48000
BPM=92
BEAT=60/BPM
SEED=20261014
def find_ffmpeg():
    configured=os.environ.get('MEIYU_FFMPEG') or shutil.which('ffmpeg')
    if configured:return Path(configured)
    for parent in ROOT.parents:
        candidates=list((parent/'work/meiyu/.venv/Lib/site-packages/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
        if candidates:return candidates[0]
    raise RuntimeError('需要FFmpeg。请安装后加入PATH，或设置MEIYU_FFMPEG为可执行文件路径。')

FFMPEG=find_ffmpeg()


def read_wave(path):
    with wave.open(str(path),'rb') as source:
        channels,width,rate,frames=source.getnchannels(),source.getsampwidth(),source.getframerate(),source.getnframes()
        assert width==2
        raw=np.frombuffer(source.readframes(frames),dtype='<i2').astype(np.float32)/32768
    raw=raw.reshape(-1,channels).mean(axis=1)
    divisor=gcd(rate,SR)
    return resample_poly(raw,SR//divisor,rate//divisor).astype(np.float32)


def save_wave(path,raw):
    raw=np.asarray(raw)
    if raw.ndim==1:raw=np.repeat(raw[:,None],2,axis=1)
    assert np.isfinite(raw).all() and np.max(np.abs(raw))<1, path
    with wave.open(str(path),'wb') as target:
        target.setnchannels(2);target.setsampwidth(2);target.setframerate(SR)
        target.writeframes(np.round(raw*32767).astype('<i2').tobytes())


def main():
    spec=json.loads((ROOT/'narration.json').read_text(encoding='utf-8'))
    timeline=[];cursor=0
    for entry in spec['scenes']:
        audio=read_wave(ROOT/(entry['id']+'.wav'))
        duration=max(12.0,len(audio)/SR+2.0)
        duration=np.ceil(duration*2)/2
        timeline.append({**entry,'start':round(cursor,4),'speech_start':round(cursor+.8,4),
                         'speech_duration':round(len(audio)/SR,4),'duration':float(duration),'end':round(cursor+duration,4)})
        cursor+=duration
    timeline[-1]['duration']+=2;timeline[-1]['end']+=2;cursor+=2
    assert cursor<179, f'旁白与画面总长{cursor}秒，需要收缩内容'
    count=round(cursor*SR)
    music=np.zeros((count,2),dtype=np.float32)
    voice=np.zeros(count,dtype=np.float32)
    rng=np.random.default_rng(SEED)
    events=[]

    def add(signal,start,amplitude,pan=0,kind='',midi=None):
        begin=round(start*SR)
        if begin<0:signal=signal[-begin:];begin=0
        end=min(count,begin+len(signal))
        if begin>=end:return
        signal=np.asarray(signal[:end-begin],dtype=np.float32)*amplitude
        music[begin:end,0]+=signal*np.sqrt((1-pan)/2)
        music[begin:end,1]+=signal*np.sqrt((1+pan)/2)
        if kind:events.append({'at':round(start,4),'instrument':kind,'midi':midi,'duration':round(len(signal)/SR,4),'gain':amplitude,'pan':round(pan,3)})

    def tone(midi,duration,kind='bell'):
        t=np.arange(round(duration*SR),dtype=np.float32)/SR
        f=440*2**((midi-69)/12)
        if kind=='pad':
            signal=(np.sin(2*np.pi*f*t)+.28*np.sin(2*np.pi*f*2*t+.08*np.sin(2*np.pi*.15*t))+.13*np.sin(2*np.pi*f*3*t))/1.41
            env=np.minimum(t/.8,1)*np.minimum((duration-t)/1.5,1)
        elif kind=='bass':
            signal=np.sin(2*np.pi*f*t)+.12*np.sin(2*np.pi*f*2*t)
            env=(1-np.exp(-t*25))*np.exp(-t*2.7)
        else:
            signal=sum(weight*np.sin(2*np.pi*f*ratio*t)*np.exp(-t*decay) for ratio,weight,decay in [(1,1,2.7),(2,.3,4),(3.01,.12,6),(4,.05,9)])
            env=(1-np.exp(-t*250))*np.minimum((duration-t)/.12,1)
        return (signal*env).astype(np.float32)

    chords=[[50,57,60,64],[53,57,60,67],[48,55,60,62],[43,50,57,62]]
    for bar in range(int(cursor/(4*BEAT))+1):
        start=bar*4*BEAT
        chord=chords[(bar//2)%4]
        section=next((i for i,s in enumerate(timeline) if s['start']<=start<s['end']),9)
        calm=section in {0,8,9}
        for j,note in enumerate(chord):add(tone(note+12,4*BEAT+1.5,'pad'),start,.009 if calm else .007,(j-1.5)*.35,'pad',note+12)
        if section in {1,2,3,5,6,7}:
            add(tone(chord[0]-12,.65,'bass'),start,.045,0,'bass',chord[0]-12)
            for beat in [1,2,3]:
                noise=rng.standard_normal(round(.055*SR)).astype(np.float32)
                high=noise-np.convolve(noise,np.ones(11)/11,mode='same')
                envelope=np.exp(-np.arange(len(high))/SR*95)
                add(high*envelope,start+beat*BEAT,.005,(-1)**beat*.3,'brushed_pulse')
        melody=[69,76,72,74,67,69,72,76]
        if not calm and bar%2==0:
            for step,beat in enumerate([0,.75,1.5,2.5]):
                note=melody[(bar//2*4+step)%8]
                add(tone(note,1.8),start+beat*BEAT,.032 if section in {2,6} else .023,(step-1.5)*.32,'glass_motif',note)
        elif calm and bar%3==0:
            note=[74,72,69][(bar//3)%3]
            add(tone(note,2.5),start+BEAT,.022,.1,'sparse_motif',note)
    for index,scene in enumerate(timeline):
        start=scene['start']
        add(tone([74,76,77,81,74,76,79,72,69,77][index],3.2),start+.12,.065,-.1,'chapter_chime',[74,76,77,81,74,76,79,72,69,77][index])
        length=round(1.3*SR);t=np.arange(length,dtype=np.float32)/SR
        sweep=np.sin(2*np.pi*(110*t+270*t*t))*(np.sin(np.pi*t/1.3)**2)
        add(sweep,start-.5,.008,.3,'soft_transition')
        raw=read_wave(ROOT/(scene['id']+'.wav'))
        raw*=.72/max(float(np.max(np.abs(raw))),.001)
        begin=round(scene['speech_start']*SR)
        voice[begin:begin+len(raw)]+=raw
    fade_in=np.minimum(np.arange(count)/SR/2.2,1)
    fade_out=np.minimum((count-1-np.arange(count))/SR/3.0,1)
    music*=np.maximum(0,fade_in*fade_out)[:,None]
    music*=1.8
    master_peak=float(np.max(np.abs(music)))
    if master_peak>.65:music*=.65/master_peak
    duck=np.ones(count,dtype=np.float32)
    for scene in timeline:
        a=max(0,round((scene['speech_start']-.15)*SR));b=min(count,round((scene['speech_start']+scene['speech_duration']+.25)*SR))
        duck[a:b]=.42
        ramp=min(round(.18*SR),(b-a)//2)
        duck[a:a+ramp]=np.linspace(1,.42,ramp)
        duck[b-ramp:b]=np.linspace(.42,1,ramp)
    playback=music*duck[:,None]
    voice_stereo=np.repeat(voice[:,None],2,axis=1)*.92
    mixed=voice_stereo+playback
    peak=float(np.max(np.abs(mixed)))
    assert peak<.98
    save_wave(ROOT/'score.wav',music)
    save_wave(ROOT/'music_playback.wav',playback)
    save_wave(ROOT/'narration.wav',voice_stereo)
    save_wave(ROOT/'mix.wav',mixed)
    for name,bitrate in [('score',128),('music_playback',128),('narration',80),('mix',160)]:
        command=[str(FFMPEG),'-hide_banner','-loglevel','error','-y','-i',str(ROOT/(name+'.wav'))]
        if name=='score':command+=['-af','loudnorm=I=-18:TP=-2:LRA=9']
        result=subprocess.run(command+['-c:a','libmp3lame','-b:a',str(bitrate)+'k',str(ROOT/(name+'.mp3'))],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
    timeline_data={'duration':cursor,'fps':30,'voice':spec['voice'],'speech_offset_seconds':.8,'scenes':timeline}
    (ROOT/'timeline.json').write_text(json.dumps(timeline_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    score_data={'title':'雨前的刻度','kind':'原创程序合成配乐','bpm':BPM,'meter':'4/4','key':'D minor / F major','seed':SEED,'sample_rate':SR,
                'instruments':['加法合成玻璃音色','缓慢和弦铺底','正弦低音','合成短噪声节拍','章节提示音'],
                'motif_midi':[69,76,72,74,67,69,72,76],'chord_midi':chords,'events':events,
                'third_party_music_assets':False,'music_balance_gain':1.8,'music_ducking_during_speech':.42,'mix_peak_linear':peak,
                'duration':cursor,'created_at_utc':datetime.now(timezone.utc).isoformat()}
    (ROOT/'score_manifest.json').write_text(json.dumps(score_data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    captions=[]
    def timestamp(t):
        ms=round(t*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    for scene in timeline:
        clauses=re.findall(r'[^。！？]+[。！？]?',scene['text'])
        total=sum(len(x) for x in clauses);offset=scene['speech_start']
        for clause in clauses:
            duration=scene['speech_duration']*len(clause)/total
            captions.append(f'{len(captions)+1}\n{timestamp(offset)} --> {timestamp(offset+duration)}\n{clause}\n')
            offset+=duration
    (ROOT/'captions.srt').write_text('\n'.join(captions),encoding='utf-8')
    summary={'duration':cursor,'scene_count':len(timeline),'score_events':len(events),'mix_peak_linear':peak,
             'voice':spec['voice'],'original_score_title':score_data['title'],'music_asset_sha256':hashlib.sha256((ROOT/'score.wav').read_bytes()).hexdigest()}
    (ROOT/'audio_check.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
