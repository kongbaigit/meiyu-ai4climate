from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from .bundle import load_bundle


def verify_package(root: Path) -> dict:
    root = root.resolve()
    bundle = load_bundle(root)
    checks = [{"name": "主表协议、内容版本与来源引用", "passed": not bundle.errors, "details": bundle.errors}]
    try:
        parquet = pd.read_parquet(root / "data" / "samples.parquet")
        pd.testing.assert_frame_equal(bundle.samples.isna(), parquet.isna())
        csv_values = bundle.samples.astype(object).where(bundle.samples.notna(), None)
        parquet_values = parquet.astype(object).where(parquet.notna(), None)
        pd.testing.assert_frame_equal(csv_values, parquet_values, check_dtype=False, check_exact=False, rtol=1e-10)
        checks.append({"name": "CSV 与 Parquet 内容一致", "passed": True})
    except (OSError, ValueError, AssertionError) as exc:
        checks.append({"name": "CSV 与 Parquet 内容一致", "passed": False, "details": str(exc)})
    source_errors = []
    for source in bundle.manifest.get("sources", []):
        path = (root / source.get("local_path", "")).resolve()
        if not path.is_relative_to(root):
            source_errors.append(f"{source.get('source_id')}：来源路径超出项目目录")
        elif not path.is_file():
            source_errors.append(f"{source.get('source_id')}：原始快照缺失")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != source.get("sha256"):
            source_errors.append(f"{source.get('source_id')}：原始快照散列不匹配")
    checks.append({"name": "来源原始快照 SHA256", "passed": not source_errors and bool(bundle.manifest.get("sources")), "details": source_errors})
    reference_errors = []
    if not bundle.samples.empty:
        try:
            observations = pd.read_csv(root / "data" / "observations.csv")
            joined = bundle.samples.merge(observations, on="obs_record_id", how="left", validate="many_to_one", suffixes=("", "_ref"), indicator=True)
            if not joined["_merge"].eq("both").all():
                reference_errors.append("主表存在没有参考观测的记录")
            for name in ["station_id", "window_start_utc", "window_end_utc", "observed_rain_mm"]:
                if not joined[name].eq(joined[name + "_ref"]).all():
                    reference_errors.append(f"{name} 与观测引用不一致")
            if bundle.samples.duplicated(["observation_window_id", "forecast_spec_id"]).any():
                reference_errors.append("同一观测窗口和预报定义出现重复")
        except (OSError, ValueError, KeyError) as exc:
            reference_errors.append(str(exc))
    checks.append({"name": "观测记录关联与配对基数", "passed": not reference_errors, "details": reference_errors})
    expected_quarantine = bundle.quality.get("summary", {}).get("quarantined_record_count")
    checks.append({"name": "隔离记录数一致", "passed": expected_quarantine == len(bundle.quarantined), "actual": len(bundle.quarantined), "expected": expected_quarantine})
    return {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "dataset_version": bundle.dataset_version,
            "passed": all(item["passed"] for item in checks), "sample_count": len(bundle.samples), "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="只读核验已构建的数据包，不重新训练或修改主表")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = verify_package(args.root)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
