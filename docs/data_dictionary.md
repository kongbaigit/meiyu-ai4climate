# 统一样本字段说明

一行代表萧山机场一个名义 UTC 日参考降水窗口，与指定 ECMWF 固定提前量逐小时序列的配对。SSOD 日界是 UTC 00:00 至次日 00:00，即北京时间 08:00 至次日 08:00。`passed` 只表示通过本项目的筛选与配对规则，不代表逐日雨量已被独立测量确认。

| 字段 | 含义、单位与限制 |
| --- | --- |
| sample_id | 观测窗口与预报来源定义共同确定的唯一标识 |
| observation_window_id | 参考观测窗口标识；多个预报版本不可重复计作独立天气事件 |
| forecast_spec_id | 预报请求定义 ID，可在 source_manifest.json 追溯 |
| station_id | SSOD 站号 CHI0000ZSHC；与 GHCN 城区站分开处理 |
| station_name | 来源中的站名 XIAOSHAN |
| station_lat / station_lon | 参考站纬度、经度，十进制度；不是用户门店位置 |
| window_start_utc / window_end_utc | 带 Z 的 UTC 起止时刻，窗口长度 24 小时 |
| observed_rain_mm | SSOD 参考日降水，毫米；可能低报，不是积水深度 |
| observation_measurement_code | D=四份 6 小时报告，F=两份 12 小时，G=一份 24 小时，24=24 份小时报告；当前样本全部为 G |
| reference_kind | ssod_derived_station，保留派生日汇总身份 |
| window_basis | nominal_utc_synoptic_day，保留名义日界身份 |
| forecast_model | ecmwf_ifs025，固定模型，不使用可变的 Best Match |
| forecast_kind | fixed_lead_composite；逐小时固定提前量合成序列 |
| run_init_utc | 无唯一初始化，当前为空；不可补一个虚构的运行时刻 |
| available_at_utc | 实际公开可用时刻未核实，当前为空 |
| availability_evidence | 当前为空；真实决策回放需要另行提供发布时间证据 |
| decision_time_utc | 当前为空；未定义历史实际决策时刻 |
| forecast_rain_mm | 24 个完整逐小时预报的累计降水，毫米 |
| forecast_temperature_mean_c | 对应 24 个预报有效时刻的平均温度，摄氏度；缺失时为空 |
| forecast_relative_humidity_mean_pct | 对应时刻平均相对湿度，百分数；缺失时为空 |
| experiment_kind | offline_fixed_lead；不能改写为运营预报成绩 |
| quality_status | passed；仅通过本项目规则 |
| audit_version | 解析和筛选规则版本 |
| obs_record_id | observations.csv 中的参考记录 ID |
| forecast_record_id | 预报来源 ID 加该配对窗口的起止时刻 |
| source_manifest_id | 对应 source_manifest.json 的 manifest_id |
| split | 原始主表统一为 unassigned；冻结实验切分另存 artifacts/sample_splits.csv |

Open-Meteo 的降水时间戳表示此前一小时累计量，因此窗口使用 $(t_0,t_1]$ 的 24 个时间戳，覆盖 $[t_0,t_1)$ 的小时区间。缺任一小时、非有限值或负降水就排除，不补零。[字段说明](https://open-meteo.com/en/docs)

预报请求为 30.2283°N、120.4317°E，接口返回格点约 30.25°N、120.5°E。格点与站点存在空间差异，不能据此生成门店级或校园级积水结论。精确返回坐标及海拔在来源清单中。

## 配套表

`observations.csv` 保留 SSOD 完整参考总量以及 GHCN 城区站的参考记录。GHCN 的 `window_basis=nominal_date_only`、`boundary_status=unverified`，表中的 UTC 日期只是检索占位，不是已证实的实际累计时段。它不进入主表。

`quarantined_records.csv` 保存排除的 ISD、SSOD 与预报配对窗口。`reason` 可包含多个用分号连接的原因；一条记录不是一个独立天气事件。其 4681 条数量不可用作缺测天数。

`source_manifest.json` 保存请求地址、来源 ID、下载时间、原始字节 SHA256、许可说明和本地快照路径。`data_quality.json` 同时保存样本 CSV 与来源清单的文件散列；应用会拒绝不一致的包。

## 覆盖分母

配置日历为 2024、2025 两个完整 UTC 年，共 731 日。完整 SSOD 候选为 670 日，缺少完整参考总量的日子为 61 日；其中可与完整预报配对的为 636 日，另外 34 个候选日缺少完整预报窗口。候选保留率为 $636/670$，完整日历覆盖率为 $636/731$，两者不可混用。5—7 月筛选只表示月份，不冒充官方逐年梅雨起止期。
