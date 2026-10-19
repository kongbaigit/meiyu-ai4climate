from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import pandas as pd

from .bundle import DataBundle, read_json
from .contracts import validate_predictions

METHOD_NAMES = {
    "training_climatology": "训练期固定事件率",
    "raw_nwp_rule": "原始预报 25 毫米规则",
    "logistic_rain": "降水概率模型",
    "logistic_weather": "降水与温湿度模型",
}


@dataclass
class ResultBundle:
    predictions: pd.DataFrame
    evaluation: dict
    run: dict
    errors: list[str]

    @property
    def ready(self) -> bool:
        return not self.errors and not self.predictions.empty


def _read_result_object(path: Path) -> dict:
    """Read a result JSON and enforce its object boundary explicitly."""

    value = read_json(path)
    # Keep this guard even though bundle.read_json validates today: callers or
    # tests may replace the reader, and a result loader must never call .get on
    # an array or null value.
    if not isinstance(value, dict):
        raise ValueError(f"实验结果 JSON 顶层必须是对象：{path}")
    return value


def load_results(root: Path, data: DataBundle) -> ResultBundle:
    run_path = root / "reports" / "experiment_run.json"
    if not run_path.exists():
        return ResultBundle(pd.DataFrame(), {}, {}, [])
    try:
        run = _read_result_object(run_path)
        model_versions = run.get("model_versions", {})
        if not isinstance(model_versions, dict):
            raise ValueError("实验记录中的 model_versions 必须是对象。")
        evaluation = _read_result_object(root / "reports" / "evaluation.json")
        predictions = pd.read_csv(root / "artifacts" / "predictions.csv")
        errors = validate_predictions(predictions, data.samples, data.dataset_version)
        if run.get("dataset_version") != data.dataset_version or evaluation.get("dataset_version") != data.dataset_version:
            errors.append("实验结果与当前数据版本不一致。")
        paths = [
            ("artifacts/predictions.csv", "predictions_file_sha256"),
            ("reports/evaluation.json", "evaluation_file_sha256"),
            ("config/experiment.yaml", "config_sha256"),
            ("artifacts/sample_splits.csv", "sample_splits_file_sha256"),
            ("artifacts/model_parameters.json", "model_parameters_file_sha256"),
        ]
        for relative, key in paths:
            path = root / relative
            expected = run.get(key)
            if not path.exists() or not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                errors.append(f"{relative} 缺失或与冻结实验散列不一致。")
        if evaluation.get("predictions_file_sha256") != run.get("predictions_file_sha256"):
            errors.append("评估报告与预测文件引用不一致。")
        if evaluation.get("source_manifest_file_sha256") != data.quality.get("source_manifest_file_sha256"):
            errors.append("实验使用的来源快照与当前数据包不一致。")
        if run.get("selected_method") != evaluation.get("selected_method"):
            errors.append("推荐方法与冻结记录不一致。")
        if set(predictions["method"]) != set(METHOD_NAMES):
            errors.append("正式实验缺少预定对照方法或包含未知方法。")
        known = set(data.samples["sample_id"])
        for method, rows in predictions.groupby("method"):
            if set(rows["sample_id"]) != known:
                errors.append(f"{method} 未覆盖共同样本集。")
            if not rows["model_version"].eq(model_versions.get(method)).all():
                errors.append(f"{method} 的模型版本与冻结记录不一致。")
        splits = pd.read_csv(root / "artifacts" / "sample_splits.csv")
        if splits["sample_id"].duplicated().any() or set(splits["sample_id"]) != known:
            errors.append("实验切分表的样本集合不一致。")
        else:
            expected_split = predictions["sample_id"].map(splits.set_index("sample_id")["experiment_split"])
            if not predictions["split"].eq(expected_split).all():
                errors.append("预测中的时间切分与冻结切分表不一致。")
        return ResultBundle(predictions, evaluation, run, errors)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ResultBundle(pd.DataFrame(), {}, {}, [f"实验结果无法完整读取：{type(exc).__name__}: {exc}"])
