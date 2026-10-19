# 数据与 AI 使用说明

本项目使用公开资料和本地统计学习代码，当前用途是降雨参考事件的离线方法实验与准备成本解释。没有采购设备、接入校方后勤数据或收集个人信息。

## 数据来源

| 来源 | 本项目用途 | 主要限制 |
| --- | --- | --- |
| [NOAA SSODv2](https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly/synoptic-summary-of-the-day) | 萧山机场 2024、2025 年名义 UTC 日参考降水 | 日汇总可能低报；完整测量码不等于高精度真值 |
| [NOAA SSOD 格式文档](https://www.ncei.noaa.gov/oa/synoptic-summary-of-the-day/v2/doc/ssodv2_DOCUMENTATION.pdf) | 核对日界、单位和报告码 | 官方文档中的下载模板与当前目录存在差异，使用实际 csv 子目录 |
| [NOAA ISD 格式文档](https://noaaisd.blob.core.windows.net/noaa-isd/pub/data/noaa/isd-format-document.pdf) | 核对 AA1—AA4；记录排除原因 | 当前文件没有满足保守规则的完整 24 小时真值，不参与标签构建 |
| [GHCN-Daily](https://www.ncei.noaa.gov/pub/data/ghcn/daily/readme.txt) | 杭州城区站交叉参考 | 异站且逐条日界未核实，不与机场记录合并 |
| [Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api) | ECMWF IFS 0.25° 固定提前量一日序列 | 日聚合含不同初始化的有效时刻，未证明某单一决策时刻全部可用 |
| [Open-Meteo Forecast API](https://open-meteo.com/en/docs) | 用户点击后获取杭州或宁波的ECMWF IFS 0.25°最新公开预报 | 网格数值预报；不直接套用冻结概率模型，不视为实测或唯一初始化预报回放 |
| [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) | ERA5本年度日降水与温度背景，保留7天延迟缓冲 | 再分析背景不是站点实测，不补入SSOD标签或主实验 |
| 杭州、浙江官方公开资料 | 问题背景和准备清单依据 | 没有本地商户访谈、意愿或付费验证；适配建议不冒充官方商户指令 |

原始文件的完整地址、字节摘要、获取时间和返回坐标见 `data/source_manifest.json`。地方资料的具体链接和适用边界见 `docs/action_sources.md`。

新增2026年同站检查独立保存于 `external/hangzhou_2026`，使用相同来源和处理口径，没有并入主636日样本。下载前先保存了本地内部协议及摘要，它不等于第三方公开预注册。2026年1—9月273个配置日只有85个完整配对日、1个事件，完整参考仅覆盖1—3月；4—9月缺少完整参考，不能声称已验证2026梅雨表现。指标、逐月覆盖、来源摘要和保留原模型的证据见 `reports/temporal_validation.json`。

## 模型和工具

在线天气和冻结实验分别保存。Python在线缓存位于`runtime/weather`，含原始响应、内容摘要、获取时刻和按来源核查的完整度；文件按内容保存，最后原子替换索引。HTML在浏览器本地保存缓存。新鲜度按获取时刻计算，预报超过3小时、背景与站点参考超过24小时会标为过期。获取时刻不等于天气模型初始化或官方发布时间。

打开页面不自动请求天气，只有显式点击刷新才连接固定官方接口。超时、限流、单位不符、错站、重复时间或坏响应不会替换有效缓存。缺少降水小时的24小时窗口不计算完整累计，也不补零。交付附带一份真实获取、可重新核对原始响应的天气快照，按其自身时间显示；它不会在离线打开时伪装成刚刚更新。

AI 的拟定任务是将数值预报输入映射成达到研究降水阈值的概率，并与简单方法在相同测试日上比较。模型和模型选择通过冻结配置离线执行，实际版本与结果以 `reports/evaluation.json` 和 `reports/experiment_run.json` 为准。页面不会临时训练、挑选测试阈值或生成没有来源的预测。

Codex 协助检索公开入口、编写解析、测试、应用和材料草稿。代码使用 Python、pandas、NumPy、scikit-learn、Streamlit 和 Plotly；当前阶段不需要 OpenAI API 密钥，也不把语言模型的文字判断当作降雨数据。人工团队仍需核对正式提交信息、用户假设和最终论述。

当前演示视频长2分49秒。三维几何、粒子、文字与图表由HTML中的程序逐帧绘制，画面通过WebCodecs直接编码，未使用截图、录屏或外部图片视频作为输入。中文旁白由Windows本地Microsoft Huihui Desktop合成。配乐《雨前的刻度》的旋律、和弦、节拍与音色由代码合成，源代码和音符记录随工程提供，没有使用第三方音乐素材。Codex协助分镜、动画、音乐程序和导出；视频仍是材料工作稿，三维商铺与地点均为示意，最终版本由团队确认。Three.js采用MIT许可，许可与版本来源随源提供。

## 使用和开放范围

Open-Meteo 数据按其 [CC BY 4.0 与使用条款](https://open-meteo.com/en/terms) 署名，免费接口用于本项目的非商业研究；不得删除原始数据来源。NOAA 文件按来源说明保留机构与上游信息，不假设所有上游数据均由项目团队拥有版权。代码许可不覆盖第三方数据、文档或库。

本项目没有证明降低真实灾损、增加经营收益或减少碳排放。气候价值定位于适应与准备：能否让使用者理解不确定性、完成适合自己的准备，需要后续试点验证。当前输出不作为官方天气预警、应急指令或店铺积水预测。
