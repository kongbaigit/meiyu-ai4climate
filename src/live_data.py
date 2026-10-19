"""运行时天气来源接口。

这个模块只负责在线来源、严格解析和独立运行时缓存。它不读取或写入
``data/``、``artifacts/``、``reports/`` 中的冻结实验文件，也不把网格
预报或再分析资料当成站点实测。

公共入口是 :func:`make_request`、:func:`parse_payload`、
:func:`read_cached` 和 :func:`fetch_snapshot`。网络请求默认使用
``requests``，测试和上层页面可以通过 ``http_get`` 注入一个无网络的
响应函数。
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import inspect
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlencode, urlparse
import re


UTC = timezone.utc
MODEL = "ecmwf_ifs025"
ARCHIVE_MODEL = "era5"
PRODUCTS = ("forecast", "archive", "station")

# 坐标与来源身份固定为当前项目已核对过的站点。预报/ERA5 返回的网格点
# 会在 parse_payload 中单独保存，不能静默替换这里的站点身份。
LOCATIONS: dict[str, dict[str, Any]] = {
    "hangzhou": {
        "key": "hangzhou",
        "name": "杭州萧山机场",
        "latitude": 30.2283,
        "longitude": 120.4317,
        "station_id": "CHI0000ZSHC",
    },
    "ningbo": {
        "key": "ningbo",
        "name": "宁波栎社机场",
        "latitude": 29.8249,
        "longitude": 121.4651,
        "station_id": "CHI0000ZSNB",
    },
}

FORECAST_TTL = timedelta(hours=3)
ARCHIVE_TTL = timedelta(hours=24)
STATION_TTL = timedelta(hours=24)
HTTP_TIMEOUT = (5, 20)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
GRID_TOLERANCE_DEGREES = 0.30
STATION_TOLERANCE_DEGREES = 0.10
_RAW_FILE_RE = re.compile(r"raw-[0-9a-f]{64}\.bin\Z")
_SNAPSHOT_FILE_RE = re.compile(r"snapshot-[0-9a-f]{64}\.json\Z")


def _utc_datetime(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if not isinstance(value, datetime):
        raise TypeError("now 必须是 datetime、date 或 None。")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _date_iso(value: date) -> str:
    return value.isoformat()


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是带 UTC 的 ISO 时间。")
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{field} 时间无效。") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} 必须是 UTC，不能使用非零偏移。")
    return parsed.astimezone(UTC)


def _parse_request_time(value: Any, field: str) -> datetime:
    try:
        return _parse_utc(value, field)
    except ValueError:
        if isinstance(value, str):
            try:
                parsed_date = date.fromisoformat(value)
            except ValueError:
                pass
            else:
                return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
        raise


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是 YYYY-MM-DD。")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} 日期无效。") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD。")
    return parsed


def _finite_number(value: Any, field: str, *, allow_none: bool = True, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field} 缺失。")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} 必须是数字或 null。")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} 不能是 NaN 或无穷值。")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} 不能小于 {minimum}。")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} 不能大于 {maximum}。")
    return number


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 含非有限数值 {value}。")


def _load_json(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("raw 必须是 bytes。")
    try:
        value = json.loads(bytes(raw).decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"JSON 响应无效：{exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON 响应顶层必须是对象，不能是数组。")
    return value


def _json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无法生成有限 JSON：{exc}") from exc
    return text.encode("utf-8")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"对象包含不可序列化值：{exc}") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _location(location_key: str) -> dict[str, Any]:
    try:
        return dict(LOCATIONS[location_key])
    except KeyError as exc:
        raise ValueError(f"未知位置：{location_key}。可选值为 {sorted(LOCATIONS)}。") from exc


def _expected_dates(request: Mapping[str, Any]) -> list[date]:
    explicit = request.get("expected_dates")
    if explicit is not None:
        if not isinstance(explicit, list):
            raise ValueError("request.expected_dates 必须是日期列表。")
        dates = [_parse_date(item, "request.expected_dates") for item in explicit]
        if len(set(dates)) != len(dates) or dates != sorted(dates):
            raise ValueError("request.expected_dates 不能重复且必须升序。")
        if len(dates) > 366:
            raise ValueError("请求日期窗口最多 366 日。")
        return dates
    product = str(request.get("product", ""))
    start = _parse_request_time(request.get("start_date"), "request.start_date").date()
    end = _parse_request_time(request.get("end_date"), "request.end_date").date()
    if product == "forecast":
        end_exclusive = end
    else:
        end_exclusive = end + timedelta(days=1)
    if end_exclusive < start:
        raise ValueError("request 日期窗口反向。")
    count = (end_exclusive - start).days
    if count > 366:
        raise ValueError("请求日期窗口最多 366 日。")
    return [start + timedelta(days=i) for i in range(count)]


def _request_location(request: Mapping[str, Any]) -> dict[str, Any]:
    loc = request.get("location")
    if isinstance(loc, str):
        return _location(loc)
    if not isinstance(loc, Mapping):
        loc = _location(str(request.get("location_key", "")))
    key = str(loc.get("key", request.get("location_key", "")))
    expected = _location(key)
    # 请求身份只能来自固定位置表；允许调用者省略 name 等展示字段，但不
    # 允许用另一个坐标悄悄冒充机场。
    for name in ("latitude", "longitude", "station_id"):
        if name in loc and str(loc[name]) != str(expected[name]):
            raise ValueError(f"request.location.{name} 与固定位置不一致。")
    return expected


def _request_product(request: Mapping[str, Any]) -> str:
    product = str(request.get("product", ""))
    if product not in PRODUCTS:
        raise ValueError(f"未知产品：{product}。")
    return product


def make_request(location_key: str, product: str, now: datetime | date | None = None) -> dict[str, Any]:
    """生成一个固定语义的来源请求描述，不执行网络请求。

    ``start_date``/``end_date`` 是 UTC ISO 边界，``expected_dates`` 是输出
    行的名义 UTC 日。Forecast 的 ``end_date`` 为排他边界，Archive 和
    Station 的 API 日期参数则以 ``api_end_date`` 表示包含当天的日期。
    """

    if product not in PRODUCTS:
        raise ValueError(f"未知产品：{product}。")
    location = _location(location_key)
    current = _utc_datetime(now)
    if product == "forecast":
        start = datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        end = start + timedelta(days=7)
        expected = [start.date() + timedelta(days=i) for i in range(7)]
        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "hourly": "precipitation,temperature_2m,relative_humidity_2m",
            "models": MODEL,
            "timezone": "UTC",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
            "forecast_days": 9,
        }
        url = "https://api.open-meteo.com/v1/forecast?" + urlencode(params)
        extra = {
            "requested_model": MODEL,
            "api_start_date": _date_iso(current.date()),
            "api_end_date": _date_iso((current.date() + timedelta(days=8))),
        }
    elif product == "archive":
        cutoff = current.date() - timedelta(days=7)
        # 年初一周也要取上一年截至 cutoff 的 ERA5 背景，不能构造
        # start=当年1月1日、end=上一年12月的反向空请求。
        start_date = date(cutoff.year, 1, 1)
        expected = [] if cutoff < start_date else [start_date + timedelta(days=i) for i in range((cutoff - start_date).days + 1)]
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(cutoff + timedelta(days=1), datetime.min.time(), tzinfo=UTC) if expected else start
        api_cutoff = max(cutoff, start_date)
        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "start_date": _date_iso(start_date),
            "end_date": _date_iso(api_cutoff),
            "daily": "precipitation_sum,temperature_2m_mean",
            "models": ARCHIVE_MODEL,
            "timezone": "UTC",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
        }
        url = "https://archive-api.open-meteo.com/v1/archive?" + urlencode(params)
        extra = {
            "requested_model": ARCHIVE_MODEL,
            "api_start_date": _date_iso(start_date),
            "api_end_date": _date_iso(api_cutoff),
        }
    else:
        year = current.year
        yesterday = current.date() - timedelta(days=1)
        start_date = date(year, 1, 1)
        expected = [] if yesterday < start_date else [start_date + timedelta(days=i) for i in range((yesterday - start_date).days + 1)]
        start = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
        end = datetime.combine(yesterday + timedelta(days=1), datetime.min.time(), tzinfo=UTC) if expected else start
        url = f"https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/access/by-year/{year}/csv/SSOD_{location['station_id']}_{year}.csv"
        extra = {
            "station_year": year,
            "api_start_date": _date_iso(start_date),
            "api_end_date": _date_iso(yesterday),
        }
    return {
        "product": product,
        "location_key": location_key,
        "location": location,
        "request_url": url,
        "start_date": _iso(start),
        "end_date": _iso(end),
        "expected_dates": [_date_iso(item) for item in expected],
        **extra,
    }


def _source(product: str) -> dict[str, Any]:
    if product == "forecast":
        return {
            "provider": "Open-Meteo",
            "kind": "ECMWF IFS 0.25° grid forecast",
            "model": MODEL,
            "licence": "Open-Meteo/ECMWF open data; CC BY 4.0 and non-commercial API terms",
        }
    if product == "archive":
        return {
            "provider": "Open-Meteo",
            "kind": "ERA5 grid reanalysis",
            "model": ARCHIVE_MODEL,
            "licence": "Open-Meteo/ECMWF open data; CC BY 4.0 and non-commercial API terms",
        }
    return {
        "provider": "NOAA/NCEI",
        "kind": "SSODv2 same-station daily summary",
        "model": None,
        "licence": "NOAA/NCEI public data; retain citation and no-warranty notice",
    }


def _check_response_location(body: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, float]:
    latitude = _finite_number(body.get("latitude"), "响应纬度", allow_none=False, minimum=-90, maximum=90)
    longitude = _finite_number(body.get("longitude"), "响应经度", allow_none=False, minimum=-180, maximum=180)
    location = _request_location(request)
    if abs(float(latitude) - float(location["latitude"])) > GRID_TOLERANCE_DEGREES or abs(float(longitude) - float(location["longitude"])) > GRID_TOLERANCE_DEGREES:
        raise ValueError("响应网格位置差异过大，拒绝冒充目标站点。")
    return {"latitude": float(latitude), "longitude": float(longitude)}


def _check_utc_response(body: Mapping[str, Any]) -> None:
    offset = body.get("utc_offset_seconds", 0)
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or float(offset) != 0:
        raise ValueError("响应不是 UTC。")
    timezone_name = body.get("timezone")
    if timezone_name is not None and timezone_name not in {"UTC", "GMT"}:
        raise ValueError("响应 timezone 不是 UTC。")


def _hour(value: Any, field: str) -> datetime:
    # Open-Meteo 在 ``timezone=UTC`` 且 ``utc_offset_seconds=0`` 时的
    # iso8601 输出实际采用 ``YYYY-MM-DDTHH:MM``，不重复写 ``Z``。顶层
    # UTC 校验已经完成，因此仅对这种无偏移写法补 UTC；带非零偏移仍拒绝。
    if isinstance(value, str) and "T" in value and not value.endswith("Z") and "+" not in value[10:] and "-" not in value[10:]:
        try:
            parsed = datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError as exc:
            raise ValueError(f"{field} 时间无效。") from exc
    else:
        parsed = _parse_utc(value, field)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError(f"{field} 必须是整点 UTC。")
    return parsed


def _daily(value: Any, field: str) -> date:
    return _parse_date(value, field)


def _row(date_value: date, *, rain: float | None, temperature: float | None, humidity: float | None, hours_present: int | None, hours_expected: int | None, reason: str) -> dict[str, Any]:
    start = datetime.combine(date_value, datetime.min.time(), tzinfo=UTC)
    end = start + timedelta(days=1)
    if hours_expected is not None and hours_present == hours_expected and rain is not None:
        status = "complete"
    elif hours_present is not None and hours_present > 0:
        status = "partial"
    elif hours_expected is None and rain is not None:
        status = "complete"
    elif hours_expected is None and reason == "missing_report":
        status = "missing"
    else:
        status = "missing" if hours_present in {None, 0} else "partial"
    return {
        "date": _date_iso(date_value),
        "start_utc": _iso(start),
        "end_utc": _iso(end),
        "rain_mm": rain,
        "temperature_mean_c": temperature,
        "humidity_mean_pct": humidity,
        "hours_present": hours_present,
        "hours_expected": hours_expected,
        "status": status,
        "reason": reason,
    }


def _coverage(rows: list[dict[str, Any]], expected: list[date]) -> dict[str, Any]:
    complete = [row["date"] for row in rows if row["status"] == "complete"]
    partial = [row["date"] for row in rows if row["status"] == "partial"]
    missing = [row["date"] for row in rows if row["status"] == "missing"]
    reported = [row["date"] for row in rows if row["status"] != "missing"]
    available = [row["date"] for row in rows if row.get("rain_mm") is not None]
    return {
        "expected_days": [_date_iso(item) for item in expected],
        "complete_days": complete,
        "partial_days": partial,
        "missing_days": missing,
        "expected_day_count": len(expected),
        "complete_day_count": len(complete),
        "partial_day_count": len(partial),
        "missing_day_count": len(missing),
        "latest_available_date": max(available) if available else None,
        "last_reported_date": max(reported) if reported else None,
    }


def _snapshot(request: Mapping[str, Any], retrieved_at_utc: str, raw: bytes, rows: list[dict[str, Any]], grid: dict[str, float]) -> dict[str, Any]:
    product = _request_product(request)
    location = _request_location(request)
    expected = _expected_dates(request)
    fetched = _parse_utc(retrieved_at_utc, "retrieved_at_utc")
    return {
        "schema_version": 1,
        "product": product,
        "location": location,
        "fetched_at_utc": _iso(fetched),
        "request_url": str(request.get("request_url", "")),
        "source": _source(product),
        "raw_sha256": _sha256(raw),
        "raw_bytes": len(raw),
        "rows": rows,
        "coverage": _coverage(rows, expected),
        "grid": grid,
    }


def _parse_forecast(body: Mapping[str, Any], request: Mapping[str, Any], raw: bytes, fetched: str) -> dict[str, Any]:
    _check_utc_response(body)
    grid = _check_response_location(body, request)
    units = body.get("hourly_units")
    if not isinstance(units, Mapping) or units.get("precipitation") != "mm":
        raise ValueError("预报降水单位不是 mm。")
    hourly = body.get("hourly")
    if not isinstance(hourly, Mapping):
        raise ValueError("预报 hourly 必须是对象。")
    times = hourly.get("time")
    precipitation = hourly.get("precipitation")
    if not isinstance(times, list) or not isinstance(precipitation, list):
        raise ValueError("预报必须包含 hourly.time 与 hourly.precipitation 列表。")
    if len(times) != len(precipitation):
        raise ValueError("预报字段长度不一致。")
    optional: dict[str, list[Any]] = {}
    for name, unit in (("temperature_2m", "°C"), ("relative_humidity_2m", "%")):
        values = hourly.get(name)
        if values is None:
            optional[name] = [None] * len(times)
            continue
        if not isinstance(values, list) or len(values) != len(times):
            raise ValueError(f"预报字段 {name} 长度不一致。")
        if units.get(name) != unit:
            raise ValueError(f"预报 {name} 单位不正确。")
        optional[name] = values
    by_time: dict[datetime, tuple[float | None, float | None, float | None]] = {}
    for index, value in enumerate(times):
        stamp = _hour(value, f"hourly.time[{index}]")
        if stamp in by_time:
            raise ValueError("预报包含重复有效时刻。")
        rain = _finite_number(precipitation[index], f"hourly.precipitation[{index}]", minimum=0)
        temperature = _finite_number(optional["temperature_2m"][index], f"hourly.temperature_2m[{index}]")
        humidity = _finite_number(optional["relative_humidity_2m"][index], f"hourly.relative_humidity_2m[{index}]", maximum=100, minimum=0)
        by_time[stamp] = rain, temperature, humidity
    expected = _expected_dates(request)
    rows: list[dict[str, Any]] = []
    for day in expected:
        start = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
        stamps = [start + timedelta(hours=hour) for hour in range(1, 25)]
        selected = [by_time.get(stamp) for stamp in stamps]
        rain_values = [item[0] for item in selected if item is not None and item[0] is not None]
        temp_values = [item[1] for item in selected if item is not None and item[1] is not None]
        humidity_values = [item[2] for item in selected if item is not None and item[2] is not None]
        hours_present = len(rain_values)
        complete = hours_present == 24
        rain = float(sum(rain_values)) if complete else None
        temperature = float(sum(temp_values) / len(temp_values)) if temp_values else None
        humidity = float(sum(humidity_values) / len(humidity_values)) if humidity_values else None
        reason = "complete" if complete else ("missing_precipitation_hours" if hours_present else "no_precipitation_coverage")
        rows.append(_row(day, rain=rain, temperature=temperature, humidity=humidity, hours_present=hours_present, hours_expected=24, reason=reason))
    return _snapshot(request, fetched, raw, rows, grid)


def _parse_archive(body: Mapping[str, Any], request: Mapping[str, Any], raw: bytes, fetched: str) -> dict[str, Any]:
    _check_utc_response(body)
    grid = _check_response_location(body, request)
    daily_units = body.get("daily_units")
    if not isinstance(daily_units, Mapping) or daily_units.get("precipitation_sum") != "mm":
        raise ValueError("ERA5 日降水单位不是 mm。")
    daily = body.get("daily")
    if not isinstance(daily, Mapping):
        raise ValueError("ERA5 daily 必须是对象。")
    times = daily.get("time")
    precipitation = daily.get("precipitation_sum")
    if not isinstance(times, list) or not isinstance(precipitation, list):
        raise ValueError("ERA5 必须包含 daily.time 与 daily.precipitation_sum 列表。")
    if len(times) != len(precipitation):
        raise ValueError("ERA5 字段长度不一致。")
    temperature_provided = "temperature_2m_mean" in daily
    temperature_values = daily.get("temperature_2m_mean")
    if temperature_values is None:
        temperature_values = [None] * len(times)
    elif not isinstance(temperature_values, list) or len(temperature_values) != len(times):
        raise ValueError("ERA5 温度字段长度不一致。")
    if temperature_provided and daily_units.get("temperature_2m_mean") != "°C":
        raise ValueError("ERA5 温度单位不正确。")
    by_day: dict[date, tuple[float | None, float | None]] = {}
    for index, value in enumerate(times):
        day = _daily(value, f"daily.time[{index}]")
        if day in by_day:
            raise ValueError("ERA5 包含重复日期。")
        rain = _finite_number(precipitation[index], f"daily.precipitation_sum[{index}]", minimum=0)
        temperature = _finite_number(temperature_values[index], f"daily.temperature_2m_mean[{index}]")
        by_day[day] = rain, temperature
    expected = _expected_dates(request)
    rows: list[dict[str, Any]] = []
    for day in expected:
        values = by_day.get(day)
        if values is None:
            rows.append(_row(day, rain=None, temperature=None, humidity=None, hours_present=None, hours_expected=None, reason="missing_date"))
        else:
            rain, temperature = values
            if rain is None:
                rows.append(_row(day, rain=None, temperature=temperature, humidity=None, hours_present=None, hours_expected=None, reason="missing_precipitation"))
            else:
                rows.append(_row(day, rain=rain, temperature=temperature, humidity=None, hours_present=None, hours_expected=None, reason="complete"))
    return _snapshot(request, fetched, raw, rows, grid)


def _parse_station(raw: bytes, request: Mapping[str, Any], fetched: str) -> dict[str, Any]:
    try:
        text = bytes(raw).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("SSOD CSV 不是 UTF-8 文本。") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = set(reader.fieldnames or [])
    required = {"STATION", "DATE", "total_precipitation", "total_precipitation_Measurement_Code"}
    if not required.issubset(fields):
        raise ValueError("SSOD CSV 缺少必要字段。")
    location = _request_location(request)
    year = int(request.get("station_year", _parse_request_time(request["start_date"], "request.start_date").year))
    expected = _expected_dates(request)
    source_id = f"ssod_{location['station_id']}_{year}"
    records: dict[date, tuple[dict[str, Any] | None, dict[str, Any] | None, float | None, float | None]] = {}
    grid: dict[str, float] | None = None
    for index, row in enumerate(reader):
        raw_date = str(row.get("DATE", "")).strip()
        try:
            day = _parse_date(raw_date, f"SSOD DATE[{index}]")
        except ValueError as exc:
            raise ValueError(f"SSOD 日期无效：{raw_date}") from exc
        if day in records:
            raise ValueError("SSOD 包含重复日期。")
        if day.year != year:
            raise ValueError("SSOD 年份与请求不一致。")
        station = str(row.get("STATION", "") or "").strip()
        if station != location["station_id"]:
            raise ValueError("SSOD station_id_mismatch。")
        # 现有项目 parser 负责 SSOD 测量码、哨兵、坐标和数值 QC。
        from .data_pipeline import parse_ssod_row

        complete, quarantine = parse_ssod_row(row, source_id, "live-runtime", location["station_id"], year)
        lat: float | None = None
        lon: float | None = None
        try:
            lat = _finite_number(float(row["LATITUDE"]), f"SSOD LATITUDE[{index}]", allow_none=False, minimum=-90, maximum=90)
            lon = _finite_number(float(row["LONGITUDE"]), f"SSOD LONGITUDE[{index}]", allow_none=False, minimum=-180, maximum=180)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("SSOD站点坐标无效，保留上次有效缓存。") from exc
        if lat is not None and lon is not None:
            if abs(lat - float(location["latitude"])) > STATION_TOLERANCE_DEGREES or abs(lon - float(location["longitude"])) > STATION_TOLERANCE_DEGREES:
                raise ValueError("SSOD 站点坐标差异过大。")
            if grid is None:
                grid = {"latitude": lat, "longitude": lon}
        rain = complete.get("observed_rain_mm") if complete else None
        reason = "complete_reference" if complete else str((quarantine or {}).get("reason") or "not_complete_reference")
        records[day] = complete, quarantine, rain, lat if lon is not None else None
        # 将原因和经度临时附在 quarantine 中，避免改变 parse_ssod_row 的返回接口。
        if quarantine is not None:
            quarantine["_live_reason"] = reason
            quarantine["_live_lon"] = lon
    rows: list[dict[str, Any]] = []
    for day in expected:
        item = records.get(day)
        if item is None:
            rows.append(_row(day, rain=None, temperature=None, humidity=None, hours_present=None, hours_expected=None, reason="missing_report"))
        else:
            complete, quarantine, rain, _ = item
            if complete is not None:
                rows.append(_row(day, rain=float(rain) if rain is not None else None, temperature=None, humidity=None, hours_present=None, hours_expected=None, reason="complete_reference"))
            else:
                reason = str((quarantine or {}).get("_live_reason") or "not_complete_reference")
                partial = _row(day, rain=None, temperature=None, humidity=None, hours_present=None, hours_expected=None, reason=reason)
                # CSV 中有该日 SSOD 报告但总量/测量码不完整时，这是“有
                # 记录的缺测”，不能和完全没有该日行的 missing 混淆。
                partial["status"] = "partial"
                rows.append(partial)
    if grid is None:
        grid = {"latitude": float(location["latitude"]), "longitude": float(location["longitude"])}
    return _snapshot(request, fetched, raw, rows, grid)


def parse_payload(raw: bytes, request: Mapping[str, Any], retrieved_at_utc: str) -> dict[str, Any]:
    """严格解析一份来源响应为标准 snapshot。

    解析不会把缺失小时或不完整 SSOD 测量码补成 0。Forecast/Archive 的
    无降水覆盖响应可以被表示为全 ``missing`` snapshot，但
    :func:`fetch_snapshot` 会阻止它覆盖已有有效缓存；Station 则允许这种
    结构有效但全缺雨的 snapshot，用于显示当前站点缺测状态。
    """

    if not isinstance(request, Mapping):
        raise TypeError("request 必须是映射。")
    product = _request_product(request)
    if not str(request.get("request_url", "")):
        raise ValueError("request.request_url 不能为空。")
    _request_location(request)
    _expected_dates(request)
    if product == "station":
        return _parse_station(raw, request, retrieved_at_utc)
    body = _load_json(raw)
    if body.get("error"):
        raise ValueError("接口返回错误：" + str(body.get("reason", "unknown")))
    if product == "forecast":
        return _parse_forecast(body, request, raw, retrieved_at_utc)
    return _parse_archive(body, request, raw, retrieved_at_utc)


def _cache_dir(root: Path, location_key: str, product: str) -> Path:
    return Path(root) / "runtime" / "weather" / location_key / product


def _ttl(product: str) -> timedelta:
    return {"forecast": FORECAST_TTL, "archive": ARCHIVE_TTL, "station": STATION_TTL}[product]


def _cache_result(status: str, snapshot: dict[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    return {"status": status, "snapshot": snapshot, "error": error}


def _safe_cache_file(directory: Path, filename: Any, pattern: re.Pattern[str]) -> Path:
    """只允许 index 指向当前缓存目录内的内容寻址文件。"""

    if not isinstance(filename, str) or Path(filename).name != filename or not pattern.fullmatch(filename):
        raise ValueError("缓存文件名不是受支持的内容寻址名称。")
    base = directory.resolve()
    candidate = (directory / filename).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise ValueError("缓存文件路径越出缓存目录。") from exc
    return candidate


def _query_value(query: Mapping[str, list[str]], name: str) -> str:
    values = query.get(name)
    if values is None or len(values) != 1:
        raise ValueError(f"缓存 request 缺少固定 URL 参数 {name}。")
    return values[0]


def _validate_cached_request(request: Mapping[str, Any], location_key: str, product: str) -> None:
    """校验 index 中的 request 没有被改成任意外部地址或日期窗口。"""

    if request.get("product") != product or request.get("location_key") != location_key:
        raise ValueError("缓存 request 身份不一致。")
    _request_location(request)
    _request_product(request)
    actual_dates = request.get("expected_dates")
    boundary_request = dict(request)
    boundary_request.pop("expected_dates", None)
    # make_request 的 start_date/end_date 是 UTC 半开边界；历史 helper 对
    # archive/station 的无显式 expected_dates 请求按 API 包含日解释，因此
    # 将结束边界退回一日后再交给它，得到与 index 中日期列表相同的窗口。
    if product != "forecast":
        boundary_start = _parse_request_time(boundary_request.get("start_date"), "request.start_date")
        boundary_end = _parse_request_time(boundary_request.get("end_date"), "request.end_date")
        if boundary_end == boundary_start:
            expected = []
        else:
            boundary_request["end_date"] = _iso(boundary_end - timedelta(days=1))
            expected = _expected_dates(boundary_request)
    else:
        expected = _expected_dates(boundary_request)
    if actual_dates != [_date_iso(item) for item in expected]:
        raise ValueError("缓存 request 日期窗口与边界不一致。")
    expected_dates = [_parse_date(item, "request.expected_dates") for item in (actual_dates or [])]
    start_date = _parse_request_time(request.get("start_date"), "request.start_date").date()
    end_date = _parse_request_time(request.get("end_date"), "request.end_date").date()
    if product == "forecast":
        if request.get("requested_model") != MODEL or request.get("api_start_date") != _date_iso(start_date - timedelta(days=1)) or request.get("api_end_date") != _date_iso(end_date):
            raise ValueError("缓存 Forecast 日期或模型语义被篡改。")
    elif product == "archive":
        if request.get("requested_model") != ARCHIVE_MODEL:
            raise ValueError("缓存 Archive 模型语义被篡改。")
        expected_start = expected_dates[0] if expected_dates else start_date
        expected_end = expected_dates[-1] if expected_dates else start_date - timedelta(days=1)
        if request.get("api_start_date") != _date_iso(expected_start) or request.get("api_end_date") != _date_iso(expected_end):
            raise ValueError("缓存 Archive 日期语义被篡改。")
    else:
        expected_start = expected_dates[0] if expected_dates else start_date
        expected_end = expected_dates[-1] if expected_dates else start_date - timedelta(days=1)
        if request.get("station_year") != start_date.year or request.get("api_start_date") != _date_iso(expected_start) or request.get("api_end_date") != _date_iso(expected_end):
            raise ValueError("缓存 Station 日期语义被篡改。")
    url = request.get("request_url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("缓存 request URL 必须是 HTTPS 官方地址。")
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    location = _location(location_key)
    if product == "forecast":
        if parsed.netloc != "api.open-meteo.com" or parsed.path != "/v1/forecast":
            raise ValueError("缓存 request URL 不是固定 Forecast 官方地址。")
        fixed = {
            "latitude": str(location["latitude"]),
            "longitude": str(location["longitude"]),
            "hourly": "precipitation,temperature_2m,relative_humidity_2m",
            "models": MODEL,
            "timezone": "UTC",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
            "forecast_days": "9",
        }
        if set(query) != set(fixed):
            raise ValueError("缓存 Forecast URL 参数集合被篡改。")
        for name, value in fixed.items():
            if _query_value(query, name) != value:
                raise ValueError(f"缓存 Forecast URL 参数 {name} 被篡改。")
    elif product == "archive":
        if parsed.netloc != "archive-api.open-meteo.com" or parsed.path != "/v1/archive":
            raise ValueError("缓存 request URL 不是固定 Archive 官方地址。")
        fixed = {
            "latitude": str(location["latitude"]),
            "longitude": str(location["longitude"]),
            "daily": "precipitation_sum,temperature_2m_mean",
            "models": ARCHIVE_MODEL,
            "timezone": "UTC",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
            "start_date": str(request.get("api_start_date", "")),
            "end_date": str(request.get("api_end_date", "")),
        }
        if set(query) != set(fixed):
            raise ValueError("缓存 Archive URL 参数集合被篡改。")
        for name, value in fixed.items():
            if _query_value(query, name) != value:
                raise ValueError(f"缓存 Archive URL 参数 {name} 被篡改。")
    else:
        year = request.get("station_year")
        if not isinstance(year, int):
            raise ValueError("缓存 Station request 缺少年份。")
        expected_path = f"/oa/synoptic-summary-of-the-day/v2/access/by-year/{year}/csv/SSOD_{location['station_id']}_{year}.csv"
        if parsed.netloc != "www.ncei.noaa.gov" or parsed.path != expected_path or parsed.query:
            raise ValueError("缓存 request URL 不是固定 Station 官方地址。")


def read_cached(root: str | Path, location_key: str, product: str, now: datetime | date | None = None) -> dict[str, Any]:
    """只读校验运行时缓存，并按产品 TTL 返回 cache/stale_cache。"""

    if product not in PRODUCTS:
        return _cache_result("error", None, f"未知产品：{product}")
    try:
        _location(location_key)
    except ValueError as exc:
        return _cache_result("error", None, str(exc))
    directory = _cache_dir(Path(root), location_key, product)
    index_path = directory / "index.json"
    if not index_path.exists():
        return _cache_result("empty", None, None)
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(index, dict):
            raise ValueError("缓存 index 顶层必须是对象。")
        if index.get("schema_version") != 1:
            raise ValueError("缓存 index schema_version 不受支持。")
        if index.get("location_key") != location_key or index.get("product") != product:
            raise ValueError("缓存身份与请求不一致。")
        raw_sha = index.get("raw_sha256")
        snapshot_sha = index.get("snapshot_sha256")
        if not isinstance(raw_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", raw_sha):
            raise ValueError("缓存 raw_sha256 无效。")
        if not isinstance(snapshot_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha):
            raise ValueError("缓存 snapshot_sha256 无效。")
        raw_filename = index.get("raw_file")
        snapshot_filename = index.get("snapshot_file")
        if raw_filename != f"raw-{raw_sha}.bin" or snapshot_filename != f"snapshot-{snapshot_sha}.json":
            raise ValueError("缓存文件名与内容摘要不一致。")
        raw_path = _safe_cache_file(directory, raw_filename, _RAW_FILE_RE)
        snapshot_path = _safe_cache_file(directory, snapshot_filename, _SNAPSHOT_FILE_RE)
        raw = raw_path.read_bytes()
        raw_bytes = index.get("raw_bytes")
        if isinstance(raw_bytes, bool) or not isinstance(raw_bytes, int):
            raise ValueError("缓存 raw_bytes 无效。")
        if _sha256(raw) != raw_sha or len(raw) != raw_bytes:
            raise ValueError("缓存 raw 摘要或字节数不一致。")
        snapshot_bytes = snapshot_path.read_bytes()
        if _sha256(snapshot_bytes) != snapshot_sha:
            raise ValueError("缓存 snapshot 摘要不一致。")
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError("缓存 snapshot 顶层必须是对象。")
        request = index.get("request")
        if not isinstance(request, dict):
            raise ValueError("缓存缺少原始 request。")
        _validate_cached_request(request, location_key, product)
        snapshot_location = snapshot.get("location")
        if not isinstance(snapshot_location, Mapping):
            raise ValueError("缓存 snapshot location 无效。")
        if index.get("raw_url") != request.get("request_url") or snapshot.get("request_url") != request.get("request_url"):
            raise ValueError("缓存来源 URL 身份不一致。")
        if index.get("fetched_at_utc") != snapshot.get("fetched_at_utc"):
            raise ValueError("缓存 index 与 snapshot 获取时间不一致。")
        if snapshot.get("schema_version") != 1 or snapshot.get("product") != product or snapshot_location.get("key") != location_key:
            raise ValueError("缓存 snapshot 身份或 schema_version 不一致。")
        reparsed = parse_payload(raw, request, str(snapshot.get("fetched_at_utc", "")))
        if _canonical(reparsed) != _canonical(snapshot):
            raise ValueError("缓存 snapshot 与 raw 重新解析结果不一致。")
        fetched = _parse_utc(snapshot.get("fetched_at_utc"), "snapshot.fetched_at_utc")
        age = _utc_datetime(now) - fetched
        if age < -timedelta(minutes=5):
            raise ValueError("缓存 fetched_at_utc 超过当前时间 5 分钟，拒绝作为新鲜缓存。")
        status = "cache" if age <= _ttl(product) else "stale_cache"
        return _cache_result(status, snapshot, None)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return _cache_result("error", None, f"缓存损坏：{exc}")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_immutable(path: Path, data: bytes) -> None:
    """写入内容寻址对象；同名对象存在时只验证，不覆盖。"""

    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"不可变缓存对象已存在但内容不一致：{path.name}")
        return
    _atomic_write(path, data)


def _write_cache(root: Path, request: Mapping[str, Any], snapshot: dict[str, Any], raw: bytes) -> None:
    location_key = str(request["location_key"])
    product = str(request["product"])
    directory = _cache_dir(root, location_key, product)
    snapshot_bytes = _json_bytes(snapshot)
    raw_sha = _sha256(raw)
    snapshot_sha = _sha256(snapshot_bytes)
    raw_file = f"raw-{raw_sha}.bin"
    snapshot_file = f"snapshot-{snapshot_sha}.json"
    index = {
        "schema_version": 1,
        "location_key": location_key,
        "product": product,
        "raw_file": raw_file,
        "snapshot_file": snapshot_file,
        "raw_url": request["request_url"],
        "raw_sha256": raw_sha,
        "raw_bytes": len(raw),
        "snapshot_sha256": snapshot_sha,
        "fetched_at_utc": snapshot["fetched_at_utc"],
        "request": dict(request),
    }
    # raw/snapshot 是内容寻址且不可变；index 最后替换。若写 index 前进程
    # 中断，旧 index 仍指向旧对象，旧有效缓存不会被新字节覆盖。
    _write_immutable(directory / raw_file, bytes(raw))
    _write_immutable(directory / snapshot_file, snapshot_bytes)
    _atomic_write(directory / "index.json", _json_bytes(index))


def _default_http_get(url: str, timeout: tuple[int, int] = HTTP_TIMEOUT) -> Any:
    import requests

    return requests.get(url, timeout=timeout)


def _response_parts(response: Any) -> tuple[int, bytes, Mapping[str, Any]]:
    if isinstance(response, (bytes, bytearray)):
        return 200, bytes(response), {}
    if isinstance(response, tuple):
        if len(response) == 3:
            status, content, headers = response
            return int(status), bytes(content), dict(headers or {})
        if len(response) == 2:
            status, content = response
            if isinstance(status, int):
                return int(status), bytes(content), {}
    if isinstance(response, Mapping):
        status = response.get("status_code", response.get("status", 200))
        content = response.get("content", response.get("body", b""))
        if isinstance(content, Mapping):
            content = _json_bytes(content)
        if isinstance(content, str):
            content = content.encode("utf-8")
        return int(status), bytes(content), dict(response.get("headers", {}) or {})
    status = int(getattr(response, "status_code", 200))
    content = getattr(response, "content", None)
    if content is None:
        text = getattr(response, "text", "")
        content = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    return status, bytes(content), dict(getattr(response, "headers", {}) or {})


def _invoke_http_get(getter: Callable[..., Any], url: str) -> Any:
    """在不重试请求的前提下兼容 ``getter(url)`` 与 ``getter(url, timeout=...)``。"""

    try:
        signature = inspect.signature(getter)
    except (TypeError, ValueError):
        return getter(url, timeout=HTTP_TIMEOUT)
    parameters = signature.parameters.values()
    accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in parameters)
    accepts_timeout = "timeout" in signature.parameters or accepts_kwargs
    if accepts_timeout:
        return getter(url, timeout=HTTP_TIMEOUT)
    return getter(url)


def _usable_snapshot(snapshot: dict[str, Any], product: str) -> bool:
    if product == "station":
        # SSOD 全部为 I/缺雨时仍是有价值的缺测监测结果。
        return True
    return any(row.get("rain_mm") is not None for row in snapshot.get("rows", []))


def fetch_snapshot(
    root: str | Path,
    location_key: str,
    product: str,
    *,
    force: bool = True,
    now: datetime | date | None = None,
    http_get: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """抓取并缓存一份来源，失败时保留旧 snapshot。

    ``http_get`` 接收 ``(url, timeout=(5, 20))``，可返回 requests.Response、
    ``(status, bytes, headers)`` 或原始 bytes。429 不重试，只返回可读错误。
    """

    if product not in PRODUCTS:
        return _cache_result("error", None, f"未知产品：{product}")
    try:
        _location(location_key)
    except ValueError as exc:
        return _cache_result("error", None, str(exc))
    root_path = Path(root)
    cached = read_cached(root_path, location_key, product, now=now)
    if not force and cached["status"] == "cache":
        return cached
    request = make_request(location_key, product, now=now)
    getter = http_get or _default_http_get
    try:
        response = _invoke_http_get(getter, request["request_url"])
        status, raw, headers = _response_parts(response)
        content_length = headers.get("Content-Length") or headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_RESPONSE_BYTES:
                    raise RuntimeError("HTTP 响应超过4MB上限。")
            except (TypeError, ValueError):
                # 无法解析的 Content-Length 不能代替实际字节长度校验；
                # 继续以 materialized response 的真实长度为准。
                pass
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("HTTP 响应超过4MB上限。")
        if status == 429:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
            suffix = f"；Retry-After={retry_after}" if retry_after else ""
            raise RuntimeError(f"HTTP 429：来源限流，未重试{suffix}；已保留旧缓存。")
        if status < 200 or status >= 300:
            raise RuntimeError(f"HTTP {status}：来源请求失败。")
        fetched = _iso(_utc_datetime(now) if now is not None else datetime.now(UTC))
        snapshot = parse_payload(raw, request, fetched)
        if not _usable_snapshot(snapshot, product):
            raise ValueError("响应没有有效降水覆盖，禁止覆盖已有缓存。")
        _write_cache(root_path, request, snapshot, raw)
        return _cache_result("updated", snapshot, None)
    except Exception as exc:  # 保留缓存边界，避免网络异常破坏页面。
        error = str(exc) or exc.__class__.__name__
        if cached.get("snapshot") is not None:
            # 返回缓存状态并同时带 error，调用方可以区分“显示旧数据”和“刷新失败”。
            return _cache_result(cached["status"] if cached["status"] in {"cache", "stale_cache"} else "error", cached["snapshot"], error)
        return _cache_result("error", None, error)


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="刷新梅雨有数运行时天气来源缓存。")
    parser.add_argument("refresh", nargs="?", choices=["refresh"], default="refresh")
    parser.add_argument("--location", choices=sorted(LOCATIONS), required=True)
    parser.add_argument("--product", choices=[*PRODUCTS, "all"], required=True)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--no-force", action="store_true", help="有效缓存内不发起请求")
    args = parser.parse_args(argv)
    products = PRODUCTS if args.product == "all" else (args.product,)
    results = {
        product: fetch_snapshot(args.root, args.location, product, force=not args.no_force)
        for product in products
    }
    print(json.dumps({"location": args.location, "results": results}, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if all(result["status"] in {"updated", "cache", "stale_cache"} for result in results.values()) else 1


if __name__ == "__main__":  # pragma: no cover - CLI smoke is covered separately.
    raise SystemExit(_cli())
