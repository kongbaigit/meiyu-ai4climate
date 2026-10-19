"""从现有工程生成静态发布目录；不请求天气，不改变冻结文件。"""
from pathlib import Path
from html import escape
from datetime import datetime, timezone
import hashlib
import json
import shutil
import argparse


def build(root: Path, source_zip: Path | None = None):
    import markdown
    output = root / 'site/dist'
    output.mkdir(parents=True, exist_ok=True)
    copies = {
        'demo.html': 'demo.html', 'media/demo.html': 'film.html',
        'docs/参赛项目说明.pdf': 'statement.pdf',
        'templates/materials_portal.html': 'materials.html',
        'templates/portal.css': 'portal.css', 'templates/downloads.js': 'downloads.js',
    }
    for source, target in copies.items():
        shutil.copyfile(root / source, output / target)
    shutil.copyfile(output / 'materials.html', output / 'index.html')
    documents = {
        'data_ai_statement.md': 'data-ai.html', '90天验证计划.md': 'validation.html',
        '演示与答辩事实卡.md': 'qa.html', '远程用户理解测试.md': 'user-test.html',
    }
    for source, target in documents.items():
        text = (root / 'docs' / source).read_text(encoding='utf-8-sig')
        body = markdown.markdown(text, extensions=['tables', 'fenced_code'])
        page = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(source[:-3]) + ' · 梅雨有数</title><link rel="stylesheet" href="portal.css"></head><body><header><a class="brand" href="materials.html">◒ 梅雨有数</a><a href="materials.html">返回材料目录</a></header><main class="document">' + body + '</main><footer>研究原型 · 实际效果与用户需求待验证</footer></body></html>'
        (output / target).write_text(page, encoding='utf-8')
    downloads = {}
    assets = output / 'assets'
    assets.mkdir(exist_ok=True)
    source_zip = source_zip or Path('dist/梅雨有数_工程_20261015.zip')
    for key, relative, content_type in [('source', source_zip, 'application/zip'), ('video', 'media/demo.mp4', 'video/mp4')]:
        path = root / relative
        data = path.read_bytes()
        parts = []
        for i, offset in enumerate(range(0, len(data), 8 * 1024 * 1024)):
            name = f'assets/{key}-{i:02}.bin'
            (output / name).write_bytes(data[offset:offset + 8 * 1024 * 1024])
            parts.append(name)
        downloads[key] = {'name': path.name, 'type': content_type, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'parts': parts}
        assert b''.join((output / name).read_bytes() for name in parts) == data
    (output / 'downloads.json').write_text(json.dumps(downloads, ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'built_at_utc': datetime.now(timezone.utc).isoformat(), 'original_demo_unchanged': (output/'demo.html').read_bytes() == (root/'demo.html').read_bytes(), 'original_film_unchanged': (output/'film.html').read_bytes() == (root/'media/demo.html').read_bytes(), 'downloads': downloads, 'files': [{'path': p.relative_to(output).as_posix(), 'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.rglob('*')) if p.is_file()]}
    (root / 'reports/internal').mkdir(parents=True, exist_ok=True)
    (root / 'reports/internal/公开材料构建.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'files':len(report['files']), 'download_integrity':'passed'}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', type=Path, help='本次完整工程ZIP；相对路径从工程根目录计算')
    args = parser.parse_args()
    build(Path(__file__).resolve().parents[1], args.source_zip)
