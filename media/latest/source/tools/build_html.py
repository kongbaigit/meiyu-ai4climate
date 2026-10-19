from pathlib import Path
import base64
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent

def main():
    html = (ROOT / 'player.html').read_text(encoding='utf-8')
    replacements = {
        '/*__GSAP__*/': (ROOT / 'vendor/gsap.min.js').read_text(encoding='utf-8'),
        '/*__INPUT__*/': (ROOT / 'film_input.json').read_text(encoding='utf-8').replace('</', '<\\/'),
        '/*__COST__*/': (ROOT / 'vendor/decision_cost.js').read_text(encoding='utf-8'),
        '/*__APP__*/': (ROOT / 'film60.js').read_text(encoding='utf-8').replace('/*__DRAWING_HELPERS__*/', (ROOT / 'drawing_helpers.js').read_text(encoding='utf-8')),
    }
    for marker, value in replacements.items():
        assert html.count(marker) == 1
        html = html.replace(marker, value)
    for marker, name in [('__VOICE__', 'narration.mp3'), ('__MUSIC__', 'music_playback.mp3')]:
        audio = ROOT / 'audio' / name
        assert audio.exists(), audio
        html = html.replace(marker, 'data:audio/mpeg;base64,' + base64.b64encode(audio.read_bytes()).decode('ascii'))
    target = ROOT.parent / '预览.html'
    target.write_text(html, encoding='utf-8')
    report = {'path': target.name, 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'self_contained': True, 'external_media_dependencies': [], 'source': 'source/player.html + film60.js + drawing_helpers.js + film_input.json + vendor + audio'}
    (ROOT / 'html_build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
