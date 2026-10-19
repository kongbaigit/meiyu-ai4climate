"""从分镜生成画面文案，不读取或生成语音。"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    storyboard = json.loads((ROOT / 'storyboard.json').read_text(encoding='utf-8'))
    cues = storyboard['text_cues']
    last_end = 0
    for cue in cues:
        if not last_end <= cue['start'] < cue['end'] <= storyboard['duration']:
            raise ValueError('动态文字时段不合法')
        if cue['accent'] not in cue['text']:
            raise ValueError('强调文字不在原文中')
        last_end = cue['end']
    weather = json.loads((ROOT / 'evidence/weather.json').read_text(encoding='utf-8'))
    data = {'timeline': storyboard, 'text_cues': cues, 'audio_mode': 'instrumental_only',
            'evidence': {'weather': weather,
                         'cost_scenario': {'probability': .6, 'move_cost_initial': 80, 'move_cost_changed': 600, 'loss_without': 1000, 'loss_after': 100},
                         'project': json.loads((ROOT / 'evidence/project_identity.json').read_text(encoding='utf-8'))}}
    (ROOT / 'film_input.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def stamp(value):
        ms = round(value * 1000)
        return f'{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}'

    (ROOT.parent / '动态文字.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(c['start'])} --> {stamp(c['end'])}\n{c['text']}" for i, c in enumerate(cues)) + '\n', encoding='utf-8')
    print(json.dumps({'duration': storyboard['duration'], 'scenes': len(storyboard['scenes']), 'text_cues': len(cues), 'speech_tracks': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
