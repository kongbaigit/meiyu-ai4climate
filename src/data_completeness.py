"""解释冻结数据的逐日缺口和字段覆盖；不填补或重建实验样本。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from .bundle import load_bundle
from .temporal_results import load_temporal_evidence


LABELS = {"paired": "已配对", "missing_forecast": "缺配对预报", "incomplete_reference": "参考报告不完整", "no_reference_record": "没有参考报告"}


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_completeness(root: Path) -> dict:
    root = Path(root)
    data = load_bundle(root)
    if data.errors:
        raise ValueError("完整度不能从未通过核验的主数据计算：" + "；".join(data.errors))
    quality = data.quality
    monthly_source = quality.get("monthly", [])
    if not monthly_source:
        raise ValueError("质量报告缺少配置月份。")
    first, last = monthly_source[0]["month"], monthly_source[-1]["month"]
    days = pd.date_range(first + "-01", pd.Period(last, freq="M").end_time.date(), freq="D", tz="UTC")
    observations = pd.read_csv(root / "data/observations.csv", dtype={"station_id": "string"})
    candidates = observations.loc[observations.source_dataset.eq("SSODv2") & observations.station_id.eq("CHI0000ZSHC") & observations.quality_status.eq("complete_reference")]
    candidate_dates = pd.to_datetime(candidates.window_start_utc, utc=True).dt.strftime("%Y-%m-%d")
    paired_dates = pd.to_datetime(data.samples.window_start_utc, utc=True).dt.strftime("%Y-%m-%d")
    if candidate_dates.duplicated().any() or paired_dates.duplicated().any():
        raise ValueError("完整度输入出现重复日期。")
    candidate_set, paired_set = set(candidate_dates), set(paired_dates)
    configured_set = {day.strftime("%Y-%m-%d") for day in days}
    if not paired_set <= candidate_set <= configured_set:
        raise ValueError("配对日、参考候选日和配置日不满足包含关系。")
    quarantined = data.quarantined
    bad = quarantined.loc[quarantined.source_dataset.eq("SSODv2") & quarantined.station_id.eq("CHI0000ZSHC")]
    reasons = {pd.Timestamp(row.window_start_utc).strftime("%Y-%m-%d"): str(row.reason) for row in bad.itertuples() if pd.notna(row.window_start_utc)}
    records = []
    for date in sorted(configured_set):
        status = "paired" if date in paired_set else "missing_forecast" if date in candidate_set else "incomplete_reference" if date in reasons else "no_reference_record"
        records.append({"date": date, "month": date[:7], "status": status, "label": LABELS[status], "reason": reasons.get(date, "forecast_missing_or_unusable" if status == "missing_forecast" else status)})
    summary = {"configured_days": len(records), "complete_reference_days": len(candidate_set), "paired_days": len(paired_set),
               "missing_reference_days": len(configured_set - candidate_set), "missing_forecast_days": len(candidate_set - paired_set),
               "incomplete_reference_days": sum(r["status"] == "incomplete_reference" for r in records),
               "no_reference_record_days": sum(r["status"] == "no_reference_record" for r in records),
               "paired_calendar_coverage": len(paired_set) / len(records), "latest_paired_date": max(paired_set) if paired_set else None}
    expected = quality["summary"]
    for key, source_key in [("configured_days", "configured_nominal_day_window_count"), ("complete_reference_days", "candidate_window_count"), ("paired_days", "sample_count"), ("missing_reference_days", "missing_reference_day_count"), ("missing_forecast_days", "unpaired_candidate_window_count")]:
        if summary[key] != expected[source_key]:
            raise ValueError(f"完整度与冻结质量报告不一致：{key}。")
    monthly = []
    for month in sorted({r["month"] for r in records}):
        selected = [r for r in records if r["month"] == month]
        row = {"month": month, "configured_days": len(selected), **{key: sum(r["status"] == key for r in selected) for key in LABELS}}
        row["paired_coverage"] = row["paired"] / row["configured_days"]
        monthly.append(row)
    gaps = []
    for row in records:
        if row["status"] == "paired":
            continue
        if gaps and gaps[-1]["status"] == row["status"] and (pd.Timestamp(row["date"]) - pd.Timestamp(gaps[-1]["end_date"])).days == 1:
            gaps[-1]["end_date"] = row["date"]
            gaps[-1]["days"] += 1
        else:
            gaps.append({"start_date": row["date"], "end_date": row["date"], "days": 1, "status": row["status"], "label": row["label"]})
    fields = []
    definitions = [("observed_rain_mm", "参考降水", True), ("forecast_rain_mm", "配对预报降水", True),
                   ("forecast_temperature_mean_c", "预报平均温度", False), ("forecast_relative_humidity_mean_pct", "预报平均相对湿度", False),
                   ("available_at_utc", "单次预报实际可用时刻", False)]
    for key, label, required in definitions:
        available = int(data.samples[key].notna().sum())
        fields.append({"field": key, "label": label, "required": required, "available": available, "missing": len(data.samples) - available,
                       "coverage": available / len(data.samples) if len(data.samples) else None,
                       "note": "固定提前量合成序列没有唯一发布时刻，不能视为业务回放。" if key == "available_at_utc" else "可选字段缺失时不补零；温湿度模型只按自己的特征协议使用。" if not required else "主表所需字段必须完整。"})
    temporal, errors = load_temporal_evidence(root, data.dataset_version)
    if errors:
        raise ValueError("新增时间段完整度证据未通过核验：" + "；".join(errors))
    temporal_summary = {"counts": temporal.get("counts", {}), "monthly": temporal.get("monthly_coverage", []), "scope": temporal.get("scope", {}), "dataset_version": temporal.get("dataset_version")} if temporal else {}
    inputs = ["data/samples.csv", "data/observations.csv", "data/quarantined_records.csv", "reports/data_quality.json", "reports/temporal_validation.json", "data/source_manifest.json"]
    return {"schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "dataset_version": data.dataset_version,
            "summary": summary, "monthly": monthly, "days": records, "gaps": sorted(gaps, key=lambda g: (-g["days"], g["start_date"])),
            "fields": fields, "temporal": temporal_summary, "input_sha256": {name: _hash(root / name) for name in inputs},
            "definition": "日覆盖按配置的UTC 00–24小时窗口计算；缺测、报告不完整和预报缺口分别保留，不能补成无雨。"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_completeness(args.root.resolve())
    output = args.output or args.root / "reports/completeness.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
