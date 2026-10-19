from __future__ import annotations

import pytest

from src.external_validation import ExternalValidationError, _download_or_use_cached, _metrics


def test_cached_ssod_prefix_requires_exact_object_key(tmp_path) -> None:
    key = "v2/access/by-year/2025/csv/SSOD_CHI0000ZSNB_2025.csv"
    prefix = tmp_path / "prefix.xml"
    prefix.write_text(
        f"<?xml version='1.0'?><ListBucketResult><Contents><Key>{key}</Key></Contents></ListBucketResult>",
        encoding="utf-8",
    )
    metadata = _download_or_use_cached("https://example.invalid/prefix", prefix, expected_key=key)
    assert metadata["retrieved_now"] is False
    assert metadata["bytes"] > 0
    with pytest.raises(ExternalValidationError, match="未列出精确对象"):
        _download_or_use_cached("https://example.invalid/prefix", prefix, expected_key=key + "-wrong")


def test_external_metrics_use_fixed_probability_threshold() -> None:
    import numpy as np

    result = _metrics(np.array([0, 1, 0, 1]), np.array([0.0, 1.0, 0.5, 0.5]))
    assert result["sample_count"] == 4
    assert result["event_count"] == 2
    assert result["brier"] == pytest.approx(0.125)
    assert result["confusion_at_probability_0_1"] == {
        "threshold": 0.1,
        "true_negative": 1,
        "false_positive": 1,
        "false_negative": 0,
        "true_positive": 2,
    }
