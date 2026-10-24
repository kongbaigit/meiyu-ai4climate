from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parent.parent

def main():
    sync=json.loads((ROOT/'music_sync.json').read_text(encoding='utf-8'))
    parser=argparse.ArgumentParser()
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,default=sync['duration_seconds'])
    parser.add_argument('--ffmpeg',required=True)
    parser.add_argument('--delivery-crf',type=int,default=None,help='Optional high-quality H.264 optimization for web delivery')
    parser.add_argument('--music-title',default=sync['title'])
    parser.add_argument('--artist',default=sync['artist'])
    parser.add_argument('--source-url',default=sync['source_url'])
    parser.add_argument('--license-name',default=sync['license_name'])
    parser.add_argument('--license-url',default=sync['license_url'])
    args=parser.parse_args()
    if args.delivery_crf is not None and not 0 <= args.delivery_crf <= 30:
        raise ValueError('delivery-crf must be between 0 and 30')
    if args.output.exists():
        raise RuntimeError('Output exists. Use a new path: '+str(args.output))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    ffmpeg=args.ffmpeg
    audio=args.audio
    if not audio.is_file():
        raise RuntimeError('Audio master not found: '+str(audio))
    video_codec=['-c:v','copy'] if args.delivery_crf is None else ['-c:v','libx264','-preset','slow','-crf',str(args.delivery_crf),'-pix_fmt','yuv420p']
    command=[ffmpeg,'-hide_banner','-n','-fflags','+genpts','-r','30','-f','h264','-i',str(args.video),
             '-ss',str(args.start),'-i',str(audio),'-map','0:v:0','-map','1:a:0',
             *video_codec,
             '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-color_range','tv',
             '-c:a','aac','-b:a','256k','-ar','48000','-t',str(args.duration),'-movflags','+faststart',
             '-metadata','title=Meiyu Prepare / English / '+args.music_title,
             '-metadata','copyright=Music: '+args.music_title+' — '+args.artist+' / '+args.license_name,
             '-metadata','comment='+args.music_title+' — '+args.artist+'; '+sync['attribution']+'; '+args.source_url+'; '+args.license_url+'; Continuous excerpt, fades and loudness matching. Original speed and pitch.',str(args.output)]
    run=subprocess.run(command,capture_output=True)
    log=args.output.with_suffix('.encoding.log')
    log.write_bytes(run.stderr)
    if run.returncode:
        raise RuntimeError(run.stderr.decode('utf-8',errors='replace')[-4000:])
    report={'output':args.output.name,'bytes':args.output.stat().st_size,'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest(),'duration':args.duration,'fps':30,'width':1920,'height':1080,'video_pipeline':'Canvas -> VideoFrame -> WebCodecs Annex-B -> '+('H.264 web optimization -> ' if args.delivery_crf is not None else '')+'H.264/AAC MP4','screenshots_used':False,'video_reencoded':args.delivery_crf is not None,'delivery_crf':args.delivery_crf,'audio_mode':'instrumental_only','speech_tracks':0,'audio_master':str(audio),'music_title':args.music_title,'artist':args.artist,'source_url':args.source_url,'license_name':args.license_name,'license_url':args.license_url,'encoding_log':log.name}
    args.output.with_suffix('.encoding.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    main()
