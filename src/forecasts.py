from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import requests

MODEL = "ecmwf_ifs025"
VARIABLES = ["precipitation_previous_day1", "temperature_2m_previous_day1", "relative_humidity_2m_previous_day1"]


def parse_previous_response(body: dict) -> pd.DataFrame:
    if body.get("error"):
        raise ValueError("预报接口返回错误：" + str(body.get("reason", "unknown")))
    hourly = body.get("hourly", {})
    times = hourly.get("time", [])
    if not times or any(len(hourly.get(name, [])) != len(times) for name in VARIABLES):
        raise ValueError("预报逐小时字段缺失或长度不一致。")
    if body.get("utc_offset_seconds", 0) != 0:
        raise ValueError("预报响应不是 UTC。")
    if body.get("hourly_units", {}).get(VARIABLES[0]) != "mm":
        raise ValueError("预报降水单位不是 mm。")
    frame = pd.DataFrame({"time_utc": pd.to_datetime(times, utc=True), **{name: pd.to_numeric(hourly[name], errors="coerce") for name in VARIABLES}})
    if frame.time_utc.duplicated().any():
        raise ValueError("预报包含重复有效时刻。")
    return frame.sort_values("time_utc").reset_index(drop=True)


def load_previous_year(root: Path, year: int, latitude: float, longitude: float, model: str = MODEL) -> tuple[pd.DataFrame, dict]:
    params = dict(latitude=latitude, longitude=longitude, start_date=f"{year}-01-01", end_date=f"{year+1}-01-01", hourly=",".join(VARIABLES), models=model, timezone="UTC")
    url = "https://previous-runs-api.open-meteo.com/v1/forecast?" + urlencode(params)
    source_id = "openmeteo_" + hashlib.sha256(url.encode()).hexdigest()[:16]
    path = root / "data" / "raw" / f"{source_id}.json"
    metadata_path = path.with_suffix(".metadata.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and metadata_path.exists():
        raw = path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("url") != url or metadata.get("sha256") != hashlib.sha256(raw).hexdigest():
            raise ValueError("预报缓存摘要或请求地址不匹配。")
        return parse_previous_response(json.loads(raw)), metadata
    failure = None
    for attempt in range(2):
        try:
            response = requests.get(url, timeout=(10, 45))
            response.raise_for_status()
            raw = response.content
            body = response.json()
            frame = parse_previous_response(body)
            metadata = dict(
                source_id=source_id, title=f"Open-Meteo {model} 固定提前量1日 · {year}",
                url=url, retrieved_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), content_type=response.headers.get("Content-Type", ""),
                licence="CC BY 4.0；免费接口仅限非商业用途", local_path=str(path.relative_to(root)).replace("\\", "/"),
                requested_latitude=latitude, requested_longitude=longitude,
                returned_latitude=body.get("latitude"), returned_longitude=body.get("longitude"),
                returned_elevation=body.get("elevation"), forecast_model=model,
                forecast_kind="fixed_lead_composite", model_initialisation_time="not_unique",
                time_semantics="precipitation is the sum of the preceding hour; fixed lead varies by valid hour",
            )
            path.write_bytes(raw)
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            return frame, metadata
        except (requests.RequestException, ValueError, KeyError) as exc:
            failure = exc
            if attempt == 0:
                time.sleep(1)
    raise RuntimeError(f"{year} 年预报下载失败：{failure}")


def aggregate_window(frame: pd.DataFrame, start: str | pd.Timestamp, end: str | pd.Timestamp, source_record: dict) -> dict:
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("聚合窗口必须带时区。")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if end - start != pd.Timedelta(hours=24):
        raise ValueError("聚合窗口必须恰好24小时。")
    # Open-Meteo降水值表示此前一小时，因此选 (start, end] 的24个时间戳。
    expected = pd.date_range(start=start + pd.Timedelta(hours=1), end=end, freq="h")
    selected = frame.loc[frame.time_utc.isin(expected)].copy()
    if len(selected) != 24 or selected.time_utc.duplicated().any() or set(selected.time_utc) != set(expected):
        raise ValueError("forecast_missing_hours")
    rain = selected[VARIABLES[0]]
    if rain.isna().any() or not np.isfinite(rain.to_numpy(dtype=float)).all() or (rain < 0).any():
        raise ValueError("forecast_invalid_precipitation")
    features = {}
    for name, output in [(VARIABLES[1], "forecast_temperature_mean_c"), (VARIABLES[2], "forecast_relative_humidity_mean_pct")]:
        values = selected[name]
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype=float)).all():
            features[output] = None
        elif output.endswith("pct") and not values.between(0, 100).all():
            features[output] = None
        else:
            features[output] = round(float(values.mean()), 4)
    return dict(forecast_rain_mm=round(float(rain.sum()), 4), **features,
                forecast_record_id=f"{source_record['source_id']}:{start.isoformat()}:{end.isoformat()}")
