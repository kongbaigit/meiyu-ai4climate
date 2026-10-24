"""Checks for the generated English static application."""

from __future__ import annotations

import json
import re
from pathlib import Path

from tools.build_english_app import render


ROOT = Path(__file__).resolve().parents[1]


def _payload(path: Path, marker: str) -> dict:
    text = path.read_text(encoding="utf-8")
    start = text.index(marker) + len(marker)
    value, _ = json.JSONDecoder().raw_decode(text[start:].lstrip())
    return value


def test_builder_emits_two_english_pages() -> None:
    report = render(ROOT)
    assert report["history_rows"] == 240
    assert report["selected_method"] == "logistic_rain"
    assert (ROOT / "en/index.html").is_file()
    assert (ROOT / "en/demo.html").is_file()

    for name in ("index.html", "demo.html"):
        page = (ROOT / "en" / name).read_text(encoding="utf-8")
        assert not re.search(r"[\u4e00-\u9fff]", page)
        assert "__EN_" not in page
        assert 'lang="en"' in page
        assert 'href="promo/"' in page
        assert 'href="../"' in page
        assert 'href="materials/"' in page
        assert 'href="/en/promo/"' not in page
        assert 'href="/"' not in page
    assert "__EN_WEATHER_CORE__" not in page


def test_decision_payload_keeps_math_examples_and_english_download() -> None:
    page = (ROOT / "en/index.html").read_text(encoding="utf-8")
    assert "Hypothetical example" in page
    assert "Uncalibrated ensemble member fraction" in page
    assert "CNY 600" in page and "CNY 140" in page and "CNY 540" in page

    demo_path = ROOT / "en/demo.html"
    payload = _payload(demo_path, "const MEIYU_HISTORY_INPUT=")
    test_metrics = payload["evaluation"]["splits"]["test"]["methods"]
    assert test_metrics["logistic_rain"]["sample_count"] == 240
    assert test_metrics["training_climatology"]["sample_count"] == 240
    assert round(test_metrics["logistic_rain"]["brier"], 4) == 0.0455
    assert round(test_metrics["training_climatology"]["brier"], 4) == 0.0697
    assert set(payload["rows"][0]["probabilities"]) == {
        "training_climatology",
        "raw_nwp_rule",
        "logistic_rain",
        "logistic_weather",
    }
    assert "native Canvas/Three.js animation" in demo_path.read_text(encoding="utf-8")
    assert "threshold is C/100" in demo_path.read_text(encoding="utf-8")
    demo_source = (ROOT / "templates/en/demo.js").read_text(encoding="utf-8")
    core_source = (ROOT / "templates/en/weather-core.js").read_text(encoding="utf-8")
    assert "raw_sha256:'computed in browser'" not in demo_source
    assert "raw_sha256: await sha256(raw)" in core_source
    assert "units[name] !== 'mm'" in core_source
    assert "stable(parsed) !== stable(summary)" in core_source
    if (ROOT / "docs/en/data-ai-statement.md").is_file():
        assert "ai_statement" in payload["downloads"]
        assert payload["downloads"]["ai_statement"]["name"] == "data-ai-statement.md"
