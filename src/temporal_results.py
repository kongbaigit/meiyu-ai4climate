"""只读核对新增时间段结果，任何身份不一致都不向页面提供数字。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .bundle import read_json


def load_temporal_evidence(root: Path, main_dataset_version: str) -> tuple[dict, list[str]]:
    report_path = root / "reports/temporal_validation.json"
    run_path = root / "reports/temporal_run.json"
    if not report_path.exists() and not run_path.exists():
        return {}, []
    try:
        if not report_path.is_file() or not run_path.is_file():
            raise ValueError("新增时间段证据缺少结果或运行身份。")
        run = read_json(run_path)
        if hashlib.sha256(report_path.read_bytes()).hexdigest() != run.get("report_sha256"):
            raise ValueError("新增时间段评估文件摘要不一致。")
        report = read_json(report_path)
        if (report.get("identity") != run.get("identity") or report.get("dataset_version") != run.get("dataset_version")
                or report.get("main_dataset_version") != main_dataset_version
                or report.get("selected_method") != "logistic_rain" or report.get("event_threshold_mm") != 25):
            raise ValueError("新增时间段与当前冻结模型身份不一致。")
        if report.get("status") != run.get("status") or report.get("status") not in {"completed", "blocked"}:
            raise ValueError("新增时间段结果状态无效。")
        files = {**report["main_file_sha256"], **report["output_sha256"],
                 "docs/新增时间段验证协议.md": report["identity"]["protocol_sha256"]}
        if not report.get("main_files_unchanged") or not report.get("output_sha256"):
            raise ValueError("新增时间段缺少主实验保留或输出摘要证据。")
        for relative, expected in files.items():
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError("新增时间段引用的文件缺失或路径越界。")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError(f"新增时间段引用文件摘要不符：{relative}")
        return report, []
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {}, [str(exc)]
