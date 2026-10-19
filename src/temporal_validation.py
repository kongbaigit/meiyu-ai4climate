"""按预先保存的协议，在新时间段使用原有参数；不拟合或选择模型。"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

from .bundle import read_json
from .contracts import PREDICTION_COLUMNS, SAMPLE_COLUMNS, validate_predictions, validate_samples
from .data_pipeline import OBSERVATION_COLUMNS, QUARANTINE_COLUMNS, build_sample_rows, parse_ssod_files
from .experiments import always_never_costs, cost_scenarios, metrics_for_split, paired_brier_bootstrap
from .forecasts import MODEL, VARIABLES, parse_previous_response
from .reproduce import METHODS, rebuild_method_predictions, verify_hashes

START = pd.Timestamp("2026-01-01T00:00:00Z")
END = pd.Timestamp("2026-10-01T00:00:00Z")
PROTOCOL_SHA = "5a31d8c9960d409791fc93549ce393702a611303b21b1a5261f54de117e1f4bc"
PARAMETERS_SHA = "297f0d6e4a574b634848fbd92a4354b7b91383439e29b404e2f81e0e5ac60418"
MAIN_PREDICTIONS_SHA = "65096b2db07625826ad9ea90e2ca9d373fe5f18c088bc50b80a0dc6e349fc961"
RATIOS = [.02, .05, .1, .2, .4, .6]
STATION = "CHI0000ZSHC"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("时间段验证文件路径超出其独立目录。")
    return path


def in_scope(record: dict) -> bool:
    start = pd.to_datetime(record.get("window_start_utc"), utc=True, errors="coerce")
    end = pd.to_datetime(record.get("window_end_utc"), utc=True, errors="coerce")
    return bool(pd.notna(start) and pd.notna(end) and start >= START and end <= END
                and end - start == pd.Timedelta(hours=24))


def verify_sources(external: Path, manifest: dict, protocol: dict) -> tuple[dict, dict]:
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not manifest.get("manifest_id"):
        raise ValueError("新增时间段来源清单缺少身份或 sources。")
    ssod, forecast = None, None
    saved_at = pd.Timestamp(protocol["saved_at_utc"])
    for source in sources:
        path = inside(external, source.get("local_path", source.get("path", "")))
        if not path.is_file() or sha256(path) != source.get("sha256"):
            raise ValueError("新增时间段原始来源缺失或散列不符。")
        if path.stat().st_size != source.get("bytes"):
            raise ValueError("新增时间段来源字节数不符。")
        if pd.Timestamp(source["retrieved_at_utc"]) < saved_at:
            raise ValueError("来源获取时间早于本轮保存协议时间，不符合本次检查身份。")
        url = urlparse(source["url"])
        if str(source.get("source_id", "")).startswith("ssod_"):
            if ssod is not None or url.netloc != "www.ncei.noaa.gov" or url.path != (
                "/oa/synoptic-summary-of-the-day/v2/access/by-year/2026/csv/SSOD_CHI0000ZSHC_2026.csv"
            ) or source.get("station_id") != STATION or int(source.get("year", 0)) != 2026:
                raise ValueError("SSOD 来源不是协议固定的同站2026对象。")
            ssod = dict(source, _resolved_path=str(path))
        elif str(source.get("source_id", "")).startswith("openmeteo_"):
            query = parse_qs(url.query)
            required = {"start_date": "2026-01-01", "end_date": "2026-10-01", "models": MODEL, "timezone": "UTC"}
            if forecast is not None or url.netloc != "previous-runs-api.open-meteo.com" or url.path != "/v1/forecast":
                raise ValueError("预报来源不符合协议接口。")
            if any(query.get(k) != [v] for k, v in required.items()):
                raise ValueError("预报日期、模型或时区不符合协议。")
            if query.get("hourly") != [",".join(VARIABLES)]:
                raise ValueError("预报变量不符合协议。")
            if not np.isclose(float(query.get("latitude", ["nan"])[0]), 30.2283) or not np.isclose(float(query.get("longitude", ["nan"])[0]), 120.4317):
                raise ValueError("预报请求点不是协议中的机场坐标。")
            forecast = dict(source, _resolved_path=str(path))
    if ssod is None or forecast is None:
        raise ValueError("缺少完整SSOD或固定提前量预报来源，停止对应效果检查。")
    return ssod, forecast


def write_frame(path: Path, rows: list[dict], columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")
    return frame


def run(root: Path, replace: bool = False) -> dict:
    root = root.resolve()
    external = root / "external/hangzhou_2026"
    protocol_path = root / "docs/新增时间段验证协议.md"
    if sha256(protocol_path) != PROTOCOL_SHA:
        raise ValueError("内部协议已变化，不能冒用原协议开展检查。")
    protocol = read_json(external / "reports/protocol_identity.json")
    if protocol.get("protocol_sha256") != PROTOCOL_SHA or sha256(external / "reports/protocol.md") != PROTOCOL_SHA:
        raise ValueError("内部协议副本或身份不一致。")
    official_run, official_evaluation, official_checks = verify_hashes(root)
    if official_run.get("model_parameters_file_sha256") != PARAMETERS_SHA or official_run.get("predictions_file_sha256") != MAIN_PREDICTIONS_SHA:
        raise ValueError("模型不是本协议已经冻结的参数与结果。")
    if official_evaluation["selected_method"] != "logistic_rain" or official_evaluation["event_threshold_mm"] != 25:
        raise ValueError("主实验选择或事件阈值不是协议约定。")
    main_paths = ["data/samples.csv", "data/source_manifest.json", "config/experiment.yaml",
                  "artifacts/predictions.csv", "artifacts/model_parameters.json",
                  "artifacts/sample_splits.csv", "reports/experiment_run.json", "reports/evaluation.json"]
    main_before = {name: sha256(root / name) for name in main_paths}
    manifest_path = external / "data/source_manifest.json"
    manifest = read_json(manifest_path)
    ssod_source, forecast_source = verify_sources(external, manifest, protocol)
    identity = {"protocol_sha256": PROTOCOL_SHA, "model_parameters_sha256": PARAMETERS_SHA,
                "main_predictions_sha256": MAIN_PREDICTIONS_SHA, "source_manifest_sha256": sha256(manifest_path)}
    report_path = root / "reports/temporal_validation.json"
    run_path = root / "reports/temporal_run.json"
    if report_path.exists() and not replace:
        saved_run = read_json(run_path)
        if saved_run.get("identity") != identity or saved_run.get("report_sha256") != sha256(report_path):
            raise ValueError("新增时间段运行身份或评估摘要不一致，停止复用。")
        previous = read_json(report_path)
        if previous.get("identity") != identity:
            raise ValueError("已有新增时间段结果身份不同，停止覆盖；必要时显式--replace并保留版本说明。")
        for relative, expected in previous.get("output_sha256", {}).items():
            path = inside(root, relative)
            if not path.is_file() or sha256(path) != expected:
                raise ValueError("已有新增时间段结果损坏，停止复用。")
        if not previous.get("output_sha256"):
            raise ValueError("已有新增时间段结果缺少输出摘要。")
        return previous
    frozen = external / "frozen"
    frozen.mkdir(parents=True, exist_ok=True)
    for relative in ["artifacts/model_parameters.json", "reports/experiment_run.json", "reports/evaluation.json", "config/experiment.yaml"]:
        destination = frozen / Path(relative).name
        if destination.exists() and sha256(destination) != main_before[relative]:
            raise ValueError("已有主实验冻结副本不一致，停止覆盖。")
        if not destination.exists():
            shutil.copy2(root / relative, destination)
    observations_all, ssod_quarantine = parse_ssod_files([ssod_source], manifest["manifest_id"])
    observations = [record for record in observations_all if in_scope(record)]
    excluded = [record for record in observations_all if not in_scope(record)]
    body = read_json(Path(forecast_source["_resolved_path"]))
    if body.get("hourly_units", {}).get(VARIABLES[1]) != "°C" or body.get("hourly_units", {}).get(VARIABLES[2]) != "%":
        raise ValueError("温度或湿度单位与主实验不同，停止检查。")
    hourly = parse_previous_response(body)
    sample_rows, forecast_quarantine = build_sample_rows(observations, {2026: hourly}, {2026: forecast_source}, "temporal-2026")
    for record in sample_rows:
        record["split"] = "test"
    samples = write_frame(external / "data/samples.csv", sample_rows, SAMPLE_COLUMNS)
    sample_errors = validate_samples(samples)
    if sample_errors:
        raise ValueError("新增时间段样本协议失败：" + "；".join(sample_errors))
    samples.to_parquet(external / "data/samples.parquet", index=False)
    write_frame(external / "data/observations.csv", observations, OBSERVATION_COLUMNS)
    write_frame(external / "data/excluded_observations.csv", excluded, OBSERVATION_COLUMNS)
    quarantined = ssod_quarantine + forecast_quarantine
    write_frame(external / "data/quarantined_records.csv", quarantined, QUARANTINE_COLUMNS)
    version = "meiyu-temporal-" + sha256(external / "data/samples.csv")[:16]
    expected_days = int((END - START).days)
    candidate_days = len({r["window_start_utc"] for r in observations})
    reference_dates = {r["window_start_utc"] for r in observations}
    missing_days = [day.isoformat().replace("+00:00", "Z") for day in pd.date_range(START, END, inclusive="left", freq="D")
                    if day.isoformat().replace("+00:00", "Z") not in reference_dates]
    threshold = 25.0
    report = {
        "status": "completed" if len(samples) else "blocked", "kind": "fixed_model_new_temporal_period",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "identity": identity,
        "protocol": protocol, "main_dataset_version": official_run["dataset_version"],
        "dataset_version": version, "selected_method": "logistic_rain", "event_threshold_mm": threshold,
        "scope": {"start_utc": str(START), "end_utc_exclusive": str(END), "station_id": STATION,
                  "role": "另存的新时间段检查，不混入主636样本或重新选择方法"},
        "counts": {"configured_days": expected_days, "complete_candidate_days": candidate_days,
                   "missing_complete_reference_days": len(missing_days), "paired_windows": len(samples),
                   "unpaired_candidate_days": candidate_days - len(samples),
                   "complete_observations_outside_protocol": len(excluded),
                   "ssod_quarantine_rows_all_raw": len(ssod_quarantine), "forecast_quarantine_rows": len(forecast_quarantine),
                   "event_count": None, "source_row_count": len(observations_all) + len(ssod_quarantine)},
        "missing_reference_window_starts_utc": missing_days,
        "quarantine_reason_counts": dict(Counter(r["reason"] for r in quarantined)),
        "measurement_code_counts": dict(Counter(r["observation_measurement_code"] for r in sample_rows)),
        "forecast_source": {k: v for k, v in forecast_source.items() if not k.startswith("_")},
        "implementation_sha256": {name: sha256(root / name) for name in [
            "src/temporal_validation.py", "src/data_pipeline.py", "src/forecasts.py",
            "src/reproduce.py", "src/experiments.py", "src/contracts.py"]},
        "metrics": {}, "paired_brier_bootstrap": [], "cost_scenarios": {},
        "main_freeze_checks": official_checks,
        "limitations": [
            "内部协议在本轮获取来源前保存，未在第三方平台注册；归档检查不是前瞻性运营试点。",
            "同站新时间段不是跨站验证；SSOD可能低报且使用名义UTC日界。",
            "预报仍为不同初始化的固定提前量合成，未证明单一决策时刻的全部信息可用。",
            "样本和事件数有限；重采样区间不消除来源、模型选择、季节和站点不确定性。",
            "成本保持准备完全避损的相对单位假设，没有真实用户、灾损或碳收益证据。",
        ],
    }
    report["counts"]["ssod_quarantine_rows_in_period"] = sum(in_scope(record) for record in ssod_quarantine)
    report["counts"]["paired_calendar_coverage"] = len(samples) / expected_days
    report["monthly_coverage"] = []
    for month in pd.period_range("2026-01", "2026-09", freq="M"):
        month_key = str(month)
        month_candidates = [record for record in observations if record["window_start_utc"].startswith(month_key)]
        month_samples = samples.loc[samples.window_start_utc.astype(str).str.startswith(month_key)]
        report["monthly_coverage"].append({"month": month_key, "configured_days": month.days_in_month,
            "complete_candidate_days": len(month_candidates), "paired_windows": len(month_samples),
            "event_count": int(month_samples.observed_rain_mm.ge(threshold).sum()) if len(month_samples) else None})
    if len(samples):
        parameters = read_json(frozen / "model_parameters.json")
        probabilities = rebuild_method_predictions(samples, parameters)
        actual = samples.observed_rain_mm.ge(threshold).astype(int)
        report["counts"]["event_count"] = int(actual.sum())
        prediction_rows = []
        for method in METHODS:
            values = probabilities[method]
            if len(values) != len(samples) or not np.isfinite(values).all() or np.any((values < 0) | (values > 1)):
                raise ValueError("冻结参数生成无效概率，停止对应效果检查。")
            report["metrics"][method] = metrics_for_split(actual, values)
            for sample_id, probability in zip(samples.sample_id, values):
                prediction_rows.append(dict(sample_id=sample_id, method=method, probability=float(probability),
                    model_version=official_run["model_versions"][method], dataset_version=version,
                    experiment_kind="offline_fixed_lead", event_threshold_mm=threshold))
        predictions = write_frame(external / "data/predictions.csv", prediction_rows, PREDICTION_COLUMNS)
        errors = validate_predictions(predictions, samples, version)
        if errors:
            raise ValueError("新增时间段预测协议失败：" + "；".join(errors))
        test_table = samples.assign(event=actual)
        if pd.to_datetime(samples.window_start_utc, utc=True).dt.tz_localize(None).dt.to_period("W").nunique() >= 2:
            for baseline in ["training_climatology", "raw_nwp_rule"]:
                report["paired_brier_bootstrap"].append(paired_brier_bootstrap(test_table, probabilities["logistic_rain"],
                    probabilities[baseline], baseline, seed=20261013, replicates=2000))
        else:
            report["limitations"].append("非空日历周少于2个，不计算周块重采样区间。")
        report["cost_scenarios"] = {
            "methods": {method: cost_scenarios(actual, values, RATIOS) for method, values in probabilities.items()},
            **always_never_costs(int(actual.sum()), len(actual), RATIOS),
            "assumption": "准备完全避免相关损失；相对单位，非实测收益。",
        }
    else:
        report["block_reason"] = "没有符合内部协议的完整配对日，停止预测与指标。"
    report["evidence_status"] = "insufficient_for_meiyu_generalization"
    report["interpretation"] = (
        f"按协议配置{expected_days}日，仅配对{len(samples)}日，参考事件{report['counts']['event_count']}个。"
        "逐月覆盖和事件数见本报告；这些数值仅作有限样本描述，不代表完整2026年或梅雨季表现。"
    )
    report["limitations"].append("缺少完整参考的日期不能当作无雨；当前新增覆盖不足以支持梅雨季泛化结论。")
    main_after = {name: sha256(root / name) for name in main_paths}
    if main_after != main_before:
        raise ValueError("主实验文件在检查中变化，停止发布新增时间段结果。")
    report["main_files_unchanged"] = True
    report["main_file_sha256"] = main_after
    output_files = [p for folder in [external / "data", external / "frozen"] for p in folder.rglob("*") if p.is_file()]
    report["output_sha256"] = {str(p.relative_to(root)).replace("\\", "/"): sha256(p) for p in sorted(output_files)}
    json_write(report_path, report)
    json_write(external / "reports/temporal_validation.json", report)
    json_write(run_path, {"status": report["status"], "identity": identity,
                         "report_sha256": sha256(report_path), "dataset_version": version,
                         "main_files_unchanged": True})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    report = run(args.root, args.replace)
    print(json.dumps({k: report[k] for k in ["status", "dataset_version", "counts", "metrics"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
