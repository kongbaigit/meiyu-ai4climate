"""实时天气情景下的纯成本决策页面。

天气页只把 ensemble 的未经校准成员占比作为降雨情景输入。天气缓存、TTL、
刷新间隔和网络错误由 :mod:`src.decision_weather` 负责；本页不创建后台线程。
只有在天气来源、快照 schema、未来窗口完整度和用户货损确认都通过时，页面才
显示 ``move``、``keep`` 或 ``tie`` 及其期望成本。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import streamlit as st

from .decision_cost import calculate_decision
from .decision_weather import (
    EVENT_THRESHOLD_MM,
    EXPECTED_MEMBERS,
    PROBABILITY_KIND,
    SOURCE as WEATHER_SOURCE,
    get_weather,
)
from .live_data import LOCATIONS


UTC = timezone.utc
BEIJING = ZoneInfo("Asia/Shanghai")
MONEY_MAX = 1_000_000_000.0
FRESHNESS_TTL = timedelta(hours=3)
CONFIRMATION_CONTEXT_KEY = "_decision_confirmation_context"
CONFIRMATION_MODE_KEY = "_decision_confirmation_mode"
CONFIRMATION_LOCATION_KEY = "_decision_confirmation_location"
CONFIRMATION_KEY_PREFIX = "decision_average_loss_confirmed_"

STATUS_LABELS = {
    "fresh": "天气缓存新鲜",
    "stale": "天气缓存已过期",
    "partial": "天气窗口不完整",
    "missing": "尚无天气缓存",
    "error": "天气数据读取失败",
}
STATUS_HELP = {
    "fresh": "当前窗口完整，可在确认平均货损估计后进行纯成本算账。",
    "stale": "缓存仍可追溯，但已超过新鲜度要求；本页不据此给出行动结论。",
    "partial": "部分窗口成员或小时数据不完整；只使用通过完整度检查的未来窗口。",
    "missing": "没有可用窗口；请手动刷新或稍后再试。",
    "error": "天气数据不可用；本页不以失败请求推断无雨或零货损。",
}


def _parse_utc(value: Any) -> datetime | None:
    """解析带时区的 ISO 时间并归一化为 UTC。"""

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _is_explicit_utc(value: Any) -> bool:
    """窗口时间必须明确表示 UTC；不把北京时间等偏移静默当成 UTC。"""

    if not isinstance(value, str) or not value.strip():
        return False
    text = value.strip()
    if text.endswith("Z"):
        return True
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


def _coerce_now(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _finite_probability(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and 0 <= result <= 1 else None


def _parse_money(value: Any) -> float | None:
    """将文本金额解析为有限非负金额；空值和非法值返回 ``None``。"""

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        result = float(value.strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0 or result > MONEY_MAX:
        return None
    return result


def _exact_number(value: Any, expected: int) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(number) and number == expected


def _valid_window(window: Any, now: datetime) -> tuple[dict[str, Any] | None, str | None]:
    """验证可供行动算账的完整、未开始的 24 小时窗口。"""

    if not isinstance(window, Mapping):
        return None, "窗口记录不是对象。"
    now = _coerce_now(now)
    start_raw = window.get("start_utc")
    end_raw = window.get("end_utc")
    if not _is_explicit_utc(start_raw) or not _is_explicit_utc(end_raw):
        return None, "窗口时间必须明确使用 UTC。"
    start = _parse_utc(start_raw)
    end = _parse_utc(end_raw)
    if start is None or end is None:
        return None, "窗口时间不是有效 UTC 时间。"
    if start <= now:
        return None, "窗口已经开始或已结束。"
    if end - start != timedelta(hours=24):
        return None, "窗口不是完整的 24 小时。"
    if window.get("complete") is not True:
        return None, "窗口成员或小时数据不完整。"
    if not _exact_number(window.get("members_expected"), EXPECTED_MEMBERS):
        return None, f"窗口预期成员数不是 {EXPECTED_MEMBERS}。"
    if not _exact_number(window.get("members_valid"), EXPECTED_MEMBERS):
        return None, f"窗口有效成员数不是 {EXPECTED_MEMBERS}。"
    if not _exact_number(window.get("hours_expected"), 24):
        return None, "窗口预期小时数不是 24。"
    if not _exact_number(window.get("hours_min"), 24):
        return None, "窗口缺少完整的 24 个小时。"
    probability = _finite_probability(window.get("probability"))
    if probability is None:
        return None, "窗口缺少有限的降雨集合成员占比。"

    checked = dict(window)
    checked["probability"] = probability
    checked["start_utc"] = start.isoformat().replace("+00:00", "Z")
    checked["end_utc"] = end.isoformat().replace("+00:00", "Z")
    return checked, None


def _eligible_windows(snapshot: Any, now: datetime) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(snapshot, Mapping) or not isinstance(snapshot.get("windows"), list):
        return [], ["天气快照缺少窗口列表。"]
    valid: list[dict[str, Any]] = []
    reasons: list[str] = []
    for window in snapshot["windows"]:
        checked, reason = _valid_window(window, now)
        if checked is not None:
            valid.append(checked)
        elif reason:
            reasons.append(reason)
    return valid, reasons


def _snapshot_gate(snapshot: Any, location_key: str, now: datetime) -> tuple[bool, str | None, datetime | None]:
    """检查天气来源身份、schema 和不超过三小时的新鲜度。"""

    if not isinstance(snapshot, Mapping):
        return False, "天气快照不是对象。", None
    if snapshot.get("schema_version") != 1:
        return False, "天气快照 schema_version 无效。", None
    if snapshot.get("location_key") != location_key:
        return False, "天气快照位置与当前选择不一致。", None
    if snapshot.get("source") != WEATHER_SOURCE:
        return False, "天气快照来源身份不是固定的 Open-Meteo/ECMWF ensemble。", None
    if snapshot.get("probability_kind") != PROBABILITY_KIND:
        return False, "天气快照的概率口径不是未经校准的集合成员占比。", None
    if not _exact_number(snapshot.get("expected_members"), EXPECTED_MEMBERS):
        return False, f"天气快照预期成员数不是 {EXPECTED_MEMBERS}。", None
    if "event_threshold_mm" in snapshot and not _exact_number(snapshot.get("event_threshold_mm"), EVENT_THRESHOLD_MM):
        return False, "天气快照降雨事件阈值不是固定值。", None
    location = snapshot.get("location")
    if location is not None and location != LOCATIONS.get(location_key):
        return False, "天气快照站点身份与当前选择不一致。", None

    fetched = _parse_utc(snapshot.get("fetched_at_utc"))
    if fetched is None:
        return False, "天气快照缺少有效的获取时间。", None
    now = _coerce_now(now)
    age = now - fetched
    if age < timedelta(0):
        return False, "天气快照获取时间晚于当前时间。", fetched
    if age > FRESHNESS_TTL:
        return False, "天气快照已超过 3 小时新鲜度要求。", fetched
    return True, None, fetched


def _window_label(window: Mapping[str, Any]) -> str:
    start = _parse_utc(window.get("start_utc"))
    end = _parse_utc(window.get("end_utc"))
    if start is None or end is None:
        return "时间无效"
    local_start = start.astimezone(BEIJING)
    local_end = end.astimezone(BEIJING)
    return f"{local_start:%m月%d日 %H:%M}—{local_end:%m月%d日 %H:%M}（p={float(window['probability']):.1%}）"


def _format_money(value: float) -> str:
    return f"¥{value:,.2f}"


def _result_text(state: str) -> str:
    return {"move": "建议搬运", "keep": "建议不搬", "tie": "同价，成本账面无法区分"}[state]


def _display_calculation(decision: Mapping[str, Any], *, title: str = "算账结果") -> None:
    st.markdown(f"#### {title}")
    columns = st.columns(3)
    columns[0].metric("不搬的期望损失", _format_money(float(decision["expected_without"])))
    columns[1].metric("搬运后的期望成本", _format_money(float(decision["expected_move"])))
    columns[2].metric("搬运带来的账面差额", _format_money(float(decision["benefit"])))
    state = str(decision["state"])
    if state == "move":
        st.success("建议搬运：在这组假设下，搬运后的期望成本更低。")
    elif state == "keep":
        st.info("建议不搬：在这组假设下，搬运成本高于预期节省。")
    else:
        st.warning("同价：两种方案在 1e-8 元容差内相等。")
    threshold = decision.get("break_even_probability")
    if threshold is None:
        st.caption("未显示回本概率阈值：搬运后货损没有低于不搬时的假设。")
    else:
        st.caption(f"回本概率阈值：{float(threshold):.2%}；超过 100% 表示这组成本假设下不可能回本。")


def _download_bill(
    *,
    mode: str,
    source: str,
    fetched_at_utc: str | None,
    window: Mapping[str, Any],
    assumptions: Mapping[str, Any],
    result: Any,
    key: str,
) -> None:
    """只在调用方已经通过所有门控后显示账单下载。"""

    bill = {
        "mode": mode,
        "source": source,
        "fetched_at_utc": fetched_at_utc,
        "window": dict(window),
        "assumptions": dict(assumptions),
        "result": result,
        "confirmed_average_loss_estimate": True,
    }
    try:
        payload = json.dumps(bill, ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        st.error(f"账单无法导出：{exc}")
        return
    st.download_button(
        "下载已确认的算账账单",
        payload,
        file_name="meiyu_decision_bill.json",
        mime="application/json",
        key=key,
        width="stretch",
    )


def _cost_inputs(prefix: str) -> tuple[float | None, float | None, float | None]:
    st.markdown("#### 成本假设")
    cost_text = st.text_input("搬运成本 C / 元（示例默认 80）", value="80", key=f"{prefix}_move_cost")
    without_text = st.text_input("事件发生时不搬运的平均货损 L0 / 元（示例默认 1000）", value="1000", key=f"{prefix}_loss_without")
    with st.expander("展开：搬运后仍可能有残余货损", expanded=False):
        after_text = st.text_input("搬运后的平均货损 L1 / 元（示例默认 100）", value="100", key=f"{prefix}_loss_after")
        st.caption("L1 是搬运后的残余损失假设，不自动按 0 处理，也不代表完全免损。")

    values = (
        _parse_money(cost_text),
        _parse_money(without_text),
        _parse_money(after_text),
    )
    labels = ("搬运成本 C", "不搬运货损 L0", "搬运后货损 L1")
    for value, label in zip(values, labels):
        if value is None:
            st.error(f"{label}必须填写 0 到 1e9 元之间的有限数字；空值不会按 0 处理。")
    return values


def _clear_confirmation_widgets() -> None:
    state = getattr(st, "session_state", None)
    if state is None:
        return
    try:
        keys = list(state.keys())
    except (AttributeError, TypeError):
        return
    for key in keys:
        if isinstance(key, str) and key.startswith(CONFIRMATION_KEY_PREFIX):
            try:
                del state[key]
            except KeyError:
                pass


def _activate_confirmation_context(context: Mapping[str, Any]) -> None:
    """位置、窗口、模式或金额变化时废止旧确认，避免静默复用。"""

    state = getattr(st, "session_state", None)
    if state is None:
        return
    try:
        encoded = json.dumps(dict(context), ensure_ascii=False, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError):
        encoded = repr(sorted(dict(context).items()))
    previous = state.get(CONFIRMATION_CONTEXT_KEY)
    if previous != encoded:
        _clear_confirmation_widgets()
        state[CONFIRMATION_CONTEXT_KEY] = encoded


def _sync_confirmation_selector(key: str, value: str) -> None:
    """同步模式或城市选择；只在选择真的变化时废止旧确认。"""

    state = getattr(st, "session_state", None)
    if state is None:
        return
    previous = state.get(key)
    if previous != value:
        _clear_confirmation_widgets()
        state[key] = value


def _confirmation(scope: str, signature: Mapping[str, Any]) -> bool:
    context = {"scope": scope, **dict(signature)}
    _activate_confirmation_context(context)
    encoded = json.dumps(context, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    token = hashlib.sha256(encoded).hexdigest()[:16]
    return st.checkbox(
        "我确认：若该 24 小时降雨事件发生，上述金额是包含可能不受损情况的条件平均货损；这些金额只用于本次算账",
        key=f"{CONFIRMATION_KEY_PREFIX}{scope}_{token}",
    )


def _render_example_mode() -> None:
    st.info("显式演示模式：与实时天气完全分开。p=0.6 是演示输入，不是当前天气或当前降雨读取结果。")
    st.caption("示例固定使用 C=80 元、L0=1000 元、L1=100 元，并另列 C=600 元展示成本翻转。")
    st.caption("p 是未经校准的降雨集合成员占比；本页不把它叫作货损概率，也不混用历史模型的 67.9%。")
    confirmed = _confirmation(
        "example",
        {"probability": 0.6, "move_costs": [80.0, 600.0], "loss_without": 1000.0, "loss_after": 100.0},
    )
    if not confirmed:
        st.info("请先确认该降雨事件发生时的条件平均货损估计，确认后才显示搬、不搬或同价结论。")
        return

    examples = []
    for cost in (80.0, 600.0):
        decision = calculate_decision(0.6, cost, 1000.0, 100.0)
        examples.append({"move_cost": cost, "decision": decision})
    st.markdown("#### 同一 p 与货损假设下的成本翻转")
    st.caption("两行都使用 p=0.6、L0=1000 元、L1=100 元；只改变搬运成本。")
    for item in examples:
        _display_calculation(item["decision"], title=f"搬运成本 {_format_money(item['move_cost'])}")
    _download_bill(
        mode="explicit_example",
        source="内置显式演示示例（非实时天气）",
        fetched_at_utc=None,
        window={"label": "p=0.6 示例", "start_utc": None, "end_utc": None},
        assumptions={
            "probability": 0.6,
            "probability_kind": "未经校准的降雨集合成员占比（示例输入，不是货损概率）",
            "move_costs": [80.0, 600.0],
            "loss_without": 1000.0,
            "loss_after": 100.0,
            "history_model_67_9_percent_used": False,
        },
        result=[item["decision"] for item in examples],
        key="decision_example_download",
    )


def _render_real_weather(root: Path) -> None:
    location_keys = sorted(LOCATIONS)
    location_key = st.selectbox(
        "天气参考点",
        location_keys,
        format_func=lambda key: str(LOCATIONS[key].get("name", key)),
        key="decision_location",
    )
    # 先按城市切换清掉旧确认，即使当前城市暂时没有可用窗口也不保留。
    _sync_confirmation_selector(CONFIRMATION_LOCATION_KEY, location_key)
    refresh_now = st.button("手动刷新天气", key="decision_force_refresh", width="stretch")
    with st.spinner("正在读取天气情景缓存……"):
        try:
            weather = get_weather(root, location_key, refresh=True, force=bool(refresh_now))
        except Exception as exc:  # 页面必须把后端异常变成可读状态，而不是伪造概率。
            weather = {"status": "error", "snapshot": None, "error": f"天气模块异常：{exc}"}

    status = str(weather.get("status", "error"))
    label = STATUS_LABELS.get(status, "天气状态未知")
    if status == "fresh":
        st.success(f"{label}。{STATUS_HELP['fresh']}")
    elif status in {"stale", "partial"}:
        st.warning(f"{label}。{STATUS_HELP[status]}")
    else:
        st.info(f"{label}。{STATUS_HELP.get(status, '暂不显示行动结论。')}")
    if weather.get("error"):
        st.caption(f"天气模块记录：{weather['error']}")

    snapshot = weather.get("snapshot")
    if not isinstance(snapshot, Mapping):
        return
    fetched_text = snapshot.get("fetched_at_utc")
    source = str(snapshot.get("source") or "未知来源")
    st.caption(f"来源：{source} · 实际获取：{fetched_text or '未知'} · SHA256：{snapshot.get('raw_sha256') or '未知'}")

    now = datetime.now(UTC)
    if status not in {"fresh", "partial"}:
        st.info("当前天气状态不满足新鲜条件，不显示实时搬运/不搬行动结论。")
        return
    identity_ok, identity_reason, fetched = _snapshot_gate(snapshot, location_key, now)
    if not identity_ok:
        st.info(f"当前天气快照未通过来源、schema 或新鲜度检查：{identity_reason}不显示行动结论。")
        return

    windows, reasons = _eligible_windows(snapshot, now)
    if not windows:
        st.info("没有仍在未来、完整且包含有限概率的 24 小时窗口；不显示行动结论。")
        if reasons:
            st.caption("；".join(dict.fromkeys(reasons)))
        return

    selected_window = st.selectbox(
        "选择 24 小时情景窗口",
        windows,
        format_func=_window_label,
        key=f"decision_window_{location_key}",
    )
    probability = float(selected_window["probability"])
    st.caption("p 是未经校准的降雨集合成员占比，不是货损概率；历史模型的 67.9% 未混入本次算账。")
    st.metric("当前窗口情景 p", f"{probability:.1%}")

    cost, loss_without, loss_after = _cost_inputs("decision_real")
    _activate_confirmation_context(
        {
            "scope": "real",
            "location": location_key,
            "window": selected_window.get("start_utc"),
            "probability": probability,
            "move_cost": cost,
            "loss_without": loss_without,
            "loss_after": loss_after,
        }
    )
    if cost is None or loss_without is None or loss_after is None:
        return
    confirmed = _confirmation(
        "real",
        {
            "location": location_key,
            "window": selected_window.get("start_utc"),
            "probability": probability,
            "move_cost": cost,
            "loss_without": loss_without,
            "loss_after": loss_after,
        },
    )
    if not confirmed:
        st.info("请先确认该降雨事件发生时的条件平均货损估计，确认后才显示搬、不搬或同价结论。")
        return
    decision = calculate_decision(probability, cost, loss_without, loss_after)
    _display_calculation(decision)
    _download_bill(
        mode="real_weather",
        source=source,
        fetched_at_utc=fetched.isoformat().replace("+00:00", "Z") if fetched is not None else None,
        window=selected_window,
        assumptions={
            "probability": probability,
            "probability_kind": "未经校准的降雨集合成员占比（不是货损概率）",
            "move_cost": cost,
            "loss_without": loss_without,
            "loss_after": loss_after,
            "average_loss_definition": "降雨事件发生时（包括可能不受损）的条件平均货损",
            "location": location_key,
            "history_model_67_9_percent_used": False,
            "raw_sha256": snapshot.get("raw_sha256"),
        },
        result=decision,
        key=f"decision_real_download_{location_key}",
    )


@st.fragment(run_every="60s")
def _decision_fragment(root: Path) -> None:
    st.markdown("### 情景建议：搬不搬，先看平均货损是否值得成本")
    st.caption("实时天气情景只提供未经校准的降雨集合成员占比；是否执行由你的货损与搬运成本假设决定。")
    mode = st.radio(
        "计算模式",
        ["实时天气情景", "显式演示模式"],
        horizontal=True,
        key="decision_mode",
    )
    _sync_confirmation_selector(CONFIRMATION_MODE_KEY, mode)
    if mode == "显式演示模式":
        _render_example_mode()
        return
    _render_real_weather(root)


def show_decision(root: Path) -> None:
    """渲染决策页；天气自动重查由 60 秒 fragment 驱动。"""

    _decision_fragment(Path(root))


__all__ = ["show_decision"]
