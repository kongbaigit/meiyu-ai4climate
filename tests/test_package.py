import json
from pathlib import Path
import zipfile
import pytest

from src.package import PackagingError, build_package


def test_package_rejects_source_file_as_output_without_changing_it(tmp_path):
    source = tmp_path / "app.py"
    source.write_bytes(b"original source\n")
    with pytest.raises(PackagingError, match=".zip"):
        build_package(tmp_path, source)
    assert source.read_bytes() == b"original source\n"


def test_package_excludes_unallowed_private_and_temporary_paths(tmp_path):
    root = tmp_path / "release"
    (root / "src").mkdir(parents=True)
    (root / "reports").mkdir()
    (root / ".streamlit").mkdir()
    (root / ".streamlit" / "config.toml").write_text("[server]\nheadless=true\n", encoding="utf-8")
    (root / ".streamlit" / "secrets.toml").write_text("TOKEN='test-only'\n", encoding="utf-8")
    (root / "reports" / "internal").mkdir()
    (root / "reports" / "internal" / "old.md").write_text("old version", encoding="utf-8")
    (root / "reports" / "续接核验_20261015").mkdir()
    (root / "reports" / "续接核验_20261015" / "page-1.png").write_bytes(b"qa image")
    (root / "reports" / "evaluation.json").write_text("{}", encoding="utf-8")
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / "__pycache__").mkdir()
    (root / "research").mkdir()
    (root / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "src" / "good.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (root / "src" / "id_rsa").write_text("private\n", encoding="utf-8")
    (root / "src" / "scratch.pyc").write_bytes(b"bytecode")
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"environment")
    (root / "__pycache__" / "bad.pyc").write_bytes(b"cache")
    (root / "research" / "secret.txt").write_text("outside allow-list\n", encoding="utf-8")
    output = tmp_path / "qa" / "candidate.zip"

    result = build_package(root, output)

    assert result["file_count"] == result["manifest_file_count"]
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
        assert "meiyu/app.py" in names
        assert "meiyu/src/good.py" in names
        assert "meiyu/reports/package_manifest.json" in names
        assert "meiyu/.streamlit/config.toml" in names
        assert "meiyu/.streamlit/secrets.toml" not in names
        assert "meiyu/reports/evaluation.json" in names
        assert not any("reports/internal/" in name or "reports/续接核验_20261015/" in name for name in names)
        assert all(name.startswith("meiyu/") for name in names)
        assert not any(".venv/" in name or "__pycache__/" in name for name in names)
        assert "meiyu/src/.env" not in names
        assert "meiyu/src/id_rsa" not in names
        assert "meiyu/src/scratch.pyc" not in names
        assert "meiyu/research/secret.txt" not in names
        manifest = json.loads(archive.read("meiyu/reports/package_manifest.json"))
    self_entries = [entry for entry in manifest["files"] if entry["path"] == "reports/package_manifest.json"]
    assert len(self_entries) == 1
    assert self_entries[0]["self_manifest"] is True
    assert self_entries[0]["sha256"] is None
