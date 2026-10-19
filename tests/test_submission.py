from pathlib import Path
import shutil

import pytest

from src.materials import build_materials
from src.submission import build


def test_legacy_entry_never_overwrites_existing_documents(tmp_path):
    docs = tmp_path / 'docs'
    docs.mkdir()
    target = docs / '参赛项目说明.md'
    target.write_bytes(b'team edits')
    with pytest.raises(ValueError, match='旧入口'):
        build_materials(tmp_path)
    assert target.read_bytes() == b'team edits'


def test_candidate_build_preserves_source_and_rejects_unsafe_or_reused_output(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    root = tmp_path / 'portable-project'
    shutil.copytree(source_root / 'templates/submission', root / 'templates/submission')
    source = root / 'templates/submission/参赛项目说明.html'
    before = source.read_bytes()
    for unsafe in [root, root / 'docs', root / 'templates/submission', root / 'artifacts', tmp_path / 'outside']:
        with pytest.raises(ValueError, match='build/'):
            build(root, unsafe)
    output = root / 'build/v1'
    build(root, output)
    assert (output / '参赛项目说明.html').read_bytes() == before
    assert '636' in (output / '参赛项目说明.md').read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='已存在'):
        build(root, output)
    assert source.read_bytes() == before
