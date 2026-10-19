"""冻结时序切分上的四种降水事件基线实验。

本模块只读 ``data/samples.csv``，不修改主表，也不使用测试集选择模型或
重新拟合。所有可比较的方法都在同一批样本上输出；逻辑回归的缺失值填充
与标准化只在训练集拟合。输出供页面读取的 predictions.csv 仍遵守统一
预测协议，额外的评估细节写入 reports/evaluation.json。
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .contracts import SAMPLE_COLUMNS, validate_predictions, validate_samples


UTC = timezone.utc
DEFAULT_CONFIG = "config/experiment.yaml"
DEFAULT_SAMPLES = "data/samples.csv"
DEFAULT_QUALITY = "reports/data_quality.json"
METHODS = ["training_climatology", "raw_nwp_rule", "logistic_rain", "logistic_weather"]
SELECTION_METHODS = ["training_climatology", "logistic_rain", "logistic_weather"]
FEATURES = {
    "logistic_rain": ["forecast_rain_mm"],
    "logistic_weather": [
        "forecast_rain_mm",
        "forecast_temperature_mean_c",
        "forecast_relative_humidity_mean_pct",
    ],
}
MODEL_FEATURE_LABELS = {
    "forecast_rain_mm": "log1p(forecast_rain_mm)",
    "forecast_temperature_mean_c": "forecast_temperature_mean_c",
    "forecast_relative_humidity_mean_pct": "forecast_relative_humidity_mean_pct",
}


class ExperimentError(RuntimeError):
    """A reproducibility or data-contract failure."""


@dataclass(frozen=True)
class SplitSpec:
    train_start: pd.Timestamp
    validation_start: pd.Timestamp
    test_start: pd.Timestamp


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_hash(path: Path) -> str:
    return _sha256(path)


def load_config(path: Path) -> dict[str, Any]:
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise ExperimentError(f"实验配置不存在：{path}") from exc
    except yaml.YAMLError as exc:
        raise ExperimentError(f"实验配置无法解析：{exc}") from exc
    if not isinstance(config, dict):
        raise ExperimentError("实验配置顶层必须是映射。")
    return config


def split_spec(config: dict[str, Any]) -> SplitSpec:
    splits = config.get("splits", {})
    try:
        def parse_utc(value: Any) -> pd.Timestamp:
            parsed = pd.Timestamp(value)
            return parsed.tz_localize("UTC") if parsed.tzinfo is None else parsed.tz_convert("UTC")

        return SplitSpec(
            train_start=parse_utc(splits.get("train_start", "1900-01-01")),
            validation_start=parse_utc(splits["validation_start"]),
            test_start=parse_utc(splits["test_start"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExperimentError("实验配置的时间切分无效。") from exc


def assign_split(start: pd.Timestamp, end: pd.Timestamp, spec: SplitSpec) -> str:
    """Assign a window only when the complete window stays in one period."""

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    if start.tzinfo is None or end.tzinfo is None:
        raise ExperimentError("样本窗口必须带 UTC 时区。")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if end <= start:
        raise ExperimentError("样本窗口结束时间必须晚于开始时间。")
    if start < spec.validation_start and end <= spec.validation_start:
        return "train"
    if start >= spec.validation_start and end <= spec.test_start:
        return "validation"
    if start >= spec.test_start:
        return "test"
    return "excluded_boundary_crossing"


def build_sample_splits(samples: pd.DataFrame, spec: SplitSpec) -> pd.DataFrame:
    required = {"sample_id", "observation_window_id", "window_start_utc", "window_end_utc", "split"}
    missing = required - set(samples.columns)
    if missing:
        raise ExperimentError("样本缺少切分字段：" + "、".join(sorted(missing)))
    starts = pd.to_datetime(samples["window_start_utc"], errors="coerce", utc=True)
    ends = pd.to_datetime(samples["window_end_utc"], errors="coerce", utc=True)
    if starts.isna().any() or ends.isna().any():
        raise ExperimentError("样本切分时间存在无效值。")
    rows = []
    for index, sample in samples.iterrows():
        split = assign_split(starts.loc[index], ends.loc[index], spec)
        rows.append(
            {
                "sample_id": sample["sample_id"],
                "observation_window_id": sample["observation_window_id"],
                "window_start_utc": starts.loc[index].isoformat().replace("+00:00", "Z"),
                "window_end_utc": ends.loc[index].isoformat().replace("+00:00", "Z"),
                "source_split": sample["split"],
                "experiment_split": split,
                "boundary_status": "complete_window_within_split" if not split.startswith("excluded") else "crosses_split_boundary",
            }
        )
    result = pd.DataFrame(rows)
    if result["sample_id"].duplicated().any() or result["observation_window_id"].duplicated().any():
        raise ExperimentError("切分表中样本或观测窗口重复。")
    if result["experiment_split"].eq("excluded_boundary_crossing").any():
        raise ExperimentError("存在跨越切分边界的窗口，已阻止实验。")
    if set(result["experiment_split"]) != {"train", "validation", "test"}:
        raise ExperimentError("训练、验证或测试切分为空，无法执行冻结比较。")
    return result


def _read_data_version(root: Path, samples_path: Path, quality_path: Path) -> dict[str, str]:
    try:
        quality = json.loads(quality_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise ExperimentError(f"无法读取数据质量报告：{quality_path}") from exc
    samples_digest = _sha256(samples_path)
    expected_version = "meiyu-" + samples_digest[:16]
    if quality.get("dataset_version") != expected_version:
        raise ExperimentError("数据版本与 samples.csv 内容不一致。")
    if quality.get("sample_file_sha256") != samples_digest:
        raise ExperimentError("质量报告中的 samples.csv 散列不一致。")
    manifest_path = root / "data" / "source_manifest.json"
    if quality.get("source_manifest_file_sha256") != _sha256(manifest_path):
        raise ExperimentError("来源清单文件散列不一致。")
    if quality.get("status_label") == "blocked":
        raise ExperimentError("数据质量报告仍为 blocked，拒绝建模。")
    return {
        "dataset_version": expected_version,
        "sample_file_sha256": samples_digest,
        "source_manifest_file_sha256": _sha256(manifest_path),
    }


def load_samples(root: Path, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, str]]:
    samples_path = root / config.get("data", {}).get("samples_path", DEFAULT_SAMPLES)
    quality_path = root / config.get("data", {}).get("quality_path", DEFAULT_QUALITY)
    if not samples_path.exists():
        raise ExperimentError(f"样本文件不存在：{samples_path}")
    # Keep row labels positional.  The split table and prediction arrays are
    # aligned by position, so a caller cannot accidentally pass through a
    # non-contiguous CSV index after filtering or concatenation.
    samples = pd.read_csv(samples_path).reset_index(drop=True)
    contract_errors = validate_samples(samples)
    if contract_errors:
        raise ExperimentError("样本协议校验失败：" + "；".join(contract_errors))
    versions = _read_data_version(root, samples_path, quality_path)
    if samples.empty:
        raise ExperimentError("样本表为空，拒绝执行实验。")
    numeric = ["observed_rain_mm", "forecast_rain_mm", "forecast_temperature_mean_c", "forecast_relative_humidity_mean_pct"]
    for column in numeric:
        values = pd.to_numeric(samples[column], errors="coerce")
        if column in {"observed_rain_mm", "forecast_rain_mm"} and values.isna().any():
            raise ExperimentError(f"{column} 含缺失值，无法建立统一事件或规则输入。")
        if not np.isfinite(values.dropna().to_numpy(dtype=float)).all():
            raise ExperimentError(f"{column} 含非有限值。")
    return samples, versions


def event_target(samples: pd.DataFrame, threshold: float) -> pd.Series:
    observed = pd.to_numeric(samples["observed_rain_mm"], errors="coerce")
    if observed.isna().any() or (observed < 0).any():
        raise ExperimentError("观测降水含缺失或负值，无法定义事件。")
    return (observed >= threshold).astype(int)


def prepare_features(samples: pd.DataFrame, method: str) -> pd.DataFrame:
    if method not in FEATURES:
        raise ExperimentError(f"未知逻辑回归方法：{method}")
    frame = pd.DataFrame(index=samples.index)
    for name in FEATURES[method]:
        values = pd.to_numeric(samples[name], errors="coerce")
        if name == "forecast_rain_mm":
            if values.isna().any() or (values < 0).any():
                raise ExperimentError("forecast_rain_mm 缺失或为负，raw_nwp_rule 与逻辑回归均拒绝执行。")
            frame[name] = np.log1p(values)
        else:
            frame[name] = values
    return frame


def make_logistic_pipeline(c_value: float, random_seed: int, feature_count: int) -> Pipeline:
    # keep_empty_features makes an all-missing optional weather field explicit
    # and deterministic; the imputer is still fitted on train only.
    return Pipeline(
        steps=[
            ("simpleimputer", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("standardscaler", StandardScaler()),
            (
                "logisticregression",
                LogisticRegression(
                    C=float(c_value),
                    max_iter=3000,
                    random_state=random_seed,
                    class_weight=None,
                    solver="lbfgs",
                ),
            ),
        ]
    )


def choose_c(
    x_train: pd.DataFrame,
    y_train: pd.Series,
    x_validation: pd.DataFrame,
    y_validation: pd.Series,
    c_grid: Iterable[float],
    random_seed: int,
) -> tuple[float, list[dict[str, Any]]]:
    if y_train.nunique() < 2:
        raise ExperimentError("训练集只有一个事件类别，逻辑回归无法在冻结规则下拟合。")
    if y_validation.empty:
        raise ExperimentError("验证集为空，不能按验证 Brier 选择 C。")
    scores = []
    for c_value in sorted(float(value) for value in c_grid):
        model = make_logistic_pipeline(c_value, random_seed, x_train.shape[1])
        model.fit(x_train, y_train)
        probability = model.predict_proba(x_validation)[:, 1]
        scores.append({"C": c_value, "validation_brier": float(brier_score_loss(y_validation, probability))})
    best_score = min(item["validation_brier"] for item in scores)
    tied = [item for item in scores if abs(item["validation_brier"] - best_score) <= 1e-12]
    selected = min(tied, key=lambda item: item["C"])
    return float(selected["C"]), scores


def fit_logistic_method(
    samples: pd.DataFrame,
    y: pd.Series,
    split_table: pd.DataFrame,
    method: str,
    c_grid: Iterable[float],
    random_seed: int,
) -> tuple[Pipeline, float, list[dict[str, Any]]]:
    feature_frame = prepare_features(samples, method)
    train_index = split_table.index[split_table["experiment_split"].eq("train")]
    validation_index = split_table.index[split_table["experiment_split"].eq("validation")]
    selected_c, grid_scores = choose_c(
        feature_frame.loc[train_index],
        y.loc[train_index],
        feature_frame.loc[validation_index],
        y.loc[validation_index],
        c_grid,
        random_seed,
    )
    final_model = make_logistic_pipeline(selected_c, random_seed, feature_frame.shape[1])
    final_model.fit(feature_frame.loc[train_index], y.loc[train_index])
    return final_model, selected_c, grid_scores


def predict_method(
    samples: pd.DataFrame,
    y: pd.Series,
    split_table: pd.DataFrame,
    method: str,
    models: dict[str, Any],
) -> np.ndarray:
    if method == "training_climatology":
        return np.full(len(samples), float(models[method]["event_rate"]), dtype=float)
    if method == "raw_nwp_rule":
        rain = pd.to_numeric(samples["forecast_rain_mm"], errors="coerce")
        if rain.isna().any():
            raise ExperimentError("raw_nwp_rule 遇到缺失 forecast_rain_mm，拒绝补零。")
        return (rain.to_numpy(dtype=float) >= models[method]["threshold_mm"]).astype(float)
    feature_frame = prepare_features(samples, method)
    return models[method]["pipeline"].predict_proba(feature_frame)[:, 1]


def _safe_auc(metric, y: np.ndarray, probability: np.ndarray) -> float | None:
    if len(np.unique(y)) < 2:
        return None
    try:
        return float(metric(y, probability))
    except ValueError:
        return None


def confusion_at_threshold(y: Iterable[int], probability: Iterable[float], threshold: float = 0.1) -> dict[str, int | float]:
    actual = np.asarray(list(y), dtype=int)
    predicted = (np.asarray(list(probability), dtype=float) >= float(threshold)).astype(int)
    return {
        "threshold": float(threshold),
        "true_negative": int(((actual == 0) & (predicted == 0)).sum()),
        "false_positive": int(((actual == 0) & (predicted == 1)).sum()),
        "false_negative": int(((actual == 1) & (predicted == 0)).sum()),
        "true_positive": int(((actual == 1) & (predicted == 1)).sum()),
    }


def calibration_bins(y: Iterable[int], probability: Iterable[float]) -> list[dict[str, Any]]:
    actual = np.asarray(list(y), dtype=int)
    predicted = np.asarray(list(probability), dtype=float)
    edges = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
    result = []
    for index in range(5):
        lower, upper = float(edges[index]), float(edges[index + 1])
        if index == 4:
            mask = (predicted >= lower) & (predicted <= upper)
            interval = f"[{lower:.1f},{upper:.1f}]"
        else:
            mask = (predicted >= lower) & (predicted < upper)
            interval = f"[{lower:.1f},{upper:.1f})"
        count = int(mask.sum())
        result.append(
            {
                "bin": interval,
                "count": count,
                "event_count": int(actual[mask].sum()) if count else 0,
                "mean_probability": float(predicted[mask].mean()) if count else None,
                "observed_event_rate": float(actual[mask].mean()) if count else None,
            }
        )
    return result


def metrics_for_split(y: pd.Series, probability: np.ndarray) -> dict[str, Any]:
    actual = y.to_numpy(dtype=int)
    probability = np.asarray(probability, dtype=float)
    return {
        "sample_count": int(len(actual)),
        "event_count": int(actual.sum()),
        "brier": float(brier_score_loss(actual, probability)),
        "roc_auc": _safe_auc(roc_auc_score, actual, probability),
        "average_precision": _safe_auc(average_precision_score, actual, probability),
        "confusion_at_probability_0_1": confusion_at_threshold(actual, probability, 0.1),
        "calibration_bins": calibration_bins(actual, probability),
    }


def _week_key(starts: pd.Series) -> pd.Series:
    utc = pd.to_datetime(starts, utc=True)
    iso = utc.dt.isocalendar()
    return iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)


def paired_brier_bootstrap(
    test_table: pd.DataFrame,
    selected_probability: np.ndarray,
    baseline_probability: np.ndarray,
    baseline_name: str,
    seed: int,
    replicates: int,
) -> dict[str, Any]:
    y = test_table["event"].to_numpy(dtype=int)
    selected_loss = (selected_probability - y) ** 2
    baseline_loss = (baseline_probability - y) ** 2
    difference = selected_loss - baseline_loss
    keys = _week_key(test_table["window_start_utc"]).to_numpy()
    blocks = [np.flatnonzero(keys == key) for key in pd.unique(keys)]
    result: dict[str, Any] = {
        "comparison": f"{baseline_name} -> selected",
        "definition": "selected individual Brier loss minus baseline individual Brier loss; negative favors selected",
        "test_sample_count": int(len(y)),
        "test_event_count": int(y.sum()),
        "calendar_week_block_count": int(len(blocks)),
        "bootstrap_replicates": int(replicates),
        "random_seed": int(seed),
        "mean_difference": float(difference.mean()) if len(difference) else None,
        "ci95": None,
        "limitations": ["测试事件数较少，周块之间仍可能相关；区间只反映本次固定测试日历的重采样不确定性。"],
    }
    if not blocks:
        return result
    rng = np.random.default_rng(seed)
    samples = np.empty(replicates, dtype=float)
    for iteration in range(replicates):
        chosen = rng.integers(0, len(blocks), size=len(blocks))
        indices = np.concatenate([blocks[index] for index in chosen])
        samples[iteration] = float(difference[indices].mean())
    result["ci95"] = {
        "lower": float(np.quantile(samples, 0.025)),
        "upper": float(np.quantile(samples, 0.975)),
    }
    return result


def cost_scenarios(y: Iterable[int], probability: Iterable[float], ratios: Iterable[float], loss_unit: float = 1.0) -> list[dict[str, Any]]:
    actual = np.asarray(list(y), dtype=int)
    predicted = np.asarray(list(probability), dtype=float)
    rows = []
    for ratio in ratios:
        ratio = float(ratio)
        threshold = ratio / float(loss_unit)
        prepare = predicted >= threshold
        realized = prepare.astype(float) * ratio + ((~prepare) & (actual == 1)).astype(float) * loss_unit
        rows.append(
            {
                "prepare_cost_ratio": ratio,
                "loss_unit": float(loss_unit),
                "decision_probability_threshold": threshold,
                "sample_count": int(len(actual)),
                "prepare_count": int(prepare.sum()),
                "event_count": int(actual.sum()),
                "event_loss_count_without_prepare": int(((~prepare) & (actual == 1)).sum()),
                "mean_realized_cost": float(realized.mean()) if len(realized) else None,
                "total_realized_cost": float(realized.sum()),
            }
        )
    return rows


def always_never_costs(event_count: int, sample_count: int, ratios: Iterable[float], loss_unit: float = 1.0) -> dict[str, list[dict[str, Any]]]:
    event_rate = event_count / sample_count if sample_count else None
    always, never = [], []
    for ratio in ratios:
        ratio = float(ratio)
        always.append(
            {
                "prepare_cost_ratio": ratio,
                "sample_count": int(sample_count),
                "mean_realized_cost": ratio,
                "total_realized_cost": ratio * sample_count,
                "decision": "always_prepare",
            }
        )
        never.append(
            {
                "prepare_cost_ratio": ratio,
                "sample_count": int(sample_count),
                "event_count": int(event_count),
                "mean_realized_cost": event_rate * loss_unit if event_rate is not None else None,
                "total_realized_cost": float(event_count * loss_unit),
                "decision": "never_prepare",
            }
        )
    return {"always_prepare": always, "never_prepare": never}


def guard_frozen_run(run_path: Path, identity: dict[str, str], replace: bool = False) -> dict[str, Any] | None:
    if not run_path.exists():
        return None
    try:
        existing = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if not replace:
            raise ExperimentError(f"已有 experiment_run.json 无法解析；如确认覆盖请使用 --replace：{exc}") from exc
        return None
    frozen = existing.get("frozen", {})
    keys = ["dataset_version", "sample_file_sha256", "source_manifest_file_sha256", "config_hash"]
    mismatch = {key: (frozen.get(key), identity.get(key)) for key in keys if frozen.get(key) != identity.get(key)}
    if mismatch and not replace:
        raise ExperimentError("已有实验冻结身份不同，拒绝覆盖；请显式使用 --replace：" + json.dumps(mismatch, ensure_ascii=False))
    if not mismatch and not replace and existing.get("status") == "completed":
        output_root = run_path.parent.parent
        output_specs = {
            "predictions": ("predictions_file_sha256", "artifacts/predictions.csv"),
            "evaluation": ("evaluation_file_sha256", "reports/evaluation.json"),
            "sample_splits": ("sample_splits_file_sha256", "artifacts/sample_splits.csv"),
            "model_parameters": ("model_parameters_file_sha256", "artifacts/model_parameters.json"),
        }
        declared_paths = existing.get("artifacts", {})
        for artifact_name, (hash_name, default_path) in output_specs.items():
            expected_hash = existing.get(hash_name)
            relative_path = declared_paths.get(artifact_name, default_path)
            if not isinstance(expected_hash, str) or not expected_hash:
                raise ExperimentError(f"已有 completed 实验缺少 {hash_name}，拒绝直接复用；请使用 --replace 重建。")
            if not isinstance(relative_path, str) or not relative_path:
                raise ExperimentError(f"已有 completed 实验缺少 {artifact_name} 路径，拒绝直接复用。")
            candidate = (output_root / Path(relative_path)).resolve()
            try:
                candidate.relative_to(output_root.resolve())
            except ValueError as exc:
                raise ExperimentError(f"实验输出路径越出项目根目录：{relative_path}") from exc
            if not candidate.is_file():
                raise ExperimentError(f"已有 completed 实验缺少输出文件：{candidate}")
            actual_hash = _sha256(candidate)
            if actual_hash != expected_hash:
                raise ExperimentError(
                    f"已有 completed 实验输出已损坏：{artifact_name} SHA256 {actual_hash} != {expected_hash}。"
                )
        return existing
    return None


def _model_version(method: str, config_hash: str, selected_c: float | None = None) -> str:
    suffix = f"-C{selected_c:g}" if selected_c is not None else ""
    return f"{method}-v1{suffix}-cfg{config_hash[:8]}"


def run_experiment(root: Path, config_path: Path | None = None, replace: bool = False) -> dict[str, Any]:
    root = Path(root)
    config_path = config_path or root / DEFAULT_CONFIG
    config = load_config(config_path)
    config_digest = _config_hash(config_path)
    samples, versions = load_samples(root, config)
    identity = {**versions, "config_hash": config_digest}
    run_path = root / "reports" / "experiment_run.json"
    previous = guard_frozen_run(run_path, identity, replace=replace)
    if previous is not None:
        return previous

    threshold = float(config.get("event", {}).get("threshold_mm", 25.0))
    seed = int(config.get("model", {}).get("random_seed", 20261013))
    max_iter = int(config.get("model", {}).get("max_iter", 3000))
    c_grid = [float(value) for value in config.get("model", {}).get("c_grid", [0.1, 1.0, 10.0])]
    bootstrap_seed = int(config.get("evaluation", {}).get("bootstrap_seed", 20261013))
    if max_iter != 3000 or seed != 20261013 or bootstrap_seed != 20261013 or c_grid != [0.1, 1.0, 10.0]:
        raise ExperimentError("模型参数已偏离冻结要求：seed=20261013、max_iter=3000、C=[0.1,1,10]。")
    split = split_spec(config)
    split_table = build_sample_splits(samples, split)
    split_table["event"] = event_target(samples, threshold).to_numpy()
    split_table["forecast_rain_mm"] = pd.to_numeric(samples["forecast_rain_mm"], errors="coerce").to_numpy()
    split_table["window_start_utc"] = samples["window_start_utc"].to_numpy()
    split_table["window_end_utc"] = samples["window_end_utc"].to_numpy()

    train_index = split_table.index[split_table["experiment_split"].eq("train")]
    validation_index = split_table.index[split_table["experiment_split"].eq("validation")]
    test_index = split_table.index[split_table["experiment_split"].eq("test")]
    y = pd.Series(split_table["event"].to_numpy(), index=samples.index, dtype=int)
    train_rate = float(y.loc[train_index].mean())
    models: dict[str, Any] = {
        "training_climatology": {"event_rate": train_rate},
        "raw_nwp_rule": {"threshold_mm": threshold},
    }
    grid_details: dict[str, Any] = {}
    selected_cs: dict[str, float] = {}
    for method in ("logistic_rain", "logistic_weather"):
        model, selected_c, scores = fit_logistic_method(samples, y, split_table, method, c_grid, seed)
        models[method] = {"pipeline": model}
        selected_cs[method] = selected_c
        grid_details[method] = {"selected_C": selected_c, "scores": scores, "fit_split": "train", "selection_split": "validation"}

    probabilities: dict[str, np.ndarray] = {}
    model_versions: dict[str, str] = {}
    for method in METHODS:
        probabilities[method] = predict_method(samples, y, split_table, method, models)
        model_versions[method] = _model_version(method, config_digest, selected_cs.get(method))

    validation_brier = {}
    for method in SELECTION_METHODS:
        validation_brier[method] = float(
            brier_score_loss(y.loc[validation_index], probabilities[method][validation_index])
        )
    # Stable tie order is the order in SELECTION_METHODS; raw_nwp_rule is only
    # a deterministic control and cannot win the recommendation.
    selected_method = min(SELECTION_METHODS, key=lambda method: (validation_brier[method], SELECTION_METHODS.index(method)))
    selected_is_logistic = selected_method.startswith("logistic_")
    recommendation = (
        f"按验证集 Brier 固定选择 {selected_method}。"
        if selected_is_logistic
        else "验证集未支持逻辑回归胜出，按冻结规则选择 training_climatology；不根据测试表现改参数。"
    )

    prediction_rows: list[dict[str, Any]] = []
    for index, sample in samples.iterrows():
        experiment_split = split_table.loc[index, "experiment_split"]
        role = {"train": "fit", "validation": "validation", "test": "holdout"}[experiment_split]
        for method in METHODS:
            prediction_rows.append(
                {
                    "sample_id": sample["sample_id"],
                    "method": method,
                    "probability": float(np.clip(probabilities[method][index], 0.0, 1.0)),
                    "model_version": model_versions[method],
                    "dataset_version": versions["dataset_version"],
                    "experiment_kind": sample["experiment_kind"],
                    "event_threshold_mm": threshold,
                    "split": experiment_split,
                    "evaluation_role": role,
                    "is_selected": method == selected_method,
                    "fit_split": "train",
                    "selection_split": "validation" if method.startswith("logistic_") else "frozen_definition",
                }
            )
    predictions = pd.DataFrame(prediction_rows)
    contract_errors = validate_predictions(predictions, samples, versions["dataset_version"])
    if contract_errors:
        raise ExperimentError("预测协议校验失败：" + "；".join(contract_errors))

    split_metrics: dict[str, Any] = OrderedDict()
    for split_name, indices in [("train", train_index), ("validation", validation_index), ("test", test_index)]:
        split_metrics[split_name] = {
            "sample_count": int(len(indices)),
            "event_count": int(y.loc[indices].sum()),
            "methods": {
                method: metrics_for_split(y.loc[indices], probabilities[method][indices]) for method in METHODS
            },
        }

    test_table = split_table.loc[test_index, ["event", "window_start_utc", "window_end_utc"]].copy()
    selected_test = probabilities[selected_method][test_index]
    bootstrap = [
        paired_brier_bootstrap(
            test_table,
            selected_test,
            probabilities[baseline][test_index],
            baseline,
            bootstrap_seed,
            int(config.get("evaluation", {}).get("bootstrap_replicates", 2000)),
        )
        for baseline in ["training_climatology", "raw_nwp_rule"]
    ]
    ratios = [float(value) for value in config.get("cost_scenarios", {}).get("prepare_cost_ratios", [0.02, 0.05, 0.1, 0.2, 0.4, 0.6])]
    costs = {
        "loss_unit": 1.0,
        "assumption": "prepare 付成本 C；未准备且事件发生付 L=1；假设准备完全避免损失；单位为相对成本，不是人民币或真实灾损。",
        "methods": {
            method: cost_scenarios(y.loc[test_index], probabilities[method][test_index], ratios, 1.0)
            for method in METHODS
        },
        **always_never_costs(int(y.loc[test_index].sum()), int(len(test_index)), ratios, 1.0),
    }

    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    sample_splits_path = artifacts / "sample_splits.csv"
    split_table.drop(columns=["event", "forecast_rain_mm", "window_start_utc", "window_end_utc"]).to_csv(
        sample_splits_path, index=False, encoding="utf-8-sig"
    )
    sample_splits_file_sha256 = _sha256(sample_splits_path)
    predictions_path = artifacts / "predictions.csv"
    predictions.to_csv(predictions_path, index=False, encoding="utf-8-sig")
    predictions_file_sha256 = _sha256(predictions_path)

    model_parameters: dict[str, Any] = {
        "random_seed": seed,
        "max_iter": max_iter,
        "class_weight": None,
        "preprocessing": {"imputer": "SimpleImputer(strategy=median, keep_empty_features=True)", "scaler": "StandardScaler", "fit_split": "train"},
        "methods": {
            "training_climatology": {"event_rate": train_rate, "model_version": model_versions["training_climatology"]},
            "raw_nwp_rule": {"threshold_mm": threshold, "deterministic_indicator": True, "model_version": model_versions["raw_nwp_rule"]},
        },
        "logistic_models": {},
    }
    for method in ("logistic_rain", "logistic_weather"):
        pipeline = models[method]["pipeline"]
        imputer = pipeline.named_steps["simpleimputer"]
        scaler = pipeline.named_steps["standardscaler"]
        classifier = pipeline.named_steps["logisticregression"]
        feature_names = [MODEL_FEATURE_LABELS[name] for name in FEATURES[method]]
        model_parameters["logistic_models"][method] = {
            "feature_order": list(FEATURES[method]),
            "features": feature_names,
            "imputer_statistics": [float(value) for value in imputer.statistics_],
            "scaler_mean": [float(value) for value in scaler.mean_],
            "scaler_scale": [float(value) for value in scaler.scale_],
            "class_labels": [value.item() if hasattr(value, "item") else value for value in classifier.classes_],
            "positive_class_label": classifier.classes_[1].item() if hasattr(classifier.classes_[1], "item") else classifier.classes_[1],
            "selected_C": selected_cs[method],
            "grid_scores": grid_details[method]["scores"],
            "coefficients_after_scaled_features": classifier.coef_[0].tolist(),
            "intercept": float(classifier.intercept_[0]),
            "model_version": model_versions[method],
            "fit_split": "train",
            "selection_split": "validation",
        }
    model_parameters_path = artifacts / "model_parameters.json"
    _json_dump(model_parameters_path, model_parameters)
    model_parameters_file_sha256 = _sha256(model_parameters_path)

    event_counts_for_report = {
        name: int(values["event_count"]) for name, values in split_metrics.items()
    }

    evaluation = {
        "dataset_version": versions["dataset_version"],
        "sample_file_sha256": versions["sample_file_sha256"],
        "source_manifest_file_sha256": versions["source_manifest_file_sha256"],
        "config_hash": config_digest,
        "config_sha256": config_digest,
        "predictions_file_sha256": predictions_file_sha256,
        "event_threshold_mm": threshold,
        "selected_method": selected_method,
        "recommendation": recommendation,
        "selection": {
            "candidate_methods": SELECTION_METHODS,
            "excluded_control": "raw_nwp_rule",
            "validation_brier": validation_brier,
            "tie_break": "SELECTION_METHODS 顺序；逻辑回归 C 平局取更小 C",
            "grid_details": grid_details,
        },
        "splits": split_metrics,
        "split_summary": {
            name: {"sample_count": values["sample_count"], "event_count": values["event_count"]}
            for name, values in split_metrics.items()
        },
        "metrics": {name: values["methods"] for name, values in split_metrics.items()},
        "paired_brier_bootstrap": bootstrap,
        "cost_scenarios": costs,
        "limitations": [
            f"训练事件{event_counts_for_report['train']}个、验证事件{event_counts_for_report['validation']}个、测试事件{event_counts_for_report['test']}个；ROC-AUC/AP 在单类切分返回 null。",
            "测试集只用于最终报告，未参与 C 或推荐方法选择；周块 bootstrap 不能消除小事件数与站点/季节相关性。",
            "logistic_weather 的部分训练湿度缺失由仅在训练集拟合的中位数填充处理；缺失处理不代表真实传感器可用性。",
            "forecast_rain_mm>=25 的 raw_nwp_rule 是确定性指示量，不是原始概率。",
            "事件阈值25mm是研究阈值，不等于官方预警等级或积水等级。",
            "成本输出是假设准备完全避免损失的相对单位，不能解释为人民币或真实灾损。",
            "样本观测为 SSOD 同站参考，存在名义 UTC 日与低报限制；结果只能作为 offline_fixed_lead 方法比较。",
        ],
    }
    _json_dump(root / "reports" / "evaluation.json", evaluation)

    run_record = {
        "status": "completed",
        "created_utc": _utc_now(),
        "experiment_version": config.get("experiment_version", "meiyu-experiment-v1"),
        "dataset_version": versions["dataset_version"],
        "config_sha256": config_digest,
        "predictions_file_sha256": predictions_file_sha256,
        "sample_splits_file_sha256": sample_splits_file_sha256,
        "model_parameters_file_sha256": model_parameters_file_sha256,
        "frozen": identity,
        "selected_method": selected_method,
        "model_versions": model_versions,
        "sample_count": int(len(samples)),
        "split_counts": {name: int(len(indices)) for name, indices in [("train", train_index), ("validation", validation_index), ("test", test_index)]},
        "event_counts": {name: int(y.loc[indices].sum()) for name, indices in [("train", train_index), ("validation", validation_index), ("test", test_index)]},
        "artifacts": {
            "predictions": "artifacts/predictions.csv",
            "sample_splits": "artifacts/sample_splits.csv",
            "model_parameters": "artifacts/model_parameters.json",
            "evaluation": "reports/evaluation.json",
        },
        "frozen_method_rules": {
            "fit_split": "train",
            "selection_split": "validation",
            "holdout_split": "test",
            "refit_train_plus_validation": False,
            "class_weight": None,
            "random_seed": seed,
            "bootstrap_seed": bootstrap_seed,
            "max_iter": max_iter,
            "c_grid": c_grid,
            "bootstrap_replicates": int(config.get("evaluation", {}).get("bootstrap_replicates", 2000)),
        },
    }
    # The report hash is recorded after the report is written; all inputs and
    # derived files can therefore be checked before the page consumes them.
    run_record["evaluation_file_sha256"] = _sha256(root / "reports" / "evaluation.json")
    _json_dump(run_path, run_record)
    return run_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="梅雨有数冻结时序模型实验")
    parser.add_argument("command", choices=["run"])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--replace", action="store_true", help="显式允许覆盖已有不同冻结身份的实验输出")
    args = parser.parse_args(argv)
    result = run_experiment(args.root, args.config, replace=args.replace)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
