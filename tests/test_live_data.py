from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

import src.live_data as live_data
from src.live_data import (
    LOCATIONS,
    PRODUCTS,
    fetch_snapshot,
    make_request,
    parse_payload,
    read_cached,
)


UTC = timezone.utc
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def _forecast_body(request, *, missing: set[datetime] | None = None, precipitation_unit="mm", latitude=None, duplicate=False):
    start = datetime.fromisoformat(request["start_date"].replace("Z", "+00:00"))
    end = start + timedelta(days=7)
    times = []
    rain = []
    temperature = []
    humidity = []
    missing = missing or set()
    cursor = start
    while cursor <= end:
        times.append(cursor.isoformat().replace("+00:00", "Z"))
        rain.append(None if cursor in missing else (999.0 if cursor == start else float((cursor.hour or 24))))
        temperature.append(20.0 if cursor not in missing else None)
        humidity.append(80.0 if cursor not in missing else None)
        cursor += timedelta(hours=1)
    if duplicate:
        times.append(times[1])
        rain.append(1.0)
        temperature.append(20.0)
        humidity.append(80.0)
    return {
        "latitude": request["location"]["latitude"] if latitude is None else latitude,
        "longitude": request["location"]["longitude"],
        "timezone": "GMT",
        "utc_offset_seconds": 0,
        "hourly_units": {"time": "iso8601", "precipitation": precipitation_unit, "temperature_2m": "°C", "relative_humidity_2m": "%"},
        "hourly": {"time": times, "precipitation": rain, "temperature_2m": temperature, "relative_humidity_2m": humidity},
    }


def _archive_body(request, *, missing=None):
    expected = request["expected_dates"]
    missing = set(missing or [])
    return {
        "latitude": request["location"]["latitude"],
        "longitude": request["location"]["longitude"],
        "timezone": "GMT",
        "utc_offset_seconds": 0,
        "daily_units": {"time": "iso8601", "precipitation_sum": "mm", "temperature_2m_mean": "°C"},
        "daily": {
            "time": expected,
            "precipitation_sum": [None if day in missing else 1.5 for day in expected],
            "temperature_2m_mean": [25.0 for _ in expected],
        },
    }


def _station_csv(request, rows=None):
    if rows is None:
        rows = [{
            "STATION": request["location"]["station_id"],
            "Station_name": request["location"]["name"],
            "DATE": "2026-01-01",
            "LATITUDE": str(request["location"]["latitude"]),
            "LONGITUDE": str(request["location"]["longitude"]),
            "total_precipitation": "2.5",
            "total_precipitation_Measurement_Code": "G",
        }]
    columns = ["STATION", "Station_name", "DATE", "LATITUDE", "LONGITUDE", "total_precipitation", "total_precipitation_Measurement_Code"]
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(str(row.get(column, "")) for column in columns))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _response(raw, status=200, headers=None):
    return {"status_code": status, "content": raw, "headers": headers or {}}


def test_locations_and_request_windows_are_fixed_utc():
    assert PRODUCTS == ("forecast", "archive", "station")
    assert LOCATIONS["hangzhou"]["station_id"] == "CHI0000ZSHC"
    assert LOCATIONS["hangzhou"]["latitude"] == 30.2283
    assert LOCATIONS["hangzhou"]["longitude"] == 120.4317
    assert LOCATIONS["ningbo"]["station_id"] == "CHI0000ZSNB"
    forecast = make_request("hangzhou", "forecast", NOW)
    assert "models=ecmwf_ifs025" in forecast["request_url"]
    assert "forecast_days=9" in forecast["request_url"]
    assert forecast["start_date"] == "2026-10-15T00:00:00Z"
    assert forecast["end_date"] == "2026-10-22T00:00:00Z"
    assert len(forecast["expected_dates"]) == 7
    archive = make_request("hangzhou", "archive", NOW)
    assert "models=era5" in archive["request_url"]
    assert "/v1/archive?" in archive["request_url"]
    assert archive["api_end_date"] == "2026-10-07"
    assert archive["expected_dates"][0] == "2026-01-01"
    assert archive["expected_dates"][-1] == "2026-10-07"
    station = make_request("ningbo", "station", NOW)
    assert station["request_url"].endswith("SSOD_CHI0000ZSNB_2026.csv")
    assert station["api_end_date"] == "2026-10-13"


def test_archive_cross_year_window_uses_cutoff_year():
    request = make_request("hangzhou", "archive", datetime(2026, 1, 5, 12, tzinfo=UTC))
    assert "/v1/archive?" in request["request_url"]
    assert request["api_start_date"] == "2025-01-01"
    assert request["api_end_date"] == "2025-12-29"
    assert request["expected_dates"][0] == "2025-01-01"
    assert request["expected_dates"][-1] == "2025-12-29"


def test_station_empty_new_year_window_round_trips_cache(tmp_path):
    now = datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    request = make_request("hangzhou", "station", now)
    assert request["expected_dates"] == []
    raw = _station_csv(request, rows=[])
    result = fetch_snapshot(tmp_path, "hangzhou", "station", force=True, now=now, http_get=lambda url, timeout: _response(raw))
    assert result["status"] == "updated"
    cached = read_cached(tmp_path, "hangzhou", "station", now=now + timedelta(minutes=1))
    assert cached["status"] == "cache"
    assert cached["snapshot"]["coverage"]["expected_day_count"] == 0


def test_forecast_uses_start_end_boundary_and_preserves_zero(tmp_path):
    request = make_request("hangzhou", "forecast", NOW)
    raw = json.dumps(_forecast_body(request)).encode("utf-8")
    snapshot = parse_payload(raw, request, "2026-10-14T12:00:00Z")
    first = snapshot["rows"][0]
    assert first["hours_present"] == 24
    assert first["hours_expected"] == 24
    # t=00 is outside (start,end] and has the sentinel value 999.
    assert first["rain_mm"] == sum(range(1, 25))
    assert first["status"] == "complete"
    assert snapshot["coverage"]["complete_day_count"] == 7


def test_forecast_missing_hour_is_partial_without_zero_fill():
    request = make_request("hangzhou", "forecast", NOW)
    start = datetime.fromisoformat(request["start_date"].replace("Z", "+00:00"))
    raw = json.dumps(_forecast_body(request, missing={start + timedelta(hours=12)})).encode("utf-8")
    snapshot = parse_payload(raw, request, "2026-10-14T12:00:00Z")
    row = snapshot["rows"][0]
    assert row["status"] == "partial"
    assert row["hours_present"] == 23
    assert row["rain_mm"] is None
    assert row["date"] in snapshot["coverage"]["partial_days"]


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda body: body.update({"hourly_units": {**body["hourly_units"], "precipitation": "inch"}}), "单位"),
        (lambda body: body.update({"utc_offset_seconds": 3600}), "UTC"),
        (lambda body: body["hourly"].update({"time": body["hourly"]["time"] + [body["hourly"]["time"][1]], "precipitation": body["hourly"]["precipitation"] + [0], "temperature_2m": body["hourly"]["temperature_2m"] + [20], "relative_humidity_2m": body["hourly"]["relative_humidity_2m"] + [80]}), "重复"),
        (lambda body: body.update({"latitude": 50.0}), "位置差异"),
    ],
)
def test_forecast_strict_rejection(mutator, match):
    request = make_request("hangzhou", "forecast", NOW)
    body = _forecast_body(request)
    mutator(body)
    with pytest.raises(ValueError, match=match):
        parse_payload(json.dumps(body).encode(), request, "2026-10-14T12:00:00Z")


def test_json_top_level_array_and_boolean_numeric_rejected():
    request = make_request("hangzhou", "forecast", NOW)
    with pytest.raises(ValueError, match="顶层"):
        parse_payload(b"[]", request, "2026-10-14T12:00:00Z")
    body = _forecast_body(request)
    body["hourly"]["precipitation"][1] = True
    with pytest.raises(ValueError, match="必须是数字"):
        parse_payload(json.dumps(body).encode(), request, "2026-10-14T12:00:00Z")


def test_archive_daily_window_and_missing_is_not_zero():
    request = make_request("hangzhou", "archive", datetime(2026, 1, 10, 12, tzinfo=UTC))
    body = _archive_body(request, missing={"2026-01-02"})
    snapshot = parse_payload(json.dumps(body).encode(), request, "2026-01-10T12:00:00Z")
    assert len(snapshot["rows"]) == 3
    assert snapshot["rows"][0]["rain_mm"] == 1.5
    assert snapshot["rows"][1]["status"] == "missing"
    assert snapshot["rows"][1]["rain_mm"] is None
    assert snapshot["rows"][2]["date"] == "2026-01-03"


def test_station_uses_existing_ssod_qc_and_all_missing_is_valid_monitoring():
    request = make_request("hangzhou", "station", datetime(2026, 1, 3, 12, tzinfo=UTC))
    raw = _station_csv(request)
    snapshot = parse_payload(raw, request, "2026-01-03T12:00:00Z")
    assert snapshot["rows"][0]["status"] == "complete"
    assert snapshot["rows"][0]["rain_mm"] == 2.5
    assert snapshot["rows"][1]["status"] == "missing"

    missing_row = {
        "STATION": request["location"]["station_id"], "Station_name": "XIAOSHAN", "DATE": "2026-01-01",
        "LATITUDE": str(request["location"]["latitude"]), "LONGITUDE": str(request["location"]["longitude"]),
        "total_precipitation": "-9999.9", "total_precipitation_Measurement_Code": "I",
    }
    all_missing = parse_payload(_station_csv(request, [missing_row]), request, "2026-01-03T12:00:00Z")
    assert all(row["rain_mm"] is None for row in all_missing["rows"])
    assert all(row["status"] == "partial" or row["status"] == "missing" for row in all_missing["rows"])

    wrong = dict(missing_row, STATION="CHI0000ZSNB")
    with pytest.raises(ValueError, match="station_id"):
        parse_payload(_station_csv(request, [wrong]), request, "2026-01-03T12:00:00Z")


def test_station_string_coordinates_are_checked_and_returned():
    request = make_request("hangzhou", "station", NOW)
    row = {"STATION": request["location"]["station_id"], "Station_name": "XIAOSHAN", "DATE": "2026-01-01",
           "LATITUDE": "30.23", "LONGITUDE": "120.43", "total_precipitation": "2.5", "total_precipitation_Measurement_Code": "G"}
    snapshot = parse_payload(_station_csv(request, [row]), request, "2026-10-14T12:00:00Z")
    assert snapshot["grid"] == {"latitude": 30.23, "longitude": 120.43}
    assert snapshot["coverage"]["complete_day_count"] == 1
    row["LATITUDE"] = "31.23"
    with pytest.raises(ValueError, match="坐标差异"):
        parse_payload(_station_csv(request, [row]), request, "2026-10-14T12:00:00Z")


def test_invalid_station_coordinates_cannot_replace_valid_cache(tmp_path):
    request = make_request("hangzhou", "station", NOW)
    before = fetch_snapshot(tmp_path, "hangzhou", "station", now=NOW, http_get=lambda url, timeout: _response(_station_csv(request)))
    row = {"STATION": request["location"]["station_id"], "Station_name": "XIAOSHAN", "DATE": "2026-01-01",
           "LATITUDE": "NaN", "LONGITUDE": "120.43", "total_precipitation": "2.5", "total_precipitation_Measurement_Code": "G"}
    after = fetch_snapshot(tmp_path, "hangzhou", "station", now=NOW + timedelta(minutes=1), http_get=lambda url, timeout: _response(_station_csv(request, [row])))
    assert after["snapshot"] == before["snapshot"]
    assert "坐标无效" in after["error"]


def test_cache_round_trip_ttl_and_corruption(tmp_path):
    request = make_request("hangzhou", "forecast", NOW)
    raw = json.dumps(_forecast_body(request)).encode()
    calls = []

    def getter(url, timeout):
        calls.append((url, timeout))
        return _response(raw)

    first = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=True, now=NOW, http_get=getter)
    assert first["status"] == "updated"
    assert len(calls) == 1
    cached = read_cached(tmp_path, "hangzhou", "forecast", now=NOW + timedelta(hours=2))
    assert cached["status"] == "cache"
    stale = read_cached(tmp_path, "hangzhou", "forecast", now=NOW + timedelta(hours=4))
    assert stale["status"] == "stale_cache"
    no_request = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=False, now=NOW + timedelta(hours=2), http_get=lambda *args, **kwargs: pytest.fail("不应刷新有效缓存"))
    assert no_request["status"] == "cache"
    raw_path = next((tmp_path / "runtime" / "weather" / "hangzhou" / "forecast").glob("raw-*.bin"))
    raw_path.write_bytes(b"corrupt")
    broken = read_cached(tmp_path, "hangzhou", "forecast", now=NOW)
    assert broken["status"] == "error"
    assert "摘要" in (broken["error"] or "")


def test_fetch_failure_and_429_keep_previous_snapshot(tmp_path):
    request = make_request("hangzhou", "archive", datetime(2026, 1, 10, 12, tzinfo=UTC))
    raw = json.dumps(_archive_body(request)).encode()
    good = fetch_snapshot(tmp_path, "hangzhou", "archive", force=True, now=datetime(2026, 1, 10, 12, tzinfo=UTC), http_get=lambda url, timeout: _response(raw))
    assert good["status"] == "updated"
    failed = fetch_snapshot(tmp_path, "hangzhou", "archive", force=True, now=datetime(2026, 1, 10, 13, tzinfo=UTC), http_get=lambda url, timeout: (_ for _ in ()).throw(RuntimeError("断网")))
    assert failed["snapshot"] is not None
    assert failed["status"] == "cache"
    assert "断网" in (failed["error"] or "")
    limited = fetch_snapshot(tmp_path, "hangzhou", "archive", force=True, now=datetime(2026, 1, 10, 13, tzinfo=UTC), http_get=lambda url, timeout: _response(b"", status=429, headers={"Retry-After": "60"}))
    assert limited["snapshot"] is not None
    assert "429" in (limited["error"] or "")


def test_invalid_no_rain_response_cannot_replace_valid_cache(tmp_path):
    request = make_request("hangzhou", "forecast", NOW)
    good_raw = json.dumps(_forecast_body(request)).encode()
    first = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=True, now=NOW, http_get=lambda url, timeout: _response(good_raw))
    assert first["status"] == "updated"
    missing_body = _forecast_body(request, missing={datetime.fromisoformat(request["start_date"].replace("Z", "+00:00")) + timedelta(hours=i) for i in range(1, 25)})
    # Clear all rain for every requested day while keeping a structurally valid response.
    missing_body["hourly"]["precipitation"] = [None for _ in missing_body["hourly"]["precipitation"]]
    second = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=True, now=NOW + timedelta(minutes=1), http_get=lambda url, timeout: _response(json.dumps(missing_body).encode()))
    assert second["status"] == "cache"
    assert second["snapshot"]["raw_sha256"] == first["snapshot"]["raw_sha256"]
    assert "有效降水覆盖" in (second["error"] or "")


def test_cache_and_runtime_do_not_modify_frozen_sample(tmp_path):
    sample_path = Path(__file__).parents[1] / "data" / "samples.csv"
    before = hashlib.sha256(sample_path.read_bytes()).hexdigest()
    request = make_request("hangzhou", "station", datetime(2026, 1, 3, 12, tzinfo=UTC))
    result = fetch_snapshot(tmp_path, "hangzhou", "station", force=True, now=datetime(2026, 1, 3, 12, tzinfo=UTC), http_get=lambda url, timeout: _response(_station_csv(request)))
    assert result["status"] == "updated"
    assert hashlib.sha256(sample_path.read_bytes()).hexdigest() == before


def test_index_write_failure_keeps_old_content_addressed_cache(tmp_path, monkeypatch):
    request = make_request("hangzhou", "forecast", NOW)
    first_raw = json.dumps(_forecast_body(request)).encode()
    first = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=True, now=NOW, http_get=lambda url, timeout: _response(first_raw))
    assert first["status"] == "updated"
    cache_dir = tmp_path / "runtime" / "weather" / "hangzhou" / "forecast"
    index_path = cache_dir / "index.json"
    old_index = index_path.read_bytes()
    old_snapshot = read_cached(tmp_path, "hangzhou", "forecast", now=NOW)["snapshot"]

    changed_body = _forecast_body(request)
    changed_body["hourly"]["precipitation"][1] = 42.0
    second_raw = json.dumps(changed_body).encode()
    original_atomic = live_data._atomic_write

    def fail_index(path, data):
        if path.name == "index.json":
            raise OSError("index write interrupted")
        return original_atomic(path, data)

    monkeypatch.setattr(live_data, "_atomic_write", fail_index)
    failed = fetch_snapshot(
        tmp_path,
        "hangzhou",
        "forecast",
        force=True,
        now=NOW + timedelta(minutes=1),
        http_get=lambda url, timeout: _response(second_raw),
    )
    assert failed["status"] == "cache"
    assert failed["snapshot"]["raw_sha256"] == old_snapshot["raw_sha256"]
    assert "index write interrupted" in (failed["error"] or "")
    assert index_path.read_bytes() == old_index
    restored = read_cached(tmp_path, "hangzhou", "forecast", now=NOW + timedelta(minutes=1))
    assert restored["status"] == "cache"
    assert restored["snapshot"]["raw_sha256"] == old_snapshot["raw_sha256"]
    assert len(list(cache_dir.glob("raw-*.bin"))) == 2


def test_future_cache_and_tampered_index_are_rejected(tmp_path):
    request = make_request("hangzhou", "forecast", NOW)
    raw = json.dumps(_forecast_body(request)).encode()
    first = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=True, now=NOW, http_get=lambda url, timeout: _response(raw))
    assert first["status"] == "updated"
    cache_dir = tmp_path / "runtime" / "weather" / "hangzhou" / "forecast"
    index_path = cache_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    snapshot_path = cache_dir / index["snapshot_file"]
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    future = NOW + timedelta(hours=1)
    snapshot["fetched_at_utc"] = future.isoformat().replace("+00:00", "Z")
    future_bytes = live_data._json_bytes(snapshot)
    future_sha = hashlib.sha256(future_bytes).hexdigest()
    future_path = cache_dir / f"snapshot-{future_sha}.json"
    future_path.write_bytes(future_bytes)
    index["snapshot_file"] = future_path.name
    index["snapshot_sha256"] = future_sha
    index["fetched_at_utc"] = snapshot["fetched_at_utc"]
    index_path.write_bytes(live_data._json_bytes(index))
    future_result = read_cached(tmp_path, "hangzhou", "forecast", now=NOW)
    assert future_result["status"] == "error"
    assert "超过当前时间" in (future_result["error"] or "")

    # 重新构造正常 index 后，用目录外文件名验证路径逃逸被拒绝。
    index["snapshot_file"] = snapshot_path.name
    index["snapshot_sha256"] = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    index["fetched_at_utc"] = first["snapshot"]["fetched_at_utc"]
    index["raw_file"] = "../" + index["raw_file"]
    index_path.write_bytes(live_data._json_bytes(index))
    escaped = read_cached(tmp_path, "hangzhou", "forecast", now=NOW)
    assert escaped["status"] == "error"
    assert "文件名" in (escaped["error"] or "")


def test_response_larger_than_four_megabytes_is_rejected(tmp_path):
    huge = b"x" * (4 * 1024 * 1024 + 1)
    result = fetch_snapshot(
        tmp_path,
        "hangzhou",
        "forecast",
        force=True,
        now=NOW,
        http_get=lambda url, timeout: _response(huge, headers={"Content-Length": str(len(huge))}),
    )
    assert result["status"] == "error"
    assert result["snapshot"] is None
    assert "4MB" in (result["error"] or "")


def test_cached_official_url_extra_parameter_is_rejected(tmp_path):
    request = make_request("hangzhou", "forecast", NOW)
    raw = json.dumps(_forecast_body(request)).encode()
    first = fetch_snapshot(tmp_path, "hangzhou", "forecast", force=True, now=NOW, http_get=lambda url, timeout: _response(raw))
    assert first["status"] == "updated"
    index_path = tmp_path / "runtime" / "weather" / "hangzhou" / "forecast" / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["request"]["request_url"] += "&evil=1"
    index_path.write_bytes(live_data._json_bytes(index))
    result = read_cached(tmp_path, "hangzhou", "forecast", now=NOW)
    assert result["status"] == "error"
    assert "参数集合" in (result["error"] or "")

