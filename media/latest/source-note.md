# 60秒影片来源

影片使用本次搬货决策版的实际成本模块。60%是明确标注的假设情景，不搬预计600元；搬货成本80元、搬后预计损失100元时，搬的预计总成本为140元。搬货成本提高至600元时，搬的预计总成本为660元，因而切换为暂不搬。这些是情景估算，没有声称已经省下钱。

天气段保留2026年10月19日北京时间13:48获取的真实Open-Meteo响应。原始响应、获取时刻、请求和摘要在source/evidence。ECMWF IFS 0.25°共51成员，包含无编号precipitation控制成员和member01至50。按照同一24小时窗口计算达到25毫米的成员占比；它未经本地实况校准，不是货损概率。

来源：[Open-Meteo Ensemble API](https://open-meteo.com/en/docs/ensemble-api)、[成员0的官方说明](https://github.com/open-meteo/open-meteo/discussions/366)、[ECMWF成员数定义](https://github.com/open-meteo/open-meteo/blob/main/Sources/App/Ecmwf/EcmwfDomain.swift)。Open-Meteo依其[条款](https://open-meteo.com/en/terms)保留CC BY 4.0署名。

实际使用GSAP 3.15.0暂停时间线，通过master.totalTime控制动画状态。vendor保留原发行文件与GSAP Standard License网页，摘要与上版核对的固定版本一致。Canvas直接交给VideoFrame和WebCodecs编码，最终1800帧；FFmpeg复制视频流并合成AAC，没有截图、录屏或外部视频输入。原生几何商铺、绘制函数与编码管线从上一版保留，本版重新安排7场景和成本计算。没有使用Three.js、385712或Codrops。

旁白7段实际新生成为zh-CN-XiaoxiaoNeural，edge-tts 7.3.1，+5%。总长32.928秒，9条实际逐句字幕。配乐《雨前的刻度·60秒有据版》采用本项目自己的合成音色，重新编排为96 BPM、4/4、24小节，234个事件，4条MIDI轨，没有第三方歌曲或采样。

Windows系统字体没有随包分发，更换系统后需要检查排版。语音服务使用条件仍适用于合成语音，工具本身的许可证不能替代服务条款。完整人工听审未检查，技术检测不代表读音或音乐效果通过。

影片内界面为原生图形重绘，保留真实计算逻辑，并不是逐像素录制产品。播放影片不会联网；应用页面会按其运行方式自动获取天气。新版代码和影片在制作时按本地交付保存；当前公开发布状态以项目主 README 的“在线演示”说明为准。
