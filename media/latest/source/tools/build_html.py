from pathlib import Path
import base64
import hashlib
import json

ROOT = Path(__file__).resolve().parent.parent

def main():
    storyboard = json.loads((ROOT / 'storyboard.json').read_text(encoding='utf-8'))
    evidence = json.loads((ROOT / 'kinetic_evidence.json').read_text(encoding='utf-8'))
    film_input = {'timeline': storyboard, 'evidence': evidence, 'text_cues': storyboard['text_cues'],
                  'legacy_evidence':json.loads((ROOT/'legacy_evidence.json').read_text(encoding='utf-8')),
                  'legacy_timeline':json.loads((ROOT/'legacy_timeline.json').read_text(encoding='utf-8'))}
    (ROOT / 'film_input.json').write_text(json.dumps(film_input, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    html = (ROOT / 'player.html').read_text(encoding='utf-8')
    replacements = {
        '/*__GSAP__*/': (ROOT / 'vendor/gsap.min.js').read_text(encoding='utf-8'),
        '/*__THREE__*/': (ROOT / 'vendor/three.min.js').read_text(encoding='utf-8'),
        '/*__LEGACY__*/': (ROOT / 'legacy3d.js').read_text(encoding='utf-8'),
        '/*__INPUT__*/': (ROOT / 'film_input.json').read_text(encoding='utf-8').replace('</', '<\\/'),
        '/*__COST__*/': (ROOT / 'vendor/decision_cost.js').read_text(encoding='utf-8'),
        '/*__APP__*/': (ROOT / 'film.js').read_text(encoding='utf-8').replace('/*__DRAWING_HELPERS__*/', (ROOT / 'drawing_helpers.js').read_text(encoding='utf-8')),
    }
    for marker, value in replacements.items():
        assert html.count(marker) == 1
        html = html.replace(marker, value)
    for marker, name in [('__MUSIC__', 'music_playback.mp3')]:
        audio = ROOT / 'audio' / name
        assert audio.exists(), audio
        html = html.replace(marker, 'data:audio/mpeg;base64,' + base64.b64encode(audio.read_bytes()).decode('ascii'))
    target = ROOT.parent / 'preview.html'
    target.write_text(html, encoding='utf-8')
    report = {'path': target.name, 'bytes': target.stat().st_size, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'duration':storyboard['duration'], 'self_contained': True, 'external_media_dependencies': [], 'source': 'source/player.html + film.js + original legacy3d.js + drawing_helpers.js + film_input.json + vendor + audio'}
    (ROOT / 'html_build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
