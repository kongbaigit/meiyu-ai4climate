"""为梅雨有数 60 秒宣传片生成纯器乐程序配乐。"""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import wave

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
SR = 48_000
BPM = 96
BEAT = 60.0 / BPM
BAR_BEATS = 4
BAR_SECONDS = BAR_BEATS * BEAT
DURATION = 60.0
BARS = int(round(DURATION / BAR_SECONDS))
SEED = 20261019
MASTER_TARGET_LUFS = -16.0
MASTER_TARGET_TP = -1.5
MASTER_TARGET_LRA = 9.0
DEFAULT_FFMPEG = Path(
    r"C:\Users\kongbai\Documents\Codex\2026-10-12\zong\work\meiyu\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
)

MIDI_TRACKS = (
    {"name": "Warm pad", "channel": 0, "program": 89},
    {"name": "Soft bass", "channel": 1, "program": 38},
    {"name": "Glass motif", "channel": 2, "program": 10},
    {"name": "Light percussion", "channel": 9, "program": None},
)
TRACK_BY_INSTRUMENT = {
    "pad": 0,
    "bass": 1,
    "glass_motif": 2,
    "result_hit": 2,
    "cost_change": 2,
    "closing_resolution": 2,
    "kick": 3,
    "brush": 3,
    "transition_air": 3,
    "action_click": 3,
}


def ffmpeg_path(value: str | os.PathLike[str] | None = None) -> str:
    """保留给 mux_video.py 使用的 FFmpeg 路径解析接口。"""

    candidate = value or os.environ.get("PROMO_FFMPEG")
    if candidate:
        path = Path(candidate)
        if path.is_file():
            return str(path)
        resolved = shutil.which(str(candidate))
        if resolved:
            return resolved
    if DEFAULT_FFMPEG.is_file():
        return str(DEFAULT_FFMPEG)
    resolved = shutil.which("ffmpeg")
    if resolved:
        return resolved
    raise RuntimeError("请安装 FFmpeg，或通过 --ffmpeg 指定可执行文件。")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_wave(path: Path, audio: np.ndarray) -> None:
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim == 1:
        audio = np.repeat(audio[:, None], 2, axis=1)
    if audio.shape != (round(DURATION * SR), 2) or not np.isfinite(audio).all():
        raise ValueError(f"音轨格式错误：{path}")
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak >= 1.0:
        raise ValueError(f"音轨削波（peak={peak:.6f}）：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SR)
        handle.writeframes(np.round(audio * 32767).astype("<i2").tobytes())


def run_checked(command: list[str], *, label: str) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, capture_output=True, check=False)
    if result.returncode:
        details = result.stderr.decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"{label}失败：{details}")
    return result


def encode_mp3(ffmpeg: str, source: Path, target: Path, bitrate: int) -> None:
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map_metadata",
            "-1",
            "-ac",
            "2",
            "-ar",
            str(SR),
            "-c:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate}k",
            str(target),
        ],
        label=f"编码 {target.name}",
    )


def vlq(value: int) -> bytes:
    value = max(0, int(value))
    output = [value & 127]
    while value >> 7:
        value >>= 7
        output.insert(0, 128 | (value & 127))
    return bytes(output)


def write_midi(path: Path, events: list[dict[str, object]]) -> None:
    """把程序音符写成 480 PPQ、96 BPM、4/4 的四轨 MIDI。"""

    tracks: list[bytes] = []
    for track_index, track in enumerate(MIDI_TRACKS):
        name = str(track["name"])
        rows: list[tuple[int, bytes]] = [
            (0, b"\xff\x03" + vlq(len(name)) + name.encode("ascii"))
        ]
        channel = int(track["channel"])
        if track_index == 0:
            tempo = round(60_000_000 / BPM)
            rows.extend(
                [
                    (0, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
                    (0, b"\xff\x58\x04\x04\x02\x18\x08"),
                ]
            )
        program = track["program"]
        if program is not None:
            rows.append((0, bytes([0xC0 | channel, int(program)])))
        for event in events:
            if event.get("track") != track_index or event.get("midi") is None:
                continue
            at = float(event["at"])
            duration = float(event["duration"])
            note = int(event["midi"])
            start_tick = round(max(0.0, at) / BEAT * 480)
            end_tick = max(start_tick + 1, round(min(DURATION, at + duration) / BEAT * 480))
            velocity = max(18, min(112, round(float(event["gain"]) * 1300)))
            rows.append((start_tick, bytes([0x90 | channel, note, velocity])))
            rows.append((end_tick, bytes([0x80 | channel, note, 0])))
        rows.sort(key=lambda item: (item[0], 0 if item[1][0] & 0xF0 == 0x80 else 1))
        body = bytearray()
        previous_tick = 0
        for tick, message in rows:
            body.extend(vlq(tick - previous_tick))
            body.extend(message)
            previous_tick = tick
        body.extend(b"\x00\xff\x2f\x00")
        tracks.append(b"MTrk" + struct.pack(">I", len(body)) + body)
    path.write_bytes(
        b"MThd"
        + struct.pack(">IHHH", 6, 1, len(tracks), 480)
        + b"".join(tracks)
    )


def tone(note: int, duration: float, kind: str) -> np.ndarray:
    count = max(1, round(duration * SR))
    t = np.arange(count, dtype=np.float32) / SR
    frequency = 440.0 * 2 ** ((note - 69) / 12)
    if kind == "pad":
        raw = np.sin(2 * np.pi * frequency * t + 0.025 * np.sin(2 * np.pi * 0.13 * t))
        raw += 0.19 * np.sin(2 * np.pi * frequency * 2 * t + 0.03)
        raw += 0.06 * np.sin(2 * np.pi * frequency * 3 * t)
        envelope = np.clip(t / 0.45, 0, 1) * np.clip((duration - t) / 0.75, 0, 1)
    elif kind == "bass":
        raw = np.sin(2 * np.pi * frequency * t) + 0.15 * np.sin(2 * np.pi * frequency * 2 * t)
        envelope = (1 - np.exp(-t * 35)) * np.exp(-t * 3.8) * np.clip((duration - t) / 0.12, 0, 1)
    else:
        raw = np.zeros_like(t)
        for harmonic in range(1, 6):
            raw += np.sin(2 * np.pi * frequency * harmonic * t + 0.02 * harmonic) * np.exp(
                -t * (1.6 + 0.6 * harmonic)
            ) / harmonic**1.7
        envelope = (1 - np.exp(-t * 600)) * np.clip((duration - t) / 0.18, 0, 1)
    return np.asarray(raw * envelope, dtype=np.float32)


def burst(rng: np.random.Generator, duration: float, *, lowpass: int = 1) -> np.ndarray:
    count = max(1, round(duration * SR))
    noise = rng.standard_normal(count).astype(np.float32)
    if lowpass > 1:
        noise = np.convolve(noise, np.ones(lowpass, dtype=np.float32) / lowpass, mode="same")
    t = np.arange(count, dtype=np.float32) / SR
    return noise * np.exp(-t * 110)


def marker_click(rng: np.random.Generator, frequency: float = 880.0) -> np.ndarray:
    count = round(0.075 * SR)
    t = np.arange(count, dtype=np.float32) / SR
    return (
        np.sin(2 * np.pi * frequency * t) * np.exp(-t * 95)
        + 0.23 * rng.standard_normal(count).astype(np.float32) * np.exp(-t * 180)
    )


def read_storyboard(root: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    storyboard = json.loads((root / "storyboard.json").read_text(encoding="utf-8"))
    scenes = storyboard.get("scenes")
    if storyboard.get("audio_mode") != "instrumental_only":
        raise ValueError("storyboard.json 必须声明 audio_mode=instrumental_only")
    if not isinstance(scenes, list) or len(scenes) != 7:
        raise ValueError("storyboard.json 应有 7 个场景")
    expected = (
        ("opening", 0, 6),
        ("live", 6, 16),
        ("inputs", 16, 28),
        ("move", 28, 38),
        ("keep", 38, 47),
        ("actions", 47, 55),
        ("closing", 55, 60),
    )
    actual = tuple(
        (str(scene["id"]), float(scene["start"]), float(scene["end"]))
        for scene in scenes
    )
    if actual != expected:
        raise ValueError(f"storyboard 时间线不匹配：{actual}")
    if float(scenes[-1]["end"]) != DURATION:
        raise ValueError("storyboard 场景未覆盖到 60 秒")
    return storyboard, scenes


def loudnorm_master(ffmpeg: str, source: Path, target: Path) -> dict[str, float]:
    """两遍 loudnorm 生成 -16 LUFS、-1.5 dBTP 目标母带。"""

    first = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(source),
            "-af",
            f"loudnorm=I={MASTER_TARGET_LUFS}:TP={MASTER_TARGET_TP}:LRA={MASTER_TARGET_LRA}:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if first.returncode:
        raise RuntimeError(first.stderr.decode("utf-8", errors="replace")[-4000:])
    stderr = first.stderr.decode("utf-8", errors="replace")
    matches = re.findall(r"\{\s*\"input_i\".*?\}", stderr, flags=re.DOTALL)
    if not matches:
        raise RuntimeError("loudnorm 第一遍没有返回测量 JSON。")
    measured = json.loads(matches[-1])
    fields = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    if any(field not in measured for field in fields):
        raise RuntimeError(f"loudnorm 测量字段不完整：{measured}")
    filter_value = (
        f"loudnorm=I={MASTER_TARGET_LUFS}:TP={MASTER_TARGET_TP}:LRA={MASTER_TARGET_LRA}:"
        f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
        f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
        f"offset={measured['target_offset']}:linear=true:print_format=summary"
    )
    run_checked(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(source),
            "-af",
            filter_value,
            "-ac",
            "2",
            "-ar",
            str(SR),
            "-map_metadata",
            "-1",
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        label=f"生成 {target.name}",
    )
    return {field: float(measured[field]) for field in fields}


def inspect_loudness(ffmpeg: str, path: Path) -> dict[str, float | None]:
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true:framelog=verbose",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace")[-4000:])
    text = result.stderr.decode("utf-8", errors="replace")
    loudness = re.findall(r"\bI:\s*(-?\d+(?:\.\d+)?)\s+LUFS", text)
    peaks = re.findall(r"(?:Peak|True peak):\s*(-?\d+(?:\.\d+)?)\s+dB(?:TP|FS)", text)
    return {
        "integrated_lufs": float(loudness[-1]) if loudness else None,
        "true_peak_dbtp": float(peaks[-1]) if peaks else None,
    }


def output_info(root: Path, path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 60 秒纯器乐宣传片配乐")
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    ffmpeg = ffmpeg_path(args.ffmpeg)
    storyboard, scenes = read_storyboard(ROOT)
    if BARS * BAR_SECONDS != DURATION:
        raise AssertionError("96 BPM / 4/4 未形成正好 24 小节和 60 秒")

    out = ROOT / "audio"
    out.mkdir(parents=True, exist_ok=True)
    count = round(DURATION * SR)
    score = np.zeros((count, 2), dtype=np.float32)
    rng = np.random.default_rng(SEED)
    events: list[dict[str, object]] = []

    def add(
        signal: np.ndarray,
        at: float,
        gain: float,
        pan: float = 0.0,
        instrument: str = "",
        midi: int | None = None,
    ) -> None:
        signal = np.asarray(signal, dtype=np.float32)
        start = round(at * SR)
        if start < 0:
            signal = signal[-start:]
            start = 0
        end = min(count, start + len(signal))
        if end <= start or not len(signal):
            return
        signal = signal[: end - start] * float(gain)
        pan = max(-1.0, min(1.0, float(pan)))
        score[start:end, 0] += signal * math.sqrt((1 - pan) / 2)
        score[start:end, 1] += signal * math.sqrt((1 + pan) / 2)
        events.append(
            {
                "at": round(max(0.0, at), 6),
                "duration": round(len(signal) / SR, 6),
                "instrument": instrument,
                "track": TRACK_BY_INSTRUMENT[instrument],
                "midi": midi,
                "gain": float(gain),
                "pan": round(pan, 4),
            }
        )

    def scene_at(moment: float) -> str:
        for scene in scenes:
            if float(scene["start"]) <= moment < float(scene["end"]):
                return str(scene["id"])
        return str(scenes[-1]["id"])

    chords = (
        (50, 57, 62, 65),
        (46, 53, 58, 62),
        (48, 55, 60, 64),
        (43, 50, 55, 62),
    )
    melody = (74, 77, 76, 72, 69, 72, 74, 77)

    for bar in range(BARS):
        at = bar * BAR_SECONDS
        scene_id = scene_at(at)
        chord = chords[(bar // 2) % len(chords)]
        scene_gain = {
            "opening": 0.020,
            "live": 0.026,
            "inputs": 0.027,
            "move": 0.031,
            "keep": 0.027,
            "actions": 0.022,
            "closing": 0.025,
        }[scene_id]
        for index, note in enumerate(chord):
            if bar % 2 == 0 or scene_id in {"move", "closing"}:
                add(
                    tone(note + 12, BAR_SECONDS * 2.05, "pad"),
                    at,
                    scene_gain,
                    (index - 1.5) * 0.30,
                    "pad",
                    note + 12,
                )

        if bar >= 2:
            add(
                tone(chord[0], 0.68, "bass"),
                at,
                0.070 if scene_id == "move" else 0.060,
                0,
                "bass",
                chord[0],
            )
            if bar % 2 == 1:
                add(tone(chord[1], 0.48, "bass"), at + 2 * BEAT, 0.045, 0, "bass", chord[1])
            for beat in (0, 2):
                length = round(0.22 * SR)
                time = np.arange(length, dtype=np.float32) / SR
                kick = np.sin(2 * np.pi * (45 * time + 2.3 * (1 - np.exp(-time * 27))))
                kick *= np.exp(-time * 27)
                add(kick.astype(np.float32), at + BEAT * beat, 0.047, 0, "kick", 36)
            for beat in (1, 3):
                add(
                    burst(rng, 0.055, lowpass=13),
                    at + BEAT * beat,
                    0.009,
                    (-1 if beat == 1 else 1) * 0.23,
                    "brush",
                    42,
                )

        if bar % 2 == 0 and scene_id in {"live", "inputs", "move", "keep", "actions"}:
            for step, beat in enumerate((0, 0.75, 1.5, 2.75)):
                note = melody[(bar * 2 + step) % len(melody)]
                add(
                    tone(note, 0.82 if scene_id == "actions" else 1.35, "keys"),
                    at + beat * BEAT,
                    0.040 if scene_id != "move" else 0.052,
                    (step - 1.5) * 0.30,
                    "glass_motif",
                    note,
                )

    for scene in scenes[1:]:
        start = float(scene["start"])
        length = round(0.75 * SR)
        envelope = np.sin(np.linspace(0, np.pi, length, dtype=np.float32)) ** 2
        add(burst(rng, 0.75, lowpass=71) * envelope, start - 0.35, 0.022, 0.35, "transition_air", None)

    markers: list[dict[str, object]] = []
    add(tone(74, 0.95, "keys"), 28.0, 0.075, -0.10, "result_hit", 74)
    add(tone(81, 0.42, "keys"), 28.0, 0.042, 0.16, "result_hit", 81)
    markers.append({"id": "result", "at": 28.0, "description": "建议结果出现"})
    add(marker_click(rng, 990), 38.0, 0.034, -0.12, "cost_change", 78)
    add(tone(78, 0.55, "keys"), 38.0, 0.050, -0.12, "cost_change", 78)
    markers.append({"id": "cost_change_start", "at": 38.0, "description": "搬运费用改变开始"})
    add(marker_click(rng, 740), 41.0, 0.030, 0.14, "cost_change", 74)
    add(tone(74, 0.50, "keys"), 41.0, 0.045, 0.14, "cost_change", 74)
    markers.append({"id": "cost_change_end", "at": 41.0, "description": "搬运费用改变完成"})
    add(marker_click(rng, 1180), 47.0, 0.036, -0.08, "action_click", 84)
    markers.append({"id": "action", "at": 47.0, "description": "确认并留下账单"})
    for index, note in enumerate((62, 65, 69, 74)):
        add(
            tone(note, 0.95, "keys"),
            55.0 + index * 0.20,
            0.045,
            (index - 1.5) * 0.18,
            "closing_resolution",
            note,
        )
    markers.append({"id": "closing", "at": 55.0, "description": "片尾开始"})

    time_axis = np.arange(count, dtype=np.float32) / SR
    fade = np.clip((DURATION - time_axis) / 3.0, 0, 1)
    fade *= np.clip(time_axis / 0.35, 0, 1)
    score *= fade[:, None]
    save_wave(out / "score.wav", score)

    with tempfile.TemporaryDirectory(prefix="meiyu_music_") as scratch:
        pre_master = Path(scratch) / "score_pre_master.wav"
        save_wave(pre_master, score)
        master = out / "master_mix.wav"
        measured = loudnorm_master(ffmpeg, pre_master, master)

    shutil.copyfile(master, out / "score.wav")
    encode_mp3(ffmpeg, master, out / "score.mp3", 192)
    shutil.copyfile(out / "score.mp3", out / "music_playback.mp3")
    measured_final = inspect_loudness(ffmpeg, master)
    write_midi(out / "score.mid", events)

    output_paths = {
        "score_wav": out / "score.wav",
        "music_playback_mp3": out / "music_playback.mp3",
        "score_mp3": out / "score.mp3",
        "score_mid": out / "score.mid",
        "master_mix_wav": out / "master_mix.wav",
    }
    manifest = {
        "schema_version": 3,
        "title": "雨前的刻度·60秒纯配乐版",
        "edition": storyboard.get("edition"),
        "source_storyboard": "storyboard.json",
        "audio_mode": "instrumental_only",
        "instrumental_only": True,
        "speech_tracks": 0,
        "ducking": {"enabled": False, "applied": False, "reason": "instrumental_only"},
        "duration_seconds": DURATION,
        "sample_rate": SR,
        "channels": 2,
        "bpm": BPM,
        "meter": "4/4",
        "bar_count": BARS,
        "bar_duration_seconds": BAR_SECONDS,
        "arrangement": "24 小节纯器乐编排；沿用已验证的程序合成音色，移除全部语音轨与语音 duck。",
        "original_synth_timbres": True,
        "third_party_music_assets": False,
        "third_party_songs": False,
        "instruments": [
            "Warm pad",
            "Soft bass",
            "Glass motif",
            "Light percussion",
        ],
        "scene_timeline": scenes,
        "text_cues": storyboard.get("text_cues", []),
        "markers": markers,
        "events": events,
        "event_count": len(events),
        "midi_tracks": list(MIDI_TRACKS),
        "seed": SEED,
        "outputs": {
            name: output_info(ROOT, path)
            for name, path in output_paths.items()
        },
        "master": {
            "target_lufs": MASTER_TARGET_LUFS,
            "target_true_peak_dbtp": MASTER_TARGET_TP,
            "target_lra": MASTER_TARGET_LRA,
            "first_pass_measurement": measured,
            "measured_integrated_lufs": measured_final["integrated_lufs"],
            "measured_true_peak_dbtp": measured_final["true_peak_dbtp"],
            "fade_out_start_seconds": 57.0,
            "fade_out_seconds": 3.0,
        },
        "verification": {
            "ffprobe_required_duration_seconds": DURATION,
            "listening_review": "未执行人工听审",
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out / "score_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "duration_seconds": DURATION,
        "sample_rate": SR,
        "channels": 2,
        "bars": BARS,
        "event_count": len(events),
        "speech_tracks": 0,
        "ducking": False,
        "master_lufs": measured_final["integrated_lufs"],
        "master_true_peak_dbtp": measured_final["true_peak_dbtp"],
        "outputs": {
            name: {
                "path": str(path),
                "bytes": path.stat().st_size,
            }
            for name, path in output_paths.items()
        },
        "manifest": str(manifest_path),
        "unresolved": ["未执行人工听审，仅完成媒体规格与响度检查"],
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
