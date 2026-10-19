"""获取并核对2026年同站输入；样本配对和冻结模型评估另行执行。"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import time
from urllib.parse import urlencode

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = ROOT / "external" / "hangzhou_2026"
RAW = EXTERNAL / "data" / "raw"
REPORTS = EXTERNAL / "reports"
STATION_ID = "CHI0000ZSHC"
YEAR = 2026
LATITUDE = 30.2283
LONGITUDE = 120.4317
MODEL = "ecmwf_ifs025"
VARIABLES = [
    "precipitation_previous_day1",
    "temperature_2m_previous_day1",
    "relative_humidity_2m_previous_day1",
]
START_DATE = "2026-01-01"
END_DATE = "2026-10-01"
PROTOCOL_SOURCE = ROOT / "docs" / "新增时间段验证协议.md"
PROTOCOL_LOCAL = ROOT / "external" / "hangzhou_2026" / "reports" / "protocol.md"
PROTOCOL_IDENTITY_LOCAL = ROOT / "external" / "hangzhou_2026" / "reports" / "protocol_identity.json"
NOAA_URL = "https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/access/by-year/2026/csv/SSOD_CHI0000ZSHC_2026.csv"
OPEN_METEO_PARAMS = {
    "latitude": LATITUDE,
    "longitude": LONGITUDE,
    "start_date": START_DATE,
    "end_date": END_DATE,
    "hourly": ",".join(VARIABLES),
    "models": MODEL,
    "timezone": "UTC",
}
OPEN_METEO_URL = "https://previous-runs-api.open-meteo.com/v1/forecast?" + urlencode(OPEN_METEO_PARAMS)
LICENCE_NOAA = "NOAA/NCEI public data; upstream terms should be retained"
LICENCE_OPEN_METEO = "CC BY 4.0；免费接口仅限非商业用途"
TIME_SEMANTICS = "precipitation is the sum of the preceding hour; fixed lead varies by valid hour"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_audit_identity() -> dict:
    """Load the delivered protocol pair without creating or rewriting either file."""
    if not PROTOCOL_LOCAL.exists():
        raise RuntimeError(
            f"缺少已交付协议副本：{PROTOCOL_LOCAL}；不会从工作区或其他路径自动生成。"
        )
    if not PROTOCOL_IDENTITY_LOCAL.exists():
        raise RuntimeError(
            f"缺少已交付协议身份：{PROTOCOL_IDENTITY_LOCAL}；不能伪造更早协议时间。"
        )
    if not PROTOCOL_SOURCE.exists():
        raise RuntimeError(f"缺少用于校验的协议源文件：{PROTOCOL_SOURCE}。")
    protocol_sha = sha256_bytes(PROTOCOL_LOCAL.read_bytes())
    expected_sha = sha256_bytes(PROTOCOL_SOURCE.read_bytes())
    if protocol_sha != expected_sha:
        raise RuntimeError(
            f"协议副本 SHA 与 docs 源不一致：{protocol_sha} != {expected_sha}。"
        )
    identity_bytes = PROTOCOL_IDENTITY_LOCAL.read_bytes()
    try:
        identity = json.loads(identity_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"协议身份不是有效 UTF-8 JSON：{PROTOCOL_IDENTITY_LOCAL}。") from exc
    if str(identity.get("protocol_sha256", "")).lower() != expected_sha:
        raise RuntimeError(
            "协议身份中的 protocol_sha256 与 docs 协议 SHA 不一致；不会重建身份文件。"
        )
    saved_at = identity.get("saved_at_utc")
    if not saved_at:
        raise RuntimeError("协议身份缺少 saved_at_utc；不会补写或伪造协议时间。")
    try:
        datetime.fromisoformat(str(saved_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError("协议身份的 saved_at_utc 不是有效时间；不会补写或伪造协议时间。") from exc
    return {
        "protocol_local_path": "reports/protocol.md",
        "protocol_sha256": protocol_sha,
        "identity_local_path": "reports/protocol_identity.json",
        "identity_sha256": sha256_bytes(identity_bytes),
        "identity": identity,
        "source": identity.get("source"),
        "is_public_preregistered": False,
    }


def cached_bytes(raw_path: Path, metadata_path: Path, url: str) -> tuple[bytes, dict] | None:
    if not raw_path.exists() and not metadata_path.exists():
        return None
    if not raw_path.exists() or not metadata_path.exists():
        raise RuntimeError(f"缓存不完整：{raw_path.name} 与元数据必须同时存在。")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw = raw_path.read_bytes()
    digest = sha256_bytes(raw)
    if metadata.get("url") != url:
        raise RuntimeError(f"缓存 URL 不一致：{raw_path.name}。")
    if metadata.get("sha256") != digest:
        raise RuntimeError(f"缓存 SHA-256 不一致：{raw_path.name}。")
    return raw, metadata


def get_bytes(url: str, raw_path: Path, metadata_path: Path) -> tuple[bytes, dict, bool]:
    cached = cached_bytes(raw_path, metadata_path, url)
    if cached is not None:
        raw, metadata = cached
        return raw, metadata, True
    last_error: Exception | None = None
    attempts = 0
    for attempt in range(3):
        attempts = attempt + 1
        try:
            response = requests.get(url, timeout=(15, 90))
            response.raise_for_status()
            raw = response.content
            metadata = {
                "url": url,
                "retrieved_at_utc": utc_now(),
                "sha256": sha256_bytes(raw),
                "bytes": len(raw),
                "content_type": response.headers.get("Content-Type", ""),
                "http_status": response.status_code,
                "last_modified": response.headers.get("Last-Modified"),
                "etag": response.headers.get("ETag"),
                "attempts": attempts,
                "cache_hit": False,
            }
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_bytes(raw)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return raw, metadata, False
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET 失败（尝试 {attempts} 次）：{url}；{last_error}")


def enrich_noaa(raw: bytes, metadata: dict) -> tuple[dict, dict]:
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("NOAA CSV 没有表头。")
    header = rows[0]
    data_rows = rows[1:]
    if not header:
        raise ValueError("NOAA CSV 表头为空。")
    record = {
        "source_id": f"ssod_{STATION_ID}_{YEAR}",
        "title": f"NOAA SSODv2 · {STATION_ID} {YEAR}",
        "url": NOAA_URL,
        "local_path": f"data/raw/SSOD_{STATION_ID}_{YEAR}.csv",
        "metadata_local_path": f"data/raw/SSOD_{STATION_ID}_{YEAR}.metadata.json",
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "retrieved_at_utc": metadata.get("retrieved_at_utc"),
        "content_type": metadata.get("content_type", ""),
        "http_status": metadata.get("http_status"),
        "last_modified": metadata.get("last_modified"),
        "etag": metadata.get("etag"),
        "licence": LICENCE_NOAA,
        "role": "2026 same-station SSOD reference source; source fetch only",
        "station_id": STATION_ID,
        "year": YEAR,
        "spec": {"station_id": STATION_ID, "year": YEAR},
        "requested_latitude": LATITUDE,
        "requested_longitude": LONGITUDE,
        "returned_latitude": None,
        "returned_longitude": None,
        "returned_elevation": None,
        "time_semantics": "SSOD nominal UTC day; one daily reference report when the upstream report layer is complete",
        "ssod_rule": "D/F/G/numeric24 complete report layer; H/I, A/B/C/E and unknown codes remain for ROOT quarantine; nominal UTC day.",
    }
    columns = {
        "count": len(header),
        "names": header,
        "data_rows": len(data_rows),
        "encoding": "utf-8-sig decoded for structural counting; raw bytes preserved",
    }
    if "DATE" in header:
        date_index = header.index("DATE")
        dates = [row[date_index] for row in data_rows if len(row) > date_index and row[date_index]]
        columns["date_field"] = "DATE"
        columns["date_count_nonempty"] = len(dates)
        columns["date_min"] = min(dates) if dates else None
        columns["date_max"] = max(dates) if dates else None
    if "STATION" in header:
        station_index = header.index("STATION")
        columns["station_field"] = "STATION"
        columns["station_values"] = sorted({row[station_index] for row in data_rows if len(row) > station_index and row[station_index]})
    for field, key in [("LATITUDE", "returned_latitude"), ("LONGITUDE", "returned_longitude"), ("ELEVATION", "returned_elevation")]:
        if field in header:
            field_index = header.index(field)
            values = [row[field_index] for row in data_rows if len(row) > field_index and row[field_index] not in {"", "."}]
            if values:
                try:
                    record[key] = float(values[0])
                except ValueError:
                    columns[f"{field.lower()}_parse_error"] = values[0]
    return record, columns


def enrich_forecast(raw: bytes, metadata: dict) -> tuple[dict, dict]:
    body = json.loads(raw.decode("utf-8"))
    # Import the existing parser exactly as requested; this does not request data.
    from src.forecasts import parse_previous_response  # noqa: PLC0415

    frame = parse_previous_response(body)
    units = body.get("hourly_units", {})
    expected_units = {
        "precipitation_previous_day1": "mm",
        "temperature_2m_previous_day1": "°C",
        "relative_humidity_2m_previous_day1": "%",
    }
    unit_checks = {key: units.get(key) == value for key, value in expected_units.items()}
    if not all(unit_checks.values()):
        raise ValueError(f"预报单位不符合协议：{units}")
    formal_start = pd.Timestamp(f"{START_DATE}T00:00:00Z")
    formal_end = pd.Timestamp(f"{END_DATE}T00:00:00Z")
    boundary_end = pd.Timestamp("2026-10-02T00:00:00Z")
    formal = frame.loc[(frame["time_utc"] >= formal_start) & (frame["time_utc"] < formal_end)]
    boundary = frame.loc[(frame["time_utc"] >= formal_end) & (frame["time_utc"] < boundary_end)]
    record = {
        "source_id": metadata["source_id"],
        "title": f"Open-Meteo {MODEL} 固定提前量1日 · {YEAR}",
        "url": OPEN_METEO_URL,
        "local_path": metadata["local_path"],
        "metadata_local_path": metadata["metadata_local_path"],
        "sha256": metadata["sha256"],
        "bytes": metadata["bytes"],
        "retrieved_at_utc": metadata.get("retrieved_at_utc"),
        "content_type": metadata.get("content_type", ""),
        "http_status": metadata.get("http_status"),
        "licence": LICENCE_OPEN_METEO,
        "role": "2026 same-station fixed-lead forecast source; source fetch only",
        "requested_latitude": LATITUDE,
        "requested_longitude": LONGITUDE,
        "returned_latitude": body.get("latitude"),
        "returned_longitude": body.get("longitude"),
        "returned_elevation": body.get("elevation"),
        "forecast_model": MODEL,
        "forecast_kind": "fixed_lead_composite",
        "model_initialisation_time": "not_unique",
        "time_semantics": TIME_SEMANTICS,
        "requested_scope": {"start_date": START_DATE, "end_date": END_DATE, "formal_end_exclusive": f"{END_DATE}T00:00:00Z"},
    }
    checks = {
        "parser": "src.forecasts.parse_previous_response",
        "utc_offset_seconds": body.get("utc_offset_seconds"),
        "utc_offset_ok": body.get("utc_offset_seconds", 0) == 0,
        "hourly_units": units,
        "unit_checks": unit_checks,
        "hourly_fields": list(VARIABLES),
        "hourly_length": len(frame),
        "time_start_utc": frame["time_utc"].min().isoformat().replace("+00:00", "Z") if not frame.empty else None,
        "time_end_utc": frame["time_utc"].max().isoformat().replace("+00:00", "Z") if not frame.empty else None,
        "formal_range": {"start_inclusive": f"{START_DATE}T00:00:00Z", "end_exclusive": f"{END_DATE}T00:00:00Z", "hours": len(formal)},
        "october_1_boundary_hours": len(boundary),
        "expected_formal_hours": 273 * 24,
        "temperature_finite_count": int(frame["temperature_2m_previous_day1"].notna().sum()),
        "relative_humidity_finite_count": int(frame["relative_humidity_2m_previous_day1"].notna().sum()),
        "precipitation_finite_count": int(frame["precipitation_previous_day1"].notna().sum()),
    }
    return record, checks


TRANSIENT_SOURCE_KEYS = {"retrieved_at_utc", "bytes", "http_status", "last_modified", "etag"}


def stable_source_records(sources: list[dict]) -> list[dict]:
    return [
        {key: value for key, value in source.items() if key not in TRANSIENT_SOURCE_KEYS}
        for source in sources
    ]


def manifest_content(manifest: dict) -> dict:
    """Return fields whose equality means the existing manifest is reusable."""
    return {
        "manifest_id": manifest.get("manifest_id"),
        "manifest_version": manifest.get("manifest_version"),
        "station": manifest.get("station"),
        "scope": manifest.get("scope"),
        "sources": stable_source_records(manifest.get("sources", [])),
        "protocol": manifest.get("protocol"),
        "source_fetch_only": manifest.get("source_fetch_only"),
    }


def write_manifest_if_changed(path: Path, candidate: dict) -> dict:
    """Keep the existing bytes when all source content and records are unchanged."""
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            existing = None
        if isinstance(existing, dict) and manifest_content(existing) == manifest_content(candidate):
            return existing
    dump_json(path, candidate)
    return candidate


def main() -> int:
    failures: list[str] = []
    protocol = load_audit_identity()
    RAW.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    source_records: list[dict] = []
    checks: dict[str, dict] = {}
    noaa_raw_path = RAW / f"SSOD_{STATION_ID}_{YEAR}.csv"
    noaa_metadata_path = noaa_raw_path.with_suffix(".metadata.json")
    noaa_fetch_metadata: dict = {"url": NOAA_URL}
    try:
        noaa_raw, noaa_fetch_metadata, noaa_cache_hit = get_bytes(NOAA_URL, noaa_raw_path, noaa_metadata_path)
        noaa_record, noaa_columns = enrich_noaa(noaa_raw, noaa_fetch_metadata)
        noaa_fetch_metadata = {**noaa_fetch_metadata, **noaa_record, "columns": noaa_columns}
        if not noaa_cache_hit:
            dump_json(noaa_metadata_path, noaa_fetch_metadata)
        source_records.append(noaa_record)
        checks["noaa"] = {"status": "available", "columns": noaa_columns, "metadata_path": str(noaa_metadata_path.relative_to(EXTERNAL)).replace("\\", "/")}
    except Exception as exc:  # preserve one-source failures while continuing to forecast fetch
        failures.append(f"NOAA: {type(exc).__name__}: {exc}")
        checks["noaa"] = {"status": "blocked", "error": f"{type(exc).__name__}: {exc}", "metadata_path": str(noaa_metadata_path.relative_to(EXTERNAL)).replace("\\", "/")}

    forecast_url_hash = hashlib.sha256(OPEN_METEO_URL.encode()).hexdigest()[:16]
    forecast_source_id = f"openmeteo_{forecast_url_hash}"
    forecast_raw_path = RAW / f"{forecast_source_id}.json"
    forecast_metadata_path = forecast_raw_path.with_suffix(".metadata.json")
    forecast_fetch_metadata: dict = {
        "source_id": forecast_source_id,
        "url": OPEN_METEO_URL,
        "requested_latitude": LATITUDE,
        "requested_longitude": LONGITUDE,
        "forecast_model": MODEL,
        "forecast_kind": "fixed_lead_composite",
        "model_initialisation_time": "not_unique",
        "time_semantics": TIME_SEMANTICS,
        "local_path": str(forecast_raw_path.relative_to(EXTERNAL)).replace("\\", "/"),
        "metadata_local_path": str(forecast_metadata_path.relative_to(EXTERNAL)).replace("\\", "/"),
    }
    try:
        forecast_raw, base_metadata, forecast_cache_hit = get_bytes(OPEN_METEO_URL, forecast_raw_path, forecast_metadata_path)
        forecast_fetch_metadata = {**forecast_fetch_metadata, **base_metadata, "source_id": forecast_source_id,
                                   "local_path": str(forecast_raw_path.relative_to(EXTERNAL)).replace("\\", "/"),
                                   "metadata_local_path": str(forecast_metadata_path.relative_to(EXTERNAL)).replace("\\", "/")}
        forecast_record, forecast_checks = enrich_forecast(forecast_raw, forecast_fetch_metadata)
        forecast_fetch_metadata = {**forecast_fetch_metadata, **forecast_record, "checks": forecast_checks}
        if not forecast_cache_hit:
            dump_json(forecast_metadata_path, forecast_fetch_metadata)
        source_records.append(forecast_record)
        checks["forecast"] = {"status": "available", **forecast_checks, "metadata_path": str(forecast_metadata_path.relative_to(EXTERNAL)).replace("\\", "/")}
    except Exception as exc:
        failures.append(f"Open-Meteo: {type(exc).__name__}: {exc}")
        checks["forecast"] = {"status": "blocked", "error": f"{type(exc).__name__}: {exc}", "metadata_path": str(forecast_metadata_path.relative_to(EXTERNAL)).replace("\\", "/")}

    stable_sources = stable_source_records(source_records)
    stable_blob = json.dumps(stable_sources, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest_id = "sm-" + hashlib.sha256(stable_blob).hexdigest()[:16]
    manifest = {
        "manifest_id": manifest_id,
        "manifest_version": "external-hangzhou-2026-v1",
        "generated_at_utc": utc_now(),
        "station": {"station_id": STATION_ID, "latitude": LATITUDE, "longitude": LONGITUDE},
        "scope": {"year": YEAR, "start_date": START_DATE, "end_date_exclusive": END_DATE, "formal_range": "2026-01-01T00:00:00Z inclusive to 2026-10-01T00:00:00Z exclusive"},
        "sources": source_records,
        "protocol": {"source": protocol["source"], "protocol_sha256": protocol["protocol_sha256"], "identity_sha256": protocol["identity_sha256"], "is_public_preregistered": False},
        "source_fetch_only": True,
    }
    manifest_path = EXTERNAL / "data" / "source_manifest.json"
    manifest = write_manifest_if_changed(manifest_path, manifest)
    report = {
        "generated_at_utc": utc_now(),
        "status": "available" if not failures and len(source_records) == 2 else "partial_or_blocked",
        "purpose": "只获取并核查 2026 同站输入；不生成样本、预测或指标。",
        "protocol": protocol,
        "scope": manifest["scope"],
        "sources": checks,
        "source_manifest": {"local_path": "data/source_manifest.json", "manifest_id": manifest_id, "sha256": sha256_bytes(manifest_path.read_bytes())},
        "failures": failures,
        "next_step": "使用 temporal_validation 模块配对和评估；本报告只核查来源。",
    }
    dump_json(REPORTS / "fetch_check.json", report)
    print(json.dumps({"status": report["status"], "manifest_id": manifest_id, "sources": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
