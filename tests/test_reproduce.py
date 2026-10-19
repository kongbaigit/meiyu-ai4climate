from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.reproduce import ReproductionError, build_features, rebuild_logistic


def _scalar_parameters() -> dict[str, object]:
    return {
        "imputer_statistics": [1.0],
        "scaler_mean": [1.0],
        "scaler_scale": [2.0],
        "coefficients_after_scaled_features": [2.0],
        "intercept": 0.0,
        "feature_order": ["forecast_rain_mm"],
        "class_labels": [0, 1],
        "positive_class_label": 1,
    }


def test_rebuild_logistic_scalar_and_training_median_imputation() -> None:
    probabilities = rebuild_logistic(np.array([[3.0], [np.nan]]), _scalar_parameters())
    assert probabilities[0] == pytest.approx(1.0 / (1.0 + np.exp(-2.0)))
    assert probabilities[1] == pytest.approx(0.5)


def test_feature_order_applies_log1p_before_parameter_imputation() -> None:
    samples = pd.DataFrame(
        {
            "forecast_rain_mm": [3.0],
            "forecast_temperature_mean_c": [10.0],
        }
    )
    parameters = {
        "feature_order": ["forecast_temperature_mean_c", "forecast_rain_mm"],
    }
    matrix = build_features(samples, parameters)
    assert matrix[0, 0] == pytest.approx(10.0)
    assert matrix[0, 1] == pytest.approx(np.log1p(3.0))


def test_rebuild_rejects_corrupt_parameter_dimensions() -> None:
    corrupted = _scalar_parameters()
    corrupted["coefficients_after_scaled_features"] = [1.0, 2.0]
    with pytest.raises(ReproductionError, match="参数维度不一致"):
        rebuild_logistic(np.array([[1.0]]), corrupted)
