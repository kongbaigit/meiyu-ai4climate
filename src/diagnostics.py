from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score

from .bundle import load_bundle
from .results import load_results


def build_diagnostics(root: Path) -> dict:
    data = load_bundle(root)
    results = load_results(root, data)
    if data.errors or not results.ready:
        raise ValueError("数据或冻结实验未通过检查：" + "；".join(data.errors + results.errors))
    table = results.predictions.loc[results.predictions["split"].eq("test")].merge(data.samples.drop(columns="split"), on="sample_id", validate="many_to_one", suffixes=("", "_sample"))
    table["event"] = table.observed_rain_mm.ge(float(results.evaluation["event_threshold_mm"]))
    table["month"] = pd.to_datetime(table.window_start_utc, utc=True).dt.month
    selected = table.loc[table.method.eq(results.evaluation["selected_method"])].copy()
    raw_auc = float(roc_auc_score(selected.event, selected.forecast_rain_mm)) if selected.event.nunique() == 2 else None
    model_auc = float(roc_auc_score(selected.event, selected.probability)) if selected.event.nunique() == 2 else None
    period_metrics = {}
    for label, months in [("2025年5至7月固定月份子集", [5, 6, 7]), ("2025年8至12月其余测试日", [8, 9, 10, 11, 12])]:
        subset = table.loc[table.month.isin(months)]
        period_metrics[label] = {method: {"sample_count": len(rows), "event_count": int(rows.event.sum()),
            "brier": float(((rows.probability - rows.event.astype(int)) ** 2).mean())} for method, rows in subset.groupby("method")}
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "dataset_version": data.dataset_version,
              "predictions_file_sha256": hashlib.sha256((root / "artifacts" / "predictions.csv").read_bytes()).hexdigest(),
              "kind": "冻结预测的补充描述性检查，不重新选择模型",
              "raw_continuous_rain_roc_auc": raw_auc, "selected_probability_roc_auc": model_auc,
              "interpretation": "降水逻辑回归为原始预报雨量的单调映射，保持其排序。AUC相同；本次改进证据针对概率表达和预定成本情景，不能说AI增加了天气排序能力。",
              "period_metrics": period_metrics,
              "limitations": ["5至7月仅为固定月份子集，不是官方逐年梅雨日期。", "子集使用已冻结预测作描述，不参与选择参数、模型或阈值。", "没有与集合预报概率产品或所有更强校准方法比较。", "本次追加检查已见过完整测试结果，不能包装成新的盲测。"]}
    report_path = root / "reports" / "sensitivity_checks.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    run_path = root / "reports" / "experiment_run.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run["supplemental_diagnostics"] = {"file": "reports/sensitivity_checks.json", "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(), "kind": "descriptive_after_main_test"}
    run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    report = build_diagnostics(Path(__file__).resolve().parents[1])
    print(json.dumps(report, ensure_ascii=False, indent=2))
