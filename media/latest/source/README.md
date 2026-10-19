# 纯配乐动态文字宣传片

本片为1920×1080、30fps、60秒，7个场景、12段动态文字。声音只有原创器乐配乐，没有配音、人声轨或语音生成步骤。

## 修改与重建

画面修改`film60.js`和`drawing_helpers.js`，文字及时段修改`storyboard.json`，音乐修改`tools/compose_audio.py`。`vendor/decision_cost.js`复用应用的计算模块，金额变化使用同一算式。

Python 3.12安装`requirements.lock.txt`，Node依赖运行`npm ci --ignore-scripts`。另需FFmpeg，可加入PATH或设置`PROMO_FFMPEG`为其绝对路径。按以下顺序重建：

    python tools/build_inputs.py
    python tools/compose_audio.py
    python tools/build_html.py
    node tools/export_video.cjs --html ../预览.html --out ../新导出.h264 --report ../新导出.json --duration 60
    python tools/mux_video.py --video ../新导出.h264 --output ../新成片.mp4 --duration 60

音乐合成在本机运行，不连接语音服务。`master_mix.wav`与H264为可重建的中间文件，不进入公开源工程包。

## 来源与边界

沿用GSAP 3.15.0、Canvas到VideoFrame/WebCodecs的已验证管线。GSAP时间线实际控制场景、文字分段进入、强调线及成本变化；许可副本在`vendor`。本片没有使用产品截图、录屏或外部视频作为输入。

天气段保留2026年10月19日北京时间13:48取得的真实响应快照。51成员包含控制成员和50个编号成员；成员占比未经校准，不是货损概率。60%及80、600、1000、100元均为明确标注的算账假设，未声称已经实现收益。

配乐沿用本项目自己的程序合成音色、96 BPM、4/4、24小节。移除配音混合和让位压低段，音乐事件与4轨MIDI在`audio`。未使用第三方歌曲或人声采样，最后3秒淡出。

Windows系统字体未分发，更换系统后须检查排版。技术检测不能替代完整的人工观看与音乐听审。
