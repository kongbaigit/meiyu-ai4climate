"""用冻结文件和已导出的参数复现梅雨有数实验结果。

本模块刻意不导入 sklearn，也不拟合模型。它先核对实验运行记录声明的
输入、配置、参数和输出文件散列，再按 JSON 中保存的插补、标准化、系数
和截距，用 NumPy 重建四种方法的预测，最后独立重算测试集 Brier 与固定
阈值混淆矩阵。该检查用于发现文件或数学实现漂移，不构成外部验证。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
import pandas as pd


UTC = timezone.utc
DEFAULT_ROOT = Path(__file__).resolve().parents[1]
METHODS = ["training_climatology", "raw_nwp_rule", "logistic_rain", "logistic_weather"]
LOGISTIC_METHODS = ["logistic_rain", "logistic_weather"]
ERROR_TOLERANCE = 1e-10
METRIC_TOLERANCE = 1e-12


class ReproductionError(RuntimeError):
    """冻结文件或独立数学复现失败。"""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReproductionError(f"无法读取文件以计算 SHA256：{path}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReproductionError(f"JSON 文件无法读取：{path}") from exc
    if not isinstance(value, dict):
        raise ReproductionError(f"JSON 顶层必须是对象：{path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _root_file(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ReproductionError(f"{label} 的路径声明为空。")
    candidate = (root / Path(relative)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ReproductionError(f"{label} 路径越出项目根目录：{relative}") from exc
    return candidate


def _hash_check(
    checks: list[dict[str, Any]],
    *,
    root: Path,
    label: str,
    path: Path,
    expected: str,
) -> None:
    actual: str | None = None
    error: str | None = None
    if not isinstance(expected, str) or not expected:
        error = "run 记录缺少期望 SHA256。"
    elif not path.is_file():
        error = "文件不存在。"
    else:
        actual = _sha256(path)
        if actual != expected:
            error = f"实际 SHA256 {actual} 与期望值不一致。"
    checks.append(
        {
            "label": label,
            "path": str(path.relative_to(root.resolve())) if path.is_relative_to(root.resolve()) else str(path),
            "expected_sha256": expected,
            "actual_sha256": actual,
            "passed": error is None,
            "error": error,
        }
    )
    if error is not None:
        raise ReproductionError(f"{label} 校验失败：{error}")


def verify_hashes(root: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """读取 run/evaluation 并验证输入、参数和全部冻结输出散列。"""

    run_path = root / "reports" / "experiment_run.json"
    run = _read_json(run_path)
    frozen = run.get("frozen")
    if not isinstance(frozen, dict):
        raise ReproductionError("experiment_run.json 缺少 frozen 身份。")
    if run.get("status") != "completed":
        raise ReproductionError(f"官方 run 状态不是 completed：{run.get('status')!r}")

    artifacts = run.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ReproductionError("experiment_run.json 缺少 artifacts 路径。")
    checks: list[dict[str, Any]] = []

    samples_path = root / "data" / "samples.csv"
    source_manifest_path = root / "data" / "source_manifest.json"
    config_path = root / "config" / "experiment.yaml"
    _hash_check(
        checks,
        root=root,
        label="主表 samples.csv",
        path=samples_path,
        expected=frozen.get("sample_file_sha256"),
    )
    _hash_check(
        checks,
        root=root,
        label="来源清单 source_manifest.json",
        path=source_manifest_path,
        expected=frozen.get("source_manifest_file_sha256"),
    )
    config_expected = run.get("config_sha256")
    if frozen.get("config_hash") != config_expected:
        raise ReproductionError("run 的 frozen.config_hash 与 config_sha256 不一致。")
    _hash_check(
        checks,
        root=root,
        label="实验配置 experiment.yaml",
        path=config_path,
        expected=config_expected,
    )

    artifact_specs = {
        "predictions": ("predictions_file_sha256", "artifacts/predictions.csv"),
        "evaluation": ("evaluation_file_sha256", "reports/evaluation.json"),
        "sample_splits": ("sample_splits_file_sha256", "artifacts/sample_splits.csv"),
        "model_parameters": ("model_parameters_file_sha256", "artifacts/model_parameters.json"),
    }
    for name, (hash_field, default_path) in artifact_specs.items():
        relative = artifacts.get(name, default_path)
        path = _root_file(root, relative, name)
        _hash_check(
            checks,
            root=root,
            label=f"冻结输出 {name}",
            path=path,
            expected=run.get(hash_field),
        )

    samples_digest = _sha256(samples_path)
    expected_dataset_version = "meiyu-" + samples_digest[:16]
    if run.get("dataset_version") != expected_dataset_version:
        raise ReproductionError("run 的 dataset_version 与主表 SHA256 不一致。")
    evaluation = _read_json(root / "reports" / "evaluation.json")
    if evaluation.get("dataset_version") != run.get("dataset_version"):
        raise ReproductionError("evaluation 的 dataset_version 与 run 不一致。")
    if evaluation.get("predictions_file_sha256") != run.get("predictions_file_sha256"):
        raise ReproductionError("evaluation 的 predictions_file_sha256 与 run 不一致。")
    return run, evaluation, checks


def _as_finite_vector(value: Any, label: str) -> np.ndarray:
    try:
        vector = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ReproductionError(f"参数 {label} 必须是一维有限数值数组。") from exc
    if vector.ndim != 1 or not np.isfinite(vector).all():
        raise ReproductionError(f"参数 {label} 必须是一维有限数值数组。")
    return vector


def rebuild_logistic(features: Any, parameters: dict[str, Any]) -> np.ndarray:
    """按已保存参数执行一层 NumPy 逻辑回归概率计算。

    ``features`` 已经是按 ``feature_order`` 排列、且雨量特征已完成
    ``log1p`` 的矩阵；缺失值使用 JSON 中保存的训练插补统计量。
    """

    matrix = np.asarray(features, dtype=float)
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2:
        raise ReproductionError("逻辑回归输入必须是二维矩阵。")
    imputer = _as_finite_vector(parameters.get("imputer_statistics"), "imputer_statistics")
    mean = _as_finite_vector(parameters.get("scaler_mean"), "scaler_mean")
    scale = _as_finite_vector(parameters.get("scaler_scale"), "scaler_scale")
    coefficients = _as_finite_vector(parameters.get("coefficients_after_scaled_features"), "coefficients")
    if matrix.shape[1] != len(imputer) or len(imputer) != len(mean) or len(mean) != len(scale) or len(scale) != len(coefficients):
        raise ReproductionError("逻辑回归参数维度不一致。")
    if not np.isfinite(matrix[~np.isnan(matrix)]).all():
        raise ReproductionError("逻辑回归输入含无穷值。")
    if np.any(scale <= 0):
        raise ReproductionError("scaler_scale 必须为正。")
    class_labels = parameters.get("class_labels")
    if class_labels != [0, 1] or parameters.get("positive_class_label") != 1:
        raise ReproductionError("逻辑回归类别标签必须明确为 0/1，且正类为 1。")
    filled = np.where(np.isnan(matrix), imputer.reshape(1, -1), matrix)
    try:
        intercept = float(parameters.get("intercept"))
    except (TypeError, ValueError) as exc:
        raise ReproductionError("逻辑回归截距不是有限值。") from exc
    if not np.isfinite(intercept):
        raise ReproductionError("逻辑回归截距不是有限值。")
    standardized = (filled - mean.reshape(1, -1)) / scale.reshape(1, -1)
    score = standardized @ coefficients + intercept
    probability = np.empty_like(score, dtype=float)
    positive = score >= 0
    probability[positive] = 1.0 / (1.0 + np.exp(-score[positive]))
    exp_score = np.exp(score[~positive])
    probability[~positive] = exp_score / (1.0 + exp_score)
    return np.clip(probability, 0.0, 1.0)


def build_features(samples: pd.DataFrame, parameters: dict[str, Any]) -> np.ndarray:
    """按参数 JSON 的 feature_order 构造模型输入，保持 log1p 顺序。"""

    order = parameters.get("feature_order")
    if not isinstance(order, list) or not order:
        raise ReproductionError("逻辑回归参数缺少 feature_order。")
    columns: list[np.ndarray] = []
    for name in order:
        if name not in {"forecast_rain_mm", "forecast_temperature_mean_c", "forecast_relative_humidity_mean_pct"}:
            raise ReproductionError(f"参数包含未知特征：{name}")
        values = pd.to_numeric(samples[name], errors="coerce").to_numpy(dtype=float)
        if not np.isfinite(values[~np.isnan(values)]).all():
            raise ReproductionError(f"特征 {name} 含无穷值。")
        if name == "forecast_rain_mm":
            if np.any(values[~np.isnan(values)] < 0):
                raise ReproductionError("forecast_rain_mm 含负值，无法执行 log1p。")
            values = np.log1p(values)
        columns.append(values)
    return np.column_stack(columns)


def rebuild_method_predictions(samples: pd.DataFrame, parameters: dict[str, Any]) -> dict[str, np.ndarray]:
    methods = parameters.get("methods")
    logistic_models = parameters.get("logistic_models")
    if not isinstance(methods, dict) or not isinstance(logistic_models, dict):
        raise ReproductionError("model_parameters.json 缺少 methods 或 logistic_models。")
    try:
        climatology = float(methods["training_climatology"]["event_rate"])
        threshold = float(methods["raw_nwp_rule"]["threshold_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ReproductionError("气候率或 raw 规则参数缺失。") from exc
    if not 0 <= climatology <= 1 or not np.isfinite(climatology) or not np.isfinite(threshold) or threshold < 0:
        raise ReproductionError("training_climatology.event_rate 无效。")
    rain = pd.to_numeric(samples["forecast_rain_mm"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(rain[~np.isnan(rain)]).all() or np.any(rain[~np.isnan(rain)] < 0):
        raise ReproductionError("forecast_rain_mm 含无效值。")
    predictions: dict[str, np.ndarray] = {
        "training_climatology": np.full(len(samples), climatology, dtype=float),
        "raw_nwp_rule": (rain >= threshold).astype(float),
    }
    if np.isnan(rain).any():
        raise ReproductionError("raw_nwp_rule 的 forecast_rain_mm 缺失，原规则不补零。")
    for method in LOGISTIC_METHODS:
        model_parameters = logistic_models.get(method)
        if not isinstance(model_parameters, dict):
            raise ReproductionError(f"缺少 {method} 的参数。")
        feature_matrix = build_features(samples, model_parameters)
        predictions[method] = rebuild_logistic(feature_matrix, model_parameters)
    return predictions


def compare_predictions(
    samples: pd.DataFrame,
    frozen: pd.DataFrame,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    if samples["sample_id"].duplicated().any():
        raise ReproductionError("主表 sample_id 不唯一。")
    key_columns = ["sample_id", "method"]
    if frozen.duplicated(key_columns).any():
        raise ReproductionError("冻结预测的 sample_id+method 不唯一。")
    expected_rows = len(samples) * len(METHODS)
    if len(frozen) != expected_rows:
        raise ReproductionError(f"冻结预测行数为 {len(frozen)}，预期 {expected_rows}。")
    expected_keys = {(sample_id, method) for sample_id in samples["sample_id"] for method in METHODS}
    actual_keys = set(zip(frozen["sample_id"], frozen["method"]))
    if actual_keys != expected_keys:
        raise ReproductionError("冻结预测的 sample_id+method 集合与主表不一致。")

    rebuilt = rebuild_method_predictions(samples, parameters)
    frozen_indexed = frozen.set_index(key_columns)
    method_summary: dict[str, Any] = {}
    global_max = 0.0
    for method in METHODS:
        actual = np.asarray(
            [float(frozen_indexed.loc[(sample_id, method), "probability"]) for sample_id in samples["sample_id"]],
            dtype=float,
        )
        expected = rebuilt[method]
        if not np.isfinite(actual).all():
            raise ReproductionError(f"冻结预测 {method} 含非有限概率。")
        difference = np.abs(actual - expected)
        max_error = float(difference.max()) if len(difference) else 0.0
        global_max = max(global_max, max_error)
        method_summary[method] = {
            "sample_count": int(len(actual)),
            "max_abs_error": max_error,
            "passed": bool(max_error <= ERROR_TOLERANCE),
        }
        if max_error > ERROR_TOLERANCE:
            raise ReproductionError(f"{method} 重建概率超过容差：{max_error}")
    return {
        "row_count": int(len(frozen)),
        "method_count": len(METHODS),
        "tolerance": ERROR_TOLERANCE,
        "max_abs_error": global_max,
        "methods": method_summary,
        "passed": True,
    }


def _confusion(actual: np.ndarray, probability: np.ndarray, threshold: float = 0.1) -> dict[str, int | float]:
    predicted = probability >= threshold
    return {
        "threshold": float(threshold),
        "true_negative": int(((actual == 0) & (~predicted)).sum()),
        "false_positive": int(((actual == 0) & predicted).sum()),
        "false_negative": int(((actual == 1) & (~predicted)).sum()),
        "true_positive": int(((actual == 1) & predicted).sum()),
    }


def independently_check_test_metrics(
    samples: pd.DataFrame,
    predictions: pd.DataFrame,
    evaluation: dict[str, Any],
    threshold: float,
) -> dict[str, Any]:
    if predictions.duplicated(["sample_id", "method"]).any():
        raise ReproductionError("预测键存在重复，无法独立聚合测试指标。")
    merged = predictions.merge(samples[["sample_id", "observed_rain_mm"]], on="sample_id", how="left", validate="many_to_one")
    if merged["observed_rain_mm"].isna().any():
        raise ReproductionError("预测无法与主表观测降水完整连接。")
    test = merged.loc[merged["split"].eq("test")].copy()
    if test.empty:
        raise ReproductionError("预测文件没有 test 行。")
    official_metrics = evaluation.get("metrics", {}).get("test")
    if not isinstance(official_metrics, dict):
        official_metrics = evaluation.get("splits", {}).get("test", {}).get("methods")
    if not isinstance(official_metrics, dict):
        raise ReproductionError("evaluation 缺少测试方法指标。")
    methods: dict[str, Any] = {}
    expected_sample_ids: set[str] | None = None
    event_count: int | None = None
    for method in METHODS:
        rows = test.loc[test["method"].eq(method)]
        if len(rows) != len(test) // len(METHODS):
            raise ReproductionError(f"{method} 测试样本数与同批方法不一致。")
        probability = pd.to_numeric(rows["probability"], errors="coerce").to_numpy(dtype=float)
        actual = (pd.to_numeric(rows["observed_rain_mm"], errors="coerce").to_numpy(dtype=float) >= threshold).astype(int)
        if not np.isfinite(actual).all() or not np.isfinite(probability).all():
            raise ReproductionError(f"{method} 测试概率无效。")
        sample_ids = set(rows["sample_id"].astype(str))
        if expected_sample_ids is None:
            expected_sample_ids = sample_ids
            event_count = int(actual.sum())
        elif sample_ids != expected_sample_ids or int(actual.sum()) != event_count:
            raise ReproductionError(f"{method} 测试样本集合或事件标签与同批方法不一致。")
        brier = float(np.mean((probability - actual) ** 2))
        confusion = _confusion(actual, probability, 0.1)
        official = official_metrics.get(method)
        if not isinstance(official, dict):
            raise ReproductionError(f"evaluation 缺少 {method} 测试指标。")
        official_confusion = official.get("confusion_at_probability_0_1")
        brier_difference = brier - float(official["brier"])
        confusion_match = confusion == official_confusion
        passed = abs(brier_difference) <= METRIC_TOLERANCE and confusion_match
        methods[method] = {
            "sample_count": int(len(rows)),
            "event_count": int(event_count or 0),
            "computed_brier": brier,
            "official_brier": float(official["brier"]),
            "brier_difference": brier_difference,
            "computed_confusion_at_probability_0_1": confusion,
            "official_confusion_at_probability_0_1": official_confusion,
            "passed": passed,
        }
        if not passed:
            raise ReproductionError(f"{method} 测试指标与 evaluation 不一致。")
    return {
        "threshold_mm": float(threshold),
        "probability_threshold": 0.1,
        "sample_count": int(len(test) // len(METHODS)),
        "event_count": int(event_count or 0),
        "methods": methods,
        "passed": True,
    }


def run_reproduction(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    run, evaluation, hash_checks = verify_hashes(root)
    samples = pd.read_csv(root / "data" / "samples.csv")
    predictions = pd.read_csv(root / "artifacts" / "predictions.csv")
    parameters = _read_json(root / "artifacts" / "model_parameters.json")
    reconstruction = compare_predictions(samples, predictions, parameters)
    threshold = float(evaluation.get("event_threshold_mm"))
    if float(predictions["event_threshold_mm"].nunique()) != 1 or not np.isclose(float(predictions["event_threshold_mm"].iloc[0]), threshold):
        raise ReproductionError("预测阈值与 evaluation 阈值不一致。")
    metric_check = independently_check_test_metrics(samples, predictions, evaluation, threshold)
    return {
        "status": "passed",
        "checked_at_utc": _utc_now(),
        "dataset_version": run.get("dataset_version"),
        "official_run": "reports/experiment_run.json",
        "hash_checks": hash_checks,
        "prediction_reconstruction": reconstruction,
        "evaluation_recheck": metric_check,
        "limitations": [
            "这是对冻结输入、参数、预测文件和数学计算的复现检查，不是独立外部验证，也没有产生新的预测效果。",
            "复现使用已导出的 SSOD 参考观测和 fixed_lead_composite 数据包；名义 UTC 日与低报限制仍然存在。",
            "测试事件数较少，指标一致只能证明文件和公式复现，不能证明泛化能力。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="梅雨有数冻结实验复现检查")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    report_path = args.root / "reports" / "reproduction_check.json"
    try:
        report = run_reproduction(args.root)
    except ReproductionError as exc:
        report = {
            "status": "failed",
            "checked_at_utc": _utc_now(),
            "error": str(exc),
            "limitations": ["复现检查未完成，不能把部分结果当作通过。"],
        }
        _write_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
