# 在线演示说明

## 发布状态

当前正在准备 2026 年 10 月 19 日的纯配乐动态文字版。公开部署状态由发布前最终检查确认，本文不把计划地址当作新版本已核验结果。计划地址如下：

- 应用首页：<https://kongbaigit.github.io/meiyu-ai4climate/>
- 60 秒宣传片：<https://kongbaigit.github.io/meiyu-ai4climate/promo/>

新成片的最终大小和 SHA-256 会在编码完成后写入 `tools/build_pages.py`，并记录在 [纯配乐版发布检查](music-only-release-check.json)。旧版影片检查记录不用于证明新成片。

## 页面内容

`site/index.html` 是项目当前的搬货决策入口，`site/demo.html` 是按历史日期保留的旧实验演示。`site/promo/` 是独立的 60 秒影片页，包含 12 段动态文字和 7 个场景，只使用原创器乐，不含配音。影片画面已经包含文字，播放器提供可选文字轨，不默认打开；页面还提供返回应用、历史演示和 `native.html` 原生动画预览链接。

静态媒体使用以下名称，避免浏览器继续复用旧版人声文件：

- `site/media/promo60-music.mp4`
- `site/media/promo60-music-cover.png`
- `site/media/promo60-music.vtt`

可编辑源码、成片、原创配乐、MIDI、字幕、封面和原生预览保留在仓库的 `media/latest/`。完整源码不复制到 Pages 静态目录。

## 在线前端行为

应用页面保持打开时每小时检查一次天气。更新失败时，如果已有缓存仍在 3 小时内且窗口完整，页面继续使用缓存计算；缓存超过 3 小时、缺成员或缺小时、所选窗口不可用时，页面暂停当前建议。页面关闭后不会留下 Python 后台；完整研究工作台仍在本机通过 `start.ps1` 启动，默认端口为 8513。新版搬货决策服务通过 `start.cmd` 启动，默认端口为 8532。

历史实验和旧影片按各自日期保留归档。旧版宣传片的配音与检查记录不代表本次纯配乐版本，当前版本只描述原创器乐和动态文字。

## 构建和检查

在项目根目录运行 `python tools/build_pages.py`。脚本只使用标准库，会复制项目入口和历史演示，转换动态文字 SRT 为 WebVTT，并检查最终成片的大小和 SHA-256。构建结果包括 `site/.nojekyll`、新命名的媒体文件、`site/promo/index.html` 和 `site/promo/native.html`。

发布前检查包括入口文件字节一致、成片摘要一致、字幕时间格式、原生预览链接和站内相对链接。完整人工看完和听完宣传片仍需单独验收，技术检查不能替代这项验收。
