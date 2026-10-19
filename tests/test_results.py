import json

import pandas as pd
import pytest

from src.bundle import DataBundle
from src.contracts import SAMPLE_COLUMNS
from src.results import load_results


def _empty_data_bundle() -> DataBundle:
    return DataBundle(
        samples=pd.DataFrame(columns=SAMPLE_COLUMNS),
        quarantined=pd.DataFrame(),
        quality={},
        manifest={},
        errors=[],
    )


@pytest.mark.parametrize(
    ("malformed_file", "malformed_value"),
    [
        ("experiment_run.json", []),
        ("evaluation.json", None),
    ],
)
def test_malformed_result_json_returns_friendly_result_error(tmp_path, malformed_file, malformed_value):
    reports = tmp_path / "reports"
    reports.mkdir()
    if malformed_file == "evaluation.json":
        (reports / "experiment_run.json").write_text("{}", encoding="utf-8")
    (reports / malformed_file).write_text(json.dumps(malformed_value), encoding="utf-8")

    result = load_results(tmp_path, _empty_data_bundle())

    assert result.predictions.empty
    assert result.errors
    assert any("JSON 顶层必须是对象" in error for error in result.errors)
    assert all("AttributeError" not in error for error in result.errors)


@pytest.mark.parametrize("model_versions", [[], None, "invalid", 1])
def test_malformed_model_versions_returns_friendly_result_error(tmp_path, model_versions):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "experiment_run.json").write_text(
        json.dumps({"model_versions": model_versions}), encoding="utf-8"
    )

    result = load_results(tmp_path, _empty_data_bundle())

    assert not result.ready
    assert result.predictions.empty
    assert any("model_versions 必须是对象" in error for error in result.errors)
