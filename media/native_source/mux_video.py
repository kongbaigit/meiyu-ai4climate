from pathlib import Path
import argparse,json,subprocess
from compose_audio import find_ffmpeg

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description='合并原生编码画面与旁白、原创配乐。')
parser.add_argument('--video',type=Path,default=ROOT/'native_raw.h264')
parser.add_argument('--output',type=Path,default=ROOT/'demo_native_master.mp4')
args=parser.parse_args()
timeline=json.loads((ROOT/'timeline.json').read_text(encoding='utf-8'))
command=[str(find_ffmpeg()),'-hide_banner','-y']
if args.video.suffix.lower()=='.h264':command+=['-fflags','+genpts','-r','30','-f','h264']
command+=['-i',str(args.video),'-i',str(ROOT/'mix.wav'),'-map','0:v:0','-map','1:a:0']
if args.video.suffix.lower()=='.h264':command+=['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r','30']
else:command+=['-c:v','copy']
command+=['-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','aac','-b:a','192k','-ar','48000','-t',str(timeline['duration']),'-movflags','+faststart',str(args.output)]
result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',errors='replace')
(ROOT/'master_encoding.log').write_text(result.stderr,encoding='utf-8')
if result.returncode:raise RuntimeError(result.stderr[-3000:])
print(json.dumps({'output':args.output.name,'bytes':args.output.stat().st_size,'duration':timeline['duration'],'audio_master':'loudnorm I=-16 TP=-1.5 LRA=11'}))
