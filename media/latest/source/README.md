# 梅雨有数：完整节奏版

配乐为 Young Visionaries，作者 Eric Matyas。全片约74秒，1920×1080、30帧，只使用配乐和动态文字。

本版保留完整10个场景。原来的168拍画面重排为112拍；转场、表格行、矩阵列和金额出现按所选音乐的节拍及细分点安排。音乐保留原速原调，截取原曲17.313873至91.180540秒，做响度匹配及首尾淡化。

打开成片MP4即可观看。`media/latest/preview.html` 已包含脚本和配乐；本机需提供常见中文字体。视频以HTML/Canvas原生绘制并逐帧编码。

## 继续编辑

- `source/film.js`：画面、文字与动作。
- `source/storyboard.json`：场景时长、实际拍点与原叙事拍点映射。
- `source/music_sync.json`：所选音乐、源起点、时长和许可。
- `source/audio/`：本项目使用的原曲、处理后母带和预览音频。
- `source/kinetic_evidence.json`：影片使用的数据快照。片中的60%及金额为明确标注的算账假设，天气画面保留实际获取时间。

导出需要Node.js、Python、FFmpeg和Edge。Node依赖已固定在source/package-lock.json；先在source目录执行npm ci。动画库随工程提供。

在仓库的 `media/latest` 目录构建预览：

```powershell
python source/tools/build_html.py
```

导出到新的文件名，保留旧版本：

```powershell
node source/tools/export_video.cjs --html preview.html --out 新版.h264 --report 新版导出.json --bitrate 14000000
python source/tools/mux_video.py --video 新版.h264 --audio source/audio/music_master.flac --output 新版.mp4 --ffmpeg ffmpeg
```

若改变配乐裁切或总时长，需同步调整音乐配置、场景时间和母带；本包带有本次裁切、响度与节奏拟合记录。Edge启动参数沿用既有合并逻辑，不能据此声称已经验证规避参数的效果。

## 配乐署名

Young Visionaries

Music by Eric Matyas  
www.soundimage.org

来源：https://soundimage.org/techno/  
许可：Soundimage International Public License  
许可原文：https://soundimage.org/sample-page/  
署名要求：https://soundimage.org/attribution-info/

本片只对原曲连续截取、调整响度及首尾淡化。发布或再次剪辑时，请保留作者、网站、许可链接和修改说明。音乐素材随本视频源工程提供，适用其自身许可。

检查记录区分运行测试、媒体技术检查、实际画面检查与主观听音；没有把数值节拍拟合写成人工听审通过。
