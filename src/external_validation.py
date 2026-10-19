"""宁波机场 2025 年固定杭州模型的跨站迁移探索。

该模块只读取已经冻结的杭州模型参数，不调用 sklearn、不拟合、不调参，
也不使用宁波结果改变站点或方法。宁波观测采用 NOAA SSODv2 完整报告层，
预报采用 Open-Meteo Previous Runs 的同一固定提前量聚合口径。
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, OrderedDict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
import requests
import yaml

from .data_pipeline import build_sample_rows, parse_ssod_files
from .forecasts import load_previous_year
from .reproduce import build_features, rebuild_logistic


UTC = timezone.utc
DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "external_validation.yaml"
METHODS = ["training_climatology", "raw_nwp_rule", "logistic_rain"]
BOOTSTRAP_SEED = 20261013
BOOTSTRAP_REPLICATES = 2000
PROBABILITY_THRESHOLD = 0.1
EXTERNAL_SAMPLE_COLUMNS = [
    "sample_id", "observation_window_id", "forecast_spec_id", "station_id", "station_name",
    "station_lat", "station_lon", "window_start_utc", "window_end_utc", "observed_rain_mm",
    "observation_measurement_code", "reference_kind", "window_basis", "forecast_model", "forecast_kind",
    "run_init_utc", "available_at_utc", "availability_evidence", "decision_time_utc", "forecast_rain_mm",
    "forecast_temperature_mean_c", "forecast_relative_humidity_mean_pct", "experiment_kind", "quality_status",
    "audit_version", "obs_record_id", "forecast_record_id", "source_manifest_id", "split",
]


class ExternalValidationError(RuntimeError):
    """外部站点数据或冻结模型复用失败。"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ExternalValidationError(f"无法读取文件 SHA256：{path}") from exc


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_config(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ExternalValidationError(f"外部验证配置无法读取：{path}") from exc
    if not isinstance(value, dict):
        raise ExternalValidationError("外部验证配置顶层必须是对象。")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExternalValidationError(f"JSON 无法读取：{path}") from exc
    if not isinstance(value, dict):
        raise ExternalValidationError(f"JSON 顶层必须是对象：{path}")
    return value


def _copy_frozen_file(source: Path, destination: Path) -> str:
    if not source.is_file():
        raise ExternalValidationError(f"杭州冻结文件不存在：{source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return _sha256(destination)


def _read_station_evidence(root: Path, output_root: Path, config: dict[str, Any]) -> dict[str, Any]:
    station_cfg = config.get("station", {})
    station_id = str(station_cfg.get("station_id", "")).strip()
    expected_name = str(station_cfg.get("expected_name", "")).strip().upper()
    source_path = root / str(station_cfg.get("station_list_path", "data/raw/ghcnh-station-list.txt"))
    if not station_id or not source_path.is_file():
        raise ExternalValidationError(f"宁波站表证据不存在：{source_path}")
    source_sha = _sha256(source_path)
    matching_line = None
    for line in source_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line[:11].strip() == station_id:
            matching_line = line
            break
    if matching_line is None:
        raise ExternalValidationError(f"站表未找到官方站号：{station_id}")
    try:
        latitude = float(matching_line[12:20])
        longitude = float(matching_line[21:30])
        elevation = float(matching_line[31:37])
        station_name = matching_line[41:71].strip()
    except (ValueError, IndexError) as exc:
        raise ExternalValidationError(f"站表坐标无法解析：{matching_line!r}") from exc
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ExternalValidationError("站表坐标越界，拒绝猜测或替换。")
    if expected_name and expected_name not in station_name.upper():
        raise ExternalValidationError(f"站表名称 {station_name!r} 不含预期标识 {expected_name!r}。")
    evidence_path = output_root / "data" / "raw" / "ghcnh_station_evidence.txt"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        "source_url: " + str(station_cfg.get("station_list_url", "")) + "\n"
        + "source_local_path: " + str(source_path) + "\n"
        + "source_sha256: " + source_sha + "\n"
        + "station_line: " + matching_line + "\n",
        encoding="utf-8",
    )
    return {
        "station_id": station_id,
        "station_name": station_name,
        "latitude": latitude,
        "longitude": longitude,
        "elevation_m": elevation,
        "line": matching_line,
        "source_url": station_cfg.get("station_list_url"),
        "source_local_path": str(source_path),
        "source_sha256": source_sha,
        "evidence_path": str(evidence_path.relative_to(output_root)).replace("\\", "/"),
        "evidence_sha256": _sha256(evidence_path),
    }


def _download_or_use_cached(url: str, path: Path, expected_key: str | None = None) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    retrieved = False
    content_type = "cached"
    if path.is_file():
        body = path.read_bytes()
    else:
        try:
            response = requests.get(url, timeout=(10, 45))
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ExternalValidationError(f"下载失败：{url}；{exc}") from exc
        body = response.content
        content_type = response.headers.get("Content-Type", "")
        path.write_bytes(body)
        retrieved = True
    if expected_key is not None:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as exc:
            raise ExternalValidationError(f"SSOD prefix 返回不是 XML：{url}") from exc
        keys = [element.text for element in root.iter() if element.tag.endswith("Key") and element.text]
        if expected_key not in keys:
            raise ExternalValidationError(f"SSOD prefix 未列出精确对象：{expected_key}")
    return {
        "url": url,
        "path": str(path),
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
        "content_type": content_type,
        "retrieved_now": retrieved,
        "retrieved_at_utc": _utc_now() if retrieved else None,
    }


def _fetch_ssod(output_root: Path, config: dict[str, Any], station_id: str, year: int) -> tuple[dict[str, Any], dict[str, Any]]:
    ssod_cfg = config.get("ssod", {})
    prefix_url = str(ssod_cfg["prefix_url_template"]).format(year=year, station_id=station_id)
    download_url = str(ssod_cfg["download_url_template"]).format(year=year, station_id=station_id)
    expected_key = f"v2/access/by-year/{year}/csv/SSOD_{station_id}_{year}.csv"
    prefix_path = output_root / "data" / "raw" / f"ssod_prefix_{year}.xml"
    csv_path = output_root / "data" / "raw" / f"SSOD_{station_id}_{year}.csv"
    prefix = _download_or_use_cached(prefix_url, prefix_path, expected_key=expected_key)
    if csv_path.is_file():
        csv_meta = _download_or_use_cached(download_url, csv_path)
    else:
        csv_meta = _download_or_use_cached(download_url, csv_path)
    try:
        header = csv_path.read_text(encoding="utf-8-sig", errors="strict").splitlines()[0]
    except (OSError, UnicodeError, IndexError) as exc:
        raise ExternalValidationError(f"SSOD CSV 无法读取：{csv_path}") from exc
    required = {"STATION", "DATE", "LATITUDE", "LONGITUDE", "total_precipitation", "total_precipitation_Measurement_Code"}
    if not required.issubset(set(header.split(","))):
        raise ExternalValidationError("SSOD CSV 缺少必要字段，拒绝按列位置猜测。")
    return (
        {
            "source_id": f"ssod_{station_id}_{year}",
            "title": f"NOAA SSODv2 · {station_id} {year}",
            "url": download_url,
            "path": str(csv_path.relative_to(output_root)).replace("\\", "/"),
            "sha256": csv_meta["sha256"],
            "bytes": csv_meta["bytes"],
            "content_type": csv_meta["content_type"],
            "retrieved_at_utc": csv_meta["retrieved_at_utc"],
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "Ningbo SSOD daily reference observation",
            "station_id": station_id,
            "year": year,
        },
        {
            "source_id": f"ssod_prefix_{station_id}_{year}",
            "title": f"NOAA SSODv2 exact object prefix listing · {station_id} {year}",
            "url": prefix_url,
            "path": str(prefix_path.relative_to(output_root)).replace("\\", "/"),
            "sha256": prefix["sha256"],
            "bytes": prefix["bytes"],
            "content_type": prefix["content_type"],
            "retrieved_at_utc": prefix["retrieved_at_utc"],
            "licence": "NOAA/NCEI directory listing",
            "role": "exact-key availability evidence",
            "expected_key": expected_key,
        },
    )


def _cached_forecast_sources(output_root: Path) -> list[dict[str, Any]]:
    """保留本次目录中已缓存但未配对的预报证据，不把它当作样本。"""

    records: list[dict[str, Any]] = []
    raw_dir = output_root / "data" / "raw"
    for metadata_path in sorted(raw_dir.glob("openmeteo_*.metadata.json")):
        try:
            metadata = _read_json(metadata_path)
        except ExternalValidationError:
            continue
        raw_name = metadata_path.name.removesuffix(".metadata.json") + ".json"
        raw_path = metadata_path.with_name(raw_name)
        if not raw_path.is_file():
            continue
        records.append(
            {
                "source_id": metadata.get("source_id", metadata_path.stem),
                "title": metadata.get("title", "Open-Meteo cached forecast"),
                "url": metadata.get("url"),
                "path": metadata.get("local_path", str(raw_path.relative_to(output_root)).replace("\\", "/")),
                "sha256": _sha256(raw_path),
                "licence": metadata.get("licence", "CC BY 4.0；免费接口仅限非商业用途"),
                "role": "cached forecast fetched before SSOD blocking; not paired",
                "requested_latitude": metadata.get("requested_latitude"),
                "requested_longitude": metadata.get("requested_longitude"),
                "returned_latitude": metadata.get("returned_latitude"),
                "returned_longitude": metadata.get("returned_longitude"),
                "forecast_model": metadata.get("forecast_model"),
                "retrieved_at_utc": metadata.get("retrieved_at_utc"),
            }
        )
    return records


def _copy_hz_freeze(root: Path, output_root: Path, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    frozen_cfg = config.get("frozen_hangzhou", {})
    run_path = root / str(frozen_cfg.get("run_path", "reports/experiment_run.json"))
    params_path = root / str(frozen_cfg.get("model_parameters_path", "artifacts/model_parameters.json"))
    evaluation_path = root / str(frozen_cfg.get("evaluation_path", "reports/evaluation.json"))
    run = _read_json(run_path)
    params = _read_json(params_path)
    evaluation = _read_json(evaluation_path)
    if run.get("status") != "completed" or run.get("selected_method") != str(frozen_cfg.get("required_method", "logistic_rain")):
        raise ExternalValidationError("杭州冻结 run 未完成或推荐方法与本次固定迁移方法不一致。")
    for source_path, field in [(params_path, "model_parameters_file_sha256"), (evaluation_path, "evaluation_file_sha256")]:
        expected = run.get(field)
        if not isinstance(expected, str) or _sha256(source_path) != expected:
            raise ExternalValidationError(f"杭州冻结文件 {source_path.name} SHA256 与 run 不一致。")
    freeze_dir = output_root / "data" / "raw"
    copied = []
    for name, source in [("frozen_hz_experiment_run.json", run_path), ("frozen_hz_model_parameters.json", params_path), ("frozen_hz_evaluation.json", evaluation_path)]:
        destination = freeze_dir / name
        digest = _copy_frozen_file(source, destination)
        stem = Path(name).stem.removeprefix("frozen_hz_")
        copied.append({"source_id": f"frozen_hz_{stem}", "title": f"Frozen Hangzhou {name}", "path": str(destination.relative_to(output_root)).replace("\\", "/"), "sha256": digest, "role": "read-only frozen model reference"})
    return run, params, evaluation, copied


def _write_rows(path: Path, rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        frame = pd.DataFrame(rows)
        if columns:
            for column in columns:
                if column not in frame:
                    frame[column] = None
            frame = frame[columns + [column for column in frame.columns if column not in columns]]
    else:
        frame = pd.DataFrame(columns=columns or [])
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return _sha256(path)


def _metrics(actual: np.ndarray, probability: np.ndarray) -> dict[str, Any]:
    predicted = probability >= PROBABILITY_THRESHOLD
    return {
        "sample_count": int(len(actual)),
        "event_count": int(actual.sum()),
        "brier": float(np.mean((probability - actual) ** 2)) if len(actual) else None,
        "confusion_at_probability_0_1": {
            "threshold": PROBABILITY_THRESHOLD,
            "true_negative": int(((actual == 0) & (~predicted)).sum()),
            "false_positive": int(((actual == 0) & predicted).sum()),
            "false_negative": int(((actual == 1) & (~predicted)).sum()),
            "true_positive": int(((actual == 1) & predicted).sum()),
        },
    }


def _week_bootstrap(
    starts: pd.Series,
    actual: np.ndarray,
    selected: np.ndarray,
    baseline: np.ndarray,
    baseline_name: str,
    seed: int,
    replicates: int,
) -> dict[str, Any]:
    iso = pd.to_datetime(starts, utc=True).dt.isocalendar()
    keys = (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).to_numpy()
    blocks = [np.flatnonzero(keys == key) for key in pd.unique(keys)]
    difference = (selected - actual) ** 2 - (baseline - actual) ** 2
    rng = np.random.default_rng(seed)
    values = np.empty(replicates, dtype=float)
    for index in range(replicates):
        chosen = rng.integers(0, len(blocks), size=len(blocks))
        rows = np.concatenate([blocks[block] for block in chosen])
        values[index] = float(difference[rows].mean())
    return {
        "comparison": f"{baseline_name} -> logistic_rain",
        "definition": "logistic_rain individual Brier loss minus fixed baseline individual Brier loss; negative favors logistic_rain",
        "sample_count": int(len(actual)),
        "event_count": int(actual.sum()),
        "calendar_week_block_count": int(len(blocks)),
        "bootstrap_replicates": int(replicates),
        "random_seed": int(seed),
        "mean_difference": float(difference.mean()),
        "ci95": {"lower": float(np.quantile(values, 0.025)), "upper": float(np.quantile(values, 0.975))},
        "limitations": ["2025 宁波与杭州 2025 测试日历可能存在天气相关；外部事件数较少，周块重采样不消除站点和季节相关性。"],
    }


def _date_range(frame: pd.DataFrame, column: str = "window_start_utc") -> dict[str, str] | None:
    if frame.empty:
        return None
    values = pd.to_datetime(frame[column], utc=True)
    return {"start": values.min().isoformat().replace("+00:00", "Z"), "end": values.max().isoformat().replace("+00:00", "Z")}


def run_external_validation(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    config_path = config_path or root / "config" / "external_validation.yaml"
    config = _load_config(config_path)
    output_root = root / str(config.get("output", {}).get("root", "external/ningbo"))
    output_root.mkdir(parents=True, exist_ok=True)
    station = _read_station_evidence(root, output_root, config)
    year = int(config.get("station", {}).get("year", 2025))
    station_id = station["station_id"]
    run, hz_params, hz_evaluation, frozen_sources = _copy_hz_freeze(root, output_root, config)
    threshold = float(config.get("event", {}).get("threshold_mm", 25.0))
    if float(hz_evaluation.get("event_threshold_mm")) != threshold:
        raise ExternalValidationError("外部阈值与杭州冻结 evaluation 不一致。")

    ssod_source, ssod_prefix_source = _fetch_ssod(output_root, config, station_id, year)
    ssod_spec = {
        "source_id": ssod_source["source_id"],
        "_resolved_path": str(output_root / ssod_source["path"]),
        "station_id": station_id,
        "year": year,
    }
    manifest_id = "external-ningbo-2025-v1"
    observations, ssod_quarantine = parse_ssod_files([ssod_spec], manifest_id)
    with (output_root / ssod_source["path"]).open("r", encoding="utf-8-sig", newline="") as ssod_handle:
        csv_rows = sum(1 for _ in csv.DictReader(ssod_handle))
    raw_dates = pd.to_datetime(
        pd.read_csv(output_root / ssod_source["path"], usecols=["DATE"])["DATE"],
        errors="coerce",
        utc=True,
    ).dropna()
    ssod_row_date_range = None if raw_dates.empty else {
        "start": raw_dates.min().isoformat().replace("+00:00", "Z"),
        "end": raw_dates.max().isoformat().replace("+00:00", "Z"),
    }
    coord_differences = []
    for observation in observations:
        difference = max(abs(float(observation["station_lat"]) - station["latitude"]), abs(float(observation["station_lon"]) - station["longitude"]))
        if difference > 1e-6:
            coord_differences.append({"date": observation["window_start_utc"], "ssod_lat": observation["station_lat"], "ssod_lon": observation["station_lon"], "station_table_lat": station["latitude"], "station_table_lon": station["longitude"]})
    if coord_differences:
        raise ExternalValidationError(f"SSOD 坐标与官方站表不一致，拒绝合并或猜测：{coord_differences[0]}")

    # A source can be reachable while still having no complete precipitation
    # total.  Preserve that evidence as a structured blocked package instead
    # of switching stations or treating missing values as zero.
    if not observations:
        data_dir = output_root / "data"
        sample_path = data_dir / "samples.csv"
        quarantine_path = data_dir / "quarantined_records.csv"
        sample_hash = _write_rows(sample_path, [], EXTERNAL_SAMPLE_COLUMNS)
        quarantine_hash = _write_rows(quarantine_path, ssod_quarantine)
        sources: list[dict[str, Any]] = [
            {
                "source_id": "ghcnh_station_evidence",
                "title": "GHCN hourly station list exact Ningbo LISHE line",
                "url": station["source_url"],
                "path": station["evidence_path"],
                "sha256": station["evidence_sha256"],
                "licence": "NOAA/NCEI public station metadata",
                "role": "official station ID and coordinates evidence",
                "source_full_file_sha256": station["source_sha256"],
            },
            ssod_prefix_source,
            ssod_source,
        ]
        cached_forecast_sources = _cached_forecast_sources(output_root)
        sources.extend(cached_forecast_sources)
        sources.extend(frozen_sources)
        source_manifest = {
            "manifest_version": "external-ningbo-v1",
            "generated_at_utc": _utc_now(),
            "station": station,
            "sources": sources,
            "ssod_rule": "D/F/G/24 complete report layer; H/I and A/B/C/E and unknown codes quarantined; nominal UTC day.",
            "forecast_rule": "Not called because no complete SSOD precipitation day remained after conservative parsing.",
        }
        manifest_path = data_dir / "source_manifest.json"
        _json_dump(manifest_path, source_manifest)
        manifest_hash = _sha256(manifest_path)
        frozen_model_path = root / str(config["frozen_hangzhou"]["model_parameters_path"])
        frozen_evaluation_path = root / str(config["frozen_hangzhou"]["evaluation_path"])
        reason_counts = Counter(item.get("reason", "") for item in ssod_quarantine)
        code_counts = Counter(item.get("measurement_code", "") for item in ssod_quarantine)
        return {
            "status": "blocked",
            "result_kind": "cross_station_transfer_exploration",
            "generated_at_utc": _utc_now(),
            "block_reason": "宁波 SSOD 对象可访问，但所有行都没有 D/F/G/24 完整降水日量；不能形成可配对样本。",
            "station": {
                "station_id": station_id,
                "station_name": station["station_name"],
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "elevation_m": station["elevation_m"],
                "station_evidence_line": station["line"],
                "coordinate_consistency": "没有完整 SSOD 行可比较；坐标仅来自官方 GHCNh 站表，不猜测或替换。",
            },
            "scope": {
                "year": year,
                "source_row_date_range": ssod_row_date_range,
                "candidate_date_range": None,
                "paired_date_range": None,
                "forecast_model": config.get("forecast", {}).get("model", "ecmwf_ifs025"),
                "experiment_kind": "offline_fixed_lead transfer; forecast not called because reference is blocked",
            },
            "ssod_access": {
                "prefix_url": ssod_prefix_source["url"],
                "download_url": ssod_source["url"],
                "expected_key": ssod_prefix_source["expected_key"],
                "prefix_sha256": ssod_prefix_source["sha256"],
                "csv_sha256": ssod_source["sha256"],
                "csv_rows": int(csv_rows),
            },
            "counts": {
                "ssod_csv_rows": int(csv_rows),
                "complete_candidate_days": 0,
                "ssod_quarantine_rows": int(len(ssod_quarantine)),
                "paired_windows": 0,
                "forecast_quarantine_rows": 0,
                "event_threshold_mm": threshold,
                "event_count": None,
                "quarantine_measurement_code_counts": dict(code_counts),
                "quarantine_reason_counts": dict(reason_counts),
            },
            "methods": {},
            "paired_brier_bootstrap": [],
            "frozen_hangzhou": {
                "dataset_version": run.get("dataset_version"),
                "selected_method": run.get("selected_method"),
                "model_versions": run.get("model_versions", {}),
                "model_parameters_sha256": _sha256(frozen_model_path),
                "evaluation_sha256": _sha256(frozen_evaluation_path),
            },
            "forecast_call": {
                "status": "cached_but_not_used_no_complete_ssod_days" if cached_forecast_sources else "not_called_no_complete_ssod_days",
                "requested_latitude": station["latitude"],
                "requested_longitude": station["longitude"],
                "forecast_model": config.get("forecast", {}).get("model", "ecmwf_ifs025"),
                "cached_source_ids": [source["source_id"] for source in cached_forecast_sources],
            },
            "source_hashes": {
                "source_manifest_sha256": manifest_hash,
                "samples_sha256": sample_hash,
                "quarantine_sha256": quarantine_hash,
                "predictions_sha256": None,
                **{str(source["source_id"]): source.get("sha256") for source in sources},
            },
            "files": {
                "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
                "samples": str(sample_path.relative_to(root)).replace("\\", "/"),
                "quarantine": str(quarantine_path.relative_to(root)).replace("\\", "/"),
                "predictions": None,
            },
            "selection_policy": "宁波结果不用于选择站点、模型、C 或方法；因 SSOD 无完整日量，未运行迁移指标。",
            "limitations": [
                "宁波机场源本身可访问，但 362 行 total_precipitation 均为 -9999.9 且测量码为 I，无法证明 2025 年降水为零。",
                "没有替换为其他站点，也没有把缺失观测强行配对或继续计算 Brier。",
                "若目录中保留了预先缓存的 Open-Meteo 文件，它们仅作为调用证据，未参与任何宁波样本或指标。",
                "这是数据可行性阻塞证据，不是杭州模型在宁波的效果结论。",
            ],
        }

    forecast_frame, forecast_source = load_previous_year(output_root, year, station["latitude"], station["longitude"], model=str(config.get("forecast", {}).get("model", "ecmwf_ifs025")))
    samples, forecast_quarantine = build_sample_rows(observations, {year: forecast_frame}, {year: forecast_source}, manifest_id)
    samples_frame = pd.DataFrame(samples)
    if samples_frame.empty:
        raise ExternalValidationError("宁波 SSOD 完整候选没有任何可配对的预报窗口。")
    if samples_frame["sample_id"].duplicated().any():
        raise ExternalValidationError("宁波外部样本 sample_id 重复。")

    data_dir = output_root / "data"
    sample_path = data_dir / "samples.csv"
    quarantine_path = data_dir / "quarantined_records.csv"
    samples_frame.to_csv(sample_path, index=False, encoding="utf-8-sig")
    quarantine_rows = ssod_quarantine + forecast_quarantine
    quarantine_hash = _write_rows(quarantine_path, quarantine_rows)
    sample_hash = _sha256(sample_path)

    model_versions = run.get("model_versions", {})
    if not all(method in model_versions for method in METHODS):
        raise ExternalValidationError("杭州冻结 run 缺少三种迁移方法版本。")
    probabilities = {
        "training_climatology": np.full(len(samples_frame), float(hz_params["methods"]["training_climatology"]["event_rate"]), dtype=float),
        "raw_nwp_rule": (samples_frame["forecast_rain_mm"].to_numpy(dtype=float) >= float(hz_params["methods"]["raw_nwp_rule"]["threshold_mm"])).astype(float),
    }
    rain_parameters = hz_params.get("logistic_models", {}).get("logistic_rain")
    if not isinstance(rain_parameters, dict):
        raise ExternalValidationError("杭州冻结参数缺少 logistic_rain。")
    probabilities["logistic_rain"] = rebuild_logistic(build_features(samples_frame, rain_parameters), rain_parameters)

    prediction_rows: list[dict[str, Any]] = []
    for index, sample in samples_frame.iterrows():
        for method in METHODS:
            prediction_rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "station_id": sample["station_id"],
                    "window_start_utc": sample["window_start_utc"],
                    "window_end_utc": sample["window_end_utc"],
                    "observed_rain_mm": float(sample["observed_rain_mm"]),
                    "forecast_rain_mm": float(sample["forecast_rain_mm"]),
                    "method": method,
                    "probability": float(np.clip(probabilities[method][index], 0.0, 1.0)),
                    "frozen_HZ_model_version": model_versions[method],
                }
            )
    predictions_frame = pd.DataFrame(prediction_rows)
    prediction_path = output_root / "predictions.csv"
    predictions_frame.to_csv(prediction_path, index=False, encoding="utf-8-sig")
    prediction_hash = _sha256(prediction_path)

    actual = (samples_frame["observed_rain_mm"].to_numpy(dtype=float) >= threshold).astype(int)
    method_metrics = OrderedDict((method, _metrics(actual, probabilities[method])) for method in METHODS)
    bootstrap = [
        _week_bootstrap(samples_frame["window_start_utc"], actual, probabilities["logistic_rain"], probabilities[baseline], baseline, BOOTSTRAP_SEED, BOOTSTRAP_REPLICATES)
        for baseline in ["training_climatology", "raw_nwp_rule"]
    ]

    sources: list[dict[str, Any]] = [
        {
            "source_id": "ghcnh_station_evidence",
            "title": "GHCN hourly station list exact Ningbo LISHE line",
            "url": station["source_url"],
            "path": station["evidence_path"],
            "sha256": station["evidence_sha256"],
            "licence": "NOAA/NCEI public station metadata",
            "role": "official station ID and coordinates evidence",
            "source_full_file_sha256": station["source_sha256"],
        },
        ssod_prefix_source,
        ssod_source,
        {
            "source_id": forecast_source["source_id"],
            "title": forecast_source["title"],
            "url": forecast_source["url"],
            "path": forecast_source["local_path"],
            "sha256": forecast_source["sha256"],
            "licence": forecast_source.get("licence", "CC BY 4.0；免费接口仅限非商业用途"),
            "role": "Open-Meteo fixed-lead composite forecast",
            "requested_latitude": forecast_source.get("requested_latitude"),
            "requested_longitude": forecast_source.get("requested_longitude"),
            "returned_latitude": forecast_source.get("returned_latitude"),
            "returned_longitude": forecast_source.get("returned_longitude"),
            "forecast_model": forecast_source.get("forecast_model"),
        },
    ]
    sources.extend(frozen_sources)
    source_manifest = {
        "manifest_version": "external-ningbo-v1",
        "generated_at_utc": _utc_now(),
        "station": station,
        "sources": sources,
        "ssod_rule": "D/F/G/24 complete report layer; H/I and A/B/C/E and unknown codes quarantined; nominal UTC day.",
        "forecast_rule": "Open-Meteo precipitation sum over (window_start, window_end] 24 hourly values; missing hours are quarantined.",
    }
    manifest_path = data_dir / "source_manifest.json"
    _json_dump(manifest_path, source_manifest)
    manifest_hash = _sha256(manifest_path)

    candidate_frame = pd.DataFrame(observations)
    report = {
        "status": "completed",
        "result_kind": "cross_station_transfer_exploration",
        "generated_at_utc": _utc_now(),
        "station": {
            "station_id": station_id,
            "station_name": station["station_name"],
            "latitude": station["latitude"],
            "longitude": station["longitude"],
            "elevation_m": station["elevation_m"],
            "station_evidence_line": station["line"],
            "coordinate_consistency": "SSOD complete rows match the official GHCNh station list coordinates exactly within 1e-6.",
        },
        "scope": {
            "year": year,
            "source_row_date_range": ssod_row_date_range,
            "candidate_date_range": _date_range(candidate_frame),
            "paired_date_range": _date_range(samples_frame),
            "forecast_model": forecast_source.get("forecast_model"),
            "experiment_kind": "offline_fixed_lead transfer; no fit or tuning",
        },
        "ssod_access": {
            "prefix_url": ssod_prefix_source["url"],
            "download_url": ssod_source["url"],
            "expected_key": ssod_prefix_source["expected_key"],
            "prefix_sha256": ssod_prefix_source["sha256"],
            "csv_sha256": ssod_source["sha256"],
            "csv_rows": int(csv_rows),
        },
        "counts": {
            "ssod_csv_rows": int(csv_rows),
            "complete_candidate_days": int(len(observations)),
            "ssod_quarantine_rows": int(len(ssod_quarantine)),
            "paired_windows": int(len(samples_frame)),
            "forecast_quarantine_rows": int(len(forecast_quarantine)),
            "event_threshold_mm": threshold,
            "event_count": int(actual.sum()),
        },
        "methods": method_metrics,
        "paired_brier_bootstrap": bootstrap,
        "frozen_hangzhou": {
            "dataset_version": run.get("dataset_version"),
            "selected_method": run.get("selected_method"),
            "model_versions": model_versions,
            "model_parameters_sha256": _sha256(root / str(config["frozen_hangzhou"]["model_parameters_path"])),
            "evaluation_sha256": _sha256(root / str(config["frozen_hangzhou"]["evaluation_path"])),
        },
        "forecast_call": {
            "url": forecast_source.get("url"),
            "source_id": forecast_source.get("source_id"),
            "requested_latitude": forecast_source.get("requested_latitude"),
            "requested_longitude": forecast_source.get("requested_longitude"),
            "returned_latitude": forecast_source.get("returned_latitude"),
            "returned_longitude": forecast_source.get("returned_longitude"),
            "forecast_model": forecast_source.get("forecast_model"),
            "time_semantics": forecast_source.get("time_semantics"),
        },
        "source_hashes": {
            "source_manifest_sha256": manifest_hash,
            "samples_sha256": sample_hash,
            "quarantine_sha256": quarantine_hash,
            "predictions_sha256": prediction_hash,
            **{str(source["source_id"]): source.get("sha256") for source in sources},
        },
        "files": {
            "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
            "samples": str(sample_path.relative_to(root)).replace("\\", "/"),
            "quarantine": str(quarantine_path.relative_to(root)).replace("\\", "/"),
            "predictions": str(prediction_path.relative_to(root)).replace("\\", "/"),
        },
        "selection_policy": "宁波结果不用于选择站点、模型、C 或方法；固定复用杭州推荐 logistic_rain、杭州训练事件率和 raw_nwp_rule 三种方法。",
        "limitations": [
            "这是事后规划的跨站迁移探索，不是新的独立天气测试或真实运营回放。",
            "宁波 2025 与杭州 2025 测试天气可能相关，且两地 SSOD 都是名义 UTC 日参考观测，不能视为独立同分布验证。",
            "SSOD 低报和完整报告码筛选会影响事件覆盖；H/I、A/B/C/E 和未知码被隔离，不补零。",
            "Open-Meteo Previous Runs 是 fixed_lead_composite，固定提前量随有效时刻变化；结果不能声称单一初始化时刻可用。",
            "Brier 和成本含义仅用于迁移探索，未改变杭州主模型选择或页面正式结论。",
        ],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="宁波机场固定杭州模型跨站迁移探索")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    report_path = args.root / "reports" / "external_validation.json"
    try:
        report = run_external_validation(args.root, args.config)
    except (ExternalValidationError, OSError, ValueError, KeyError) as exc:
        report = {
            "status": "blocked",
            "generated_at_utc": _utc_now(),
            "error": str(exc),
            "limitations": ["宁波机场源或冻结迁移输入不可用，未把阻塞状态解释为模型效果。"],
        }
        _json_dump(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    _json_dump(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "completed" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
