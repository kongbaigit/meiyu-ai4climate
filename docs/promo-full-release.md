# 74 秒宣传片发布说明

## 状态

这是 2026 年 10 月 19 日选定的完整版宣传片发布记录。仓库文件和 GitHub Pages 文件待发布后再做线上核验；本页不把待发布状态写成已上线。

## 成片信息

- 文件：`media/latest/promo-full-young-visionaries.mp4`
- GitHub Pages 文件：`site/media/promo-full-young-visionaries.mp4`
- 页面：<https://kongbaigit.github.io/meiyu-ai4climate/promo/>
- 原生预览：`media/latest/preview.html`；发布页为 `/promo/native.html`
- 时长：73.866666667 秒
- 画面：1920×1080、30fps、2216 帧、10 个场景
- 编码：H.264 视频、AAC 音频；单音轨、无配音
- SHA-256：`2b52e74cf2302196d46e128802613a280aa584a914dc416fdc727dd3b91d2d86`

## 音乐来源

- 曲名：Young Visionaries
- 作者：Eric Matyas
- 许可：Soundimage International Public License
- 署名：Music by Eric Matyas / www.soundimage.org
- 来源页：<https://soundimage.org/techno/>
- 许可页：<https://soundimage.org/sample-page/>
- 原曲裁切：17.313872945628–91.180539612295 秒
- 处理：原速原调、连续裁切、首尾淡变，无循环

这里使用 Soundimage 的许可名称和来源，不将其写成 Creative Commons 或等效许可。

## 已完成检查

- 原生 WebCodecs 导出：通过。
- MP4 媒体技术检查：通过，包括完整解码、帧数、时长、H.264/AAC 轨道、AAC 响度与 true peak、头尾音频非零和 Soundimage 标签。
- 实际关键帧抽查：通过，覆盖 10 个场景中段、场景边界、集合拍点、结果状态和片尾署名。
- 播放器控件检查：通过，覆盖播放、暂停、重播、跳转、画布时间同步、单音轨和无配音控件。

这些检查不包含主观观看、主观听审或线上部署核验。发布后需要再次核对 Pages 文件、页面加载、实际播放和移动端布局，再更新发布状态。

## 相关源文件

当前源工程位于 `media/latest/source/`。历史阶段素材和旧检查记录不作为本版本的来源或验收依据，需要追溯时从 Git 历史恢复。
