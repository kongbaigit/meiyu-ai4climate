import hashlib
import json

from src.data_pipeline import build_source_manifest


def test_identical_snapshots_preserve_manifest_bytes_and_changed_snapshot_gets_new_id(tmp_path):
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    source = raw / "fixture.csv"
    source.write_text("fixture-data", encoding="utf-8")
    config = {"sources": [{"source_id": "fixture", "url": "https://example.invalid/fixture.csv", "path": "data/raw/fixture.csv"}]}
    first, first_id = build_source_manifest(tmp_path, config)
    manifest_path = tmp_path / "data" / "source_manifest.json"
    first_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    second, second_id = build_source_manifest(tmp_path, config)
    assert first == second
    assert second_id == first_id
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == first_hash
    source.write_text("changed-fixture-data", encoding="utf-8")
    third, third_id = build_source_manifest(tmp_path, config)
    assert third_id != first_id
    assert third["sources"][0]["sha256"] != first["sources"][0]["sha256"]
