"""构建不依赖外部脚本或图片的搬货决策首页。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .decision_weather import EXPECTED_MEMBERS, GRID, LOCATIONS, MODEL, SOURCE, read_weather


def build(root: Path) -> dict:
    root = Path(root).resolve()
    template = (root / 'templates/decision.html').read_text(encoding='utf-8')
    sources = ['templates/decision.html', 'templates/decision.css', 'templates/decision_client.js', 'templates/decision_cost.js', 'src/decision_build.py', 'src/decision_weather.py']
    payload = {
        'schema_version': 1,
        'built_at_utc': datetime.now(timezone.utc).isoformat(),
        'locations': LOCATIONS, 'grids': GRID, 'expected_members': EXPECTED_MEMBERS,
        'model': MODEL, 'source': SOURCE,
        'weather_seed': {key: read_weather(root, key) for key in LOCATIONS},
        'base_project_commit': '79e3056b25b7a7101a44381a98d5410327e10826',
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    replacements = {
        '/*__DECISION_CSS__*/': (root / 'templates/decision.css').read_text(encoding='utf-8'),
        '/*__DECISION_INPUT__*/': encoded,
        '/*__DECISION_COST__*/': (root / 'templates/decision_cost.js').read_text(encoding='utf-8'),
        '/*__DECISION_CLIENT__*/': (root / 'templates/decision_client.js').read_text(encoding='utf-8'),
    }
    for key, value in replacements.items():
        if template.count(key) != 1:
            raise ValueError('首页模板占位符不唯一：' + key)
        template = template.replace(key, value)
    if '__DECISION_' in template:
        raise ValueError('首页模板仍有未替换内容。')
    encoded_page = template.encode('utf-8')
    (root / 'index.html').write_bytes(encoded_page)
    report = {'schema_version': 1, 'output': 'index.html', 'bytes': len(encoded_page), 'sha256': hashlib.sha256(encoded_page).hexdigest(), 'built_at_utc': payload['built_at_utc'], 'inputs': {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in sources}}
    (root / 'runtime').mkdir(exist_ok=True)
    (root / 'runtime/decision_build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    print(json.dumps(build(Path(__file__).resolve().parents[1]), ensure_ascii=False))
