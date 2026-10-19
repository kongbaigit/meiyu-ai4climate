# 原生影片的可编辑源

修改app.js中的场景、镜头和文字，或修改narration.json中的旁白。音乐的音符、和弦和章节编排在compose_audio.py与score_manifest.json中。player.html负责播放控制。没有应用截图或外部视频作为画面素材。

直接观看使用上一级demo.html。重建需Python（NumPy、SciPy、pandas和本项目依赖）、FFmpeg；导出另需Node.js、Playwright和Microsoft Edge。Windows本地旁白要求已安装Microsoft Huihui Desktop。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File synthesize.ps1 -Rate 1
python compose_audio.py
python build_inputs.py
python build_html.py
python -m http.server 8530 --bind 127.0.0.1
```

在另一个终端执行node export_native.cjs，再执行python mux_video.py。结果为native_raw.h264和demo_native_master.mp4。FFmpeg需在PATH内，或设置MEIYU_FFMPEG为它的绝对路径。Playwright优先使用本目录可解析的安装，当前Codex电脑也支持已存在的运行时；换电脑需自行安装Node、Playwright与Edge。浏览器的AutofillAiWalletPrivatePasses参数只保证合并，未验证其规避效果。

WebCodecs直接将Canvas封装为VideoFrame并编码。视频画面不经过截图、PNG序列或屏幕录制。QA用的静态检查图没有进入成片管线。HTML声音由两路原始音轨播放，成片另有自动音量控制。

以用户提供的HTML分析镜头与排版，原场景、文字和实现未复制。额外风格参考为https://www.avilevi.co.il/showreel/index.html与https://miaai-lab.github.io/GPT-6-Astra-100-HTML-Files/。Three.js为0.160.1，MIT许可及官方包来源摘要在vendor中。

score.mid保留原配乐的旋律与和声事件，可导入支持MIDI的编曲软件。自制音色、噪声转场和混音以compose_audio.py与实际音轨为准；write_midi.py可重建MIDI。若单独移动源目录，可用MEIYU_PROJECT_ROOT指定完整工程位置。
