from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

import src.decision_view as view


UTC = timezone.utc
NOW = datetime(2026, 10, 19, 23, tzinfo=UTC)


@pytest.fixture
def frozen_view_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: timezone | None = None) -> datetime:
            return NOW if tz is not None else NOW.replace(tzinfo=None)

    monkeypatch.setattr(view, "datetime", FrozenDateTime)


def _window(start: datetime | None = None, **overrides: Any) -> dict[str, Any]:
    start = start or datetime(2026, 10, 21, tzinfo=UTC)
    value: dict[str, Any] = {
        "start_utc": start.isoformat().replace("+00:00", "Z"),
        "end_utc": (start + timedelta(hours=24)).isoformat().replace("+00:00", "Z"),
        "probability": 0.6,
        "complete": True,
        "members_expected": view.EXPECTED_MEMBERS,
        "members_valid": view.EXPECTED_MEMBERS,
        "hours_expected": 24,
        "hours_min": 24,
    }
    value.update(overrides)
    return value


def _snapshot(location_key: str = "hangzhou", *, fetched: datetime = NOW) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "location_key": location_key,
        "location": view.LOCATIONS[location_key],
        "source": view.WEATHER_SOURCE,
        "probability_kind": view.PROBABILITY_KIND,
        "event_threshold_mm": 25,
        "expected_members": view.EXPECTED_MEMBERS,
        "fetched_at_utc": fetched.isoformat().replace("+00:00", "Z"),
        "raw_sha256": "a" * 64,
        "windows": [_window()],
    }


def test_money_and_window_gate_reject_empty_invalid_or_partial_values():
    assert view._parse_money("0") == 0.0
    assert view._parse_money("1000000000") == 1_000_000_000.0
    for value in ("", "  ", "nan", "inf", "-1", "1000000001", "not-money"):
        assert view._parse_money(value) is None

    checked, reason = view._valid_window(_window(), NOW)
    assert checked is not None
    assert reason is None
    for bad in (
        {"members_expected": view.EXPECTED_MEMBERS - 1},
        {"members_valid": view.EXPECTED_MEMBERS - 1},
        {"hours_min": 23},
        {"complete": False},
        {"start_utc": "2026-10-21T08:00:00+08:00"},
        {"start_utc": "2026-10-19T23:00:00Z"},
    ):
        checked, reason = view._valid_window({**_window(), **bad}, NOW)
        assert checked is None
        assert reason


def test_snapshot_gate_requires_identity_and_three_hour_freshness():
    good, reason, fetched = view._snapshot_gate(_snapshot(), "hangzhou", NOW)
    assert good is True
    assert reason is None
    assert fetched == NOW

    wrong_source = _snapshot()
    wrong_source["source"] = "old-history-model"
    assert view._snapshot_gate(wrong_source, "hangzhou", NOW)[0] is False

    wrong_schema = _snapshot()
    wrong_schema["schema_version"] = 2
    assert view._snapshot_gate(wrong_schema, "hangzhou", NOW)[0] is False

    stale = _snapshot(fetched=NOW - timedelta(hours=3, seconds=1))
    assert view._snapshot_gate(stale, "hangzhou", NOW)[0] is False


def test_bill_has_required_fields_and_result(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    def download_button(label: str, data: str, **kwargs: Any) -> None:
        captured.update({"label": label, "data": data, **kwargs})

    monkeypatch.setattr(view.st, "download_button", download_button)
    view._download_bill(
        mode="real_weather",
        source=view.WEATHER_SOURCE,
        fetched_at_utc="2026-10-19T23:00:00Z",
        window=_window(),
        assumptions={"probability": 0.6, "move_cost": 80.0},
        result={"state": "move"},
        key="test_bill",
    )
    bill = json.loads(captured["data"])
    assert {"mode", "assumptions", "source", "window", "result"} <= set(bill)
    assert bill["result"]["state"] == "move"


class _Column:
    def __init__(self, owner: "_FakeStreamlit") -> None:
        self.owner = owner

    def metric(self, label: str, value: str) -> None:
        self.owner.messages.append((label, value))


class _FakeStreamlit:
    def __init__(self, *, confirmed: bool = False) -> None:
        self.session_state: dict[str, Any] = {}
        self.confirmed = confirmed
        self.selected_location = "hangzhou"
        self.messages: list[tuple[str, str]] = []
        self.downloads: list[dict[str, Any]] = []

    def selectbox(self, label: str, options: list[Any], **kwargs: Any) -> Any:
        if options and isinstance(options[0], str):
            return self.selected_location
        return options[0]

    def button(self, *args: Any, **kwargs: Any) -> bool:
        return False

    def spinner(self, *args: Any, **kwargs: Any):
        return nullcontext()

    def success(self, text: str) -> None:
        self.messages.append(("success", text))

    def info(self, text: str) -> None:
        self.messages.append(("info", text))

    def warning(self, text: str) -> None:
        self.messages.append(("warning", text))

    def error(self, text: str) -> None:
        self.messages.append(("error", text))

    def caption(self, text: str) -> None:
        self.messages.append(("caption", text))

    def markdown(self, text: str) -> None:
        self.messages.append(("markdown", text))

    def metric(self, label: str, value: str) -> None:
        self.messages.append((label, value))

    def columns(self, count: int) -> list[_Column]:
        return [_Column(self) for _ in range(count)]

    def expander(self, *args: Any, **kwargs: Any):
        return nullcontext()

    def text_input(self, label: str, *, value: str, key: str) -> str:
        return value

    def checkbox(self, label: str, *, key: str) -> bool:
        self.session_state[key] = self.confirmed
        return self.confirmed

    def download_button(self, label: str, data: str, **kwargs: Any) -> None:
        self.downloads.append({"label": label, "data": data, **kwargs})


def test_render_uses_selected_city_and_confirmation_gates_move_result(
    monkeypatch: pytest.MonkeyPatch, frozen_view_clock: None
):
    fake = _FakeStreamlit(confirmed=False)
    calls: list[tuple[str, bool, bool]] = []

    def fake_weather(root: Path, location: str, *, refresh: bool, force: bool) -> dict[str, Any]:
        calls.append((location, refresh, force))
        return {"status": "fresh", "snapshot": _snapshot(location, fetched=NOW), "error": None}

    monkeypatch.setattr(view, "st", fake)
    monkeypatch.setattr(view, "get_weather", fake_weather)
    view._render_real_weather(Path("."))
    assert calls == [("hangzhou", True, False)]
    assert not any("建议搬运" in text for _, text in fake.messages)
    assert not fake.downloads

    fake.confirmed = True
    view._render_real_weather(Path("."))
    assert any("建议搬运" in text for _, text in fake.messages)
    assert len(fake.downloads) == 1
    assert json.loads(fake.downloads[0]["data"])["result"]["state"] == "move"

    # 城市切换清掉旧确认；没有把杭州的确认带到宁波。
    old_confirmation_keys = [key for key in fake.session_state if key.startswith(view.CONFIRMATION_KEY_PREFIX)]
    assert old_confirmation_keys
    fake.selected_location = "ningbo"
    fake.confirmed = False
    before = len(fake.messages)
    view._render_real_weather(Path("."))
    assert not any("建议搬运" in text for _, text in fake.messages[before:])
    assert not any(key in fake.session_state for key in old_confirmation_keys)


def test_partial_snapshot_can_use_a_complete_future_window(
    monkeypatch: pytest.MonkeyPatch, frozen_view_clock: None
):
    fake = _FakeStreamlit(confirmed=True)

    def fake_weather(root: Path, location: str, *, refresh: bool, force: bool) -> dict[str, Any]:
        return {"status": "partial", "snapshot": _snapshot(location, fetched=NOW), "error": None}

    monkeypatch.setattr(view, "st", fake)
    monkeypatch.setattr(view, "get_weather", fake_weather)
    view._render_real_weather(Path("."))

    assert any("建议搬运" in text for _, text in fake.messages)

