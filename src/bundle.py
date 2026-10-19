from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import pandas as pd

from .contracts import SAMPLE_COLUMNS, validate_samples


@dataclass
class DataBundle:
    samples: pd.DataFrame
    quarantined: pd.DataFrame
    quality: dict
    manifest: dict
    errors: list[str]

    @property
    def dataset_version(self) -> str:
        if not isinstance(self.quality, dict):
            return ""
        return str(self.quality.get("dataset_version", ""))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON 无法读取：{path}：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 顶层必须是对象：{path}")
    return value


def load_bundle(root: Path) -> DataBundle:
    errors: list[str] = []
    path = root / "data" / "samples.csv"
    samples = pd.read_csv(path, dtype={"station_id": "string", "sample_id": "string"}) if path.exists() else pd.DataFrame(columns=SAMPLE_COLUMNS)
    quarantine_path = root / "data" / "quarantined_records.csv"
    quarantined = pd.read_csv(quarantine_path, dtype={"station_id": "string"}, low_memory=False) if quarantine_path.exists() else pd.DataFrame()
    json_files = [
        (root / "reports" / "data_quality.json", "质量报告"),
        (root / "data" / "source_manifest.json", "来源清单"),
    ]
    loaded_json: dict[str, dict] = {}
    for json_path, label in json_files:
        try:
            loaded_json[label] = read_json(json_path)
        except (OSError, ValueError) as exc:
            loaded_json[label] = {}
            errors.append(f"{label}无法读取：{exc}")
    quality = loaded_json["质量报告"]
    manifest = loaded_json["来源清单"]
    errors.extend(validate_samples(samples))
    if not samples.empty and not quality.get("dataset_version"):
        errors.append("样本包缺少数据版本。")
    summary = quality.get("summary", {})
    if not isinstance(summary, dict):
        errors.append("质量报告中的 summary 必须是对象。")
        summary = {}
    if summary.get("sample_count") not in (None, len(samples)):
        errors.append("质量报告中的样本数与主表不一致。")
    if not samples.empty or quality:
        for file_path, key, label in [
            (path, "sample_file_sha256", "统一样本表"),
            (root / "data" / "source_manifest.json", "source_manifest_file_sha256", "来源清单"),
        ]:
            expected = quality.get(key)
            if not expected or not file_path.exists() or hashlib.sha256(file_path.read_bytes()).hexdigest() != expected:
                errors.append(f"{label}文件散列不匹配或缺失，请重新构建完整数据包。")
        if path.exists() and quality.get("dataset_version") != "meiyu-" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]:
            errors.append("数据版本与统一样本表内容不一致。")
    if not samples.empty:
        if not manifest.get("manifest_id") or not samples["source_manifest_id"].eq(manifest["manifest_id"]).all():
            errors.append("样本中的来源清单引用不一致。")
        sources = manifest.get("sources", [])
        if not isinstance(sources, list):
            errors.append("来源清单中的 sources 必须是数组。")
            sources = []
        source_ids = {source.get("source_id") for source in sources if isinstance(source, dict)}
        if not samples["forecast_spec_id"].isin(source_ids).all():
            errors.append("样本包含无法追溯的预报来源。")
    return DataBundle(samples, quarantined, quality, manifest, errors)
