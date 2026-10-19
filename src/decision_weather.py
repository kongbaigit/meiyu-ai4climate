"""运行时决策天气后端。

本模块只保存 ``runtime/decision_weather/<location>/`` 下的内容寻址缓存。
数据来自 Open-Meteo Ensemble API 的 ECMWF IFS 0.25° ensemble；这里的
``probability`` 是完整成员中满足 24 小时累计降水 ``>=25 mm`` 的成员
比例，是未经校准的集合情景估计，不是货损概率。

Open-Meteo 的 ``precipitation`` 按前一小时结束时刻标记，因此一个
``[start_utc, end_utc)`` 窗口使用 API 时间标签 ``(start_utc, end_utc]``。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import tempfile
import threading
import time as time_module
from typing import Any, Mapping
from urllib.parse import parse_qs, urlencode, urlparse
from zoneinfo import ZoneInfo

import requests

from src.live_data import LOCATIONS


UTC = timezone.utc
BEIJING = ZoneInfo("Asia/Shanghai")
ENDPOINT = "https://ensemble-api.open-meteo.com/v1/ensemble"
MODEL = "ecmwf_ifs025"
MODEL_LABEL = "ECMWF IFS 0.25° ensemble"
SOURCE = "Open-Meteo/ECMWF IFS 0.25° ensemble"
SOURCE_DOCUMENTATION_URL = "https://open-meteo.com/en/docs/ensemble-api"
SOURCE_CODE_DOCUMENTATION_URL = "https://github.com/open-meteo/open-meteo/blob/main/Sources/App/Ecmwf/EcmwfDomain.swift"
CONTROL_MEMBER_DOCUMENTATION_URL = "https://github.com/open-meteo/open-meteo/discussions/366"
PROBABILITY_KIND = "ensemble_member_fraction_uncalibrated"
EVENT_THRESHOLD_MM = 25
CONTROL_MEMBER_ID = "member00"
PERTURBED_MEMBER_IDS = tuple(f"member{i:02d}" for i in range(1, 51))
MEMBER_IDS = (CONTROL_MEMBER_ID, *PERTURBED_MEMBER_IDS)
EXPECTED_MEMBERS = len(MEMBER_IDS)
# Open-Meteo serialises the control forecast as ``hourly.precipitation`` and
# only numbers the 50 perturbed forecasts. Keep the public numbered field list
# stable while exposing the control mapping through member_definition metadata.
CONTROL_MEMBER_FIELD = "precipitation"
MEMBER_FIELDS = tuple(f"precipitation_{member}" for member in PERTURBED_MEMBER_IDS)
ALL_MEMBER_FIELDS = (CONTROL_MEMBER_FIELD, *MEMBER_FIELDS)
MEMBER_DEFINITION = {
    "control_member": CONTROL_MEMBER_ID,
    "control_field": CONTROL_MEMBER_FIELD,
    "perturbed_members": "member01..member50",
    "perturbed_field_pattern": "precipitation_memberNN",
    "count": EXPECTED_MEMBERS,
}
MEMBER_FIELD_RE = re.compile(r"precipitation_member\d{2}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
GRID = {
    "hangzhou": {"latitude": 30.25, "longitude": 120.5},
    "ningbo": {"latitude": 29.75, "longitude": 121.5},
}
TTL = timedelta(hours=3)
NORMAL_REFRESH_INTERVAL = timedelta(hours=1)
MIN_RETRY_INTERVAL = timedelta(minutes=5)
HTTP_TIMEOUT = (5, 30)
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
WINDOW_COUNT = 7
WINDOW_HOURS = 24


_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _utc_datetime(value: datetime | date | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, date) and not isinstance(value, datetime):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if not isinstance(value, datetime):
        raise TypeError("now 必须是 datetime、date 或 None。")
    if value.tzinfo is None:
        # 与 src.live_data 一致：无时区时间按 UTC 解释，避免机器本地时区
        # 影响窗口边界。
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _api_hour(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def _parse_utc(value: Any, field: str, *, require_hour: bool = True) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是 UTC ISO 时间。")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} 时间无效。") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} 必须是 UTC。")
    parsed = parsed.astimezone(UTC)
    if require_hour and (parsed.minute or parsed.second or parsed.microsecond):
        raise ValueError(f"{field} 必须是整点 UTC。")
    return parsed


def _parse_api_hour(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是字符串。")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field} 时间无效。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    elif parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} 必须是 UTC。")
    parsed = parsed.astimezone(UTC)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise ValueError(f"{field} 必须是唯一整点。")
    return parsed


def _finite_nonnegative(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} 必须是非负有限数或 null。")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} 必须是非负有限数。")
    return number


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"JSON 含非有限数值 {value}。")


def _load_json(raw: bytes) -> dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise TypeError("响应必须是 bytes。")
    try:
        body = json.loads(bytes(raw).decode("utf-8"), parse_constant=_reject_json_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"响应 JSON 无效：{exc}") from exc
    if not isinstance(body, dict):
        raise ValueError("响应顶层必须是对象。")
    return body


def _json_bytes(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无法生成有限 JSON：{exc}") from exc


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"对象不可序列化：{exc}") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _location(location_key: str) -> dict[str, Any]:
    try:
        location = dict(LOCATIONS[location_key])
    except KeyError as exc:
        raise ValueError(f"未知位置：{location_key}。可选值为 {sorted(LOCATIONS)}。") from exc
    if location_key not in GRID:
        raise ValueError(f"位置 {location_key} 缺少固定 ensemble 网格。")
    return location


def _window_specs(now: datetime | date | None) -> list[dict[str, str]]:
    current = _utc_datetime(now)
    local_date = current.astimezone(BEIJING).date() + timedelta(days=1)
    first_local = datetime.combine(local_date, time(8), tzinfo=BEIJING)
    first = first_local.astimezone(UTC)
    return [
        {"start_utc": _iso(first + timedelta(days=index)), "end_utc": _iso(first + timedelta(days=index + 1))}
        for index in range(WINDOW_COUNT)
    ]


def _window_datetimes(windows: list[Mapping[str, Any]]) -> list[tuple[datetime, datetime]]:
    if not isinstance(windows, list) or len(windows) != WINDOW_COUNT:
        raise ValueError("窗口数量必须是 7。")
    parsed: list[tuple[datetime, datetime]] = []
    for index, window in enumerate(windows):
        if not isinstance(window, Mapping):
            raise ValueError(f"窗口 {index} 无效。")
        start = _parse_utc(window.get("start_utc"), f"windows[{index}].start_utc")
        end = _parse_utc(window.get("end_utc"), f"windows[{index}].end_utc")
        if end - start != timedelta(hours=WINDOW_HOURS):
            raise ValueError(f"窗口 {index} 必须恰好 24 小时。")
        if parsed and start != parsed[-1][1]:
            raise ValueError("窗口必须连续且升序。")
        parsed.append((start, end))
    return parsed


def _request_url(location_key: str, windows: list[Mapping[str, Any]]) -> str:
    location = _location(location_key)
    parsed_windows = _window_datetimes(list(windows))
    first_start = parsed_windows[0][0]
    last_end = parsed_windows[-1][1]
    params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "models": MODEL,
        "hourly": "precipitation",
        "start_hour": _api_hour(first_start + timedelta(hours=1)),
        "end_hour": _api_hour(last_end),
        "timezone": "UTC",
        "timeformat": "iso8601",
        "precipitation_unit": "mm",
        "cell_selection": "nearest",
    }
    return ENDPOINT + "?" + urlencode(params)


def make_request(location_key: str, now: datetime | date | None = None) -> dict[str, Any]:
    """生成固定窗口的请求元数据，不执行网络请求。

    前端或诊断工具可以复用这里的窗口、成员身份和官方 URL 口径。
    """

    _location(location_key)
    windows = _window_specs(now)
    return {
        "location_key": location_key,
        "location": _location(location_key),
        "source": SOURCE,
        "model": MODEL,
        "expected_members": EXPECTED_MEMBERS,
        "member_fields": list(MEMBER_FIELDS),
        "all_member_fields": list(ALL_MEMBER_FIELDS),
        "member_definition": deepcopy(MEMBER_DEFINITION),
        "precipitation_time_semantics": "preceding_hour_sum; aggregate window uses (start_utc,end_utc] labels",
        "windows": windows,
        "request_url": _request_url(location_key, windows),
    }


def _query_one(query: Mapping[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values or len(values) != 1:
        raise ValueError(f"缓存请求参数 {key} 无效。")
    return values[0]


def _validate_url(url: str, location_key: str, windows: list[Mapping[str, Any]]) -> None:
    expected_url = _request_url(location_key, windows)
    if url != expected_url:
        raise ValueError("缓存 request_url 与固定窗口请求不一致。")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "ensemble-api.open-meteo.com" or parsed.path != "/v1/ensemble":
        raise ValueError("请求地址不是固定 Open-Meteo Ensemble 官方地址。")
    query = parse_qs(parsed.query, keep_blank_values=True)
    expected_query = parse_qs(urlparse(expected_url).query, keep_blank_values=True)
    if query != expected_query:
        raise ValueError("请求参数集合被篡改。")
    for key in expected_query:
        _query_one(query, key)


def _normalise_windows(windows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    parsed = _window_datetimes(list(windows))
    return [{"start_utc": _iso(start), "end_utc": _iso(end)} for start, end in parsed]


def _parse_payload(
    raw: bytes,
    *,
    location_key: str,
    windows: list[Mapping[str, Any]],
    request_url: str,
    fetched_at_utc: str,
) -> dict[str, Any]:
    location = _location(location_key)
    normal_windows = _normalise_windows(windows)
    _validate_url(request_url, location_key, normal_windows)
    fetched = _parse_utc(fetched_at_utc, "fetched_at_utc", require_hour=False)
    body = _load_json(raw)
    if body.get("error"):
        raise ValueError(f"接口返回错误：{body.get('reason', body.get('error'))}")

    returned_lat = _finite_nonnegative(body.get("latitude"), "响应纬度")
    returned_lon_raw = body.get("longitude")
    if isinstance(returned_lon_raw, bool) or not isinstance(returned_lon_raw, (int, float)) or not math.isfinite(float(returned_lon_raw)):
        raise ValueError("响应经度必须是有限数。")
    returned_lon = float(returned_lon_raw)
    if returned_lat is None or not -90 <= returned_lat <= 90 or not -180 <= returned_lon <= 180:
        raise ValueError("响应坐标超出范围。")
    expected_grid = GRID[location_key]
    if float(returned_lat) != float(expected_grid["latitude"]) or returned_lon != float(expected_grid["longitude"]):
        raise ValueError("响应不在固定 ensemble 网格。")
    offset = body.get("utc_offset_seconds")
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or float(offset) != 0:
        raise ValueError("响应不是 UTC。")
    if body.get("timezone") not in {"UTC", "GMT"}:
        raise ValueError("响应 timezone 不是 UTC。")

    hourly_units = body.get("hourly_units")
    hourly = body.get("hourly")
    if not isinstance(hourly_units, Mapping) or not isinstance(hourly, Mapping):
        raise ValueError("响应缺少 hourly_units 或 hourly。")
    if hourly_units.get("time") not in {"iso8601", None}:
        raise ValueError("响应时间单位不是 iso8601。")
    if hourly_units.get("precipitation") != "mm":
        raise ValueError("响应降水单位不是 mm。")
    times = hourly.get("time")
    if not isinstance(times, list):
        raise ValueError("hourly.time 必须是列表。")

    expected_hour_values: list[datetime] = []
    parsed_windows = _window_datetimes(normal_windows)
    for start, end in parsed_windows:
        expected_hour_values.extend(start + timedelta(hours=offset_hours) for offset_hours in range(1, WINDOW_HOURS + 1))
    expected_hours = set(expected_hour_values)
    time_values: list[datetime] = []
    seen: set[datetime] = set()
    for index, value in enumerate(times):
        parsed = _parse_api_hour(value, f"hourly.time[{index}]")
        if parsed in seen:
            raise ValueError("响应包含重复整点。")
        if parsed not in expected_hours:
            raise ValueError("响应时间超出固定窗口。")
        seen.add(parsed)
        time_values.append(parsed)
    if time_values != sorted(time_values):
        raise ValueError("响应整点必须按 UTC 升序。")
    by_time_index = {parsed: index for index, parsed in enumerate(time_values)}

    present_members: list[str] = []
    for key in hourly:
        if isinstance(key, str) and MEMBER_FIELD_RE.fullmatch(key):
            member = key[len("precipitation_") :]
            if member not in PERTURBED_MEMBER_IDS:
                raise ValueError(f"响应包含未知成员 {member}。")
            present_members.append(member)
    if len(set(present_members)) != len(present_members):
        raise ValueError("成员字段重复。")

    values_by_member: dict[str, dict[datetime, float | None]] = {}
    control_values = hourly.get(CONTROL_MEMBER_FIELD)
    if control_values is not None:
        if not isinstance(control_values, list):
            raise ValueError("控制成员 precipitation 必须是列表。")
        if len(control_values) > len(time_values):
            raise ValueError("控制成员 precipitation 长度超过 hourly.time。")
        indexed_control: dict[datetime, float | None] = {}
        for index, value in enumerate(control_values):
            indexed_control[time_values[index]] = _finite_nonnegative(value, f"{CONTROL_MEMBER_FIELD}[{index}]")
        values_by_member[CONTROL_MEMBER_ID] = indexed_control

    for member in present_members:
        field = f"precipitation_{member}"
        if hourly_units.get(field) != "mm":
            raise ValueError(f"{field} 单位不是 mm。")
        values = hourly.get(field)
        if not isinstance(values, list):
            raise ValueError(f"{field} 必须是列表。")
        if len(values) > len(time_values):
            raise ValueError(f"{field} 长度超过 hourly.time。")
        indexed: dict[datetime, float | None] = {}
        for index, value in enumerate(values):
            indexed[time_values[index]] = _finite_nonnegative(value, f"{field}[{index}]")
        values_by_member[member] = indexed

    window_outputs: list[dict[str, Any]] = []
    for start, end in parsed_windows:
        expected_hours_for_window = [start + timedelta(hours=offset_hours) for offset_hours in range(1, WINDOW_HOURS + 1)]
        totals: list[float] = []
        valid_counts: list[int] = []
        for member in MEMBER_IDS:
            member_values = values_by_member.get(member, {})
            values = [member_values.get(hour) for hour in expected_hours_for_window]
            numeric_values = [value for value in values if value is not None]
            valid_counts.append(len(numeric_values))
            if len(numeric_values) == WINDOW_HOURS:
                totals.append(sum(numeric_values))
        members_valid = len(totals)
        hours_min = min(valid_counts) if valid_counts else 0
        complete = members_valid == EXPECTED_MEMBERS and hours_min == WINDOW_HOURS
        event_members = sum(total >= EVENT_THRESHOLD_MM for total in totals) if totals else None
        probability = (event_members / EXPECTED_MEMBERS) if complete and event_members is not None else None
        window_outputs.append(
            {
                "start_utc": _iso(start),
                "end_utc": _iso(end),
                "probability": probability if probability is not None else None,
                "complete": complete,
                "members_valid": members_valid,
                "members_expected": EXPECTED_MEMBERS,
                "hours_min": hours_min,
                "hours_expected": WINDOW_HOURS,
                "event_members": event_members,
                "rain_median_mm": round(float(statistics.median(totals)), 3) if totals else None,
                "rain_min_mm": round(float(min(totals)), 3) if totals else None,
                "rain_max_mm": round(float(max(totals)), 3) if totals else None,
            }
        )

    return {
        "schema_version": 1,
        "location_key": location_key,
        "location": location,
        "source": SOURCE,
        "request_url": request_url,
        "fetched_at_utc": _iso(fetched),
        "raw_sha256": _sha256(bytes(raw)),
        "probability_kind": PROBABILITY_KIND,
        "event_threshold_mm": EVENT_THRESHOLD_MM,
        "expected_members": EXPECTED_MEMBERS,
        "member_definition": deepcopy(MEMBER_DEFINITION),
        "windows": window_outputs,
    }


def parse_payload(
    raw: bytes,
    location_key: str,
    *,
    now: datetime | date | None = None,
    request_url: str | None = None,
) -> dict[str, Any]:
    """解析一份 API 原始响应，供测试和只读诊断使用。"""

    windows = _window_specs(now)
    url = request_url or _request_url(location_key, windows)
    fetched = _iso(_utc_datetime(now)) if now is not None else _iso(datetime.now(UTC))
    return _parse_payload(raw, location_key=location_key, windows=windows, request_url=url, fetched_at_utc=fetched)


def _cache_dir(root: str | Path, location_key: str) -> Path:
    return Path(root) / "runtime" / "decision_weather" / location_key


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 不把目标文件名带进临时文件名。Windows 的 MAX_PATH 会在较深的
    # pytest/工作区目录下先被长 snapshot 文件名触发，导致 os.replace
    # 抛出“找不到文件”；临时文件只需在同一目录内唯一即可。
    descriptor, temporary = tempfile.mkstemp(prefix=".tmp-", suffix=".tmp", dir=str(path.parent))
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
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"不可变缓存对象内容不一致：{path.name}")
        return
    _atomic_write(path, data)


def _base_index(location_key: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "location_key": location_key,
        "raw_file": None,
        "snapshot_file": None,
        "raw_sha256": None,
        "snapshot_sha256": None,
        "fetched_at_utc": None,
        "request_url": None,
        "last_attempt_utc": None,
        "last_attempt_status": None,
        "last_error": None,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _verify_cached_snapshot(root: str | Path, location_key: str, now: datetime) -> dict[str, Any]:
    directory = _cache_dir(root, location_key)
    index_path = directory / "current.json"
    if not index_path.exists():
        return {"state": "missing", "snapshot": None, "index": _base_index(location_key), "error": None, "age": None}
    try:
        index = _read_json(index_path)
        if not isinstance(index, dict):
            raise ValueError("current index 顶层必须是对象。")
        if index.get("schema_version") != 1 or index.get("location_key") != location_key:
            raise ValueError("current index 身份或 schema_version 无效。")
        raw_sha = index.get("raw_sha256")
        snapshot_sha = index.get("snapshot_sha256")
        raw_file = index.get("raw_file")
        snapshot_file = index.get("snapshot_file")
        if not isinstance(raw_sha, str) or not SHA256_RE.fullmatch(raw_sha) or raw_file != f"raw-{raw_sha}.bin":
            raise ValueError("current index raw 摘要或文件名无效。")
        if not isinstance(snapshot_sha, str) or not SHA256_RE.fullmatch(snapshot_sha) or snapshot_file != f"snapshot-{snapshot_sha}.json":
            raise ValueError("current index snapshot 摘要或文件名无效。")
        raw_path = directory / raw_file
        snapshot_path = directory / snapshot_file
        if raw_path.parent != directory or snapshot_path.parent != directory:
            raise ValueError("缓存文件路径越界。")
        raw = raw_path.read_bytes()
        snapshot_bytes = snapshot_path.read_bytes()
        if _sha256(raw) != raw_sha:
            raise ValueError("原始响应 SHA 不一致。")
        if _sha256(snapshot_bytes) != snapshot_sha:
            raise ValueError("snapshot SHA 不一致。")
        snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        if not isinstance(snapshot, dict):
            raise ValueError("snapshot 顶层必须是对象。")
        if snapshot.get("schema_version") != 1 or snapshot.get("location_key") != location_key:
            raise ValueError("snapshot 身份或 schema_version 无效。")
        if snapshot.get("location") != _location(location_key):
            raise ValueError("snapshot 位置与固定位置不一致。")
        if snapshot.get("raw_sha256") != raw_sha:
            raise ValueError("snapshot raw_sha256 不一致。")
        fetched_text = snapshot.get("fetched_at_utc")
        fetched = _parse_utc(fetched_text, "snapshot.fetched_at_utc", require_hour=False)
        windows = snapshot.get("windows")
        parsed_windows = _window_datetimes(windows)
        normal_windows = _normalise_windows(windows)
        request_url = snapshot.get("request_url")
        if not isinstance(request_url, str):
            raise ValueError("snapshot request_url 无效。")
        _validate_url(request_url, location_key, normal_windows)
        if index.get("request_url") != request_url or index.get("fetched_at_utc") != fetched_text:
            raise ValueError("current index 与 snapshot 来源不一致。")
        reparsed = _parse_payload(
            raw,
            location_key=location_key,
            windows=normal_windows,
            request_url=request_url,
            fetched_at_utc=fetched_text,
        )
        if _canonical(reparsed) != _canonical(snapshot):
            raise ValueError("snapshot 与原始响应重新解析结果不一致。")
        age = now - fetched
        if age < -MIN_RETRY_INTERVAL:
            raise ValueError("snapshot 获取时间超过当前时间，拒绝使用。")
        return {"state": "valid", "snapshot": snapshot, "index": index, "error": None, "age": age}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        try:
            index = _read_json(index_path)
            if not isinstance(index, dict):
                index = _base_index(location_key)
        except Exception:
            index = _base_index(location_key)
        return {"state": "error", "snapshot": None, "index": index, "error": f"缓存损坏：{exc}", "age": None}


def _filter_snapshot(snapshot: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    result = deepcopy(snapshot)
    windows = []
    for window in snapshot.get("windows", []):
        try:
            # 已经开始的 24 小时窗口不再作为未来窗口返回；这也避免旧
            # 缓存跨北京时间 00:00 后把进行中的窗口当成下一窗口。
            start = _parse_utc(window.get("start_utc"), "window.start_utc")
        except ValueError:
            continue
        if start > now:
            windows.append(deepcopy(window))
    result["windows"] = windows
    return result if windows else None


def _status(snapshot: dict[str, Any] | None, age: timedelta | None, now: datetime) -> tuple[str, dict[str, Any] | None]:
    if snapshot is None:
        return "missing", None
    filtered = _filter_snapshot(snapshot, now)
    if filtered is None:
        return "missing", None
    if any(not window.get("complete", False) for window in filtered["windows"]):
        return "partial", filtered
    return ("fresh" if age is not None and age <= TTL else "stale"), filtered


def _snapshot_matches_current_windows(snapshot: Mapping[str, Any], now: datetime) -> bool:
    """判断缓存是否仍对应当前北京时间日期的七个未来窗口。"""

    try:
        actual = _normalise_windows(snapshot.get("windows"))
        expected = _normalise_windows(_window_specs(now))
    except (TypeError, ValueError):
        return False
    return actual == expected


def _result(status: str, snapshot: dict[str, Any] | None, error: str | None = None) -> dict[str, Any]:
    return {"status": status, "snapshot": snapshot, "error": error}


def read_weather(root: str | Path, location_key: str, now: datetime | date | None = None) -> dict[str, Any]:
    """只读并完整校验当前天气缓存，绝不发起网络请求。

    只读入口把跨北京时间日期的旧七窗口视为 ``missing``，由调用方决定
    是否显式使用 :func:`get_weather` 刷新；这样构建或离线启动不会因为
    缺缓存而隐式触网。
    """

    try:
        _location(location_key)
        current = _utc_datetime(now)
    except (TypeError, ValueError) as exc:
        return _result("error", None, str(exc))
    cache = _verify_cached_snapshot(root, location_key, current)
    if cache["state"] == "error":
        return _result("error", None, cache["error"])
    if cache["state"] == "missing":
        return _result("missing", None, None)
    if not _snapshot_matches_current_windows(cache["snapshot"], current):
        return _result("missing", None, cache["index"].get("last_error"))
    status, snapshot = _status(cache["snapshot"], cache["age"], current)
    return _result(status, snapshot, cache["index"].get("last_error"))


def read_cached(root: str | Path, location_key: str, *, now: datetime | date | None = None) -> dict[str, Any]:
    """兼容旧调用方的只读缓存别名。"""

    return read_weather(root, location_key, now=now)


def _response_parts(response: Any) -> tuple[int, bytes, Mapping[str, Any]]:
    if isinstance(response, (bytes, bytearray)):
        return 200, bytes(response), {}
    if isinstance(response, tuple):
        if len(response) == 3:
            status, content, headers = response
            return int(status), bytes(content), dict(headers or {})
        if len(response) == 2:
            status, content = response
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


def _last_attempt(index: Mapping[str, Any]) -> datetime | None:
    value = index.get("last_attempt_utc")
    if value is None:
        return None
    try:
        return _parse_utc(value, "last_attempt_utc", require_hour=False)
    except ValueError:
        return None


def _record_failure(directory: Path, index: Mapping[str, Any], now: datetime, error: str) -> None:
    updated = dict(index)
    updated.setdefault("schema_version", 1)
    updated.setdefault("location_key", directory.name)
    updated["last_attempt_utc"] = _iso(now)
    updated["last_attempt_status"] = "error"
    updated["last_error"] = error
    _atomic_write(directory / "current.json", _json_bytes(updated))


def _write_success(root: str | Path, location_key: str, snapshot: dict[str, Any], raw: bytes, now: datetime) -> None:
    directory = _cache_dir(root, location_key)
    snapshot_bytes = _json_bytes(snapshot)
    raw_sha = _sha256(raw)
    snapshot_sha = _sha256(snapshot_bytes)
    raw_file = f"raw-{raw_sha}.bin"
    snapshot_file = f"snapshot-{snapshot_sha}.json"
    _write_immutable(directory / raw_file, bytes(raw))
    _write_immutable(directory / snapshot_file, snapshot_bytes)
    index = {
        "schema_version": 1,
        "location_key": location_key,
        "raw_file": raw_file,
        "snapshot_file": snapshot_file,
        "raw_sha256": raw_sha,
        "snapshot_sha256": snapshot_sha,
        "fetched_at_utc": snapshot["fetched_at_utc"],
        "request_url": snapshot["request_url"],
        "last_attempt_utc": _iso(now),
        "last_attempt_status": "success",
        "last_error": None,
    }
    _atomic_write(directory / "current.json", _json_bytes(index))


def _complete_snapshot(snapshot: Mapping[str, Any]) -> bool:
    windows = snapshot.get("windows")
    return (
        isinstance(windows, list)
        and len(windows) == WINDOW_COUNT
        and all(isinstance(window, Mapping) and window.get("complete") is True for window in windows)
    )


def _fetch_and_parse(root: str | Path, location_key: str, windows: list[dict[str, str]], now: datetime) -> dict[str, Any]:
    url = _request_url(location_key, windows)
    response = requests.get(url, timeout=HTTP_TIMEOUT)
    status, raw, headers = _response_parts(response)
    content_length = headers.get("Content-Length") or headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise RuntimeError("HTTP 响应超过 8MB 上限。")
        except (TypeError, ValueError):
            pass
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("HTTP 响应超过 8MB 上限。")
    if status == 429:
        retry_after = headers.get("Retry-After") or headers.get("retry-after")
        suffix = f"；Retry-After={retry_after}" if retry_after else ""
        raise RuntimeError(f"HTTP 429：来源限流，未重试{suffix}。")
    if status < 200 or status >= 300:
        raise RuntimeError(f"HTTP {status}：来源请求失败。")
    snapshot = _parse_payload(
        raw,
        location_key=location_key,
        windows=windows,
        request_url=url,
        fetched_at_utc=_iso(now),
    )
    return {"snapshot": snapshot, "raw": raw}


def get_weather(
    root: str | Path,
    location_key: str,
    *,
    now: datetime | date | None = None,
    refresh: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """返回一个位置的未来天气情景窗口，并按需刷新。

    缺少缓存时会自动尝试首次抓取。已有缓存只有在 ``refresh=True`` 且
    已到每小时正常刷新间隔，或 ``force=True`` 的手动刷新时才请求网络。
    ``force`` 不会在 ``refresh=False`` 时生效。
    """

    try:
        _location(location_key)
        current = _utc_datetime(now)
    except (TypeError, ValueError) as exc:
        return _result("error", None, str(exc))
    with _location_lock(location_key):
        cache = _verify_cached_snapshot(root, location_key, current)
        cache_snapshot = cache.get("snapshot") if cache["state"] == "valid" else None
        windows_match = bool(cache_snapshot is not None and _snapshot_matches_current_windows(cache_snapshot, current))
        # 跨北京时间 00:00 后，即使旧缓存尚未过 TTL，也必须按新的本地
        # 日期重新请求；旧窗口不能作为当前未来窗口返回。
        fallback_snapshot = cache_snapshot if windows_match else None
        if fallback_snapshot is not None:
            cache_status, cache_view = _status(fallback_snapshot, cache.get("age"), current)
        else:
            cache_status, cache_view = ("missing", None)
        index = cache.get("index") or _base_index(location_key)
        last_error = index.get("last_error")
        if not isinstance(last_error, str):
            last_error = None
        manual_force = bool(force and refresh)
        should_fetch = False
        if cache["state"] == "missing":
            should_fetch = True
        elif cache["state"] == "error":
            should_fetch = bool(refresh)
        elif not windows_match:
            should_fetch = True
        elif refresh:
            age = cache.get("age")
            should_fetch = bool(manual_force or age is None or age >= NORMAL_REFRESH_INTERVAL)
        if should_fetch and not manual_force:
            attempt = _last_attempt(index)
            if attempt is not None and current - attempt < MIN_RETRY_INTERVAL:
                message = last_error or "5 分钟内已有一次失败尝试，暂不重试。"
                if fallback_snapshot is not None:
                    return _result(cache_status, cache_view, message)
                return _result("error", None, message)
        if not should_fetch:
            if cache["state"] == "error":
                return _result("error", None, last_error or cache.get("error"))
            return _result(cache_status, cache_view, last_error)

        windows = _window_specs(current)
        try:
            fetched = _fetch_and_parse(root, location_key, windows, current)
            incoming = fetched["snapshot"]
            if fallback_snapshot is not None and _complete_snapshot(fallback_snapshot) and not _complete_snapshot(incoming):
                raise ValueError("响应缺少预期成员或小时，已保留有效缓存。")
            _write_success(root, location_key, incoming, fetched["raw"], current)
            status, view = _status(incoming, timedelta(0), current)
            return _result(status, view, None)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            directory = _cache_dir(root, location_key)
            try:
                _record_failure(directory, index, current, error)
            except Exception as write_exc:
                error = f"{error}；记录失败：{write_exc}"
            if fallback_snapshot is not None:
                return _result(cache_status, cache_view, error)
            return _result("error", None, error)


def _location_lock(location_key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(location_key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[location_key] = lock
        return lock


def _write_worker_status(root: str | Path, location_key: str, status: dict[str, Any]) -> None:
    directory = _cache_dir(root, location_key)
    _atomic_write(directory / "worker.json", _json_bytes(status))


def _cli(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="刷新决策天气 ensemble 缓存。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--location", choices=sorted(LOCATIONS), required=True)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    result = get_weather(args.root, args.location, refresh=args.refresh or args.force, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in {"fresh", "stale", "partial"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())

