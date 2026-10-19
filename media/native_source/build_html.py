from pathlib import Path
import base64,hashlib,json

ROOT=Path(__file__).resolve().parent
template=(ROOT/'player.html').read_text(encoding='utf-8')
evidence=json.loads((ROOT/'evidence.json').read_text(encoding='utf-8'))
timeline=json.loads((ROOT/'timeline.json').read_text(encoding='utf-8'))
inputs={'evidence':evidence,'timeline':timeline,
        'voice':base64.b64encode((ROOT/'narration.mp3').read_bytes()).decode(),
        'music':base64.b64encode((ROOT/'music_playback.mp3').read_bytes()).decode()}
html=template.replace('/*__THREE__*/',(ROOT/'vendor/three.min.js').read_text(encoding='utf-8'))
html=html.replace('/*__INPUT__*/',json.dumps(inputs,ensure_ascii=False,separators=(',',':')).replace('</',r'<\/'))
html=html.replace('/*__APP__*/',(ROOT/'app.js').read_text(encoding='utf-8'))
assert '/*__' not in html
(ROOT/'index.html').write_text(html,encoding='utf-8')
written_html=(ROOT/'index.html').read_bytes()
report={'kind':'原生代码动画，未使用截图、图片或视频作为画面输入','canvas':'Three.js WebGL → Canvas 2D合成','duration':timeline['duration'],
        'html_sha256':hashlib.sha256(written_html).hexdigest(),'html_bytes':len(written_html),'data_version':evidence['dataset_version'],
        'input_sha256':evidence['inputs_sha256'],'original_score':'雨前的刻度','third_party_runtime':'three@0.160.1 MIT, inline',
        'audio_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['score.wav','music_playback.mp3','narration.mp3','mix.mp3'] if (ROOT/name).is_file()},
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['app.js','player.html','evidence.json','timeline.json','compose_audio.py','score_manifest.json']}}
(ROOT/'html_build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'html_bytes':report['html_bytes'],'duration':timeline['duration'],'html_sha256':report['html_sha256']}))
