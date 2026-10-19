import hashlib
import json

from src.temporal_results import load_temporal_evidence


def test_temporal_evidence_blocks_referenced_artifact_after_byte_change(tmp_path):
    (tmp_path / "reports").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "external").mkdir()
    protocol = tmp_path / "docs/新增时间段验证协议.md"
    protocol.write_text("fixture protocol", encoding="utf-8")
    predictions = tmp_path / "external/predictions.csv"
    predictions.write_bytes(b"fixture predictions\n")
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    identity = {"protocol_sha256": digest(protocol)}
    report = {"status": "completed", "identity": identity, "dataset_version": "external-fixture",
              "main_dataset_version": "main-fixture", "selected_method": "logistic_rain", "event_threshold_mm": 25,
              "main_files_unchanged": True, "main_file_sha256": {},
              "output_sha256": {"external/predictions.csv": digest(predictions)}}
    report_path = tmp_path / "reports/temporal_validation.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    (tmp_path / "reports/temporal_run.json").write_text(json.dumps({
        "status": "completed", "identity": identity, "dataset_version": "external-fixture",
        "report_sha256": digest(report_path)}), encoding="utf-8")
    assert load_temporal_evidence(tmp_path, "main-fixture") == (report, [])
    predictions.write_bytes(b"changed predictions\n")
    blocked, errors = load_temporal_evidence(tmp_path, "main-fixture")
    assert blocked == {}
    assert any("摘要不符" in error for error in errors)
