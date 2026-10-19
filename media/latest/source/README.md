# 60秒宣传片可编辑工程

本片为1920×1080、30fps、60秒，7个场景。旁白7段共32.928秒，实际逐句字幕9条。剩余时间留给操作与阅读结果。

## 修改与重建

修改画面用film60.js和drawing_helpers.js，修改配音文本用narration.json，修改音乐用tools/compose_audio.py。vendor/decision_cost.js直接复用本版应用的计算模块，确保画面中的成本变化按真实算式计算。

Python 3.12安装requirements.lock.txt，Node安装依赖使用npm ci --ignore-scripts。另需安装FFmpeg并加入PATH，或设置PROMO_FFMPEG为其绝对路径。运行顺序如下：

    python tools/synthesize.py --root .
    python tools/build_inputs.py
    python tools/compose_audio.py
    python tools/build_html.py
    node tools/export_video.cjs --html ../预览.html --out ../新导出.h264 --report ../新导出.json --duration 60
    python tools/mux_video.py --video ../新导出.h264 --output ../新成片.mp4 --duration 60

没有修改旁白时，语音脚本可按配置和文件摘要复用已生成MP3；修改后需要连接语音服务。WAV和原始H264是可重建中间文件，不进入源工程包。运行compose_audio会重建master_mix.wav供合成MP4使用。

## 来源与边界

沿用GSAP 3.15.0、Canvas到WebCodecs的已验证管线。GSAP暂停时间线实际控制界面进入、费用变化与状态反馈，许可副本在vendor。drawing_helpers.js复用上一版本的原生几何商铺、文字、指针和形状函数。本片没有用产品截图、录屏或外部视频作为输入。

天气镜头使用2026年10月19日北京时间13:48获取的真实响应，保留在evidence。51成员包括无编号precipitation控制成员及50个编号成员。它是未经校准的集合情景估计，不是货损概率。60%和80/600/1000/100元均为明确标注的算账示例。应用本地版本源码随总交付包提供，片尾未冒称新版已发布。

新语音为edge-tts 7.3.1的zh-CN-XiaoxiaoNeural，+5%。原创配乐《雨前的刻度·60秒有据版》为96 BPM、4/4、24小节，234个事件、4条MIDI轨，没有第三方歌曲或采样。逐句边界、请求、摘要及音乐事件均随包保留。音频元数据内的绝对路径是生成时记录，重建脚本使用当前工程的相对路径。

Windows系统字体未分发，更换系统后须检查排版。完整人工听审仍待团队确认。技术检测不能替代读音和音乐效果的听审。
