"""只读核验本次接手包，不联网、不执行工程代码。"""
import argparse
import hashlib
import json
from pathlib import Path
from verify_handoff import checked_path


def check(root):
    root = root.resolve()
    manifest = json.loads((root / 'delivery_manifest.json').read_text(encoding='utf-8'))
    entries = manifest['files']
    errors, seen = [], set()
    if not entries:
        errors.append('文件清单为空')
    for entry in entries:
        name = entry['path']
        try:
            if name in seen:
                raise ValueError('重复路径：' + name)
            seen.add(name)
            content = checked_path(root, name).read_bytes()
            if len(content) != entry['bytes'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise ValueError('大小或摘要不一致：' + name)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    baseline = json.loads((root / 'handoff_manifest.json').read_text(encoding='utf-8'))
    for name, expected in baseline['frozen_sha256'].items():
        try:
            if hashlib.sha256(checked_path(root, name).read_bytes()).hexdigest() != expected:
                raise ValueError('冻结摘要不一致：' + name)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    return {'status': 'passed' if not errors else 'failed', 'checked_files': len(entries),
            'frozen_files': len(baseline['frozen_sha256']), 'errors': errors,
            'note': '仅核对清单所列文件；本地新增文件不参与摘要比较。ZIP身份由外部SHA256核对。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = check(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {'status': 'failed', 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
