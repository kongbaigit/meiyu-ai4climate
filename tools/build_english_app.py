"""Build the standalone English Meiyu Prepare pages from the frozen Chinese build.

The source pages remain untouched.  Only numeric experiment records and the raw
download bytes are carried into the English bundle; user-facing copy is owned by
templates/en and is not translated at runtime.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EN_DIR = ROOT / "en"
TEMPLATE_DIR = ROOT / "templates" / "en"


def extract_json(text: str, marker: str) -> Any:
    """Decode the first JSON value after a marker without evaluating JavaScript."""
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"marker not found: {marker}")
    start += len(marker)
    value, end = json.JSONDecoder().raw_decode(text[start:].lstrip())
    if not isinstance(value, (dict, list)):
        raise ValueError(f"expected an object or array after {marker}")
    return value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_decision_source(root: Path) -> dict[str, Any]:
    page = (root / "index.html").read_text(encoding="utf-8")
    input_data = extract_json(page, "const MEIYU_DECISION_INPUT=")
    keep = {
        "schema_version": input_data.get("schema_version", 1),
        "locations": copy.deepcopy(input_data.get("locations", {})),
        "grids": copy.deepcopy(input_data.get("grids", {})),
        "expected_members": input_data.get("expected_members", 51),
        "model": input_data.get("model", "ecmwf_ifs025"),
        "source": "Open-Meteo/ECMWF IFS 0.25° ensemble",
        "weather_seed": copy.deepcopy(input_data.get("weather_seed", {})),
    }
    english_names = {
        "hangzhou": "Hangzhou Xiaoshan Airport",
        "ningbo": "Ningbo Lishe Airport",
    }
    for key, location in keep["locations"].items():
        location["name"] = english_names.get(key, key.title())
    for seed in keep["weather_seed"].values():
        snapshot = seed.get("snapshot") if isinstance(seed, dict) else None
        if isinstance(snapshot, dict) and isinstance(snapshot.get("location"), dict):
            key = snapshot.get("location_key")
            snapshot["location"]["name"] = english_names.get(key, key or "reference point")
    return keep


def simplify_method(method: dict[str, Any]) -> dict[str, Any]:
    keep = {
        key: method.get(key)
        for key in (
            "sample_count",
            "event_count",
            "brier",
            "roc_auc",
            "average_precision",
            "confusion_at_probability_0_1",
            "calibration_bins",
        )
        if key in method
    }
    return keep


def read_history_source(root: Path, decision: dict[str, Any]) -> dict[str, Any]:
    page = (root / "demo.html").read_text(encoding="utf-8")
    match = re.search(
        r'<script id="meiyu-data" type="application/json">(?P<json>.*?)</script>',
        page,
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError("the frozen demo payload was not found in demo.html")
    source = json.loads(match.group("json"))
    evaluation_source = source.get("evaluation", {})
    splits_source = evaluation_source.get("splits", {})
    splits: dict[str, Any] = {}
    for split in ("train", "validation", "test"):
        original = splits_source.get(split, {})
        splits[split] = {
            "sample_count": original.get("sample_count"),
            "event_count": original.get("event_count"),
            "methods": {
                name: simplify_method(method)
                for name, method in original.get("methods", {}).items()
            },
        }

    diagnostics = source.get("diagnostics", {})
    bootstrap = []
    for item in (
        diagnostics.get("paired_brier_bootstrap", [])
        or evaluation_source.get("paired_brier_bootstrap", [])
    ):
        bootstrap.append(
            {
                key: item.get(key)
                for key in (
                    "comparison",
                    "mean_difference",
                    "ci95",
                    "calendar_week_block_count",
                    "bootstrap_replicates",
                )
                if key in item
            }
        )
    cost_scenarios = diagnostics.get("cost_scenarios", {}) or evaluation_source.get(
        "cost_scenarios", {}
    )
    cost_methods = cost_scenarios.get("methods", {})
    selected_method = source.get("selected_method", "logistic_rain")

    temporal_source = source.get("temporal") or {}
    temporal = {
        "summary": (
            "The separately checked 2026 period has limited complete reference coverage; "
            "it is not mixed into the 636-window historical experiment."
        ),
        "months": [],
    }
    # Keep only compact monthly counts.  Labels from the Chinese report are not
    # copied into the English payload.
    monthly_items = []
    if isinstance(temporal_source, dict):
        monthly_items = temporal_source.get("monthly", []) or temporal_source.get(
            "monthly_coverage", []
        )
    for item in monthly_items:
        temporal["months"].append(
            [
                str(item.get("month", "")),
                str(
                    item.get(
                        "paired_windows",
                        item.get("paired_days", item.get("complete_days", "—")),
                    )
                ),
                "limited independent check",
            ]
        )
    if not temporal["months"]:
        temporal["months"] = [
            ["2026-01 to 2026-03", "limited", "independent check"],
            ["2026-04 to 2026-09", "0 complete paired months", "coverage gap"],
        ]

    downloads: dict[str, Any] = {}
    original_downloads = source.get("downloads", {})
    english_statement = root / "docs" / "en" / "data-ai-statement.md"
    for key, item in original_downloads.items():
        # The original Chinese AI statement must never be embedded in the
        # English page.  The document agent supplies the English replacement.
        if key == "ai_statement":
            continue
        if not isinstance(item, dict) or "base64" not in item:
            continue
        downloads[key] = {
            "name": item.get("name", key),
            "mime": item.get("mime", "application/octet-stream"),
            "sha256": item.get("sha256"),
            "base64": item["base64"],
        }
    if english_statement.is_file():
        raw = english_statement.read_bytes()
        downloads["ai_statement"] = {
            "name": "data-ai-statement.md",
            "mime": "text/markdown;charset=utf-8",
            "sha256": sha256_bytes(raw),
            "base64": base64.b64encode(raw).decode("ascii"),
        }

    completeness_source = (source.get("live") or {}).get("completeness", {})
    summary = completeness_source.get("summary") or {
        "paired_days": 636,
        "configured_days": 636,
        "missing_reference_days": 0,
        "missing_forecast_days": 0,
    }
    fields = []
    for field in completeness_source.get("fields", []):
        fields.append(
            {
                "label": {
                    "sample_count": "Sample count",
                    "forecast_rain_mm": "Forecast rain",
                    "observed_rain_mm": "Reference rain",
                    "observation_measurement_code": "Measurement code",
                }.get(field.get("key"), "Frozen field"),
                "available": field.get("available", summary.get("paired_days", 636)),
                "coverage": field.get("coverage", 1.0),
                "note": "Missing remains missing; it is not filled as zero.",
            }
        )
    days = []
    for day in completeness_source.get("days", []):
        if not isinstance(day, dict) or not day.get("date"):
            continue
        days.append(
            {
                "date": day["date"],
                "month": day["date"][:7],
                "status": day.get("status", "paired"),
            }
        )

    rows = []
    for row in source.get("rows", []):
        rows.append(
            {
                key: row.get(key)
                for key in (
                    "id",
                    "date",
                    "start_utc",
                    "end_utc",
                    "probability",
                    "rain_mm",
                    "forecast_mm",
                    "measurement_code",
                    "model_version",
                    "obs_record_id",
                    "forecast_record_id",
                    "probabilities",
                )
                if key in row
            }
        )
    live = {
        "model": decision["model"],
        "expected_members": decision["expected_members"],
        "locations": {
            key: {
                "name": value.get("name", key.title()),
                "latitude": value["latitude"],
                "longitude": value["longitude"],
            }
            for key, value in decision["locations"].items()
        },
        "grids": copy.deepcopy(decision["grids"]),
    }
    return {
        "dataset_version": source.get("dataset_version", "frozen-dataset"),
        "selected_method": selected_method,
        "event_threshold_mm": source.get("event_threshold_mm", 25),
        "rows": rows,
        "evaluation": {
            "selected_method": selected_method,
            "split_summary": source.get("evaluation", {}).get("split_summary", {}),
            "splits": splits,
        },
        "diagnostics": {
            "paired_brier_bootstrap": bootstrap,
            "cost_scenarios": {
                "methods": {selected_method: cost_methods.get(selected_method, [])}
            },
        },
        "temporal": temporal,
        "actions": [
            {
                "id": "inspect",
                "label": "Check low or moisture-sensitive stock",
                "action": "Inspect cardboard, paper and low shelves first.",
            },
            {
                "id": "place",
                "label": "Choose a dry stable place",
                "action": "Keep a clear walkway and protect goods from splash.",
            },
            {
                "id": "record",
                "label": "Record what happened",
                "action": "Compare actual cost and loss after the event.",
            },
        ],
        "downloads": downloads,
        "completeness": {"summary": summary, "fields": fields, "days": days},
        "live": live,
    }


def render(root: Path) -> dict[str, Any]:
    decision = read_decision_source(root)
    history = read_history_source(root, decision)
    index_template = (root / "templates/en/index.html").read_text(encoding="utf-8")
    index_html = index_template.replace(
        "__EN_INDEX_CSS__", (root / "templates/en/index.css").read_text(encoding="utf-8")
    )
    index_html = index_html.replace(
        "__EN_WEATHER_CORE__", (root / "templates/en/weather-core.js").read_text(encoding="utf-8")
    )
    index_html = index_html.replace(
        "__EN_DECISION_INPUT__",
        json.dumps(decision, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029"),
    )
    index_html = index_html.replace(
        "__EN_INDEX_JS__", (root / "templates/en/index.js").read_text(encoding="utf-8")
    )
    # Keep the terminology identical in static copy and in strings emitted by
    # the client script.  IDs and calculation field names intentionally stay
    # unchanged so the underlying decision contract is reused verbatim.
    for old, new in {
        "Cost example": "Hypothetical example",
        "cost example": "hypothetical example",
        "Share of members reaching the rain threshold": "Uncalibrated ensemble member fraction",
        "Uncalibrated ensemble scenario estimate": "Uncalibrated ensemble member fraction",
        "This is not locally calibrated.": "This is an uncalibrated ensemble member fraction.",
        "Move: moving cost +": "Relocate: relocation cost C +",
        "Move: relocation cost +": "Relocate: relocation cost C +",
        "Hold: probability × expected loss without moving.": "Keep in place: probability × conditional loss if kept L0.",
        "loss without moving": "conditional loss if kept L0",
        "loss after moving": "conditional loss after relocation L1",
        "CNY 600 means hold": "CNY 600 means keep in place",
        "event estimate × expected loss without moving": "event estimate × Conditional loss if kept L0",
        "Event estimate × expected loss without moving": "Event estimate × Conditional loss if kept L0",
        "expected loss after moving": "Conditional loss after relocation L1",
        "Expected loss without moving": "Conditional loss if kept L0",
        "Moving cost +": "Relocation cost C +",
        "Moving cost": "Relocation cost C",
        "moving cost": "relocation cost",
        "Move under these assumptions": "Relocate under these assumptions",
        "Hold under these assumptions": "Keep in place under these assumptions",
        "Moving does not": "Relocation does not",
        "Moving does not reduce": "Relocation does not reduce",
        "(r.state==='move'?'Moving':'Holding')": "(r.state==='move'?'Relocating':'Keeping in place')",
    }.items():
        index_html = index_html.replace(old, new)
    demo_template = (root / "templates/en/demo.html").read_text(encoding="utf-8")
    demo_html = demo_template.replace(
        "__EN_DEMO_CSS__", (root / "templates/en/demo.css").read_text(encoding="utf-8")
    )
    demo_html = demo_html.replace(
        "__EN_WEATHER_CORE__", (root / "templates/en/weather-core.js").read_text(encoding="utf-8")
    )
    demo_html = demo_html.replace(
        "__EN_HISTORY_INPUT__",
        json.dumps(history, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029"),
    )
    demo_html = demo_html.replace(
        "__EN_DEMO_JS__", (root / "templates/en/demo.js").read_text(encoding="utf-8")
    )
    if "__EN_" in index_html or "__EN_" in demo_html:
        raise ValueError("English template placeholders remain after rendering")
    if re.search(r"[\u4e00-\u9fff]", index_html + demo_html):
        raise ValueError("English pages still contain CJK characters")
    output_dir = root / "en"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(index_html, encoding="utf-8", newline="\n")
    (output_dir / "demo.html").write_text(demo_html, encoding="utf-8", newline="\n")
    return {
        "output": {
            "index": {
                "path": "en/index.html",
                "bytes": (output_dir / "index.html").stat().st_size,
                "sha256": sha256_bytes((output_dir / "index.html").read_bytes()),
            },
            "demo": {
                "path": "en/demo.html",
                "bytes": (output_dir / "demo.html").stat().st_size,
                "sha256": sha256_bytes((output_dir / "demo.html").read_bytes()),
            },
        },
        "dataset_version": history["dataset_version"],
        "history_rows": len(history["rows"]),
        "english_ai_statement": "ai_statement" in history["downloads"],
        "selected_method": history["selected_method"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(render(args.root.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
