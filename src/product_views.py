from __future__ import annotations

from html import escape
import hashlib
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .bundle import DataBundle, read_json
from .results import METHOD_NAMES, ResultBundle
from .temporal_results import load_temporal_evidence

TEAL = "#167f8a"
INK = "#173c4e"
GOLD = "#d99b55"


def section(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="section-title">{escape(title)}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def result_status(results: ResultBundle) -> bool:
    if results.errors:
        st.error("实验结果校验未通过，已停止展示概率和评估数字。")
        for error in results.errors:
            st.write("• " + error)
        return False
    if not results.ready:
        st.info("模型实验尚未接入。可以先到数据核查页面查看真实数据与配对限制。")
        return False
    return True


def test_predictions(data: DataBundle, results: ResultBundle) -> pd.DataFrame:
    return results.predictions.loc[results.predictions["split"].eq("test")].merge(
        data.samples.drop(columns=["split", "experiment_kind"]), on="sample_id", how="left", validate="many_to_one")


def show_temporal_evidence(root: Path, data: DataBundle) -> None:
    report, errors = load_temporal_evidence(root, data.dataset_version)
    if errors:
        st.warning("新增时间段证据校验失败，已停止展示它的数字；主实验仍按自己的身份核验。")
        for error in errors:
            st.caption(error)
        return
    if not report:
        return
    with st.expander("2026 年新增时间段：覆盖不足，不能补上梅雨验证", expanded=True):
        counts = report["counts"]
        st.write(f"按本地事先保存的协议检查 2026 年 1—9 月 {counts['configured_days']} 日，只有 {counts['paired_windows']} 个完整配对日、{counts['event_count']} 个参考事件。完整参考只覆盖 1—3 月，4—9 月全部缺少完整参考；缺测不代表无雨。")
        st.caption("内部协议在本轮下载来源前保存，未在第三方平台注册。直接使用冻结参数，不拟合、不更换推荐方法；这不是前瞻试点或跨站验证。")
        monthly = pd.DataFrame(report["monthly_coverage"]).rename(columns={"month": "月份", "configured_days": "配置日", "complete_candidate_days": "完整参考日", "paired_windows": "配对日", "event_count": "参考事件"})
        st.dataframe(monthly, hide_index=True, width="stretch")
        if report["metrics"]:
            rows = [{"冻结方法": METHOD_NAMES.get(method, method), "新增样本 Brier": metrics["brier"]}
                    for method, metrics in report["metrics"].items()]
            st.dataframe(pd.DataFrame(rows).style.format({"新增样本 Brier": "{:.4f}"}), hide_index=True, width="stretch")
        st.caption("这些分数只描述 85 日、1 个事件；不能据此评价完整 2026 年或梅雨季表现。完整指标、失误、重采样与来源摘要均保留在报告中。原主实验 636 日和 240 日测试段没有改变。")
        st.download_button("下载2026时间段完整检查", (root / "reports/temporal_validation.json").read_bytes(),
                           "temporal_validation.json", "application/json", key="temporal-evidence-download")


def show_demo(root: Path, data: DataBundle, results: ResultBundle) -> None:
    section("先看预测，再看这一天的参考降水", "历史离线演示 · 萧山机场公开参考点 · 测试段 2025 年 5—12 月")
    if not result_status(results):
        return
    selected_method = results.evaluation["selected_method"]
    table = test_predictions(data, results)
    selected = table.loc[table["method"].eq(selected_method)].sort_values("window_start_utc").copy()
    selected["month"] = pd.to_datetime(selected["window_start_utc"], utc=True).dt.strftime("%Y-%m")
    months = sorted(selected["month"].unique())
    month_column, date_column = st.columns([1, 2])
    with month_column:
        month = st.selectbox("选择演示月份", months, index=months.index("2025-06") if "2025-06" in months else 0)
    subset = selected.loc[selected["month"].eq(month)]
    date_labels = {row.sample_id: pd.Timestamp(row.window_start_utc).tz_convert("Asia/Shanghai").strftime("%Y 年 %m 月 %d 日 08:00 起") for row in subset.itertuples()}
    with date_column:
        sample_id = st.selectbox("选择历史窗口", list(date_labels), format_func=date_labels.get)
    row = subset.loc[subset["sample_id"].eq(sample_id)].iloc[0]
    probability = float(row.probability)
    event_threshold = float(row.event_threshold_mm)
    left, right = st.columns([1.12, 1])
    with left:
        probability_text = "小于 0.1%" if 0 < probability < .001 else f"{probability:.1%}"
        st.markdown(f'''<div class="probability-card"><div class="kicker">参考日降水 ≥ {event_threshold:g} 毫米</div>
<div class="probability-value">{probability_text}</div><div class="probability-label">模型估计概率</div>
<div class="probability-track"><span style="width:{probability * 100:.3f}%"></span></div>
<div class="probability-meta">{escape(METHOD_NAMES[selected_method])} · 24 小时名义 UTC 日</div></div>''', unsafe_allow_html=True)
        st.caption("低概率仍可能发生事件。这个数值没有表示门店积水概率。")
    with right:
        section("一次准备，值不值得做？")
        st.write("假设未准备且事件发生时损失为 100 单位，准备能完全避免这项损失。")
        cost = st.slider("每次准备的假设成本 / 单位", min_value=2, max_value=95, value=10, step=1)
        trigger = probability >= cost / 100
        threshold = cost / 100
        st.markdown(f"本次情景阈值为 **{threshold:.0%}**。当估计概率达到这个值时，模型情景选择准备。")
        if trigger:
            st.info("达到本次假设阈值，可以查看下方准备项。")
        else:
            st.info("未达到本次假设阈值；仍可核对已有准备并关注官方天气信息。")
        st.caption("这里的成本与避损能力是假设，不是报价、实测收益或应急建议。改变成本不会重新训练模型。")
    section("把准备拆成三件看得见的事", "以下为根据公开资料适配的小商户准备建议。请按实际商品和条件判断。")
    action_data = read_json(root / "docs" / "action_sources.json")
    actions = action_data.get("recommended_actions", [])
    columns = st.columns(3)
    for index, action in enumerate(actions[:3]):
        with columns[index]:
            with st.container(border=True):
                st.markdown(f"**0{index + 1} · {action['label']}**")
                st.write(action["action"])
                st.checkbox("已核对这一项", key=f"action-{sample_id}-{action['id']}")
    with st.expander("准备建议的来源和适用范围"):
        st.write("这些是资料适配建议，尚未经过商户试点。政府救灾物资规则不能直接改写成商户的法定义务或必买目录。")
        for source in action_data.get("sources", []):
            st.markdown(f"[{source['title']}]({source['url']})")
            st.caption(source.get("publication_date", ""))
    reveal = st.checkbox("揭晓该日参考降水", key=f"reveal-{sample_id}")
    if reveal:
        amount = float(row.observed_rain_mm)
        event = amount >= event_threshold
        a, b, c = st.columns(3)
        a.metric("SSOD 参考日降水", f"{amount:.1f} mm")
        b.metric("原始数值预报累计", f"{float(row.forecast_rain_mm):.1f} mm")
        c.metric("是否达到研究阈值", "达到" if event else "未达到")
        st.caption("SSOD 可能低报；测量码 G 表示一份 24 小时报告。单日揭示用于解释案例，不能代替完整测试段评估。")
    with st.expander("查看这次预测的依据"):
        st.write({"窗口开始UTC": row.window_start_utc, "窗口结束UTC": row.window_end_utc,
                  "北京时间日界": "08:00 至次日 08:00", "数据版本": data.dataset_version,
                  "模型版本": row.model_version, "实验类型": "固定提前量离线实验",
                  "参考日界": row.window_basis, "原始数值预报/mm": float(row.forecast_rain_mm)})
        st.write("固定提前量逐小时合成序列没有唯一初始化时刻。本演示没有核实历史真实发布时间，不能解释为当时某一时刻已经收到的全天预报。")
    record = {"用途": "历史离线演示", "sample_id": sample_id, "dataset_version": data.dataset_version,
              "model_version": row.model_version, "method": selected_method, "probability": probability,
              "event_threshold_mm": event_threshold, "window_start_utc": row.window_start_utc,
              "window_end_utc": row.window_end_utc, "assumed_prepare_cost": cost, "assumed_unprepared_event_loss": 100,
              "assumed_full_loss_avoidance": True, "scenario_prepare": trigger,
              "reference_rain_mm": float(row.observed_rain_mm) if reveal else None,
              "限制": "SSOD名义UTC日参考；可能低报；非官方预警；非门店积水预测；成本为假设。"}
    st.download_button("下载这次演示记录", json.dumps(record, ensure_ascii=False, indent=2).encode("utf-8"), "meiyu_demo_record.json", "application/json")


def show_comparison(root: Path, data: DataBundle, results: ResultBundle) -> None:
    section("把模型放到同一批测试日上比较", "模型和参数由验证段选择；测试段只用于报告，不参与挑选。")
    if not result_status(results):
        return
    evaluation = results.evaluation
    summary = evaluation["split_summary"]
    split_columns = st.columns(3)
    for column, split, label in zip(split_columns, ["train", "validation", "test"], ["训练 · 2024", "验证 · 2025.01—04", "测试 · 2025.05—12"]):
        column.metric(label, f"{summary[split]['sample_count']} 日", f"{summary[split]['event_count']} 个参考事件", delta_color="off")
    test_metrics = evaluation["metrics"]["test"]
    selected_method = evaluation["selected_method"]
    values = []
    for method, metrics in test_metrics.items():
        values.append({"方法": METHOD_NAMES.get(method, method), "验证 Brier": evaluation["metrics"]["validation"][method]["brier"],
                       "测试 Brier": metrics["brier"], "测试 ROC-AUC": metrics["roc_auc"],
                       "测试 AP": metrics["average_precision"], "验证选中": "是" if method == selected_method else ""})
    st.dataframe(pd.DataFrame(values).style.format({"验证 Brier": "{:.4f}", "测试 Brier": "{:.4f}", "测试 ROC-AUC": "{:.3f}", "测试 AP": "{:.3f}"}, na_rep="不可计算"), hide_index=True, width="stretch")
    st.caption("Brier 越小越好。原始预报规则是雨量达到 25 毫米的 0/1 判断，并非天气机构提供的原始概率；因此不代表与其概率产品的比较。")
    diagnostic_identity = results.run.get("supplemental_diagnostics", {})
    diagnostic_path = root / "reports" / "sensitivity_checks.json"
    if diagnostic_path.exists() and hashlib.sha256(diagnostic_path.read_bytes()).hexdigest() == diagnostic_identity.get("sha256"):
        diagnostics = read_json(diagnostic_path)
        if diagnostics.get("dataset_version") == data.dataset_version and diagnostics.get("predictions_file_sha256") == results.run.get("predictions_file_sha256"):
            with st.expander("固定月份与原始雨量排序的补充检查", expanded=True):
                st.write(f"原始连续预报雨量与选中模型的 ROC-AUC 均为 {diagnostics['raw_continuous_rain_roc_auc']:.4f}。降水模型保持原始雨量排序；当前证据针对概率表达和情景成本，不能解释为增加了天气排序能力。")
                period_rows = []
                for label, methods in diagnostics["period_metrics"].items():
                    selected_metrics = methods[selected_method]
                    period_rows.append({"固定月份子集": label, "日数 / 事件数": f"{selected_metrics['sample_count']} / {selected_metrics['event_count']}",
                                        "固定事件率 Brier": methods["training_climatology"]["brier"], "原始规则 Brier": methods["raw_nwp_rule"]["brier"], "选中模型 Brier": selected_metrics["brier"]})
                st.dataframe(pd.DataFrame(period_rows).style.format({"固定事件率 Brier": "{:.4f}", "原始规则 Brier": "{:.4f}", "选中模型 Brier": "{:.4f}"}), hide_index=True, width="stretch")
                st.caption("补充描述性检查使用同一份冻结预测。5—7 月不等于官方梅雨期，检查没有参与调参，也不是新的盲测。尚未与集合预报概率产品或所有更强校准方法比较。")
    show_temporal_evidence(root, data)
    left, right = st.columns([1, 1])
    with left:
        section("概率与实际频率是否相称")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], name="一致参考线", mode="lines", line=dict(color="#bdcbd1", dash="dash")))
        for method in [selected_method, "training_climatology"]:
            bins = pd.DataFrame(test_metrics[method]["calibration_bins"])
            bins = bins.loc[bins["count"].gt(0)]
            fig.add_trace(go.Scatter(x=bins.mean_probability, y=bins.observed_event_rate, name=METHOD_NAMES[method],
                                     mode="lines+markers", marker=dict(size=9), customdata=bins["count"], hovertemplate="估计概率 %{x:.1%}<br>参考事件率 %{y:.1%}<br>该箱 %{customdata} 日<extra></extra>"))
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=15, b=10), legend=dict(orientation="h", y=1.2), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", xaxis_title="估计概率", yaxis_title="参考事件率")
        fig.update_xaxes(range=[0, 1], tickformat=".0%", gridcolor="#edf1f3")
        fig.update_yaxes(range=[0, 1], tickformat=".0%", gridcolor="#edf1f3")
        st.plotly_chart(fig, width="stretch")
        st.caption("固定五个概率箱；空箱不绘制。测试事件只有 18 个，高概率箱样本很少，曲线不足以证明概率已经可靠。")
    with right:
        section("差异有多不确定")
        for item in evaluation["paired_brier_bootstrap"]:
            baseline = item["comparison"].split(" -> ")[0]
            ci = item["ci95"]
            st.markdown(f"相对 **{METHOD_NAMES.get(baseline, baseline)}**")
            st.write(f"配对 Brier 差 {item['mean_difference']:.4f}；95% 周块重采样区间 [{ci['lower']:.4f}, {ci['upper']:.4f}]。")
        st.caption("负值有利于验证选中的方法。区间反映当前 36 个日历周块的重采样；同一站点、季节变化、标签低报与模型选择不确定性没有因此消失。")
        st.info("当前离线测试支持进一步验证。下一步应增加独立季节与参考站数据，开展用户理解测试，再验证真实可用预报。")
    section("把准备成本当作一个可调整的假设", "固定预测和固定测试日；下面只改变情景成本，不重新选择模型。")
    st.write("每次准备付 C，未准备且事件发生付 L=1。这里假设准备完全避免相关损失；没有测量真实商户的成本与避损能力。")
    costs = evaluation["cost_scenarios"]
    fig = go.Figure()
    for method in [selected_method, "raw_nwp_rule", "training_climatology"]:
        points = costs["methods"][method]
        fig.add_trace(go.Scatter(x=[p["prepare_cost_ratio"] for p in points], y=[p["mean_realized_cost"] for p in points], name=METHOD_NAMES[method], mode="lines+markers"))
    for key, name in [("always_prepare", "每次都准备"), ("never_prepare", "从不准备")]:
        points = costs[key]
        fig.add_trace(go.Scatter(x=[p["prepare_cost_ratio"] for p in points], y=[p["mean_realized_cost"] for p in points], name=name, mode="lines", line=dict(dash="dot")))
    fig.update_layout(height=330, margin=dict(l=12, r=12, t=25, b=10), legend=dict(orientation="h", y=1.22), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", xaxis_title="准备成本 C / 未准备事件损失 L", yaxis_title="每测试日平均情景成本 / 相对单位")
    fig.update_xaxes(tickformat=".0%", gridcolor="#edf1f3")
    fig.update_yaxes(gridcolor="#edf1f3", rangemode="tozero")
    st.plotly_chart(fig, width="stretch")
    section("也看失败案例", "按验证选中方法的逐日 Brier 误差排序，显示最大的五个测试误差，不用案例替代整体指标。")
    table = test_predictions(data, results)
    table = table.loc[table["method"].eq(selected_method)].copy()
    table["参考事件"] = table.observed_rain_mm.ge(float(evaluation["event_threshold_mm"]))
    table["单日 Brier 误差"] = (table.probability - table["参考事件"].astype(int)) ** 2
    worst = table.nlargest(5, "单日 Brier 误差")[["window_start_utc", "probability", "observed_rain_mm", "参考事件", "单日 Brier 误差"]].rename(columns={"window_start_utc": "窗口开始 UTC", "probability": "估计概率", "observed_rain_mm": "参考降水 / mm"})
    st.dataframe(worst, hide_index=True, width="stretch")
    with st.expander("实验约定与完整限制"):
        st.write("两个逻辑回归各在验证段从 C=0.1、1、10 中选择；填充、标准化和拟合只使用 2024 年训练段，没有用训练加验证重新拟合。")
        for limitation in evaluation.get("limitations", []):
            st.markdown("- " + limitation)
    st.download_button("下载完整评估 JSON", (root / "reports" / "evaluation.json").read_bytes(), "evaluation.json", "application/json")
