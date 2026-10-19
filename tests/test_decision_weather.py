from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.decision_weather as weather
import src.weather_worker as worker


UTC = timezone.utc
NOW = datetime(2026, 10, 19, 23, tzinfo=UTC)


def _times(now: datetime) -> list[datetime]:
    windows = weather._window_specs(now)
    start = weather._parse_utc(windows[0]["start_utc"], "start")
    end = weather._parse_utc(windows[-1]["end_utc"], "end")
    return [start + timedelta(hours=offset) for offset in range(1, int((end - start).total_seconds() // 3600) + 1)]


def _body(
    now: datetime,
    *,
    missing_member: str | None = None,
    missing_hour: int | None = None,
    unit: str = "mm",
    latitude: float = 30.25,
    longitude: float = 120.5,
) -> dict:
    times = _times(now)
    encoded_times = [item.strftime("%Y-%m-%dT%H:%M") for item in times]
    units = {"time": "iso8601", "precipitation": unit}
    hourly = {"time": encoded_times, "precipitation": [0.0] * len(times)}
    # ``precipitation`` is the unnumbered control member00; only the 50
    # perturbed members use numbered fields.
    for index in range(1, 51):
        member = f"member{index:02d}"
        if member == missing_member:
            continue
        field = f"precipitation_{member}"
        units[field] = unit
        # member01 exceeds 25 mm in the first window; member02 is just below.
        amount = 1.1 if index == 1 else (1.0 if index == 2 else 0.0)
        values = [amount] * len(times)
        if missing_hour is not None:
            values.pop(missing_hour)
        hourly[field] = values
    if missing_hour is not None:
        hourly["time"].pop(missing_hour)
        hourly["precipitation"].pop(missing_hour)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "hourly_units": units,
        "hourly": hourly,
    }


def _raw(body: dict) -> bytes:
    return json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _response(content: bytes, status: int = 200, headers: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(status_code=status, content=content, headers=headers or {})


def _patch_get(monkeypatch: pytest.MonkeyPatch, content: bytes, *, status: int = 200, headers: dict | None = None):
    calls: list[tuple[str, object]] = []

    def getter(url: str, timeout: object):
        calls.append((url, timeout))
        return _response(content, status=status, headers=headers)

    monkeypatch.setattr(weather.requests, "get", getter)
    return calls


def test_make_request_and_window_crosses_beijing_date():
    request = weather.make_request("hangzhou", now=NOW)
    # UTC 23:00 is Beijing next day 07:00, so tomorrow Beijing 08:00 is
    # UTC two calendar dates after NOW, not UTC tomorrow.
    assert request["windows"][0] == {"start_utc": "2026-10-21T00:00:00Z", "end_utc": "2026-10-22T00:00:00Z"}
    assert request["windows"][-1]["end_utc"] == "2026-10-28T00:00:00Z"
    assert "start_hour=2026-10-21T01%3A00" in request["request_url"]
    assert "end_hour=2026-10-28T00%3A00" in request["request_url"]
    assert request["expected_members"] == 51
    assert request["member_fields"][0] == "precipitation_member01"
    assert request["all_member_fields"][0] == "precipitation"
    assert request["member_definition"] == {
        "control_member": "member00",
        "control_field": "precipitation",
        "perturbed_members": "member01..member50",
        "perturbed_field_pattern": "precipitation_memberNN",
        "count": 51,
    }


def test_complete_members_are_aggregated_at_end_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    body = _body(NOW)
    calls = _patch_get(monkeypatch, _raw(body))
    original_atomic = weather._atomic_write

    def debug_atomic(path, data):
        try:
            return original_atomic(path, data)
        except Exception:
            print("ATOMIC_DEBUG", path, path.parent.exists(), list(path.parent.glob("*")))
            raise

    monkeypatch.setattr(weather, "_atomic_write", debug_atomic)
    result = weather.get_weather(tmp_path, "hangzhou", now=NOW)
    assert result["status"] == "fresh", result
    assert result["error"] is None
    first = result["snapshot"]["windows"][0]
    assert first["probability"] == 1 / 51
    assert first["complete"] is True
    assert first["event_members"] == 1
    assert first["members_valid"] == 51
    assert first["members_expected"] == 51
    assert first["hours_min"] == 24
    assert first["rain_min_mm"] == 0.0
    assert len(calls) == 1
    assert (tmp_path / "runtime" / "decision_weather" / "hangzhou" / "current.json").exists()


def test_missing_member_and_hour_make_window_partial_without_zero_fill():
    missing_member = weather.parse_payload(_raw(_body(NOW, missing_member="member50")), "hangzhou", now=NOW)
    member_window = missing_member["windows"][0]
    assert member_window["probability"] is None
    assert member_window["complete"] is False
    assert member_window["members_valid"] == 50
    assert member_window["members_expected"] == 51
    assert member_window["hours_min"] == 0

    missing_hour = weather.parse_payload(_raw(_body(NOW, missing_hour=4)), "hangzhou", now=NOW)
    hour_window = missing_hour["windows"][0]
    assert hour_window["probability"] is None
    assert hour_window["complete"] is False
    assert hour_window["members_valid"] == 0
    assert hour_window["hours_min"] == 23
    assert hour_window["rain_min_mm"] is None


def test_missing_control_member_is_partial_without_zero_fill():
    body = _body(NOW)
    del body["hourly"]["precipitation"]
    parsed = weather.parse_payload(_raw(body), "hangzhou", now=NOW)
    window = parsed["windows"][0]
    assert window["probability"] is None
    assert window["complete"] is False
    assert window["members_valid"] == 50
    assert window["members_expected"] == 51
    assert window["hours_min"] == 0


def test_control_member_unit_and_shape_are_checked():
    wrong_unit = _body(NOW)
    wrong_unit["hourly_units"]["precipitation"] = "inch"
    with pytest.raises(ValueError, match="降水单位"):
        weather.parse_payload(_raw(wrong_unit), "hangzhou", now=NOW)

    wrong_shape = _body(NOW)
    wrong_shape["hourly"]["precipitation"] = "not-a-list"
    with pytest.raises(ValueError, match="控制成员"):
        weather.parse_payload(_raw(wrong_shape), "hangzhou", now=NOW)


def test_wrong_unit_and_grid_do_not_replace_valid_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    good = _raw(_body(NOW))
    _patch_get(monkeypatch, good)
    first = weather.get_weather(tmp_path, "hangzhou", now=NOW)
    raw_sha = first["snapshot"]["raw_sha256"]

    _patch_get(monkeypatch, _raw(_body(NOW, unit="inch")))
    wrong_unit = weather.get_weather(tmp_path, "hangzhou", now=NOW + timedelta(hours=1), refresh=True, force=True)
    assert wrong_unit["status"] == "fresh"
    assert "单位" in wrong_unit["error"]
    assert wrong_unit["snapshot"]["raw_sha256"] == raw_sha

    _patch_get(monkeypatch, _raw(_body(NOW, latitude=30.5)))
    wrong_grid = weather.get_weather(tmp_path, "hangzhou", now=NOW + timedelta(hours=2), refresh=True, force=True)
    assert wrong_grid["status"] == "fresh"
    assert "固定 ensemble 网格" in wrong_grid["error"]
    assert wrong_grid["snapshot"]["raw_sha256"] == raw_sha


def test_cache_rechecks_raw_sha_and_reparse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw = _raw(_body(NOW))
    _patch_get(monkeypatch, raw)
    good = weather.get_weather(tmp_path, "hangzhou", now=NOW)
    cache_dir = tmp_path / "runtime" / "decision_weather" / "hangzhou"
    raw_path = next(cache_dir.glob("raw-*.bin"))
    raw_path.write_bytes(b"tampered")
    broken = weather.read_cached(tmp_path, "hangzhou", now=NOW)
    assert broken["status"] == "error"
    assert "SHA" in broken["error"]
    assert good["snapshot"] is not None


def test_fetched_and_attempt_times_allow_subhour_precision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    precise_now = NOW.replace(second=37)
    _patch_get(monkeypatch, _raw(_body(precise_now)))
    result = weather.get_weather(tmp_path, "hangzhou", now=precise_now)
    assert result["status"] == "fresh", result
    assert result["snapshot"]["fetched_at_utc"].endswith("23:00:37Z")
    cached = weather.read_cached(tmp_path, "hangzhou", now=precise_now + timedelta(seconds=1))
    assert cached["status"] == "fresh", cached
    index = json.loads((tmp_path / "runtime" / "decision_weather" / "hangzhou" / "current.json").read_text(encoding="utf-8"))
    assert index["last_attempt_utc"].endswith("23:00:37Z")


def test_read_weather_is_strictly_read_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("read_weather 不应触网")

    monkeypatch.setattr(weather.requests, "get", forbidden)
    result = weather.read_weather(tmp_path, "hangzhou", NOW)
    assert result == {"status": "missing", "snapshot": None, "error": None}


def test_failure_and_429_keep_cache_and_record_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    raw = _raw(_body(NOW))
    _patch_get(monkeypatch, raw)
    first = weather.get_weather(tmp_path, "hangzhou", now=NOW)

    calls: list[str] = []

    def failing(url: str, timeout: object):
        calls.append(url)
        return _response(b"", status=429, headers={"Retry-After": "60"})

    monkeypatch.setattr(weather.requests, "get", failing)
    limited = weather.get_weather(tmp_path, "hangzhou", now=NOW + timedelta(hours=1), refresh=True, force=True)
    assert limited["status"] == "fresh"
    assert "429" in limited["error"]
    assert limited["snapshot"]["raw_sha256"] == first["snapshot"]["raw_sha256"]
    index = json.loads((tmp_path / "runtime" / "decision_weather" / "hangzhou" / "current.json").read_text(encoding="utf-8"))
    assert "429" in index["last_error"]
    assert len(calls) == 1


def test_minimum_retry_interval_skips_second_failed_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def failing(url: str, timeout: object):
        calls.append(url)
        raise RuntimeError("network down")

    monkeypatch.setattr(weather.requests, "get", failing)
    first = weather.get_weather(tmp_path, "ningbo", now=NOW)
    second = weather.get_weather(tmp_path, "ningbo", now=NOW + timedelta(minutes=1))
    assert first["status"] == "error"
    assert second["status"] == "error"
    assert "network down" in second["error"]
    assert len(calls) == 1


def test_ttl_and_expired_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _patch_get(monkeypatch, _raw(_body(NOW)))
    fresh = weather.get_weather(tmp_path, "hangzhou", now=NOW)
    assert fresh["status"] == "fresh"
    stale = weather.read_cached(tmp_path, "hangzhou", now=NOW + timedelta(hours=4))
    assert stale["status"] == "stale"
    assert stale["snapshot"]["windows"]
    missing = weather.read_cached(tmp_path, "hangzhou", now=NOW + timedelta(days=9))
    assert missing["status"] == "missing"
    assert missing["snapshot"] is None


def test_cache_rolls_at_beijing_midnight_and_started_windows_are_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    rollover = datetime(2026, 10, 20, 16, 1, tzinfo=UTC)  # 北京 10 月 21 日 00:01
    responses = [_raw(_body(NOW)), _raw(_body(rollover))]
    calls: list[str] = []

    def getter(url: str, timeout: object):
        calls.append(url)
        return _response(responses.pop(0))

    monkeypatch.setattr(weather.requests, "get", getter)
    first = weather.get_weather(tmp_path, "hangzhou", now=NOW)
    assert first["status"] == "fresh"

    # 跨北京时间 00:00 自动生成新日期的请求，即使旧缓存还没到 3 小时 TTL。
    second = weather.get_weather(tmp_path, "hangzhou", now=rollover)
    assert second["status"] == "fresh", second
    assert len(calls) == 2
    assert second["snapshot"]["windows"][0]["start_utc"] == "2026-10-22T00:00:00Z"
    assert "start_hour=2026-10-22T01%3A00" in calls[1]

    # 窗口开始后不再作为未来窗口返回。
    during_now = rollover + timedelta(days=1, hours=9)
    during = weather.read_cached(tmp_path, "hangzhou", now=during_now)
    assert during["status"] == "missing"
    filtered_status, filtered = weather._status(second["snapshot"], timedelta(hours=1), during_now)
    assert filtered_status == "fresh"
    assert len(filtered["windows"]) == 6
    assert filtered["windows"][0]["start_utc"] == "2026-10-23T00:00:00Z"


def test_update_all_runs_two_cities_and_records_station_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple[str, str]] = []

    def fake_weather(root, location_key, *, now, refresh, force):
        calls.append((location_key, "ensemble"))
        return {"status": "fresh", "snapshot": {"location_key": location_key}, "error": None}

    def fake_live(root, location_key, product, *, now, force):
        calls.append((location_key, product))
        return {"status": "cache", "snapshot": {"product": product}, "error": None}

    monkeypatch.setattr(worker, "get_weather", fake_weather)
    monkeypatch.setattr(worker.live_data, "fetch_snapshot", fake_live)
    result = worker.update_all(tmp_path, now=NOW)
    assert not result["errors"]
    for location_key in weather.LOCATIONS:
        assert (location_key, "ensemble") in calls
        assert (location_key, "station") in calls
        assert (location_key, "archive") in calls
        assert (tmp_path / "runtime" / "decision_weather" / location_key / "worker.json").exists()


@pytest.mark.skipif(os.environ.get("RUN_REAL_WEATHER_TEST") != "1", reason="真实 API 测试需显式 RUN_REAL_WEATHER_TEST=1")
def test_real_open_meteo_smoke_is_opt_in(tmp_path: Path):
    result = weather.get_weather(tmp_path, "hangzhou", now=datetime.now(UTC), refresh=True, force=True)
    assert result["status"] in {"fresh", "partial", "stale"}
    assert result["snapshot"]["expected_members"] == 51

