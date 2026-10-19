# 在线演示说明

## 发布状态

应用首页已通过线上文件与实际播放核验。74 秒完整版宣传片已准备发布，以下宣传片入口和文件在 GitHub 更新后再做线上核验：

- 应用首页：<https://kongbaigit.github.io/meiyu-ai4climate/>
- 宣传片：<https://kongbaigit.github.io/meiyu-ai4climate/promo/>
- 原生预览：`/promo/native.html`

## 当前宣传片

- Pages 文件：`site/media/promo-full-young-visionaries.mp4`
- 源文件：`media/latest/promo-full-young-visionaries.mp4`
- 源工程：`media/latest/source/`
- 时长：73.866666667 秒；1920×1080、30fps、2216 帧、10 个场景。
- H.264/AAC，单音轨、无配音。
- Young Visionaries — Eric Matyas；Soundimage International Public License。
- 署名：Music by Eric Matyas / www.soundimage.org。
- 来源：<https://soundimage.org/techno/>；许可：<https://soundimage.org/sample-page/>。
- 原曲裁切区间 17.313872945628–91.180539612295 秒，原速原调、无循环。
- SHA-256：`2b52e74cf2302196d46e128802613a280aa584a914dc416fdc727dd3b91d2d86`。

完整事实、检查范围和待办见 [74 秒宣传片发布说明](promo-full-release.md)。

## 应用行为

`site/index.html` 是当前搬货决策入口。页面打开时请求公开集合天气，保持打开时按小时检查；天气超过 3 小时、缺成员或缺小时，页面停止当前天气搬货结论。费用只在浏览器内计算，不上传到天气服务，关闭页面后不会留下后台任务。

天气自动更新与历史离线模型分开。当前天气使用通过来源、schema、新鲜度和集合成员身份检查的 Open-Meteo/ECMWF ensemble 快照；集合成员占比未经校准，不是货损概率。模型不在线重新训练；历史模型结果只用于离线研究说明，不替代官方天气预警。成本展示是用户输入的情景假设，不等同实测成本或真实货损。

## 构建与检查

在项目根目录运行 `python tools/build_pages.py`。构建结果应包括 `site/.nojekyll`、`site/media/promo-full-young-visionaries.mp4`、`site/promo/index.html` 和 `site/promo/native.html`，并核对成片 SHA-256 与站内相对链接。

发布前已完成原生导出、媒体技术、实际关键帧和播放器控件检查；线上文件加载、实际播放、移动端布局以及主观观看、听审待发布后完成。

历史阶段文件和旧发布记录不作为当前入口；需要追溯时从 Git 历史恢复。
