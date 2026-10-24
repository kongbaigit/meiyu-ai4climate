# 梅雨有数

[English documentation and materials](README.en.md)

面向杭州与宁波小商户的降雨情景与搬货成本计算原型 · AI for Climate

## 当前入口

- [在线应用](https://kongbaigit.github.io/meiyu-ai4climate/)：自动获取公开集合天气，填写成本假设后比较搬与不搬。
- [74秒完整宣传片](https://kongbaigit.github.io/meiyu-ai4climate/promo/)：现成配乐与动态文字，无配音；已上线并核验。
- 应用入口文件：`index.html`；成片：`media/latest/promo-full-young-visionaries.mp4`。
- 原生预览：`media/latest/preview.html`；可编辑源：`media/latest/source/`。

## 应用与更新

`index.html` 打开时请求公开天气；页面保持打开时按小时检查。天气超过 3 小时、缺成员或缺小时，页面停止当前天气搬货结论。费用只在浏览器内计算，不上传到天气服务。关闭页面后不会留下后台任务。

双击 `start.cmd` 启动搬货决策应用，默认端口 8532；`start.ps1` 启动完整研究工作台，默认端口 8513。首次运行需 Python 3.11 或更新版本，并安装对应 requirements 文件中的依赖。

应用使用真实获取时间标注天气快照。天气自动更新与历史离线模型分开；应用不在线重新训练模型，也不需要 API 密钥。

## 当前宣传片

- 时长：73.866666667 秒；1920×1080、30fps、2216 帧、10 个场景。
- 编码：H.264/AAC；单音轨、无配音。
- 配乐：Young Visionaries — Eric Matyas。
- 许可：Soundimage International Public License；署名为 `Music by Eric Matyas / www.soundimage.org`。
- 来源：<https://soundimage.org/techno/>；许可：<https://soundimage.org/sample-page/>。
- 原曲裁切区间：17.313872945628–91.180539612295 秒；原速原调、无循环。
- SHA-256：`2b52e74cf2302196d46e128802613a280aa584a914dc416fdc727dd3b91d2d86`。

已完成成片技术、线上文件摘要、实际播放与手机布局核验。团队完整观看与听审仍待完成。完整记录见 [74 秒宣传片发布说明](docs/promo-full-release.md)。

## 核心方法与边界

- 历史实验使用 636 个统一日窗口，事件阈值为参考日降水达到 25 毫米；训练、验证、测试分别为 276、120、240 个窗口。
- 概率模型是历史离线研究方法。最新天气页展示公开来源更新，不把历史模型说成线上预测，也不替代官方天气预警。
- 费用图表是用户输入的情景假设，不是实测人民币成本、真实货损或货损概率。
- 实时天气使用通过来源、schema、新鲜度和集合成员身份检查的 Open-Meteo/ECMWF ensemble 快照；集合成员占比未经校准，不是货损概率，也不混用历史模型结果。
- 预报窗口按小时语义 `(start,end]` 聚合；来源、快照、模型参数和评估结果保存在项目数据与报告目录。

## 运行与复现

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

完整研究复现、数据核查和测试命令见 `docs/` 中的研究说明与脚本帮助。运行前请保留数据、模型和报告的文件摘要。

## 最终目录

| 位置 | 内容 |
| --- | --- |
| `app.py` / `src` | 应用、数据管道、实验和参数复现代码 |
| `data` | CSV/Parquet、来源清单和公开数据快照 |
| `artifacts` / `reports` | 模型结果、评估、质量与运行检查 |
| `media/latest` | 当前宣传片、原生预览和源工程 |
| `tools/build_pages.py` | 从仓库素材生成 `site/`，用于发布 GitHub Pages |
| `docs` | 项目说明、AI 使用声明、比赛 PDF、字段和发布记录 |
| `tests` | 数据、日界、泄漏隔离、概率和公式检查 |

## 许可与状态

项目新增代码采用 MIT 许可；第三方数据、文档和音乐按各自来源条款使用。Soundimage 音乐遵循其 International Public License，不写成 Creative Commons 或等效许可。

当前主分支保留交付版；旧影片、过程提示词与重复材料已移除，历史版本可从 Git 历史追溯。线上核验记录见 [发布检查](docs/release-check.json)。
