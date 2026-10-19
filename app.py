from __future__ import annotations

import io
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.bundle import load_bundle
from src.bundle import read_json
from src.contracts import validate_predictions
from src.results import load_results
from src.product_views import show_comparison, show_demo
from src.online_views import show_online

ROOT = Path(__file__).resolve().parent
KINDS = {"offline_fixed_lead": "固定提前量离线实验", "offline_hindcast": "历史回报方法实验", "operational_replay": "已核实的决策回放"}
st.set_page_config(page_title="梅雨有数 · 数据工作台", page_icon="🌧️", layout="wide")
st.markdown("""
<style>
html, body, [class*="css"], [data-testid="stApp"] {font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;}
.block-container {padding-top:2rem; padding-bottom:2.5rem; max-width:1440px;}
#MainMenu, footer, [data-testid="stToolbar"] {visibility:hidden;}
.hero {background:linear-gradient(115deg,#102c40,#164751); color:white; border-radius:18px; padding:32px 38px; margin-bottom:22px;}
.hero .eyebrow {font-size:12px; letter-spacing:3px; color:#9bd4d6; margin-bottom:12px;}
.hero h1 {font-size:35px; font-weight:600; color:white; margin:0 0 12px; padding:0;}
.hero p {font-size:15px; color:#c6dce1; margin:0; max-width:900px; line-height:1.8;}
.tag {display:inline-block; border:1px solid #517b82; border-radius:20px; padding:4px 12px; color:#bce8e6; font-size:12px; margin-top:18px;}
[data-testid="stMetric"] {background:white; border:1px solid #e2eaee; border-radius:12px; padding:18px 20px; min-height:112px;}
[data-testid="stMetricValue"] {color:#143f51; font-weight:600;}
[data-baseweb="tab-list"] {gap:24px; padding:9px 0 14px;}
[data-baseweb="tab"] {font-size:15px;}
.section-title {font-size:19px; font-weight:600; margin:14px 0 6px; color:#173c4e;}
.subtle {font-size:13px; color:#637b8a; line-height:1.8;}
.note {background:#eef5f6; border-left:3px solid #31838b; padding:14px 18px; border-radius:0 9px 9px 0; color:#3c6170; font-size:13px; line-height:1.9; margin:12px 0 20px;}
.source-card {background:white; border:1px solid #e2eaee; border-radius:10px; padding:15px 18px; margin:9px 0;}
section[data-testid="stSidebar"] {background:#eaf0f2;}
.probability-card {background:linear-gradient(125deg,#11394a,#1a6670);color:white;border-radius:16px;padding:28px 30px;min-height:275px;margin-top:10px;}
.kicker {font-size:14px;color:#b8dfe1;letter-spacing:1px;}
.probability-value {font-size:64px;font-weight:600;line-height:1.25;margin-top:9px;}
.probability-label {font-size:14px;color:#cae2e5;}
.probability-track {height:6px;background:#ffffff25;border-radius:5px;margin:22px 0 15px;overflow:hidden;}
.probability-track span {height:100%;display:block;background:#91d6d0;min-width:2px;border-radius:5px;}
.probability-meta {font-size:12px;color:#a4d5d7;}
@media(max-width:700px){.hero{padding:24px 22px;}.hero h1{font-size:30px;}.probability-value{font-size:52px;}[data-baseweb="tab-list"]{gap:12px;}.st-key-headline_metrics{display:none;}}
</style>
""", unsafe_allow_html=True)

try:
    bundle = load_bundle(ROOT)
except Exception as exc:
    st.error(f"数据包无法读取：{type(exc).__name__}: {exc}")
    st.stop()

st.markdown("""<div class="hero"><div class="eyebrow">MEIYU · OPEN WEATHER LAB</div>
<h1>梅雨有数</h1><p>准备要花多少精力，值得提前做吗？用公开天气数据解释降雨概率与准备成本，让每一步判断都能回到证据。</p>
<span class="tag">杭州与宁波 · 在线天气与冻结实验</span></div>""", unsafe_allow_html=True)

if bundle.errors:
    st.error("数据包校验未通过，已停止正常展示。")
    for error in bundle.errors:
        st.write("• " + error)
    st.stop()

samples = bundle.samples
quality = bundle.quality
summary = quality.get("summary", {})
version = bundle.dataset_version
results = load_results(ROOT, bundle)
with st.sidebar:
    st.markdown("### 数据包")
    st.caption("打开页面不自动请求天气；到最新天气页点击按钮可在线更新。")
    st.caption("版本：" + (version if version else "尚未生成"))
    st.write("样本协议：", "1.0.0")
    if not samples.empty:
        names = samples[["station_id", "station_name"]].drop_duplicates()
        st.write("观测点：", "、".join(names["station_name"].astype(str)))
        st.write("实验类型：", "、".join(KINDS.get(x, x) for x in samples["experiment_kind"].unique()))
        st.download_button("下载统一样本 CSV", (ROOT / "data" / "samples.csv").read_bytes(), "samples.csv", "text/csv", width="stretch")
    if quality:
        st.download_button("下载质量报告 JSON", (ROOT / "reports" / "data_quality.json").read_bytes(), "data_quality.json", "application/json", width="stretch")
    st.divider()
    st.caption("当前数据用于方法研究。站点降雨不能直接等同于某家商铺积水；请查看数据口径与适用限制。")

window_count = samples["observation_window_id"].nunique() if not samples.empty else 0
months = pd.to_datetime(samples["window_start_utc"], utc=True).dt.strftime("%Y-%m").nunique() if not samples.empty else 0
candidate_count = summary.get("candidate_window_count", 0)
retention = f"{window_count / candidate_count:.1%}" if candidate_count else "—"
with st.container(key="headline_metrics"):
    st.caption("冻结主实验数据")
    cols = st.columns(4)
    cols[0].metric("已配对观测窗口", f"{window_count:,}")
    cols[1].metric("覆盖月份", str(months))
    cols[2].metric("候选窗口保留率", retention)
    cols[3].metric("已核查来源文件", str(len(bundle.manifest.get("sources", []))))

online, demo, comparison, overview, browser, models = st.tabs(["最新天气", "历史演示", "方法比较", "数据核查", "样本浏览", "模型接入"])

with online:
    show_online(ROOT)

with demo:
    show_demo(ROOT, bundle, results)

with comparison:
    show_comparison(ROOT, bundle, results)


def rain_chart(frame: pd.DataFrame, height: int = 330):
    frame = frame.sort_values("window_end_utc")
    figure = go.Figure()
    x = pd.to_datetime(frame["window_end_utc"], utc=True).dt.tz_convert("Asia/Shanghai")
    figure.add_trace(go.Bar(x=x, y=frame["observed_rain_mm"], name="SSOD 参考日降水", marker_color="#1d8490", opacity=.8))
    figure.add_trace(go.Scatter(x=x, y=frame["forecast_rain_mm"], name="原始预报累计降水", mode="lines+markers", line=dict(color="#e29b52", width=2), marker=dict(size=4)))
    figure.update_layout(height=height, margin=dict(l=12,r=12,t=20,b=15), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="white", font=dict(color="#456171"), legend=dict(orientation="h", y=1.12, x=0), yaxis_title="24 小时累计降水 / 毫米", xaxis_title="窗口结束时刻 / 北京时间", hovermode="x unified")
    figure.update_yaxes(gridcolor="#edf1f3", rangemode="tozero")
    st.plotly_chart(figure, width="stretch")


with overview:
    st.markdown('<div class="section-title">先确认数据能回答什么</div>', unsafe_allow_html=True)
    status_text = {"ready_offline_fixed_lead": "已完成配对，可用于固定提前量离线实验", "blocked": "数据构建受阻，请查看核查结果"}.get(quality.get("status_label"), "数据核查尚未完成")
    if samples.empty:
        st.warning(status_text)
    else:
        st.success(status_text)
    for limitation in quality.get("limitations", []):
        st.markdown(f"- {limitation}")
    external = read_json(ROOT / "reports" / "external_validation.json")
    if external.get("status") == "blocked":
        with st.expander("拓展到宁波前的数据检查"):
            st.write("宁波栎社机场 2025 年 SSOD 文件可访问，但 362 行降水均缺失，测量码全部为 I。没有完整参考日，因此停止配对与迁移评估。")
            st.caption("数据源可访问不等于数据可用。没有更换站点凑样本，也没有计算宁波模型效果。")
            st.write(external.get("ssod_access", {}).get("download_url", ""))
            st.download_button("下载宁波数据阻塞证据", (ROOT / "reports" / "external_validation.json").read_bytes(), "external_validation.json", "application/json")
    monthly = pd.DataFrame(quality.get("monthly", []))
    left, right = st.columns([1.65, 1])
    with left:
        st.markdown('<div class="section-title">月份覆盖</div>', unsafe_allow_html=True)
        st.caption("月份按窗口开始的 UTC 日期统计。候选日须有完整参考总量；缺失不会补成无雨。")
        if not monthly.empty and {"month", "candidate_windows", "paired_windows"}.issubset(monthly.columns):
            fig = go.Figure()
            fig.add_trace(go.Bar(x=monthly["month"], y=monthly["candidate_windows"], name="候选窗口", marker_color="#d8e4e8"))
            fig.add_trace(go.Bar(x=monthly["month"], y=monthly["paired_windows"], name="合格配对", marker_color="#248b93"))
            fig.update_layout(height=310, barmode="group", margin=dict(l=8,r=8,t=40,b=10), legend=dict(orientation="h", y=1.18), plot_bgcolor="white", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="窗口数")
            fig.update_yaxes(gridcolor="#edf1f3")
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("尚无完整的月份覆盖统计。")
    with right:
        st.markdown('<div class="section-title">核查结果</div>', unsafe_allow_html=True)
        findings = quality.get("findings", [])
        if findings:
            for item in findings:
                with st.expander(item.get("title", item.get("issue", "数据问题")), expanded=item.get("severity") == "critical"):
                    st.write(item.get("evidence", ""))
                    st.caption(item.get("impact", ""))
                    if item.get("remediation"):
                        st.write("处理：", item["remediation"])
        else:
            st.info("审计结果尚未生成。")
    with st.expander("数据来源与追溯", expanded=False):
        for source in bundle.manifest.get("sources", []):
            st.markdown(f"**{source.get('title', source.get('source_id', '来源'))}**")
            st.write(source.get("url", ""))
            st.caption(f"许可：{source.get('licence', '待核查')} · SHA256：{source.get('sha256', '')}")
        if not bundle.manifest.get("sources"):
            st.write("尚无来源记录。")
    with st.expander("隔离记录与排除原因"):
        if bundle.quarantined.empty:
            st.write("当前没有隔离记录。")
        else:
            reason_column = "exclusion_reason" if "exclusion_reason" in bundle.quarantined else "reason"
            if reason_column in bundle.quarantined:
                counts = bundle.quarantined[reason_column].value_counts().rename_axis("原因").reset_index(name="记录数")
                st.dataframe(counts, hide_index=True, width="stretch")
            st.dataframe(bundle.quarantined.head(200), hide_index=True, width="stretch")
            st.download_button("下载全部隔离记录", (ROOT / "data" / "quarantined_records.csv").read_bytes(), "quarantined_records.csv", "text/csv")

with browser:
    st.markdown('<div class="section-title">查看一段真实的历史窗口</div>', unsafe_allow_html=True)
    if samples.empty:
        st.info("尚无通过质量与窗口配对检查的主样本。请先查看数据概览中的原因。")
    else:
        st.caption("SSOD 名义 UTC 00–24 日，对应北京时间 08:00 至次日 08:00；不是本地自然日，也不是积水观测。")
        month_values = sorted(pd.to_datetime(samples["window_start_utc"], utc=True).dt.strftime("%Y-%m").unique())
        selected_month = st.selectbox("选择月份", month_values, index=max(0, len(month_values)-1))
        subset = samples.loc[pd.to_datetime(samples["window_start_utc"], utc=True).dt.strftime("%Y-%m").eq(selected_month)].copy()
        rain_chart(subset)
        options = subset.sort_values("window_end_utc")["sample_id"].tolist()
        labels = {row.sample_id: f"{pd.Timestamp(row.window_end_utc).tz_convert('Asia/Shanghai').strftime('%m 月 %d 日 %H:%M')} · {row.station_name}" for row in subset.itertuples()}
        selected_id = st.selectbox("查看单个样本", options, format_func=lambda value: labels[value])
        row = subset.loc[subset["sample_id"].eq(selected_id)].iloc[0]
        a, b, c = st.columns(3)
        a.metric("SSOD 参考日降水", f"{row.observed_rain_mm:.1f} mm")
        b.metric("原始预报累计降水", f"{row.forecast_rain_mm:.1f} mm")
        c.metric("窗口长度", "24 小时")
        st.markdown('<div class="note">这里比较的是原始预报与参考观测，尚未表达 AI 校准收益。固定提前量合成序列和历史回报试验的结果，不能解释为当时实际发布的全天预报。</div>', unsafe_allow_html=True)
        details = {
            "样本 ID": row.sample_id,
            "窗口开始 / UTC": row.window_start_utc,
            "窗口结束 / UTC": row.window_end_utc,
            "实验类型": KINDS.get(row.experiment_kind, row.experiment_kind),
            "预报模型": row.forecast_model,
            "参考类型": row.reference_kind,
            "累计日界依据": row.window_basis,
            "报告测量码": str(row.observation_measurement_code),
            "初始化时刻": "无唯一时刻或未知" if pd.isna(row.run_init_utc) else row.run_init_utc,
            "实际可用时刻": "未核实" if pd.isna(row.available_at_utc) else row.available_at_utc,
            "观测记录引用": row.obs_record_id,
            "预报记录引用": row.forecast_record_id,
            "数据划分": row.split,
        }
        st.dataframe(pd.DataFrame(details.items(), columns=["字段", "内容"]), hide_index=True, width="stretch")
        with st.expander("查看当前月份样本表"):
            st.dataframe(subset, hide_index=True, width="stretch")

with models:
    st.markdown('<div class="section-title">接入队友的独立实验结果</div>', unsafe_allow_html=True)
    st.caption("应用只展示通过协议检查的预测，不在页面里重新训练或挑选阈值。")
    uploaded = st.file_uploader("上传 predictions.csv", type=["csv"])
    prediction_path = ROOT / "artifacts" / "predictions.csv"
    prediction_data = uploaded.getvalue() if uploaded is not None else prediction_path.read_bytes() if prediction_path.exists() else None
    if prediction_data is None:
        st.info("尚未接入模型结果。当前页面不展示校准概率或效果数字。")
        st.markdown("队友交付包含样本 ID、方法、概率、模型版本、数据版本、实验类型及事件阈值的 CSV 后，即可在这里检查和展示。")
    elif samples.empty:
        st.error("当前没有可用主样本，不能接入模型预测。")
    else:
        try:
            predictions = pd.read_csv(io.BytesIO(prediction_data), dtype={"sample_id": "string", "dataset_version": "string"})
            errors = validate_predictions(predictions, samples, version)
            if errors:
                st.error("预测文件校验失败，已阻止展示。")
                for error in errors:
                    st.write("• " + error)
            else:
                st.success(f"协议检查通过：{len(predictions):,} 条预测。协议通过不等于模型效果已通过验证。")
                st.write(f"预测目标：24 小时累计降水达到 {float(predictions.event_threshold_mm.iloc[0]):g} 毫米。")
                st.dataframe(predictions, hide_index=True, width="stretch")
        except Exception as exc:
            st.error(f"无法读取预测文件：{type(exc).__name__}: {exc}")
    contract = ROOT / "docs" / "model_result_contract.md"
    if contract.exists():
        with st.expander("模型结果接口说明"):
            st.markdown(contract.read_text(encoding="utf-8"))

st.caption("梅雨有数 · 公开数据与可复现研究。模型效果、用户使用收益和实际灾损减少需要分别验证。")
