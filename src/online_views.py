"""在线天气与完整度页面，只有明确点击刷新按钮才访问外部接口。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .data_completeness import build_completeness
from .live_data import LOCATIONS, PRODUCTS, fetch_snapshot, make_request, parse_payload, read_cached

TITLES = {"forecast": "未来7个完整窗口", "archive": "本年度天气背景", "station": "最新站点参考覆盖"}


def _read_display(root: Path, key: str, product: str) -> dict:
    result = read_cached(root, key, product)
    if result.get("snapshot"):
        return result
    seed_path = root / "external/live_seed/seed.json"
    if not seed_path.exists():
        return result
    try:
        packed = json.loads(seed_path.read_text(encoding="utf-8")).get(key, {}).get(product)
        if not packed:
            return result
        saved = packed["snapshot"]
        fetched = datetime.fromisoformat(saved["fetched_at_utc"].replace("Z", "+00:00"))
        if fetched.tzinfo is None or fetched.timestamp() > datetime.now(timezone.utc).timestamp() + 300:
            raise ValueError("交付快照的获取时刻无效。")
        parsed = parse_payload(packed["raw_utf8"].encode("utf-8"), make_request(key, product, fetched), saved["fetched_at_utc"])
        if parsed != saved:
            raise ValueError("交付快照与原始响应不一致。")
        age = (datetime.now(timezone.utc) - fetched).total_seconds() / 3600
        return {"status": "stale_cache" if age > (3 if product == "forecast" else 24) else "cache", "snapshot": parsed,
                "error": result.get("error"), "origin": "交付快照"}
    except (ValueError, TypeError, KeyError, OSError) as exc:
        return {"status": "error", "snapshot": None, "error": "交付快照无法核验：" + str(exc)}


def _refresh(root: Path, key: str, products: list[str]) -> None:
    with st.spinner("正在核对公开来源，成功的数据会分别保存……"):
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {product: executor.submit(fetch_snapshot, root, key, product, force=True) for product in products}
            for product, future in futures.items():
                st.session_state[f"live_refresh_{key}_{product}"] = future.result()


def _snapshot_card(root: Path, key: str, product: str) -> None:
    result = _read_display(root, key, product)
    prior = st.session_state.get(f"live_refresh_{key}_{product}", {})
    st.markdown(f"### {TITLES[product]}")
    if st.button("单独刷新", key=f"refresh_one_{key}_{product}"):
        _refresh(root, key, [product])
        result = _read_display(root, key, product)
        prior = st.session_state.get(f"live_refresh_{key}_{product}", {})
    error = prior.get("error") or result.get("error")
    if error:
        st.warning("更新未完成，保留上次有效缓存。" if result.get("snapshot") else "当前没有可显示的有效缓存，请重试更新。")
        with st.expander("查看本次失败原因"):
            st.caption(str(error))
    snapshot = result.get("snapshot")
    if not snapshot:
        st.info("尚未保存在线数据。点击“获取最新数据”连接公开接口；历史实验和完整度仍可离线查看。")
        return
    fetched = pd.Timestamp(snapshot["fetched_at_utc"])
    age = max(0, (pd.Timestamp.now(tz="UTC") - fetched).total_seconds() / 3600)
    stale = result["status"] == "stale_cache"
    st.caption(f"{result.get('origin', '本机缓存')} · {'已过期' if stale else '有效'} · {age:.1f}小时前获取 · 北京时间{fetched.tz_convert('Asia/Shanghai').strftime('%Y-%m-%d %H:%M:%S')}")
    coverage = snapshot["coverage"]
    metrics = st.columns(3)
    metrics[0].metric("完整降水日", f"{coverage['complete_day_count']} / {coverage['expected_day_count']}")
    metrics[1].metric("最后有效降水日", coverage.get("latest_available_date") or "—")
    metrics[2].metric("未满足完整条件", str(coverage["expected_day_count"] - coverage["complete_day_count"]))
    if product == "forecast":
        st.caption("UTC 00–24小时，对应北京08:00至次日08:00。明日起7个窗口按(start,end]聚合24小时；这里展示数值预报，不套用历史实验概率。")
    elif product == "archive":
        st.info("ERA5是再分析天气背景，不是新增站点实测。用于补充天气背景覆盖，不会补入SSOD标签。为避开数据延迟，截止日保留7天缓冲。")
    else:
        st.info(f"末次报告日期：{coverage.get('last_reported_date') or '—'}。只有完整测量码与有效日降水总量才计入完整参考，缺测不算无雨。在线结果另存，不改变冻结的636日主实验和85日新增检查。")
    rows = pd.DataFrame(snapshot["rows"])
    if not rows.empty:
        if product != "station":
            figure = go.Figure()
            if product == "forecast":
                figure.add_trace(go.Bar(x=rows.date, y=rows.rain_mm, marker_color="#248b79", name="数值预报日降水"))
            else:
                figure.add_trace(go.Scatter(x=rows.date, y=rows.rain_mm, line=dict(color="#248b79", width=2), mode="lines", connectgaps=False, name="ERA5背景日降水"))
            figure.update_layout(height=270, margin=dict(l=8, r=8, t=15, b=10), yaxis_title="降水 / mm", xaxis_title="窗口开始日期 / UTC", plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
            figure.update_yaxes(gridcolor="#edf1f3", rangemode="tozero")
            st.plotly_chart(figure, width="stretch", key=f"live_chart_{key}_{product}")
        with st.expander("查看逐日完整度与数值"):
            display = rows[["date", "rain_mm", "temperature_mean_c", "hours_present", "hours_expected", "status"]].copy()
            display["status"] = display.status.map({"complete": "完整", "partial": "不完整", "missing": "缺失"})
            display = display.rename(columns={"date": "UTC开始日", "rain_mm": "降水 / mm", "temperature_mean_c": "平均温度 / °C", "hours_present": "有效降水小时", "hours_expected": "所需小时", "status": "状态"})
            st.dataframe(display, hide_index=True, width="stretch")
    with st.expander("来源与原始记录"):
        source = snapshot["source"]
        st.write("来源：", source["provider"], "模型：", source.get("model") or "SSODv2")
        st.write("请求位置：", snapshot["location"]["latitude"], snapshot["location"]["longitude"])
        st.write("返回位置：", snapshot["grid"]["latitude"], snapshot["grid"]["longitude"])
        st.link_button("打开原始接口", snapshot["request_url"])
        st.caption("NOAA/NCEI公共数据保留引用；Open-Meteo按CC BY 4.0署名，免费接口限非商业使用。")
        st.code(snapshot["raw_sha256"], language=None)
    st.download_button("下载数据与来源记录", json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False), f"meiyu_{key}_{product}.json", "application/json", key=f"live_download_{key}_{product}")


def show_online(root: Path) -> None:
    st.markdown('<div class="section-title">天气可更新，缺口也看得清</div>', unsafe_allow_html=True)
    st.caption("最新天气、再分析背景和站点参考分别保存；每一类都有获取时刻、来源摘要与完整度。打开页面不会自动请求天气。")
    left, right = st.columns([2, 1])
    with left:
        key = st.selectbox("公开参考点", list(LOCATIONS), format_func=lambda k: LOCATIONS[k]["name"], key="live_location")
    with right:
        st.write("")
        st.write("")
        if st.button("获取最新数据", type="primary", width="stretch", key="refresh_weather"):
            _refresh(root, key, list(PRODUCTS))
    for product in PRODUCTS:
        with st.container(border=True):
            _snapshot_card(root, key, product)
    st.divider()
    st.markdown("### 冻结数据的完整度")
    try:
        report = build_completeness(root)
    except (ValueError, OSError, KeyError) as exc:
        st.error("完整度证据无法核验：" + str(exc))
        return
    summary = report["summary"]
    a, b, c = st.columns(3)
    a.metric("主实验配对日", f"{summary['paired_days']} / {summary['configured_days']}")
    b.metric("缺少完整参考日", str(summary["missing_reference_days"]))
    c.metric("缺少配对预报日", str(summary["missing_forecast_days"]))
    monthly = pd.DataFrame(report["monthly"])
    chart = go.Figure()
    for field, title, color in [("paired", "已配对", "#248b79"), ("missing_forecast", "缺配对预报", "#e4b478"), ("incomplete_reference", "参考不完整", "#a3b4c1"), ("no_reference_record", "无参考报告", "#dfe7eb")]:
        chart.add_trace(go.Bar(x=monthly.month, y=monthly[field], name=title, marker_color=color))
    chart.update_layout(height=320, barmode="stack", yaxis_title="配置日数", margin=dict(l=8, r=8, t=30, b=10), legend=dict(orientation="h", y=1.15), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(chart, width="stretch", key="completeness_chart")
    with st.expander("逐日状态、字段覆盖与连续缺口"):
        month = st.selectbox("完整度月份", monthly.month.tolist(), index=len(monthly)-1, key="coverage_month")
        days = pd.DataFrame(report["days"])
        st.dataframe(days.loc[days.month.eq(month), ["date", "label"]].rename(columns={"date": "UTC开始日", "label": "状态"}), hide_index=True, width="stretch")
        fields = pd.DataFrame(report["fields"])
        fields["coverage"] = fields.coverage.map(lambda value: f"{value:.1%}")
        st.dataframe(fields[["label", "available", "missing", "coverage", "note"]].rename(columns={"label": "字段", "available": "可用日", "missing": "缺失日", "coverage": "覆盖率", "note": "解释"}), hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(report["gaps"])[["start_date", "end_date", "days", "label"]].rename(columns={"start_date": "缺口开始", "end_date": "缺口结束", "days": "日数", "label": "原因"}), hide_index=True, width="stretch")
    counts = report["temporal"]["counts"]
    st.caption(f"2026年独立检查仍为{counts['paired_windows']}/{counts['configured_days']}日配对、{counts['event_count']}个参考事件，4—9月无完整参考。在线天气背景不会改变该验证结果。")
    st.download_button("下载完整度报告", json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), "meiyu_completeness.json", "application/json", key="completeness_download")
