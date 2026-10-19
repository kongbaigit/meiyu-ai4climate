"""审计并构建《梅雨有数》的公开数据样本包。

该模块只消费已经缓存的 NOAA/NCEI 文件和 Open-Meteo Previous Runs。它把
``SSOD`` 的同站逐日汇总作为名义 UTC 日的参考观测，并将不完整或语义不
确定的记录保留在隔离表中。只有预报逐小时覆盖完整时，才会写入离线样本。
这里不把任何缺失值补成 0，也不把 SSOD 参考量描述成高精度国家站真值。
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .contracts import SAMPLE_COLUMNS, validate_samples


DATASET_VERSION = "meiyu-audit-v1"
AUDIT_VERSION = "meiyu-audit-v1"
UTC = timezone.utc

# These code meanings were transcribed from the cached NOAA ISD format PDF.
ISD_CONDITION_CODES = {
    "1": "measurement_impossible_or_inaccurate",
    "2": "trace",
    "3": "begin_accumulated_period",
    "4": "end_accumulated_period",
    "5": "begin_deleted_period",
    "6": "end_deleted_period",
    "7": "begin_missing_period",
    "8": "end_missing_period",
    "E": "estimated",
    "I": "incomplete_missing_reports",
    "J": "incomplete_erroneous_reports",
    "9": "missing",
}
ISD_QUALITY_CODES = {
    "0": "passed_gross_limits",
    "1": "passed_all_qc",
    "2": "suspect",
    "3": "erroneous",
    "4": "passed_gross_limits_ncei",
    "5": "passed_all_qc_ncei",
    "6": "suspect_ncei",
    "7": "erroneous_ncei",
    "9": "passed_gross_if_present",
    "A": "suspect_accepted_good",
    "I": "inserted",
    "M": "manual_change",
    "P": "replaced_by_validator",
    "R": "software_computed",
    "U": "edited_replacement",
}
ISD_PASS_QUALITY = {"0", "1", "4", "5", "9"}
SSOD_COMPLETE_CODES = {"D", "F", "G", "24"}
SSOD_PARTIAL_CODES = {"A", "B", "C", "E"}
SSOD_H_OCCURRENCE_CODES = {"H"}
SSOD_I_NO_RECORD_CODES = {"I"}
SSOD_OCCURRENCE_CODES = SSOD_H_OCCURRENCE_CODES | SSOD_I_NO_RECORD_CODES
SSOD_H_REASON = "precipitation_occurrence_without_total"
SSOD_I_REASON = "no_precipitation_data_or_occurrence_record"

OBSERVATION_COLUMNS = [
    "obs_record_id",
    "source_id",
    "source_dataset",
    "station_id",
    "station_name",
    "station_lat",
    "station_lon",
    "window_start_utc",
    "window_end_utc",
    "observed_rain_mm",
    "measurement_code",
    "source_flag",
    "reference_only",
    "quality_status",
    "window_basis",
    "boundary_status",
    "source_manifest_id",
]
QUARANTINE_COLUMNS = [
    "record_id",
    "source_id",
    "source_dataset",
    "station_id",
    "station_name",
    "record_timestamp_utc",
    "window_start_utc",
    "window_end_utc",
    "period_hours",
    "depth_raw",
    "depth_mm",
    "condition_code",
    "quality_code",
    "measurement_code",
    "observed_rain_mm",
    "reason",
    "details",
    "source_manifest_id",
]


@dataclass(frozen=True)
class ISDGroup:
    """A parsed AA1-AA4 group with conservative interpretation."""

    group_name: str
    group_index: int
    period_hours: int | None
    depth_raw: int | None
    depth_mm: float | None
    condition_code: str
    quality_code: str
    candidate_window: bool
    exact_measurable: bool
    observed_rain_mm: float | None
    reasons: tuple[str, ...]


def _now_utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _iso_z(value: datetime | pd.Timestamp) -> str:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat().replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"dataset_version": DATASET_VERSION, "sources": _default_sources()}
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError("data_sources.yaml 顶层必须是映射。")
        return loaded
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("读取 data_sources.yaml 需要 .venv 中的 PyYAML。") from exc


def _default_sources() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "isd_58457099999_2024",
            "title": "NOAA Global Hourly · Xiaoshan ISD 2024",
            "path": "data/raw/58457099999_2024.csv",
            "url": "https://noaa-global-hourly-pds.s3.amazonaws.com/2024/58457099999.csv",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "ISD AA1-AA4 diagnostic",
            "year": 2024,
            "station_id": "58457099999",
        },
        {
            "source_id": "isd_58457099999_2025",
            "title": "NOAA Global Hourly · Xiaoshan ISD 2025",
            "path": "data/raw/58457099999_2025.csv",
            "url": "https://noaa-global-hourly-pds.s3.amazonaws.com/2025/58457099999.csv",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "ISD AA1-AA4 diagnostic",
            "year": 2025,
            "station_id": "58457099999",
        },
        {
            "source_id": "ghcn_prcp_CHM00058457",
            "title": "GHCN-Daily CHM00058457 PRCP reference",
            "path": "data/raw/CHM00058457.dly",
            "url": "https://www.ncei.noaa.gov/pub/data/ghcn/daily/all/CHM00058457.dly",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "daily reference only",
            "station_id": "CHM00058457",
        },
        {
            "source_id": "ghcn_station_metadata_CHM00058457",
            "title": "GHCN-Daily station metadata excerpt · CHM00058457",
            "path": "data/raw/CHM00058457_ghcn_station_metadata.txt",
            "url": "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "station coordinates used for reference table",
            "station_id": "CHM00058457",
        },
        {
            "source_id": "ghcnh_station_list",
            "title": "GHCN hourly station list",
            "path": "data/raw/ghcnh-station-list.txt",
            "url": "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh-station-list.txt",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "station identity research evidence",
        },
        {
            "source_id": "isd_history",
            "title": "NOAA ISD station history excerpt · 58457099999",
            "path": "data/raw/58457099999_isd_history.csv",
            "url": "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "station identity research evidence",
        },
        {
            "source_id": "ssod_CHI0000ZSHC_2024",
            "title": "NOAA SSODv2 · Xiaoshan 2024",
            "path": "data/raw/SSOD_CHI0000ZSHC_2024.csv",
            "url": "https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/access/by-year/2024/csv/SSOD_CHI0000ZSHC_2024.csv",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "same-station daily reference",
            "year": 2024,
            "station_id": "CHI0000ZSHC",
        },
        {
            "source_id": "ssod_CHI0000ZSHC_2025",
            "title": "NOAA SSODv2 · Xiaoshan 2025",
            "path": "data/raw/SSOD_CHI0000ZSHC_2025.csv",
            "url": "https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/access/by-year/2025/csv/SSOD_CHI0000ZSHC_2025.csv",
            "licence": "NOAA/NCEI public data; upstream terms should be retained",
            "role": "same-station daily reference",
            "year": 2025,
            "station_id": "CHI0000ZSHC",
        },
        {
            "source_id": "isd_format_document",
            "title": "NOAA ISD format document",
            "path": "data/raw/noaa_isd_format_document.pdf",
            "url": "https://noaaisd.blob.core.windows.net/noaa-isd/pub/data/noaa/isd-format-document.pdf",
            "licence": "NOAA/NCEI documentation",
            "role": "field-code documentation",
        },
        {
            "source_id": "ssodv2_documentation",
            "title": "NOAA SSODv2 documentation",
            "path": "data/raw/ssodv2_DOCUMENTATION.pdf",
            "url": "https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/doc/ssodv2_DOCUMENTATION.pdf",
            "licence": "NOAA/NCEI documentation",
            "role": "SSOD field-code documentation",
        },
    ]


def _load_research_manifest(root: Path) -> dict[str, Any]:
    path = root / "research" / "download_manifest.json"
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _source_specs(root: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [dict(item) for item in config.get("sources", _default_sources())]
    # Forecast loader writes a small metadata sidecar beside each JSON. Include
    # those records automatically so the resulting source manifest is complete.
    raw_dir = root / "data" / "raw"
    seen = {str(item.get("source_id")) for item in specs}
    for metadata_path in sorted(raw_dir.glob("openmeteo_*.metadata.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_id = str(metadata.get("source_id", metadata_path.stem.replace(".metadata", "")))
        if source_id in seen:
            continue
        raw_name = metadata_path.name.removesuffix(".metadata.json") + ".json"
        item = dict(metadata)
        item.update(
            source_id=source_id,
            path=f"data/raw/{raw_name}",
            role="fixed-lead forecast input",
        )
        specs.append(item)
        seen.add(source_id)
    return specs


def build_source_manifest(root: Path, config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Hash every configured/cached file and return manifest plus stable ID."""

    previous_path = root / "data" / "source_manifest.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else {}
    previous_sources = {item.get("source_id"): item for item in previous.get("sources", [])}
    research = _load_research_manifest(root)
    downloads = research.get("downloads", {}) if isinstance(research, dict) else {}
    by_url = {str(v.get("url")): v for v in downloads.values() if isinstance(v, dict) and v.get("url")}
    by_name = {
        Path(str(v.get("path", ""))).name: v
        for v in downloads.values()
        if isinstance(v, dict) and v.get("path")
    }
    sources: list[dict[str, Any]] = []
    for spec in _source_specs(root, config):
        entry = dict(spec)
        relative = str(spec.get("path", ""))
        path = Path(relative)
        if not path.is_absolute():
            path = root / path
        entry["local_path"] = str(path.relative_to(root)).replace("\\", "/") if path.exists() else relative.replace("\\", "/")
        entry["bytes"] = path.stat().st_size if path.exists() else None
        entry["sha256"] = _hash_file(path) if path.exists() else None
        preserved = previous_sources.get(spec.get("source_id"), {})
        prior = by_url.get(str(spec.get("url"))) or by_name.get(path.name)
        if preserved.get("url") == spec.get("url") and preserved.get("sha256") == entry["sha256"] and preserved.get("retrieved_at_utc"):
            entry["retrieved_at_utc"] = preserved["retrieved_at_utc"]
        elif prior:
            entry["retrieved_at_utc"] = prior.get("download_utc")
        elif entry.get("retrieved_at_utc"):
            pass
        elif path.exists():
            entry["retrieved_at_utc"] = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat().replace("+00:00", "Z")
        else:
            entry["retrieved_at_utc"] = None
        entry["status"] = "available" if path.exists() else "not_cached"
        entry.setdefault("licence", "未在本地单独核验；见来源 URL")
        sources.append(entry)
    stable_fields = [
        {key: value for key, value in item.items() if key not in {"retrieved_at_utc", "bytes", "status", "local_path"}}
        | {"local_path": item.get("local_path"), "sha256": item.get("sha256")}
        for item in sources
    ]
    stable_blob = json.dumps(stable_fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    manifest_id = "sm-" + hashlib.sha256(stable_blob).hexdigest()[:16]
    generated = previous.get("generated_utc") if previous.get("manifest_id") == manifest_id and previous.get("sources") == sources else _now_utc()
    manifest = {"manifest_id": manifest_id, "generated_utc": generated, "sources": sources}
    _json_dump(root / "data" / "source_manifest.json", manifest)
    return manifest, manifest_id


def parse_isd_group(raw: str | None, group_name: str = "AA1") -> list[ISDGroup]:
    """Parse AA1-AA4 without silently converting sentinels or trace to zero."""

    if raw is None or not str(raw).strip():
        return []
    parsed: list[ISDGroup] = []
    for index, token in enumerate(str(raw).split(";")):
        parts = [piece.strip() for piece in token.split(",")]
        if not token.strip():
            continue
        if len(parts) < 4:
            parsed.append(
                ISDGroup(group_name, index, None, None, None, "", "", False, False, None, ("malformed_group",))
            )
            continue
        period_raw, depth_raw_text, condition, quality = parts[:4]
        period_raw = period_raw.upper()
        condition = condition.upper()
        quality = quality.upper()
        reasons: list[str] = []
        try:
            period_hours = None if period_raw in {"", "99"} else int(period_raw)
        except ValueError:
            period_hours = None
            reasons.append("unknown_period_code")
        if period_raw == "99":
            reasons.append("missing_period_sentinel")
        try:
            depth_raw_value = None if depth_raw_text in {"", "9999"} else int(depth_raw_text)
        except ValueError:
            depth_raw_value = None
            reasons.append("unknown_depth_code")
        if depth_raw_text == "9999":
            reasons.append("missing_depth_sentinel")
        depth_mm = None if depth_raw_value is None else round(depth_raw_value / 10.0, 4)
        if condition not in ISD_CONDITION_CODES:
            reasons.append("unknown_condition_code")
        if quality not in ISD_QUALITY_CODES:
            reasons.append("unknown_quality_code")
        if period_hours != 24:
            reasons.append("non_24_hour_period")
        if condition == "2":
            reasons.append("trace_not_exact_zero")
        elif condition == "3":
            reasons.append("begin_accumulated_period")
        elif condition in {"5", "6", "7", "8", "9", "I", "J"}:
            reasons.append("incomplete_or_missing_condition")
        elif condition == "1":
            reasons.append("measurement_impossible_or_inaccurate")
        elif condition == "E":
            reasons.append("estimated_condition")
        if quality not in ISD_PASS_QUALITY:
            reasons.append("quality_not_accepted")
        candidate = (
            period_hours == 24
            and depth_mm is not None
            and condition in ISD_CONDITION_CODES
            and quality in ISD_QUALITY_CODES
        )
        exact = candidate and condition == "4" and quality in ISD_PASS_QUALITY
        observed = depth_mm if exact else None
        if candidate and not exact:
            reasons.append("not_complete_measurable_total")
        parsed.append(
            ISDGroup(
                group_name=group_name,
                group_index=index,
                period_hours=period_hours,
                depth_raw=depth_raw_value,
                depth_mm=depth_mm,
                condition_code=condition,
                quality_code=quality,
                candidate_window=candidate,
                exact_measurable=exact,
                observed_rain_mm=observed,
                reasons=tuple(dict.fromkeys(reasons)),
            )
        )
    return parsed


def _station_metadata(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if path.exists():
        line = next((item.strip("\n") for item in path.read_text(encoding="utf-8", errors="replace").splitlines() if item.strip()), "")
        try:
            return {
                "station_id": line[:11].strip() or fallback.get("station_id"),
                "station_lat": float(line[12:20]),
                "station_lon": float(line[21:30]),
                "station_name": line[41:71].strip() or "HANGZHOU",
            }
        except (ValueError, IndexError):
            pass
    return dict(
        station_id=fallback.get("station_id", "CHM00058457"),
        station_lat=30.2330,
        station_lon=120.1670,
        station_name="HANGZHOU",
    )


def parse_ghcn_prcp(
    path: Path,
    years: Iterable[int] = (2024, 2025),
    source_id: str = "ghcn_prcp_CHM00058457",
    manifest_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse GHCN .dly PRCP cells as reference-only nominal UTC dates."""

    if not path.exists():
        return []
    metadata = metadata or {}
    allowed = {int(year) for year in years}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        if len(line) < 29 or line[17:21] != "PRCP":
            continue
        station_id = line[:11].strip()
        try:
            year, month = int(line[11:15]), int(line[15:17])
        except ValueError:
            continue
        if year not in allowed:
            continue
        for day in range(1, 32):
            start = 21 + (day - 1) * 8
            cell = line[start : start + 8]
            if len(cell) < 8:
                continue
            try:
                date = datetime(year, month, day, tzinfo=UTC)
            except ValueError:
                continue
            try:
                raw_value = int(cell[:5])
            except ValueError:
                continue
            if raw_value == -9999:
                continue
            end = date + timedelta(days=1)
            source_flag = cell[7].strip()
            rows.append(
                {
                    "obs_record_id": f"ghcn-{station_id}-{date:%Y%m%d}",
                    "source_id": source_id,
                    "source_dataset": "GHCN-Daily",
                    "station_id": station_id,
                    "station_name": metadata.get("station_name", "HANGZHOU"),
                    "station_lat": metadata.get("station_lat", 30.2330),
                    "station_lon": metadata.get("station_lon", 120.1670),
                    "window_start_utc": _iso_z(date),
                    "window_end_utc": _iso_z(end),
                    "observed_rain_mm": round(raw_value / 10.0, 4),
                    "measurement_code": "",
                    "source_flag": source_flag,
                    "reference_only": True,
                    "quality_status": "reference_only",
                    "window_basis": "nominal_date_only",
                    "boundary_status": "unverified",
                    "source_manifest_id": manifest_id,
                }
            )
    return rows


def parse_ssod_row(
    row: dict[str, Any],
    source_id: str,
    manifest_id: str,
    expected_station: str | None = None,
    expected_year: int | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return a complete SSOD observation or an explicit quarantine record."""

    record_id = f"ssod-{source_id}-{str(row.get('DATE', '')).replace('-', '')}"
    raw_date = str(row.get("DATE", "")).strip()
    date = None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date):
        try:
            date = pd.Timestamp(raw_date, tz="UTC")
        except (TypeError, ValueError):
            date = None
    code = str(row.get("total_precipitation_Measurement_Code", "") or "").strip().upper()
    try:
        amount = float(row.get("total_precipitation", ""))
    except (TypeError, ValueError):
        amount = None
    reason: list[str] = []
    if date is None:
        reason.append("invalid_date")
    if amount is None or not math.isfinite(amount):
        reason.append("invalid_precipitation_value")
    elif amount <= -9990:
        reason.append("missing_precipitation_sentinel")
    elif amount < 0:
        reason.append("negative_precipitation_value")
    if code in SSOD_PARTIAL_CODES:
        reason.append("partial_measurement_code")
    elif code in SSOD_H_OCCURRENCE_CODES:
        reason.append(SSOD_H_REASON)
    elif code in SSOD_I_NO_RECORD_CODES:
        reason.append(SSOD_I_REASON)
    elif code not in SSOD_COMPLETE_CODES:
        reason.append("unknown_measurement_code")
    station_id = str(row.get("STATION", "") or "").strip()
    station_name = str(row.get("Station_name", "XIAOSHAN"))
    if expected_station and station_id != str(expected_station):
        reason.append("station_id_mismatch")
    if expected_year is not None and (date is None or int(date.year) != int(expected_year)):
        reason.append("year_mismatch")
    lat = row.get("LATITUDE", "")
    lon = row.get("LONGITUDE", "")
    coord_valid = True
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        coord_valid = False
        lat, lon = None, None
    if coord_valid and (not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90) or not (-180 <= lon <= 180)):
        coord_valid = False
        reason.append("invalid_coordinate")
    elif not coord_valid:
        reason.append("invalid_coordinate")
    complete = (
        date is not None
        and amount is not None
        and math.isfinite(amount)
        and 0 <= amount < 9990
        and code in SSOD_COMPLETE_CODES
        and coord_valid
    )
    complete = complete and not any(
        marker in reason for marker in ("invalid_date", "invalid_precipitation_value", "negative_precipitation_value", "station_id_mismatch", "year_mismatch", "invalid_coordinate")
    )
    if complete:
        end = date + pd.Timedelta(days=1)
        return (
            {
                "obs_record_id": record_id,
                "source_id": source_id,
                "source_dataset": "SSODv2",
                "station_id": station_id,
                "station_name": station_name,
                "station_lat": lat,
                "station_lon": lon,
                "window_start_utc": _iso_z(date),
                "window_end_utc": _iso_z(end),
                "observed_rain_mm": round(amount, 4),
                "measurement_code": code,
                "source_flag": "",
                "reference_only": True,
                "quality_status": "complete_reference",
                "window_basis": "nominal_utc_synoptic_day",
                "boundary_status": "documented_00_24_utc",
                "source_manifest_id": manifest_id,
            },
            None,
        )
    if code in SSOD_H_OCCURRENCE_CODES:
        details = "SSOD H 表示存在降水发生记录，但总量为零或无法计算；仍隔离，不作为完整日量。"
    elif code in SSOD_I_NO_RECORD_CODES:
        details = "SSOD I 表示未报告降水数据及发生记录；仍隔离，不作为完整日量。"
    else:
        details = "SSOD 仅保留 D/F/G/数值24 完整报告层；其他测量码与缺测进入隔离表。"
    quarantine = {
        "record_id": record_id,
        "source_id": source_id,
        "source_dataset": "SSODv2",
        "station_id": station_id,
        "station_name": station_name,
        "record_timestamp_utc": _iso_z(date) if date is not None else raw_date,
        "window_start_utc": _iso_z(date) if date is not None else "",
        "window_end_utc": _iso_z(date + pd.Timedelta(days=1)) if date is not None else "",
        "period_hours": 24,
        "depth_raw": amount,
        "depth_mm": amount,
        "condition_code": "",
        "quality_code": "",
        "measurement_code": code,
        "observed_rain_mm": None,
        "reason": ";".join(dict.fromkeys(reason)) or "not_complete_reference",
        "details": details,
        "source_manifest_id": manifest_id,
    }
    return None, quarantine


def parse_ssod_files(specs: list[dict[str, Any]], manifest_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observations: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for spec in specs:
        path = Path(str(spec.get("local_path", spec.get("path", ""))))
        if not path.is_absolute():
            # local_path is resolved by _resolved_spec_paths before this function.
            path = Path(spec.get("_resolved_path", path))
        if not path.exists() or not str(spec.get("source_id", "")).startswith("ssod_"):
            continue
        seen_windows: set[tuple[str, str]] = set()
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    observation, quarantine = parse_ssod_row(
                        row,
                        str(spec["source_id"]),
                        manifest_id,
                        expected_station=str(spec.get("station_id", "")) or None,
                        expected_year=int(spec["year"]) if spec.get("year") is not None else None,
                    )
                    if observation:
                        key = (observation["station_id"], observation["window_start_utc"])
                        if key in seen_windows:
                            observation = None
                            quarantine = {
                                "record_id": f"{spec['source_id']}:duplicate:{row.get('DATE', '')}",
                                "source_id": spec["source_id"],
                                "source_dataset": "SSODv2",
                                "station_id": row.get("STATION", ""),
                                "station_name": row.get("Station_name", "XIAOSHAN"),
                                "record_timestamp_utc": str(row.get("DATE", "")),
                                "window_start_utc": str(row.get("DATE", "")),
                                "window_end_utc": "",
                                "period_hours": 24,
                                "depth_raw": row.get("total_precipitation"),
                                "depth_mm": row.get("total_precipitation"),
                                "condition_code": "",
                                "quality_code": "",
                                "measurement_code": row.get("total_precipitation_Measurement_Code", ""),
                                "observed_rain_mm": None,
                                "reason": "duplicate_nominal_day",
                                "details": "同一文件同一站点同一名义UTC日出现重复行。",
                                "source_manifest_id": manifest_id,
                            }
                        else:
                            seen_windows.add(key)
                    if observation:
                        observations.append(observation)
                    if quarantine:
                        quarantined.append(quarantine)
        except (OSError, csv.Error) as exc:
            quarantined.append(
                {
                    "record_id": f"{spec['source_id']}:file",
                    "source_id": spec["source_id"],
                    "source_dataset": "SSODv2",
                    "station_id": spec.get("station_id", "CHI0000ZSHC"),
                    "station_name": "XIAOSHAN",
                    "record_timestamp_utc": "",
                    "window_start_utc": "",
                    "window_end_utc": "",
                    "period_hours": None,
                    "depth_raw": None,
                    "depth_mm": None,
                    "condition_code": "",
                    "quality_code": "",
                    "measurement_code": "",
                    "observed_rain_mm": None,
                    "reason": "file_parse_error",
                    "details": str(exc),
                    "source_manifest_id": manifest_id,
                }
            )
    return observations, quarantined


def parse_isd_files(specs: list[dict[str, Any]], manifest_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    for spec in specs:
        path = Path(str(spec.get("_resolved_path", spec.get("path", ""))))
        if not path.exists() or not str(spec.get("source_id", "")).startswith("isd_"):
            continue
        try:
            # NOAA Global Hourly may contain non-UTF-8 station text in the
            # NAME/REM fields.  AA1-AA4 are ASCII; latin-1 preserves every
            # byte and avoids dropping a precipitation group on a name decode.
            with path.open("r", encoding="latin-1", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    timestamp = pd.to_datetime(row.get("DATE", ""), utc=True, errors="coerce")
                    if pd.isna(timestamp):
                        continue
                    for group_name in ("AA1", "AA2", "AA3", "AA4"):
                        for group in parse_isd_group(row.get(group_name), group_name):
                            end = timestamp
                            start = end - pd.Timedelta(hours=group.period_hours) if group.period_hours is not None else pd.NaT
                            record_id = f"isd-{spec.get('year', timestamp.year)}-{timestamp:%Y%m%dT%H%M}-{group_name}-{group.group_index}"
                            record = {
                                "record_id": record_id,
                                "source_id": spec["source_id"],
                                "source_dataset": "NOAA-ISD",
                                "station_id": spec.get("station_id", "58457099999"),
                                "station_name": "XIAOSHAN",
                                "record_timestamp_utc": _iso_z(end),
                                "window_start_utc": _iso_z(start) if not pd.isna(start) else "",
                                "window_end_utc": _iso_z(end),
                                "period_hours": group.period_hours,
                                "depth_raw": group.depth_raw,
                                "depth_mm": group.depth_mm,
                                "condition_code": group.condition_code,
                                "quality_code": group.quality_code,
                                "measurement_code": "",
                                "observed_rain_mm": group.observed_rain_mm,
                                "reason": ";".join(group.reasons) or "candidate_not_paired",
                                "details": "ISD AA1-AA4；24小时候选须同时有完整结束条件和可接受质量码；trace 不等于精确0mm。",
                                "source_manifest_id": manifest_id,
                                "candidate_window": group.candidate_window,
                            }
                            records.append(record)
                            # Keep every 24-hour candidate and any unknown/sentinel
                            # record auditable; shorter periods remain diagnostic only.
                            if group.period_hours == 24 or any("unknown_" in reason for reason in group.reasons):
                                quarantined.append(record.copy())
        except (OSError, csv.Error) as exc:
            quarantined.append(
                {
                    "record_id": f"{spec['source_id']}:file",
                    "source_id": spec["source_id"],
                    "source_dataset": "NOAA-ISD",
                    "station_id": spec.get("station_id", "58457099999"),
                    "station_name": "XIAOSHAN",
                    "record_timestamp_utc": "",
                    "window_start_utc": "",
                    "window_end_utc": "",
                    "period_hours": None,
                    "depth_raw": None,
                    "depth_mm": None,
                    "condition_code": "",
                    "quality_code": "",
                    "measurement_code": "",
                    "observed_rain_mm": None,
                    "reason": "file_parse_error",
                    "details": str(exc),
                    "source_manifest_id": manifest_id,
                }
            )
    return records, quarantined


def _resolved_specs(root: Path, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resolved = []
    for item in specs:
        spec = dict(item)
        path = Path(str(item.get("path", "")))
        spec["_resolved_path"] = str(path if path.is_absolute() else root / path)
        resolved.append(spec)
    return resolved


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")
    return frame


def _write_empty_samples(root: Path) -> pd.DataFrame:
    frame = pd.DataFrame(columns=SAMPLE_COLUMNS)
    frame.to_csv(root / "data" / "samples.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    try:
        frame.to_parquet(root / "data" / "samples.parquet", index=False)
    except (ImportError, ValueError) as exc:  # pragma: no cover - environment guard
        (root / "data" / "samples.parquet").write_bytes(b"")
        raise RuntimeError("写入 samples.parquet 需要 .venv 中的 parquet 引擎。") from exc
    return frame


def _write_samples(root: Path, rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=SAMPLE_COLUMNS)
    errors = validate_samples(frame)
    if errors:
        raise ValueError("样本协议校验失败：" + "；".join(errors))
    frame.to_csv(root / "data" / "samples.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    frame.to_parquet(root / "data" / "samples.parquet", index=False)
    return frame


def build_sample_rows(
    observations: list[dict[str, Any]],
    forecast_frames: dict[int, pd.DataFrame],
    forecast_sources: dict[int, dict[str, Any]],
    dataset_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pair only complete SSOD rows with complete forecast windows.

    ``aggregate_window`` deliberately raises on missing hours; this function
    quarantines that window and never substitutes 0 or interpolated values.
    """

    from .forecasts import aggregate_window

    samples: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen_observation_windows: set[tuple[str, str]] = set()
    for observation in observations:
        if observation.get("source_dataset") != "SSODv2":
            continue
        if observation.get("quality_status") != "complete_reference":
            continue
        observation_key = (str(observation.get("station_id", "")), str(observation.get("window_start_utc", "")))
        if observation_key in seen_observation_windows:
            continue
        seen_observation_windows.add(observation_key)
        year = int(str(observation["window_start_utc"])[:4])
        frame = forecast_frames.get(year)
        source_record = forecast_sources.get(year)
        if frame is None or source_record is None:
            quarantined.append(
                {
                    "record_id": observation["obs_record_id"],
                    "source_id": observation["source_id"],
                    "source_dataset": "SSODv2+Open-Meteo",
                    "station_id": observation["station_id"],
                    "station_name": observation["station_name"],
                    "record_timestamp_utc": observation["window_end_utc"],
                    "window_start_utc": observation["window_start_utc"],
                    "window_end_utc": observation["window_end_utc"],
                    "period_hours": 24,
                    "depth_raw": observation["observed_rain_mm"],
                    "depth_mm": observation["observed_rain_mm"],
                    "condition_code": "",
                    "quality_code": "",
                    "measurement_code": observation["measurement_code"],
                    "observed_rain_mm": observation["observed_rain_mm"],
                    "reason": "forecast_source_missing",
                    "details": "没有该年份的完整 Previous Runs 预报缓存。",
                    "source_manifest_id": observation.get("source_manifest_id", ""),
                }
            )
            continue
        try:
            forecast = aggregate_window(frame, observation["window_start_utc"], observation["window_end_utc"], source_record)
        except (ValueError, KeyError) as exc:
            quarantined.append(
                {
                    "record_id": observation["obs_record_id"],
                    "source_id": observation["source_id"],
                    "source_dataset": "SSODv2+Open-Meteo",
                    "station_id": observation["station_id"],
                    "station_name": observation["station_name"],
                    "record_timestamp_utc": observation["window_end_utc"],
                    "window_start_utc": observation["window_start_utc"],
                    "window_end_utc": observation["window_end_utc"],
                    "period_hours": 24,
                    "depth_raw": observation["observed_rain_mm"],
                    "depth_mm": observation["observed_rain_mm"],
                    "condition_code": "",
                    "quality_code": "",
                    "measurement_code": observation["measurement_code"],
                    "observed_rain_mm": observation["observed_rain_mm"],
                    "reason": "forecast_window_incomplete",
                    "details": str(exc),
                    "source_manifest_id": observation.get("source_manifest_id", ""),
                }
            )
            continue
        start = observation["window_start_utc"]
        end = observation["window_end_utc"]
        key = observation["obs_record_id"]
        forecast_spec_id = str(source_record["source_id"])
        samples.append(
            {
                "sample_id": f"sample-{key}-{forecast_spec_id}",
                "observation_window_id": f"window-{key}",
                "forecast_spec_id": forecast_spec_id,
                "station_id": observation["station_id"],
                "station_name": observation["station_name"],
                "station_lat": observation["station_lat"],
                "station_lon": observation["station_lon"],
                "window_start_utc": start,
                "window_end_utc": end,
                "observed_rain_mm": observation["observed_rain_mm"],
                "observation_measurement_code": observation["measurement_code"],
                "reference_kind": "ssod_derived_station",
                "window_basis": "nominal_utc_synoptic_day",
                "forecast_model": source_record.get("forecast_model", "ecmwf_ifs025"),
                "forecast_kind": "fixed_lead_composite",
                "run_init_utc": None,
                "available_at_utc": None,
                "availability_evidence": "Open-Meteo Previous Runs；固定提前量随有效时刻变化，非单一初始化时刻。",
                "decision_time_utc": None,
                "forecast_rain_mm": forecast["forecast_rain_mm"],
                "forecast_temperature_mean_c": forecast.get("forecast_temperature_mean_c"),
                "forecast_relative_humidity_mean_pct": forecast.get("forecast_relative_humidity_mean_pct"),
                "experiment_kind": "offline_fixed_lead",
                "quality_status": "passed",
                "audit_version": AUDIT_VERSION,
                "obs_record_id": observation["obs_record_id"],
                "forecast_record_id": forecast["forecast_record_id"],
                "source_manifest_id": observation.get("source_manifest_id", ""),
                "split": "unassigned",
            }
        )
    return samples, quarantined


def _canonical_version(root: Path) -> str:
    # The public dataset version follows the bytes users load into the main
    # table.  Source-manifest retrieval timestamps may change between runs;
    # they must not silently change the content version.
    path = root / "data" / "samples.csv"
    return "meiyu-" + hashlib.sha256(path.read_bytes() if path.exists() else b"").hexdigest()[:16]


def _candidate_observation_keys(observations: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("station_id", "")), str(row.get("window_start_utc", "")))
        for row in observations
        if row.get("source_dataset") == "SSODv2" and row.get("quality_status") == "complete_reference"
    }


def _monthly_counts(observations: list[dict[str, Any]], samples: pd.DataFrame) -> list[dict[str, Any]]:
    candidate_months = Counter()
    for station_id, window_start in _candidate_observation_keys(observations):
        candidate_months[window_start[:7]] += 1
    paired_keys = set()
    for _, row in samples.iterrows():
        paired_keys.add((str(row.get("station_id", "")), str(row.get("window_start_utc", ""))))
    paired_months = Counter(window_start[:7] for _, window_start in paired_keys)
    months = sorted(set(candidate_months) | set(paired_months))
    expected = {}
    for year in (2024, 2025):
        for month in range(1, 13):
            first = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
            last = first + pd.offsets.MonthEnd(1)
            expected[first.strftime("%Y-%m")] = int(last.day)
    months = sorted(set(months) | set(expected))
    return [
        {
            "month": month,
            "configured_nominal_days": int(expected.get(month, 0)),
            "candidate_windows": int(candidate_months[month]),
            "missing_candidate_windows": int(max(expected.get(month, 0) - candidate_months[month], 0)),
            "paired_windows": int(paired_months[month]),
        }
        for month in months
    ]


def _ssod_quarantine_summary(quarantined: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Summarize SSOD quarantine codes and reasons without counting ISD rows."""

    rows = [row for row in quarantined if row.get("source_dataset") == "SSODv2"]
    code_counts = Counter(str(row.get("measurement_code", "") or "") for row in rows)
    reason_counts = Counter(
        reason
        for row in rows
        for reason in str(row.get("reason", "") or "").split(";")
        if reason
    )
    return {
        "measurement_code_counts": dict(sorted(code_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
    }


def _findings(
    observations: list[dict[str, Any]],
    isd_records: list[dict[str, Any]],
    quarantined: list[dict[str, Any]],
    sample_count: int,
    forecast_error: str | None,
) -> list[dict[str, Any]]:
    ssod_complete = len(_candidate_observation_keys(observations))
    ssod_quarantine = sum(row.get("source_dataset") == "SSODv2" for row in quarantined)
    ssod_quarantine_codes = Counter(
        str(row.get("measurement_code", "") or "")
        for row in quarantined
        if row.get("source_dataset") == "SSODv2"
    )
    condition_counts = Counter(row.get("condition_code", "") for row in isd_records if row.get("period_hours") == 24)
    findings = [
        {
            "title": "SSOD 同站完整报告只能作为参考观测",
            "severity": "high",
            "evidence": (
                f"CHI0000ZSHC/XIAOSHAN 有 {ssod_complete} 条 D/F/G/24 完整层；另有 {ssod_quarantine} 条隔离记录，"
                f"其中 H={ssod_quarantine_codes.get('H', 0)}（有发生记录但总量为零或无法计算），"
                f"I={ssod_quarantine_codes.get('I', 0)}（未报告降水数据及发生记录）。"
            ),
            "impact": "可做 offline_fixed_lead 回测，但不能宣称高精度国家站真值。",
            "remediation": "保留 reference_kind=ssod_derived_station，并在结果中披露低报和缺测风险。",
        },
        {
            "title": "ISD AA1-AA4 没有形成可信的完整24小时真值",
            "severity": "high",
            "evidence": f"24小时字段条件码计数为 {dict(condition_counts)}；condition=3/9 表示累计未结束或缺失，trace 不等于精确0mm。",
            "impact": "ISD 记录只能留在隔离审计表，不作为主表观测标签。",
            "remediation": "等待明确 condition=4 且质量码可接受的记录，再单独设计配对规则。",
        },
        {
            "title": "GHCN 日降水仍是跨站参考",
            "severity": "blocking",
            "evidence": "CHM00058457 是 Hangzhou（约30.2330,120.1670），SSOD/ISD 是 Xiaoshan（约30.2283,120.4317）；GHCN .dly 的 PRCP 单元没有逐条结束时刻。",
            "impact": "不把 GHCN PRCP 与机场 SSOD 合并成同一站点或精确日界。",
            "remediation": "如需跨源校验，单独标记 reference_only，并取得同址逐小时或明确日界资料。",
        },
    ]
    if forecast_error:
        findings.append(
            {
                "title": "预报输入未能完整取得",
                "severity": "blocking",
                "evidence": forecast_error,
                "impact": "samples.csv/parquet 必须保持表头或只含成功聚合的离线窗口。",
                "remediation": "缓存对应年份的完整 Previous Runs 响应后重新运行 build。",
            }
        )
    if sample_count:
        findings.append(
            {
                "title": "主表仅定义离线固定提前量实验",
                "severity": "medium",
                "evidence": f"成功配对 {sample_count} 个24小时窗口；forecast_kind=fixed_lead_composite。",
                "impact": "不能据此声称可在当时刻获得单一初始化的生产预报。",
                "remediation": "展示为可复现实验基线，另行补充真实发布时间证据才可做 operational_replay。",
            }
        )
    candidate_count = len(_candidate_observation_keys(observations))
    if sample_count < candidate_count:
        findings.append(
            {
                "title": "部分候选日缺少完整预报小时",
                "severity": "high",
                "evidence": f"SSOD 完整候选日 {candidate_count} 个，成功配对 {sample_count} 个；其余窗口进入 quarantined_records.csv。",
                "impact": "样本覆盖不等于完整日历覆盖，不能把缺失窗口当作无雨或负例。",
                "remediation": "只在获得完整逐小时 Previous Runs 后补建对应窗口，不补零。",
            }
        )
    if candidate_count < 731:
        findings.append(
            {
                "title": "SSOD 覆盖少于配置的731个名义日",
                "severity": "high",
                "evidence": f"2024—2025 配置范围为731个 UTC 名义日，SSOD 完整候选 {candidate_count} 个，缺 {731 - candidate_count} 个；缺日不作为无雨样本。",
                "impact": "月度覆盖不完整，样本分母必须使用实际候选日并单列缺测。",
                "remediation": "保留缺测日为未观测；若补源，按相同站号和报告码规则重新审计。",
            }
        )
    return findings


def audit_project(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    """Parse cached sources and write auditable reference/quarantine outputs."""

    root = Path(root)
    config = _load_yaml(config_path or root / "config" / "data_sources.yaml")
    specs = _resolved_specs(root, _source_specs(root, config))
    manifest, manifest_id = build_source_manifest(root, config)
    ssod_specs = [item for item in specs if str(item.get("source_id", "")).startswith("ssod_")]
    isd_specs = [item for item in specs if str(item.get("source_id", "")).startswith("isd_")]
    ghcn_spec = next((item for item in specs if item.get("source_id") == "ghcn_prcp_CHM00058457"), None)
    ghcn_meta = _station_metadata(root / "data" / "raw" / "CHM00058457_ghcn_station_metadata.txt", ghcn_spec or {})
    ghcn_path = Path(ghcn_spec["_resolved_path"]) if ghcn_spec else root / "data" / "raw" / "CHM00058457.dly"
    ghcn_rows = parse_ghcn_prcp(ghcn_path, manifest_id=manifest_id, metadata=ghcn_meta)
    ssod_rows, ssod_quarantine = parse_ssod_files(ssod_specs, manifest_id)
    isd_records, isd_quarantine = parse_isd_files(isd_specs, manifest_id)
    observations = ghcn_rows + ssod_rows
    all_quarantine = ssod_quarantine + isd_quarantine
    ssod_quarantine_summary = _ssod_quarantine_summary(all_quarantine)
    data_dir = root / "data"
    _write_csv(data_dir / "observations.csv", observations, OBSERVATION_COLUMNS)
    _write_csv(data_dir / "quarantined_records.csv", all_quarantine, QUARANTINE_COLUMNS)
    samples = _write_empty_samples(root)
    report = {
        "dataset_version": _canonical_version(root),
        "status_label": "blocked",
        "summary": {
            "sample_count": 0,
            "candidate_window_count": len(_candidate_observation_keys(observations)),
            "configured_nominal_day_window_count": 731,
            "paired_window_count": 0,
            "quarantined_record_count": len(all_quarantine),
            "observation_reference_count": len(observations),
            "ssod_quarantine_measurement_code_counts": ssod_quarantine_summary["measurement_code_counts"],
            "ssod_quarantine_reason_counts": ssod_quarantine_summary["reason_counts"],
        },
        "monthly": _monthly_counts(observations, samples),
        "findings": _findings(observations, isd_records, all_quarantine, 0, None),
        "limitations": [
            "SSOD 仅保留 D/F/G/数值24 完整报告；H 表示有降水发生记录但总量为零或无法计算，I 表示未报告降水数据及发生记录；H/I、A/B/C/E、未知码和缺测均进入隔离表。",
            "SSOD 为名义 UTC 00–24 日汇总，存在低报与站点缺测风险；不是高精度国家站真值。",
            "GHCN CHM00058457 与 SSOD/ISD 站点不同，且 .dly PRCP 单元没有逐条实际结束时刻。",
            "ISD AA1-AA4 的 trace、condition=3/9、9999 深度和未知质量码不被补零或提升为标签。",
            "Previous Runs 是固定提前量合成序列；样本仅支持 offline_fixed_lead。",
        ],
    }
    report["sample_file_sha256"] = _hash_file(root / "data" / "samples.csv")
    report["source_manifest_file_sha256"] = _hash_file(root / "data" / "source_manifest.json")
    report["dataset_version_basis"] = "sha256(samples.csv actual bytes)"
    _json_dump(root / "reports" / "data_quality.json", report)
    return {
        "manifest": manifest,
        "manifest_id": manifest_id,
        "config": config,
        "specs": specs,
        "observations": observations,
        "ssod_rows": ssod_rows,
        "quarantined": all_quarantine,
        "isd_records": isd_records,
        "samples": samples,
        "report": report,
    }


def build_project(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    """Fetch/cache Previous Runs through the approved adapter, then pair samples."""

    root = Path(root)
    forecast_frames: dict[int, pd.DataFrame] = {}
    forecast_sources: dict[int, dict[str, Any]] = {}
    forecast_error: str | None = None
    try:
        from .forecasts import load_previous_year

        for year in (2024, 2025):
            frame, source = load_previous_year(root, year, 30.2283, 120.4317)
            forecast_frames[year] = frame
            forecast_sources[year] = source
    except Exception as exc:  # keep an auditable blocked package on failure
        forecast_error = f"Previous Runs 获取失败：{type(exc).__name__}: {exc}"

    result = audit_project(root, config_path)
    sample_rows: list[dict[str, Any]] = []
    forecast_quarantine: list[dict[str, Any]] = []
    if forecast_error is None:
        sample_rows, forecast_quarantine = build_sample_rows(
            result["ssod_rows"], forecast_frames, forecast_sources, DATASET_VERSION
        )
    if sample_rows:
        try:
            samples = _write_samples(root, sample_rows)
        except (ValueError, ImportError, OSError) as exc:
            forecast_error = f"样本写入或协议校验失败：{type(exc).__name__}: {exc}"
            samples = _write_empty_samples(root)
            forecast_quarantine = [
                {
                    "record_id": "sample-build",
                    "source_id": "pipeline",
                    "source_dataset": "SSODv2+Open-Meteo",
                    "station_id": "CHI0000ZSHC",
                    "station_name": "XIAOSHAN",
                    "record_timestamp_utc": "",
                    "window_start_utc": "",
                    "window_end_utc": "",
                    "period_hours": 24,
                    "depth_raw": None,
                    "depth_mm": None,
                    "condition_code": "",
                    "quality_code": "",
                    "measurement_code": "",
                    "observed_rain_mm": None,
                    "reason": "sample_build_failed",
                    "details": str(exc),
                    "source_manifest_id": result["manifest_id"],
                }
            ]
    else:
        samples = _write_empty_samples(root)
    if forecast_quarantine:
        all_quarantine = result["quarantined"] + forecast_quarantine
        _write_csv(root / "data" / "quarantined_records.csv", all_quarantine, QUARANTINE_COLUMNS)
    else:
        all_quarantine = result["quarantined"]
    version = _canonical_version(root)
    report = result["report"]
    report["dataset_version"] = version
    report["dataset_version_basis"] = "sha256(samples.csv actual bytes)"
    report["status_label"] = "ready_offline_fixed_lead" if not samples.empty else "blocked"
    report["summary"].update(
        sample_count=int(len(samples)),
        paired_window_count=int(len(samples)),
        quarantined_record_count=len(all_quarantine),
        missing_reference_day_count=int(report["summary"]["configured_nominal_day_window_count"] - report["summary"]["candidate_window_count"]),
        unpaired_candidate_window_count=int(report["summary"]["candidate_window_count"] - len(samples)),
    )
    report["monthly"] = _monthly_counts(result["observations"], samples)
    report["findings"] = _findings(result["observations"], result["isd_records"], all_quarantine, len(samples), forecast_error)
    report["limitations"] = list(dict.fromkeys(report["limitations"] + ([forecast_error] if forecast_error else [])))
    report["sample_file_sha256"] = _hash_file(root / "data" / "samples.csv")
    report["source_manifest_file_sha256"] = _hash_file(root / "data" / "source_manifest.json")
    _json_dump(root / "reports" / "data_quality.json", report)
    result.update(samples=samples, quarantined=all_quarantine, report=report, forecast_error=forecast_error)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="梅雨有数数据审计与离线样本构建")
    parser.add_argument("command", choices=["audit", "build"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.command == "audit" and (args.root / "reports" / "data_quality.json").exists():
        from .verify import verify_package

        report = verify_package(args.root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    result = build_project(args.root, args.config) if args.command == "build" else audit_project(args.root, args.config)
    print(json.dumps(result["report"], ensure_ascii=False, indent=2))
    return 0 if result["report"]["status_label"] != "blocked" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
