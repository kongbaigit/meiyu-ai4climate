from __future__ import annotations

import math
import pandas as pd

SCHEMA_VERSION = "1.0.0"
SAMPLE_COLUMNS = [
    "sample_id", "observation_window_id", "forecast_spec_id", "station_id",
    "station_name", "station_lat", "station_lon", "window_start_utc",
    "window_end_utc", "observed_rain_mm", "observation_measurement_code",
    "reference_kind", "window_basis", "forecast_model", "forecast_kind",
    "run_init_utc", "available_at_utc", "availability_evidence",
    "decision_time_utc", "forecast_rain_mm", "forecast_temperature_mean_c",
    "forecast_relative_humidity_mean_pct", "experiment_kind", "quality_status",
    "audit_version", "obs_record_id", "forecast_record_id", "source_manifest_id",
    "split",
]
EXPERIMENT_KINDS = {"offline_fixed_lead", "offline_hindcast", "operational_replay"}
REFERENCE_KINDS = {"ssod_derived_station", "station_observation"}
WINDOW_BASES = {"nominal_utc_synoptic_day", "verified_station_window"}
PREDICTION_COLUMNS = [
    "sample_id", "method", "probability", "model_version", "dataset_version",
    "experiment_kind", "event_threshold_mm",
]


def _finite_numeric(series: pd.Series, lower: float | None = None) -> bool:
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().any() or not values.map(math.isfinite).all():
        return False
    return lower is None or bool((values >= lower).all())


def validate_samples(frame: pd.DataFrame) -> list[str]:
    errors = []
    missing = sorted(set(SAMPLE_COLUMNS) - set(frame.columns))
    if missing:
        return ["主表缺少字段：" + "、".join(missing)]
    if frame.empty:
        return []
    for column in ["sample_id", "observation_window_id", "forecast_spec_id", "station_id",
                   "obs_record_id", "forecast_record_id", "source_manifest_id"]:
        if frame[column].isna().any() or frame[column].astype(str).str.strip().eq("").any():
            errors.append(f"{column} 存在空值。")
    if frame["sample_id"].duplicated().any():
        errors.append("sample_id 不唯一。")
    if not frame["quality_status"].eq("passed").all():
        errors.append("主表包含未通过质量检查的记录。")
    if not frame["experiment_kind"].isin(EXPERIMENT_KINDS).all():
        errors.append("实验类型不在约定范围内。")
    if not frame["reference_kind"].isin(REFERENCE_KINDS).all():
        errors.append("参考观测类型不在约定范围内。")
    if not frame["window_basis"].isin(WINDOW_BASES).all():
        errors.append("累计日界依据不在约定范围内。")
    for name in ["observed_rain_mm", "forecast_rain_mm"]:
        if not _finite_numeric(frame[name], 0):
            errors.append(f"{name} 包含缺失、非有限值或负值。")
    for name, low, high in [("station_lat", -90, 90), ("station_lon", -180, 180)]:
        values = pd.to_numeric(frame[name], errors="coerce")
        if not _finite_numeric(frame[name]) or not values.between(low, high).all():
            errors.append(f"{name} 坐标无效。")
    times = {}
    for name in ["window_start_utc", "window_end_utc"]:
        raw = frame[name].astype("string")
        if not raw.str.contains(r"(?:Z|\+00:00)$", regex=True, na=False).all():
            errors.append(f"{name} 必须显式标注 UTC。")
        times[name] = pd.to_datetime(frame[name], errors="coerce", utc=True)
        if times[name].isna().any():
            errors.append(f"{name} 时间无效。")
    if not (times["window_end_utc"] - times["window_start_utc"]).eq(pd.Timedelta(hours=24)).all():
        errors.append("主表存在非 24 小时窗口。")
    nominal = frame["window_basis"].eq("nominal_utc_synoptic_day")
    if not times["window_start_utc"].loc[nominal].eq(times["window_start_utc"].loc[nominal].dt.normalize()).all():
        errors.append("名义 UTC 日必须从 00:00 开始。")
    ssod = frame["reference_kind"].eq("ssod_derived_station")
    if not frame.loc[ssod, "observation_measurement_code"].astype(str).isin({"D", "F", "G", "24"}).all():
        errors.append("SSOD 参考观测缺少完整报告测量码。")
    if not frame.loc[ssod, "window_basis"].eq("nominal_utc_synoptic_day").all():
        errors.append("SSOD 参考观测必须保留名义 UTC 日标记。")
    expected_kind = frame["experiment_kind"].map({"offline_fixed_lead": "fixed_lead_composite", "offline_hindcast": "hindcast", "operational_replay": "operational_archive"})
    if not frame["forecast_kind"].eq(expected_kind).all():
        errors.append("预报类型与实验类型不一致，hindcast 或合成序列不能用于实际决策回放。")
    if not frame["split"].fillna("unassigned").isin({"unassigned", "train", "validation", "test"}).all():
        errors.append("split 含未知划分名称。")
    for name in ["forecast_temperature_mean_c", "forecast_relative_humidity_mean_pct"]:
        provided = frame[name].notna()
        if not _finite_numeric(frame.loc[provided, name]):
            errors.append(f"{name} 包含无法解释的非数值或非有限值。")
    rh = pd.to_numeric(frame["forecast_relative_humidity_mean_pct"], errors="coerce")
    if not rh.dropna().between(0, 100).all():
        errors.append("预报相对湿度超出 0 到 100。")
    replay = frame["experiment_kind"].eq("operational_replay")
    if replay.any():
        subset = frame.loc[replay]
        available = pd.to_datetime(subset["available_at_utc"], errors="coerce", utc=True)
        decision = pd.to_datetime(subset["decision_time_utc"], errors="coerce", utc=True)
        initialisation = pd.to_datetime(subset["run_init_utc"], errors="coerce", utc=True)
        start = times["window_start_utc"].loc[replay]
        explicit = all(subset[name].astype("string").str.contains(r"(?:Z|\+00:00)$", regex=True, na=False).all() for name in ["run_init_utc", "available_at_utc", "decision_time_utc"])
        if not explicit or initialisation.isna().any() or available.isna().any() or decision.isna().any() or not ((initialisation <= available) & (available <= decision) & (decision <= start)).all():
            errors.append("实际决策回放缺少可信可用时刻或违反时间顺序。")
        if subset["availability_evidence"].isna().any() or subset["availability_evidence"].astype(str).str.strip().eq("").any():
            errors.append("实际决策回放缺少发布时间证据。")
        if not subset["forecast_kind"].eq("operational_archive").all():
            errors.append("实际决策回放不能使用 hindcast 或合成序列。")
    return errors


def validate_predictions(frame: pd.DataFrame, samples: pd.DataFrame, dataset_version: str) -> list[str]:
    missing = sorted(set(PREDICTION_COLUMNS) - set(frame.columns))
    if missing:
        return ["预测文件缺少字段：" + "、".join(missing)]
    if frame.empty:
        return ["预测文件没有记录。"]
    errors = []
    for name in ["sample_id", "method", "model_version", "dataset_version", "experiment_kind"]:
        if frame[name].isna().any() or frame[name].astype(str).str.strip().eq("").any():
            errors.append(f"预测文件的 {name} 存在空值。")
    if not dataset_version or not frame["dataset_version"].eq(dataset_version).all():
        errors.append("预测文件的数据版本与当前样本包不一致。")
    unknown = set(frame["sample_id"].dropna()) - set(samples["sample_id"])
    if unknown:
        errors.append(f"预测文件包含 {len(unknown)} 个未知样本。")
    if frame.duplicated(["sample_id", "method", "model_version"]).any():
        errors.append("同一模型方法存在重复样本预测。")
    probabilities = pd.to_numeric(frame["probability"], errors="coerce")
    if not _finite_numeric(frame["probability"], 0) or not probabilities.between(0, 1).all():
        errors.append("概率必须为 0 到 1 之间的有限数值。")
    thresholds = pd.to_numeric(frame["event_threshold_mm"], errors="coerce")
    if not _finite_numeric(frame["event_threshold_mm"]) or not (thresholds > 0).all() or thresholds.nunique() != 1:
        errors.append("预测文件需要一个明确且一致的正降水阈值。")
    kind_map = samples.set_index("sample_id")["experiment_kind"] if not samples["sample_id"].duplicated().any() else pd.Series(dtype=str)
    if not kind_map.empty:
        expected = frame["sample_id"].map(kind_map)
        known = expected.notna()
        if not frame.loc[known, "experiment_kind"].eq(expected.loc[known]).all():
            errors.append("预测文件的实验类型与对应样本不一致。")
    return errors
