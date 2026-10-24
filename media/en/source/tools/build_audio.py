"""Create the licensed English-film excerpt without changing speed or pitch."""
from pathlib import Path
import argparse
import json
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SHARED=ROOT.parents[1]/'latest/source'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ffmpeg',required=True)
    args=parser.parse_args()
    sync=json.loads((ROOT/'music_sync.json').read_text(encoding='utf-8'))
    original=SHARED/'audio/original_music.mp3'
    master=ROOT/'audio/music_master.flac'
    playback=ROOT/'audio/music_playback.mp3'
    if master.exists() or playback.exists():
        raise FileExistsError('Keep existing audio. Use a separate source copy for another edit.')
    base=[args.ffmpeg,'-hide_banner','-nostdin','-ss',str(sync['audio_start_seconds']),'-t',str(sync['duration_seconds']),'-i',str(original)]
    fades=f"afade=t=in:st=0:d=0.01,afade=t=out:st={sync['duration_seconds']-1.2}:d=1.2,"
    analysis=subprocess.run(base+['-af',fades+'loudnorm=I=-17:TP=-2:LRA=11:print_format=json','-f','null','NUL'],capture_output=True,check=True)
    text=analysis.stderr.decode('utf-8',errors='replace')
    measurement=json.loads(re.findall(r'\{[^{}]+\}',text)[-1])
    normalize='loudnorm=I=-17:TP=-2:LRA=11:linear=true:print_format=json'+''.join(f':{target}={measurement[source]}' for target,source in [
        ('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),('measured_thresh','input_thresh'),('offset','target_offset')])
    master.parent.mkdir(parents=True,exist_ok=True)
    mixed=subprocess.run(base+['-af',fades+normalize,'-ar','48000','-c:a','flac','-sample_fmt','s32','-metadata','title=Young Visionaries / English film excerpt',
                              '-metadata','artist=Eric Matyas','-metadata','copyright=Soundimage International Public License','-n',str(master)],capture_output=True,check=True)
    subprocess.run([args.ffmpeg,'-hide_banner','-nostdin','-i',str(master),'-c:a','libmp3lame','-b:a','256k','-ar','48000','-n',str(playback)],capture_output=True,check=True)
    result={'source':'../../latest/source/audio/original_music.mp3','start':sync['audio_start_seconds'],'end':sync['audio_end_seconds'],
            'duration':sync['duration_seconds'],'original_speed_and_pitch':True,'looped':False,'target_lufs':-17,'target_true_peak_db':-2,
            'measurement':measurement,'master':'audio/music_master.flac','playback':'audio/music_playback.mp3',
            'artist':sync['artist'],'title':sync['title'],'license':sync['license_name'],'license_url':sync['license_url']}
    (ROOT/'audio/audio-build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':
    main()
