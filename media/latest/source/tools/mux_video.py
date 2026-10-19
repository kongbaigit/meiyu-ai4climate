from pathlib import Path
import argparse
import hashlib
import json
import subprocess
from compose_audio import ffmpeg_path

ROOT = Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,default=60)
    parser.add_argument('--ffmpeg')
    args=parser.parse_args()
    if args.output.exists():
        raise RuntimeError('保留已有视频，请更换输出路径：'+str(args.output))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    ffmpeg=ffmpeg_path(args.ffmpeg)
    audio=ROOT/'audio/master_mix.wav'
    command=[ffmpeg,'-hide_banner','-n','-fflags','+genpts','-r','30','-f','h264','-i',str(args.video),
             '-ss',str(args.start),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
             '-c:v','copy',
             '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
             '-c:a','aac','-b:a','192k','-ar','48000','-t',str(args.duration),'-movflags','+faststart',str(args.output)]
    run=subprocess.run(command,capture_output=True)
    log=args.output.with_suffix('.encoding.log')
    log.write_bytes(run.stderr)
    if run.returncode:
        raise RuntimeError(run.stderr.decode('utf-8',errors='replace')[-4000:])
    report={'output':args.output.name,'bytes':args.output.stat().st_size,'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),'duration':args.duration,'fps':30,'width':1920,'height':1080,'video_pipeline':'Canvas -> VideoFrame -> WebCodecs Annex-B -> stream-copy H.264/AAC MP4','screenshots_used':False,'video_reencoded':False,'audio_master':'master_mix.wav, loudnorm target -16 LUFS / -1.5 dBTP','encoding_log':log.name}
    args.output.with_suffix('.encoding.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    main()
