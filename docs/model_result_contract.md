# 模型结果接口

数据包是模型输入，应用不负责训练或决定行动阈值。队友的新预测应另存到独立版本目录，例如 research/模型名_日期/predictions.csv，再通过页面上传 CSV。artifacts/predictions.csv 是冻结主实验文件，不得用新预测覆盖；该临时研究目录默认不进入工程包，需要交付新实验时另立版本与清单。

## 必需字段

| 字段 | 要求 |
| --- | --- |
| sample_id | 必须存在于当前 samples.csv |
| method | 方法名称，不能为空 |
| probability | 0 到 1 之间的有限数值，不能缺失 |
| model_version | 可追溯的模型版本，不能为空 |
| dataset_version | 必须与 reports/data_quality.json 完全一致 |
| experiment_kind | 必须与该样本的实验类型一致 |
| event_threshold_mm | 本文件统一的正降水阈值，明确预测目标为 24 小时累计降水达到此值 |

同一 sample_id、method、model_version 组合必须唯一。可以提交同一方法在部分样本上的结果，但材料应另外报告其覆盖范围。数据包中的 split 初始为 unassigned；实验方需在训练前固定时间切分，并自行保留模型与实验配置。

协议校验通过只表示文件能够正确关联，不代表模型有效、概率可信或已经通过独立评测。应用不会根据上传文件自行生成准确率或灾损改善数字。

离线固定提前量实验、hindcast 与真实决策回放必须保持区分。当前数据包未核实发布时间时，模型结果不得改写成实际提前若干小时的运营成绩。
