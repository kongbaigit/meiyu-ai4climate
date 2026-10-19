"""将已核验的冻结结果打包成可双击打开的离线演示。"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from .bundle import load_bundle, read_json
from .results import METHOD_NAMES, load_results
from .temporal_results import load_temporal_evidence
from .data_completeness import build_completeness
from .live_data import LOCATIONS


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path) -> dict:
    data = load_bundle(root)
    results = load_results(root, data)
    if data.errors or results.errors or not results.ready:
        raise ValueError("不能用未通过核验的文件生成演示：" + "；".join(data.errors + results.errors))
    diagnostics = read_json(root / "reports/sensitivity_checks.json")
    diagnostic_identity = results.run.get("supplemental_diagnostics", {})
    if (sha256(root / "reports/sensitivity_checks.json") != diagnostic_identity.get("sha256")
            or diagnostics.get("dataset_version") != data.dataset_version
            or diagnostics.get("predictions_file_sha256") != results.run["predictions_file_sha256"]):
        raise ValueError("补充检查与冻结实验不一致。")
    selected = results.evaluation["selected_method"]
    temporal, temporal_errors = load_temporal_evidence(root, data.dataset_version)
    if temporal_errors:
        raise ValueError("新增时间段证据未通过核验：" + "；".join(temporal_errors))
    test = results.predictions.loc[results.predictions["split"].eq("test")]
    selected_rows = test.loc[test["method"].eq(selected)]
    merged = selected_rows.merge(data.samples.drop(columns=["split", "experiment_kind"]),
                                 on="sample_id", how="left", validate="one_to_one")
    probabilities = test.pivot(index="sample_id", columns="method", values="probability")
    rows = []
    for row in merged.sort_values("window_start_utc").itertuples():
        local = pd.Timestamp(row.window_start_utc).tz_convert("Asia/Shanghai")
        rows.append({
            "id": row.sample_id, "date": local.strftime("%Y-%m-%d"),
            "start_utc": row.window_start_utc, "end_utc": row.window_end_utc,
            "probability": float(row.probability), "rain_mm": float(row.observed_rain_mm),
            "forecast_mm": float(row.forecast_rain_mm), "measurement_code": row.observation_measurement_code,
            "model_version": row.model_version, "obs_record_id": row.obs_record_id,
            "forecast_record_id": row.forecast_record_id,
            "probabilities": {key: float(value) for key, value in probabilities.loc[row.sample_id].items()},
        })
    files = {
        "samples": ("data/samples.csv", "text/csv;charset=utf-8"),
        "predictions": ("artifacts/predictions.csv", "text/csv;charset=utf-8"),
        "evaluation": ("reports/evaluation.json", "application/json"),
        "sources": ("data/source_manifest.json", "application/json"),
        "ai_statement": ("docs/data_ai_statement.md", "text/markdown;charset=utf-8"),
    }
    if temporal:
        files["temporal"] = ("reports/temporal_validation.json", "application/json")
    downloads = {}
    for key, (relative, mime) in files.items():
        path = root / relative
        downloads[key] = {"name": path.name, "mime": mime, "sha256": sha256(path),
                          "base64": base64.b64encode(path.read_bytes()).decode("ascii")}
    inputs = ["data/samples.csv", "data/source_manifest.json", "reports/data_quality.json",
              "artifacts/predictions.csv", "reports/evaluation.json", "reports/experiment_run.json",
              "reports/sensitivity_checks.json", "reports/external_validation.json",
              "docs/action_sources.json", "docs/data_ai_statement.md", "templates/offline.html", "src/offline.py"]
    if temporal:
        inputs += ["reports/temporal_validation.json", "reports/temporal_run.json", "docs/新增时间段验证协议.md"]
    generated = datetime.now(timezone.utc).isoformat()
    payload = {
        "generated_at_utc": generated, "dataset_version": data.dataset_version,
        "selected_method": selected, "method_names": METHOD_NAMES,
        "event_threshold_mm": results.evaluation["event_threshold_mm"],
        "rows": rows, "evaluation": results.evaluation, "run": results.run,
        "diagnostics": diagnostics, "quality": data.quality, "manifest": data.manifest,
        "temporal": temporal,
        "live": {"locations": LOCATIONS, "completeness": build_completeness(root),
                 "seed": read_json(root / "external/live_seed/seed.json")},
        "external": read_json(root / "reports/external_validation.json"),
        "actions": read_json(root / "docs/action_sources.json"), "downloads": downloads,
    }
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    embedded = embedded.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (root / "templates/offline.html").read_text(encoding="utf-8")
    if template.count("__MEIYU_PAYLOAD__") != 1:
        raise ValueError("离线模板占位符不唯一。")
    inputs += ["src/data_completeness.py", "src/live_data.py", "templates/live_client.js", "templates/live_client.css"]
    if (root / "external/live_seed/seed.json").exists():
        inputs.append("external/live_seed/seed.json")
    output = root / "demo.html"
    rendered = template.replace("__MEIYU_PAYLOAD__", embedded)
    rendered = rendered.replace("__MEIYU_LIVE_CSS__", (root / "templates/live_client.css").read_text(encoding="utf-8"))
    rendered = rendered.replace("__MEIYU_LIVE_JS__", (root / "templates/live_client.js").read_text(encoding="utf-8"))
    if "__MEIYU_" in rendered:
        raise ValueError("演示模板仍有未替换内容。")
    output.write_text(rendered, encoding="utf-8")
    report = {"status": "built_from_verified_frozen_results", "generated_at_utc": generated,
              "dataset_version": data.dataset_version, "test_sample_count": len(rows),
              "selected_method": selected, "inputs": {name: sha256(root / name) for name in inputs},
              "output": {"path": "demo.html", "sha256": sha256(output), "bytes": output.stat().st_size},
              "limitations": ["历史实验冻结；在线天气只在用户点击时更新，另存来源与缓存。", "本地HTML不是公开网址。",
                              "打包校验与浏览器交互检查不能证明真实商户效果。"]}
    (root / "reports/offline_build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = build(args.root.resolve())
    print(json.dumps({key: result[key] for key in ["status", "dataset_version", "test_sample_count", "output"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
