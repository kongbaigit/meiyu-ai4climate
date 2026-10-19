import pandas as pd
import pytest

from src.contracts import SAMPLE_COLUMNS, validate_predictions, validate_samples


@pytest.fixture
def samples():
    row = {name: None for name in SAMPLE_COLUMNS}
    row.update(
        sample_id="fixture-sample", observation_window_id="fixture-window",
        forecast_spec_id="fixture-forecast", station_id="fixture-station",
        station_name="测试夹具，不是真实观测", station_lat=30.2, station_lon=120.4,
        window_start_utc="2024-06-01T00:00:00Z", window_end_utc="2024-06-02T00:00:00Z",
        observed_rain_mm=10.0, forecast_rain_mm=12.0, forecast_model="fixture",
        observation_measurement_code="24", reference_kind="ssod_derived_station",
        window_basis="nominal_utc_synoptic_day",
        forecast_kind="fixed_lead_composite", experiment_kind="offline_fixed_lead",
        quality_status="passed", audit_version="1.0.0", obs_record_id="fixture-obs",
        forecast_record_id="fixture-fc", source_manifest_id="fixture-source", split="unassigned",
    )
    return pd.DataFrame([row], columns=SAMPLE_COLUMNS)


@pytest.fixture
def predictions():
    return pd.DataFrame([dict(sample_id="fixture-sample", method="fixture", probability=0.3,
                             model_version="test-only", dataset_version="dataset-test",
                             experiment_kind="offline_fixed_lead", event_threshold_mm=25)])


def test_offline_sample_allows_unknown_publication(samples):
    assert validate_samples(samples) == []


@pytest.mark.parametrize("value", [None, -1, float("inf"), "not-a-number"])
def test_bad_rain_cannot_enter_main_table(samples, value):
    samples["observed_rain_mm"] = samples["observed_rain_mm"].astype(object)
    samples.loc[0, "observed_rain_mm"] = value
    assert any("observed_rain_mm" in error for error in validate_samples(samples))


def test_window_requires_timezone_and_24_hours(samples):
    samples.loc[0, "window_end_utc"] = "2024-06-02T01:00:00"
    errors = validate_samples(samples)
    assert any("UTC" in error for error in errors)
    assert any("24 小时" in error for error in errors)


def test_duplicates_rejected(samples):
    assert any("不唯一" in error for error in validate_samples(pd.concat([samples, samples])))


def test_unverified_quality_rejected(samples):
    samples.loc[0, "quality_status"] = "unknown"
    assert any("质量" in error for error in validate_samples(samples))


def test_ssod_window_basis_and_measurement_code_cannot_be_relabelled(samples):
    samples.loc[0, "observation_measurement_code"] = "H"
    samples.loc[0, "window_basis"] = "verified_station_window"
    errors = validate_samples(samples)
    assert any("测量码" in error for error in errors)
    assert any("名义 UTC 日" in error for error in errors)


def test_nominal_day_cannot_shift_six_hours(samples):
    samples.loc[0, "window_start_utc"] = "2024-06-01T06:00:00Z"
    samples.loc[0, "window_end_utc"] = "2024-06-02T06:00:00Z"
    assert any("00:00" in error for error in validate_samples(samples))


def test_operational_replay_cannot_use_future_or_hindcast(samples):
    samples.loc[0, "experiment_kind"] = "operational_replay"
    samples.loc[0, "forecast_kind"] = "hindcast"
    samples.loc[0, "available_at_utc"] = "2024-06-01T02:00:00Z"
    samples.loc[0, "decision_time_utc"] = "2024-06-01T00:00:00Z"
    samples.loc[0, "availability_evidence"] = "fixture-evidence"
    errors = validate_samples(samples)
    assert any("时间顺序" in error for error in errors)
    assert any("hindcast" in error for error in errors)


def test_prediction_protocol_passes(samples, predictions):
    assert validate_predictions(predictions, samples, "dataset-test") == []


@pytest.mark.parametrize("probability", [-0.1, 1.1, float("nan"), float("inf")])
def test_prediction_invalid_probability(samples, predictions, probability):
    predictions.loc[0, "probability"] = probability
    assert any("概率" in error for error in validate_predictions(predictions, samples, "dataset-test"))


def test_prediction_unknown_version_and_sample(samples, predictions):
    predictions.loc[0, "sample_id"] = "unknown"
    errors = validate_predictions(predictions, samples, "other-version")
    assert any("版本" in error for error in errors)
    assert any("未知样本" in error for error in errors)


def test_prediction_duplicates_and_experiment_mismatch(samples, predictions):
    predictions.loc[0, "experiment_kind"] = "operational_replay"
    errors = validate_predictions(pd.concat([predictions, predictions]), samples, "dataset-test")
    assert any("重复" in error for error in errors)
    assert any("实验类型" in error for error in errors)


def test_prediction_requires_target_definition(samples, predictions):
    errors = validate_predictions(predictions.drop(columns="event_threshold_mm"), samples, "dataset-test")
    assert any("缺少字段" in error for error in errors)
