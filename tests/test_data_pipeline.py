from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.contracts import SAMPLE_COLUMNS, validate_samples
from src.data_pipeline import (
    build_sample_rows,
    parse_isd_group,
    parse_ssod_files,
    parse_ssod_row,
)
from src.forecasts import VARIABLES


def test_isd_depth_uses_tenths_of_mm_and_trace_is_not_zero():
    exact = parse_isd_group("24,0025,4,1")[0]
    assert exact.depth_raw == 25
    assert exact.depth_mm == 2.5
    assert exact.exact_measurable is True
    assert exact.observed_rain_mm == 2.5

    trace = parse_isd_group("24,0000,2,1")[0]
    assert trace.depth_mm == 0.0
    assert trace.observed_rain_mm is None
    assert "trace_not_exact_zero" in trace.reasons


def test_isd_sentinels_and_unknown_codes_are_quarantined():
    missing_depth = parse_isd_group("24,9999,4,1")[0]
    assert missing_depth.depth_mm is None
    assert missing_depth.candidate_window is False
    assert "missing_depth_sentinel" in missing_depth.reasons

    unknown_condition = parse_isd_group("24,0025,X,1")[0]
    assert unknown_condition.candidate_window is False
    assert "unknown_condition_code" in unknown_condition.reasons

    unknown_quality = parse_isd_group("24,0025,4,X")[0]
    assert unknown_quality.candidate_window is False
    assert "unknown_quality_code" in unknown_quality.reasons


def test_ssod_keeps_complete_layer_and_separates_h_i_quarantine_reasons():
    complete, quarantine = parse_ssod_row(
        {
            "STATION": "CHI0000ZSHC",
            "Station_name": "XIAOSHAN",
            "DATE": "2024-06-10",
            "LATITUDE": "30.2283",
            "LONGITUDE": "120.4317",
            "total_precipitation": "31.5",
            "total_precipitation_Measurement_Code": "G",
        },
        "ssod_2024",
        "sm-test",
    )
    assert complete is not None
    assert complete["observed_rain_mm"] == 31.5
    assert complete["reference_only"] is True
    assert quarantine is None

    for code, expected_reason, forbidden_reason, expected_text in [
        ("H", "precipitation_occurrence_without_total", "no_precipitation_data_or_occurrence_record", "存在降水发生记录"),
        ("I", "no_precipitation_data_or_occurrence_record", "precipitation_occurrence_without_total", "未报告降水数据及发生记录"),
    ]:
        complete, quarantine = parse_ssod_row(
            {"DATE": "2024-06-11", "total_precipitation": "-9999.9", "total_precipitation_Measurement_Code": code},
            "ssod_2024",
            "sm-test",
        )
        assert complete is None
        assert quarantine is not None
        assert "missing_precipitation_sentinel" in quarantine["reason"]
        assert expected_reason in quarantine["reason"]
        assert forbidden_reason not in quarantine["reason"]
        assert expected_text in quarantine["details"]
        assert quarantine["observed_rain_mm"] is None


def test_ssod_rejects_negative_nonfinite_and_invalid_coordinates():
    base = {
        "STATION": "CHI0000ZSHC",
        "Station_name": "XIAOSHAN",
        "DATE": "2024-06-10",
        "LATITUDE": "30.2283",
        "LONGITUDE": "120.4317",
        "total_precipitation_Measurement_Code": "G",
    }
    for value, expected in [("-1", "negative_precipitation_value"), ("nan", "invalid_precipitation_value"), ("inf", "invalid_precipitation_value")]:
        row = {**base, "total_precipitation": value}
        observation, quarantine = parse_ssod_row(row, "ssod_2024", "sm-test", "CHI0000ZSHC", 2024)
        assert observation is None
        assert expected in quarantine["reason"]

    row = {**base, "total_precipitation": "1.0", "LATITUDE": "not-a-coordinate"}
    observation, quarantine = parse_ssod_row(row, "ssod_2024", "sm-test", "CHI0000ZSHC", 2024)
    assert observation is None
    assert "invalid_coordinate" in quarantine["reason"]


def test_ssod_file_enforces_station_and_year():
    path = Path(__file__).with_name("_ssod_pipeline_fixture.csv")
    path.write_text(
        "STATION,Station_name,DATE,LATITUDE,LONGITUDE,total_precipitation,total_precipitation_Measurement_Code\n"
        "OTHER,TEST,2025-06-10,30.2,120.4,1.0,G\n",
        encoding="utf-8",
    )
    try:
        observations, quarantined = parse_ssod_files(
            [{
                "source_id": "ssod_2024",
                "station_id": "CHI0000ZSHC",
                "year": 2024,
                "_resolved_path": str(path),
            }],
            "sm-test",
        )
        assert observations == []
        assert len(quarantined) == 1
        assert "station_id_mismatch" in quarantined[0]["reason"]
        assert "year_mismatch" in quarantined[0]["reason"]
    finally:
        path.unlink(missing_ok=True)


def test_missing_forecast_hours_block_pairing_without_zero_fill():
    observation = {
        "obs_record_id": "ssod-2024-20240610",
        "source_id": "ssod_2024",
        "source_dataset": "SSODv2",
        "station_id": "CHI0000ZSHC",
        "station_name": "XIAOSHAN",
        "station_lat": 30.2283,
        "station_lon": 120.4317,
        "window_start_utc": "2024-06-10T00:00:00Z",
        "window_end_utc": "2024-06-11T00:00:00Z",
        "observed_rain_mm": 31.5,
        "measurement_code": "G",
        "reference_only": True,
        "quality_status": "complete_reference",
    }
    # 23 hours intentionally: aggregate_window must reject this window.
    frame = pd.DataFrame(
        {
            "time_utc": pd.date_range("2024-06-10T01:00:00Z", periods=23, freq="h"),
            VARIABLES[0]: [0.0] * 23,
            VARIABLES[1]: [25.0] * 23,
            VARIABLES[2]: [80.0] * 23,
        }
    )
    rows, quarantined = build_sample_rows(
        [observation],
        {2024: frame},
        {2024: {"source_id": "openmeteo-test", "forecast_model": "fixture"}},
        "fixture-version",
    )
    assert rows == []
    assert quarantined[0]["reason"] == "forecast_window_incomplete"
    assert "forecast_missing_hours" in quarantined[0]["details"]
    assert not any(row.get("forecast_rain_mm") == 0 for row in rows)


def test_sample_id_binds_observation_window_and_forecast_spec():
    observation = {
        "obs_record_id": "ssod-2024-20240610",
        "source_id": "ssod_2024",
        "source_dataset": "SSODv2",
        "station_id": "CHI0000ZSHC",
        "station_name": "XIAOSHAN",
        "station_lat": 30.2283,
        "station_lon": 120.4317,
        "window_start_utc": "2024-06-10T00:00:00Z",
        "window_end_utc": "2024-06-11T00:00:00Z",
        "observed_rain_mm": 31.5,
        "measurement_code": "G",
        "reference_only": True,
        "quality_status": "complete_reference",
        "source_manifest_id": "sm-test",
    }
    frame = pd.DataFrame(
        {
            "time_utc": pd.date_range("2024-06-10T01:00:00Z", periods=24, freq="h"),
            VARIABLES[0]: [0.1] * 24,
            VARIABLES[1]: [25.0] * 24,
            VARIABLES[2]: [80.0] * 24,
        }
    )
    rows, quarantined = build_sample_rows(
        [observation],
        {2024: frame},
        {2024: {"source_id": "openmeteo-test", "forecast_model": "fixture"}},
        "fixture-version",
    )
    assert quarantined == []
    assert len(rows) == 1
    assert rows[0]["sample_id"] == "sample-ssod-2024-20240610-openmeteo-test"
    assert validate_samples(pd.DataFrame(rows, columns=SAMPLE_COLUMNS)) == []


def test_empty_sample_contract_is_header_only():
    empty = pd.DataFrame(columns=SAMPLE_COLUMNS)
    assert validate_samples(empty) == []
