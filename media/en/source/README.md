# Meiyu Prepare: English film source

The English film is 87.066666667 seconds, 1920 by 1080, 30 fps and 2,612 frames. It contains ten scenes, existing instrumental music and no voiceover. The Chinese film remains unchanged in `media/latest/`.

The renderer uses the existing GSAP timeline and Three.js shop geometry. It draws the English interface directly on Canvas and exports through VideoFrame and WebCodecs. The web edition applies high-quality H.264 compression at CRF 18 to reduce download size. Screenshots are used only for quality checks and the poster.

## Edit and rebuild

Run these commands from the repository root. The full repository supplies shared vendors, the frozen evidence and original music in `media/latest/source/`.

```powershell
python media/en/source/tools/build_html.py
node media/latest/source/tools/export_video.cjs --html media/en/preview.html --out build/english-new.h264 --report build/english-new-export.json --bitrate 14000000
python media/en/source/tools/mux_video.py --video build/english-new.h264 --audio media/en/source/audio/music_master.flac --output build/english-new.mp4 --ffmpeg ffmpeg --delivery-crf 18
```

Create the `build` directory before export. Use new output names for revised films. Node.js with Playwright, a supported browser, Python and FFmpeg are required. The shared package lock is in `media/latest/source/`; run `npm ci` in that directory when setting up another machine. The existing browser helper merges the requested Edge feature flag with the other disabled features. Its effectiveness as a browser workaround has not been established.

- `film.js`: English composition and animation.
- `drawing_helpers.js`: Canvas drawing helpers.
- `storyboard.json`: scene boundaries, captions and quarter-beat mapping.
- `music_sync.json`: source excerpt, tempo, timing and licensing.
- `audio/music_master.flac`: lossless edited soundtrack.
- `audio/music_playback.mp3`: browser preview soundtrack.
- `../preview.html`: self-contained native preview with embedded scripts and audio.

The original track is shared at `media/latest/source/audio/original_music.mp3`. The English excerpt runs from 6.764338247872 to 93.831004914539 seconds. It preserves the track's speed and pitch and does not loop. `tools/build_audio.py` documents the two-pass loudness workflow and refuses to overwrite existing audio.

## Evidence and limits

Historical data, model parameters and the captured forecast are shared with the Chinese edition. The recorded ensemble snapshot was obtained on 19 October 2026. The 60% probability input and CNY 80/1,000/100 costs are hypothetical. Their expected-cost difference is a scenario calculation, not measured savings.

Technical checks cover encoding, decoding, timing, signal levels and selected rendered frames. They do not establish subjective listening approval or real merchant validation.

## Music and libraries

Young Visionaries

Music by Eric Matyas  
www.soundimage.org

Source: https://soundimage.org/techno/  
License: Soundimage International Public License  
License text: https://soundimage.org/sample-page/  
Attribution requirements: https://soundimage.org/attribution-info/

The edit is a continuous excerpt with loudness matching and short fades. Retain the artist, website, license and edit description when redistributing this project. GSAP and Three.js retain their respective license files under `media/latest/source/vendor/`.
