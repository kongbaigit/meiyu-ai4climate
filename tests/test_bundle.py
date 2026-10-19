import hashlib
import json

import pandas as pd

from src.bundle import load_bundle
from src.contracts import SAMPLE_COLUMNS


def empty_package(root):
    (root / "data").mkdir()
    (root / "reports").mkdir()
    path = root / "data" / "samples.csv"
    pd.DataFrame(columns=SAMPLE_COLUMNS).to_csv(path, index=False)
    manifest = root / "data" / "source_manifest.json"
    manifest.write_text(json.dumps({"manifest_id": "fixture", "sources": []}))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    quality = {"dataset_version": "meiyu-" + digest[:16], "summary": {"sample_count": 0},
               "sample_file_sha256": digest,
               "source_manifest_file_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    (root / "reports" / "data_quality.json").write_text(json.dumps(quality))


def test_empty_bundle_is_readable(tmp_path):
    assert load_bundle(tmp_path).errors == []
    empty_package(tmp_path)
    assert load_bundle(tmp_path).errors == []


def test_modified_source_manifest_is_blocked(tmp_path):
    empty_package(tmp_path)
    (tmp_path / "data" / "source_manifest.json").write_text('{"sources": []}')
    assert any("来源清单文件散列" in error for error in load_bundle(tmp_path).errors)


def test_modified_samples_is_blocked_even_if_schema_stays_valid(tmp_path):
    empty_package(tmp_path)
    with (tmp_path / "data" / "samples.csv").open("a") as handle:
        handle.write("\n")
    errors = load_bundle(tmp_path).errors
    assert any("统一样本表文件散列" in error for error in errors)
    assert any("数据版本" in error for error in errors)
