import pandas as pd
import pytest

from src.forecasts import VARIABLES, aggregate_window, parse_previous_response


def hours():
    return pd.DataFrame({"time_utc": pd.date_range("2024-06-01T00:00:00Z", periods=26, freq="h"),
                         VARIABLES[0]: list(range(26)), VARIABLES[1]: [20.] * 26, VARIABLES[2]: [80.] * 26})


def test_precipitation_uses_preceding_hour_boundary():
    result = aggregate_window(hours(), "2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", {"source_id": "fixture"})
    assert result["forecast_rain_mm"] == sum(range(1, 25))
    assert result["forecast_temperature_mean_c"] == 20


def test_missing_hour_does_not_become_zero():
    with pytest.raises(ValueError, match="missing_hours"):
        aggregate_window(hours().drop(index=12), "2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", {"source_id": "fixture"})


def test_duplicate_hour_rejected():
    data = pd.concat([hours(), hours().iloc[[1]]])
    with pytest.raises(ValueError, match="missing_hours"):
        aggregate_window(data, "2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", {"source_id": "fixture"})


def test_nan_precipitation_rejected():
    data = hours()
    data[VARIABLES[0]] = data[VARIABLES[0]].astype(float)
    data.loc[12, VARIABLES[0]] = float("nan")
    with pytest.raises(ValueError, match="invalid_precipitation"):
        aggregate_window(data, "2024-06-01T00:00:00Z", "2024-06-02T00:00:00Z", {"source_id": "fixture"})


def test_api_error_and_unit_mismatch_rejected():
    with pytest.raises(ValueError, match="接口返回错误"):
        parse_previous_response({"error": True, "reason": "test"})
    body = {"hourly": {"time": ["2024-01-01T00:00"], **{name: [0] for name in VARIABLES}}, "hourly_units": {VARIABLES[0]: "inch"}}
    with pytest.raises(ValueError, match="单位"):
        parse_previous_response(body)
