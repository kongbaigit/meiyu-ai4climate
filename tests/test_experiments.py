from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.contracts import validate_predictions
from src.experiments import (
    ExperimentError,
    SplitSpec,
    always_never_costs,
    assign_split,
    build_sample_splits,
    calibration_bins,
    cost_scenarios,
    guard_frozen_run,
    make_logistic_pipeline,
    metrics_for_split,
    paired_brier_bootstrap,
    prepare_features,
)


def _spec() -> SplitSpec:
    return SplitSpec(
        pd.Timestamp("1900-01-01T00:00:00Z"),
        pd.Timestamp("2025-01-01T00:00:00Z"),
        pd.Timestamp("2025-05-01T00:00:00Z"),
    )


def test_complete_windows_are_split_at_boundaries_and_crossing_is_rejected() -> None:
    spec = _spec()
    assert assign_split(pd.Timestamp("2024-12-31T00:00:00Z"), pd.Timestamp("2025-01-01T00:00:00Z"), spec) == "train"
    assert assign_split(pd.Timestamp("2025-01-01T00:00:00Z"), pd.Timestamp("2025-01-02T00:00:00Z"), spec) == "validation"
    assert assign_split(pd.Timestamp("2025-04-30T00:00:00Z"), pd.Timestamp("2025-05-01T00:00:00Z"), spec) == "validation"
    assert assign_split(pd.Timestamp("2025-05-01T00:00:00Z"), pd.Timestamp("2025-05-02T00:00:00Z"), spec) == "test"
    assert assign_split(pd.Timestamp("2024-12-31T12:00:00Z"), pd.Timestamp("2025-01-01T12:00:00Z"), spec) == "excluded_boundary_crossing"

    frame = pd.DataFrame(
        [
            ["a", "wa", "2024-12-30T00:00:00Z", "2024-12-31T00:00:00Z", "train"],
            ["b", "wb", "2025-01-02T00:00:00Z", "2025-01-03T00:00:00Z", "validation"],
            ["c", "wc", "2025-05-02T00:00:00Z", "2025-05-03T00:00:00Z", "test"],
        ],
        columns=["sample_id", "observation_window_id", "window_start_utc", "window_end_utc", "split"],
    )
    result = build_sample_splits(frame, spec)
    assert result["experiment_split"].tolist() == ["train", "validation", "test"]

    crossing = pd.concat(
        [
            frame,
            pd.DataFrame(
                [["x", "wx", "2024-12-31T12:00:00Z", "2025-01-01T12:00:00Z", "train"]],
                columns=frame.columns,
            ),
        ],
        ignore_index=True,
    )
    with pytest.raises(ExperimentError, match="跨越切分边界"):
        build_sample_splits(crossing, spec)


def test_imputer_is_fit_on_training_values_only() -> None:
    training = pd.DataFrame(
        {
            "rain": [0.0, 1.0, 2.0, 3.0],
            "temperature": [10.0, 11.0, np.nan, 13.0],
        }
    )
    y = [0, 0, 1, 1]
    pipeline = make_logistic_pipeline(1.0, 20261013, 2)
    pipeline.fit(training, y)
    statistics = pipeline.named_steps["simpleimputer"].statistics_
    assert statistics.tolist() == [1.5, 11.0]
    assert pipeline.named_steps["logisticregression"].class_weight is None
    assert pipeline.named_steps["logisticregression"].max_iter == 3000


def test_missing_or_negative_rain_is_rejected_without_zero_fill() -> None:
    with pytest.raises(ExperimentError, match="缺失或为负"):
        prepare_features(pd.DataFrame({"forecast_rain_mm": [0.0, np.nan]}), "logistic_rain")
    with pytest.raises(ExperimentError, match="缺失或为负"):
        prepare_features(pd.DataFrame({"forecast_rain_mm": [1.0, -0.1]}), "logistic_rain")
    with pytest.raises(ExperimentError, match="未知逻辑回归方法"):
        prepare_features(pd.DataFrame({"forecast_rain_mm": [1.0]}), "unknown")


def test_brier_confusion_calibration_and_costs_use_the_same_rows() -> None:
    y = pd.Series([0, 1, 0, 1])
    probability = np.array([0.0, 1.0, 0.5, 0.5])
    metrics = metrics_for_split(y, probability)
    assert metrics["sample_count"] == 4
    assert metrics["event_count"] == 2
    assert metrics["brier"] == pytest.approx(0.125)
    assert metrics["confusion_at_probability_0_1"] == {
        "threshold": 0.1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 0,
        "true_positive": 2,
    }
    assert len(metrics["calibration_bins"]) == 5
    assert sum(item["count"] for item in calibration_bins(y, probability)) == len(y)

    costs = cost_scenarios(y, probability, [0.1], loss_unit=1.0)[0]
    assert costs["prepare_count"] == 3
    assert costs["event_loss_count_without_prepare"] == 0
    assert costs["total_realized_cost"] == pytest.approx(0.3)
    controls = always_never_costs(event_count=2, sample_count=4, ratios=[0.1])
    assert controls["always_prepare"][0]["total_realized_cost"] == pytest.approx(0.4)
    assert controls["never_prepare"][0]["total_realized_cost"] == pytest.approx(2.0)


def test_week_block_bootstrap_is_reproducible_and_reports_event_limitations() -> None:
    table = pd.DataFrame(
        {
            "event": [0, 1, 0, 1],
            "window_start_utc": [
                "2025-05-05T00:00:00Z",
                "2025-05-06T00:00:00Z",
                "2025-05-12T00:00:00Z",
                "2025-05-13T00:00:00Z",
            ],
            "window_end_utc": [
                "2025-05-06T00:00:00Z",
                "2025-05-07T00:00:00Z",
                "2025-05-13T00:00:00Z",
                "2025-05-14T00:00:00Z",
            ],
        }
    )
    selected = np.array([0.1, 0.8, 0.2, 0.7])
    baseline = np.array([0.2, 0.7, 0.2, 0.6])
    first = paired_brier_bootstrap(table, selected, baseline, "baseline", 20261013, 100)
    second = paired_brier_bootstrap(table, selected, baseline, "baseline", 20261013, 100)
    assert first == second
    assert first["calendar_week_block_count"] == 2
    assert first["test_event_count"] == 2
    assert first["ci95"] is not None
    assert first["limitations"]


def test_predictions_keep_all_methods_on_the_same_sample_set() -> None:
    samples = pd.DataFrame(
        {
            "sample_id": ["s1", "s2"],
            "experiment_kind": ["offline_fixed_lead", "offline_fixed_lead"],
        }
    )
    methods = ["training_climatology", "raw_nwp_rule", "logistic_rain", "logistic_weather"]
    rows = [
        {
            "sample_id": sample_id,
            "method": method,
            "probability": 0.5,
            "model_version": method + "-v1",
            "dataset_version": "meiyu-test",
            "experiment_kind": "offline_fixed_lead",
            "event_threshold_mm": 25.0,
        }
        for sample_id in samples["sample_id"]
        for method in methods
    ]
    predictions = pd.DataFrame(rows)
    assert validate_predictions(predictions, samples, "meiyu-test") == []
    assert {method: set(predictions.loc[predictions["method"].eq(method), "sample_id"]) for method in methods} == {
        method: {"s1", "s2"} for method in methods
    }


def test_frozen_run_checks_all_outputs_and_rejects_corruption(tmp_path: Path) -> None:
    identity = {
        "dataset_version": "meiyu-a",
        "sample_file_sha256": "sample-a",
        "source_manifest_file_sha256": "manifest-a",
        "config_hash": "config-a",
    }
    reports = tmp_path / "reports"
    artifacts = tmp_path / "artifacts"
    reports.mkdir()
    artifacts.mkdir()
    output_paths = {
        "predictions": artifacts / "predictions.csv",
        "evaluation": reports / "evaluation.json",
        "sample_splits": artifacts / "sample_splits.csv",
        "model_parameters": artifacts / "model_parameters.json",
    }
    for index, path in enumerate(output_paths.values()):
        path.write_text(f"output-{index}\n", encoding="utf-8")
    output_hashes = {
        name + "_file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in output_paths.items()
    }
    run_path = reports / "experiment_run.json"
    record = {
        "status": "completed",
        "frozen": identity,
        **output_hashes,
        "artifacts": {
            "predictions": "artifacts/predictions.csv",
            "evaluation": "reports/evaluation.json",
            "sample_splits": "artifacts/sample_splits.csv",
            "model_parameters": "artifacts/model_parameters.json",
        },
    }
    run_path.write_text(json.dumps(record), encoding="utf-8")
    assert guard_frozen_run(run_path, identity) == record

    output_paths["model_parameters"].write_text("corrupted\n", encoding="utf-8")
    with pytest.raises(ExperimentError, match="输出已损坏"):
        guard_frozen_run(run_path, identity)

    changed = {**identity, "config_hash": "config-b"}
    with pytest.raises(ExperimentError, match="冻结身份不同"):
        guard_frozen_run(run_path, changed)
    assert guard_frozen_run(run_path, changed, replace=True) is None
