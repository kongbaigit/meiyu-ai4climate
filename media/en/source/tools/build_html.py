"""Build the English native preview from shared, versioned project assets."""
from pathlib import Path
import base64
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SHARED=ROOT.parents[1]/'latest/source'

def main():
    storyboard=json.loads((ROOT/'storyboard.json').read_text(encoding='utf-8'))
    evidence=json.loads((SHARED/'kinetic_evidence.json').read_text(encoding='utf-8'))
    evidence['weather']['window_label']='20 Oct 08:00 to 21 Oct 08:00'
    evidence['weather']['capture_label']='Captured 2026-10-19 19:22 UTC+08:00'
    payload={'timeline':storyboard,'evidence':evidence,'text_cues':storyboard['text_cues'],
             'legacy_evidence':json.loads((SHARED/'legacy_evidence.json').read_text(encoding='utf-8')),
             'legacy_timeline':json.loads((SHARED/'legacy_timeline.json').read_text(encoding='utf-8'))}
    (ROOT/'film_input.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    html=(ROOT/'player.html').read_text(encoding='utf-8')
    replacements={
        '/*__GSAP__*/':(SHARED/'vendor/gsap.min.js').read_text(encoding='utf-8'),
        '/*__THREE__*/':(SHARED/'vendor/three.min.js').read_text(encoding='utf-8'),
        '/*__LEGACY__*/':(SHARED/'legacy3d.js').read_text(encoding='utf-8'),
        '/*__COST__*/':(SHARED/'vendor/decision_cost.js').read_text(encoding='utf-8'),
        '/*__INPUT__*/':json.dumps(payload,ensure_ascii=False).replace('</','<\\/'),
        '/*__APP__*/':(ROOT/'film.js').read_text(encoding='utf-8').replace('/*__DRAWING_HELPERS__*/',(ROOT/'drawing_helpers.js').read_text(encoding='utf-8')),
        '__MUSIC__':'data:audio/mpeg;base64,'+base64.b64encode((ROOT/'audio/music_playback.mp3').read_bytes()).decode(),
    }
    for marker,value in replacements.items():
        if html.count(marker)!=1:
            raise ValueError(f'Expected one {marker}')
        html=html.replace(marker,value)
    target=ROOT.parent/'preview.html'
    target.write_text(html,encoding='utf-8',newline='\n')
    report={'path':target.name,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'duration':storyboard['duration'],'self_contained':True,'external_media_dependencies':[],
            'shared_assets':'../../latest/source/','language':'en'}
    (ROOT/'html_build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':
    main()
