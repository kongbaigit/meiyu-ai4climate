#!/usr/bin/env python3
"""宣传片视频的可重复技术验收工具。

本工具只做容器/流元数据、完整解码和抽帧检查。抽帧不会替代人工视觉检查，
工具也不会声称已经听过音频、完成视觉验收或判断视频可发布。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from fractions import Fraction
from typing import Any, Iterable


REPORT_NAME = "report.json"
MAX_DIAGNOSTIC_CHARS = 8_000


class InputError(Exception):
    """命令行参数或输入路径错误。"""


class ToolError(Exception):
    """ffmpeg/ffprobe 缺失或无法启动。"""


class OperationError(Exception):
    """外部工具执行失败或输出无法解析。"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    # argparse 会把以负号开头的逗号串误认为下一个选项；将其改写为
    # --sample-times=<值>，这样负时间点也能按“按时长裁剪”规则处理。
    normalized_argv = list(argv)
    for index in range(len(normalized_argv) - 1):
        if (
            normalized_argv[index] == "--sample-times"
            and normalized_argv[index + 1].startswith("-")
            and not normalized_argv[index + 1].startswith("--")
        ):
            normalized_argv[index] = "--sample-times=" + normalized_argv[index + 1]
            del normalized_argv[index + 1]
            break
    parser = argparse.ArgumentParser(
        description="检查宣传片视频的技术完整性并生成 report.json；视觉检查仍需人工完成。"
    )
    parser.add_argument("video", help="待检查的视频文件（只读）")
    parser.add_argument("--out-dir", required=True, help="必须不存在的新输出目录")
    parser.add_argument("--duration", type=float, help="要求的视频时长（秒）")
    parser.add_argument("--width", type=int, help="要求的视频宽度（像素）")
    parser.add_argument("--height", type=int, help="要求的视频高度（像素）")
    parser.add_argument("--fps", help="要求的帧率，支持整数、小数或 fraction（例如 30000/1001）")
    parser.add_argument("--require-audio", action="store_true", help="要求至少存在一条音频流")
    parser.add_argument(
        "--sample-times",
        help="抽帧时间点（秒），逗号分隔；会自动加入首尾并按时长裁剪",
    )
    parser.add_argument("--ffmpeg", help="ffmpeg 可执行文件路径")
    parser.add_argument("--ffprobe", help="ffprobe 可执行文件路径")
    return parser.parse_args(normalized_argv)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def trim_diagnostic(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if len(value) <= MAX_DIAGNOSTIC_CHARS:
        return value
    return value[-MAX_DIAGNOSTIC_CHARS:]


def display_path(path: Path) -> str:
    return str(path)


def resolve_tool(cli_value: str | None, env_name: str, executable: str) -> str:
    """按 CLI > 环境变量 > PATH 解析工具，不下载或修改工具。"""
    selected = cli_value
    source = "--" + executable
    if not selected:
        selected = os.environ.get(env_name)
        source = env_name
    if selected:
        candidate = Path(selected)
        if candidate.exists() and candidate.is_file():
            return str(candidate)
        # 允许用户传入 PATH 中的命令名；明确给出的路径若无效则报错。
        if len(candidate.parts) == 1:
            found = shutil.which(selected)
            if found:
                return found
        raise ToolError(f"{source} 指定的工具不可用：{selected}")
    found = shutil.which(executable)
    if found:
        return found
    raise ToolError(f"找不到 {executable}；请通过 CLI、{env_name} 或 PATH 提供工具")


def validate_args(args: argparse.Namespace) -> tuple[Path, Path, Fraction | None]:
    video = Path(args.video)
    out_dir = Path(args.out_dir)
    if not video.exists():
        raise InputError(f"视频文件不存在：{display_path(video)}")
    if not video.is_file():
        raise InputError(f"视频路径不是文件：{display_path(video)}")
    if out_dir.exists():
        raise InputError(f"输出目录已存在，为避免覆盖旧结果而停止：{display_path(out_dir)}")
    if args.duration is not None and (
        not math.isfinite(args.duration) or args.duration < 0
    ):
        raise InputError("--duration 必须是非负有限秒数")
    if args.width is not None and args.width <= 0:
        raise InputError("--width 必须是正整数")
    if args.height is not None and args.height <= 0:
        raise InputError("--height 必须是正整数")
    expected_fps = parse_fraction(args.fps, "--fps") if args.fps is not None else None
    # parent 可以不存在，脚本会创建它；如果父路径最终无法创建，主流程会报告错误。
    return video, out_dir, expected_fps


def parse_fraction(value: str, label: str = "帧率") -> Fraction:
    raw = value.strip()
    if not raw:
        raise InputError(f"{label} 不能为空")
    try:
        if "/" in raw:
            numerator, denominator = raw.split("/", 1)
            result = Fraction(int(numerator.strip()), int(denominator.strip()))
        else:
            result = Fraction(raw)
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        raise InputError(f"{label} 不是有效的整数、小数或 fraction：{value}") from exc
    if result <= 0:
        raise InputError(f"{label} 必须大于 0：{value}")
    return result


def parse_sample_times(raw: str | None) -> list[float] | None:
    if raw is None:
        return None
    pieces = [piece.strip() for piece in raw.split(",")]
    if not pieces or any(piece == "" for piece in pieces):
        raise InputError("--sample-times 必须是逗号分隔的数字，不能包含空时间点")
    result: list[float] = []
    for piece in pieces:
        try:
            value = float(piece)
        except ValueError as exc:
            raise InputError(f"--sample-times 含无效时间点：{piece}") from exc
        if not math.isfinite(value):
            raise InputError(f"--sample-times 含非有限时间点：{piece}")
        result.append(value)
    return result


def run_command(
    argv: list[str], *, label: str, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"{label} 无法启动：{argv[0]}") from exc
    except OSError as exc:
        raise ToolError(f"{label} 无法启动：{exc}") from exc
    except subprocess.TimeoutExpired as exc:
        stderr = trim_diagnostic(
            (exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr)
        )
        detail = f"；stderr：{stderr}" if stderr else ""
        raise OperationError(f"{label} 超时{detail}") from exc


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
                size += len(block)
    except OSError as exc:
        raise InputError(f"读取视频失败，无法计算 SHA-256：{exc}") from exc
    return digest.hexdigest(), size


def number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value))
    except (ValueError, TypeError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(str(value))
    except (ValueError, TypeError):
        return None
    return parsed if parsed >= 0 else None


def fraction_from_value(value: Any) -> Fraction | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw in {"0/0", "N/A", "nan", "NaN"}:
        return None
    try:
        if "/" in raw:
            numerator, denominator = raw.split("/", 1)
            fraction = Fraction(int(numerator), int(denominator))
        else:
            fraction = Fraction(raw)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
    return fraction if fraction > 0 else None


def fraction_json(value: Fraction | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": float(value),
        "text": f"{value.numerator}/{value.denominator}",
    }


def first_stream(streams: Iterable[dict[str, Any]], codec_type: str) -> dict[str, Any] | None:
    for stream in streams:
        if stream.get("codec_type") == codec_type:
            return stream
    return None


def probe_video(ffprobe: str, video: Path) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-count_frames",
        "-show_format",
        "-show_streams",
        "-show_entries",
        (
            "format=format_name,format_long_name,duration,size,bit_rate:"
            "stream=index,codec_type,codec_name,codec_long_name,width,height,"
            "r_frame_rate,avg_frame_rate,nb_frames,nb_read_frames,duration,"
            "time_base,sample_rate,channels,channel_layout"
        ),
        "-of",
        "json",
        str(video),
    ]
    completed = run_command(command, label="ffprobe")
    if completed.returncode != 0:
        detail = trim_diagnostic(completed.stderr)
        suffix = f"；stderr：{detail}" if detail else ""
        raise OperationError(f"ffprobe 读取视频失败（退出码 {completed.returncode}）{suffix}")
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = trim_diagnostic(completed.stderr)
        suffix = f"；stderr：{detail}" if detail else ""
        raise OperationError(f"ffprobe 输出不是有效 JSON{suffix}") from exc
    if not isinstance(data, dict):
        raise OperationError("ffprobe 输出结构无效")
    return data


def summarize_probe(data: dict[str, Any]) -> dict[str, Any]:
    raw_streams = data.get("streams")
    streams = raw_streams if isinstance(raw_streams, list) else []
    streams = [stream for stream in streams if isinstance(stream, dict)]
    format_info = data.get("format")
    if not isinstance(format_info, dict):
        format_info = {}
    video_stream = first_stream(streams, "video")
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]

    video_fps = None
    video_fps_source = None
    if video_stream:
        video_fps = fraction_from_value(video_stream.get("avg_frame_rate"))
        video_fps_source = "avg_frame_rate"
        if video_fps is None:
            video_fps = fraction_from_value(video_stream.get("r_frame_rate"))
            video_fps_source = "r_frame_rate" if video_fps is not None else None

    container_duration = number_or_none(format_info.get("duration"))
    video_duration = number_or_none(video_stream.get("duration")) if video_stream else None
    audio_durations = [number_or_none(stream.get("duration")) for stream in audio_streams]
    audio_durations = [value for value in audio_durations if value is not None]
    audio_duration = audio_durations[0] if audio_durations else None
    chosen_duration = container_duration
    duration_source = "container" if container_duration is not None else None
    if chosen_duration is None and video_duration is not None:
        chosen_duration = video_duration
        duration_source = "video_stream"
    audio_video_difference = None
    if audio_duration is not None and video_duration is not None:
        audio_video_difference = abs(audio_duration - video_duration)

    streams_summary: list[dict[str, Any]] = []
    for stream in streams:
        streams_summary.append(
            {
                "index": int_or_none(stream.get("index")),
                "codec_type": stream.get("codec_type"),
                "codec_name": stream.get("codec_name"),
                "width": int_or_none(stream.get("width")),
                "height": int_or_none(stream.get("height")),
                "r_frame_rate": stream.get("r_frame_rate"),
                "avg_frame_rate": stream.get("avg_frame_rate"),
                "nb_frames": int_or_none(stream.get("nb_frames")),
                "nb_read_frames": int_or_none(stream.get("nb_read_frames")),
                "duration_seconds": number_or_none(stream.get("duration")),
                "sample_rate": stream.get("sample_rate"),
                "channels": int_or_none(stream.get("channels")),
            }
        )

    return {
        "format": {
            "format_name": format_info.get("format_name"),
            "format_long_name": format_info.get("format_long_name"),
            "duration_seconds": container_duration,
            "size_bytes": int_or_none(format_info.get("size")),
            "bit_rate": int_or_none(format_info.get("bit_rate")),
        },
        "streams": streams_summary,
        "video": {
            "present": video_stream is not None,
            "index": int_or_none(video_stream.get("index")) if video_stream else None,
            "codec_name": video_stream.get("codec_name") if video_stream else None,
            "width": int_or_none(video_stream.get("width")) if video_stream else None,
            "height": int_or_none(video_stream.get("height")) if video_stream else None,
            "duration_seconds": video_duration,
            "frame_count": (
                int_or_none(video_stream.get("nb_read_frames"))
                if video_stream and int_or_none(video_stream.get("nb_read_frames")) is not None
                else int_or_none(video_stream.get("nb_frames")) if video_stream else None
            ),
            "frame_count_source": (
                "nb_read_frames"
                if video_stream and int_or_none(video_stream.get("nb_read_frames")) is not None
                else "nb_frames" if video_stream and int_or_none(video_stream.get("nb_frames")) is not None else None
            ),
            "frame_rate": fraction_json(video_fps),
            "frame_rate_source": video_fps_source,
            "r_frame_rate": video_stream.get("r_frame_rate") if video_stream else None,
            "avg_frame_rate": video_stream.get("avg_frame_rate") if video_stream else None,
        },
        "audio": {
            "stream_count": len(audio_streams),
            "present": bool(audio_streams),
            "first_duration_seconds": audio_duration,
            "streams": [
                {
                    "index": int_or_none(stream.get("index")),
                    "codec_name": stream.get("codec_name"),
                    "duration_seconds": number_or_none(stream.get("duration")),
                    "sample_rate": stream.get("sample_rate"),
                    "channels": int_or_none(stream.get("channels")),
                }
                for stream in audio_streams
            ],
        },
        "durations": {
            "selected_seconds": chosen_duration,
            "selected_source": duration_source,
            "container_seconds": container_duration,
            "video_stream_seconds": video_duration,
            "audio_stream_seconds": audio_duration,
            "audio_video_difference_seconds": audio_video_difference,
            "audio_video_difference_checked": audio_video_difference is not None,
        },
    }


def run_full_decode(ffmpeg: str, video: Path) -> dict[str, Any]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-xerror",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-f",
        "null",
        "-",
    ]
    completed = run_command(command, label="ffmpeg 全片解码")
    stderr = trim_diagnostic(completed.stderr)
    if completed.returncode != 0:
        detail = f"；stderr：{stderr}" if stderr else ""
        return {
            "status": "error",
            "returncode": completed.returncode,
            "diagnostic": stderr,
            "message": f"ffmpeg 全片解码失败（退出码 {completed.returncode}）{detail}",
        }
    return {
        "status": "passed",
        "returncode": completed.returncode,
        "diagnostic": stderr,
        "message": "ffmpeg 已完成全片视频（及存在的音频流）解码检查",
    }


def canonical_times(
    explicit: list[float] | None, duration: float | None, fps: Fraction | None
) -> list[dict[str, Any]]:
    """生成去重排序后的抽帧计划，并记录原始/裁剪信息。"""
    if explicit is None:
        if duration is not None and duration > 0:
            raw_times = [duration * index / 4 for index in range(5)]
            sources = ["auto_uniform"] * len(raw_times)
        else:
            raw_times = [0.0]
            sources = ["auto_first_duration_missing"]
    else:
        raw_times = list(explicit)
        sources = ["explicit"] * len(raw_times)
        # 显式抽帧始终补自动首点；只有已知时长时才能补自动尾点。
        raw_times.append(0.0)
        sources.append("auto_first")
        if duration is not None:
            raw_times.append(duration)
            sources.append("auto_last")

    plan: list[dict[str, Any]] = []
    for raw, source in zip(raw_times, sources):
        # 即使时长元数据缺失，也不能把负时间点传给 ffmpeg；上界仅在时长可用时裁剪。
        clipped = max(raw, 0.0)
        if duration is not None:
            clipped = min(clipped, max(duration, 0.0))
        # 微小浮点误差不应产生两个相同抽帧点。
        clipped = round(clipped, 6)
        plan.append(
            {
                "requested_seconds": raw,
                "time_seconds": clipped,
                "source": source,
            }
        )
    plan.sort(key=lambda item: item["time_seconds"])
    deduped: list[dict[str, Any]] = []
    for item in plan:
        if deduped and math.isclose(
            item["time_seconds"], deduped[-1]["time_seconds"], abs_tol=1e-6, rel_tol=0
        ):
            # 保留更具体的显式请求信息，同时仍记录自动首尾已覆盖。
            previous = deduped[-1]
            if previous["source"].startswith("auto_") and item["source"] == "explicit":
                item["source"] = "explicit+" + previous["source"]
            elif item["source"].startswith("auto_") and previous["source"] == "explicit":
                previous["source"] = "explicit+" + item["source"]
            continue
        deduped.append(item)
    # fps 仅用于向调用方保留“最后一帧失败时的回退步长”所需信息；这里不修改时间。
    if fps is not None:
        for item in deduped:
            item["fallback_step_seconds"] = float(1 / fps)
    return deduped


def format_time(value: float) -> str:
    return f"{value:.6f}"


def extract_samples(
    ffmpeg: str,
    video: Path,
    out_dir: Path,
    plan: list[dict[str, Any]],
    duration: float | None,
    fps: Fraction | None,
) -> dict[str, Any]:
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=False, exist_ok=False)
    frames: list[dict[str, Any]] = []
    any_error = False
    fallback_step = float(1 / fps) if fps is not None else 0.001
    for index, item in enumerate(plan, start=1):
        target = float(item["time_seconds"])
        safe_name = f"frame_{index:03d}_{target:012.6f}.png".replace("-", "m")
        output_path = frames_dir / safe_name
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            format_time(target),
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-an",
            "-f",
            "image2",
            str(output_path),
        ]
        completed = run_command(command, label=f"ffmpeg 抽帧 {target:.6f}s")
        used_target = target
        stderr = trim_diagnostic(completed.stderr)
        # 精确落在容器末尾时，有些编码器没有可输出的帧；回退到最后一个帧时长内的位置。
        if (completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0) and duration is not None and duration > 0:
            fallback_target = max(0.0, min(target, duration) - fallback_step)
            if fallback_target < target - 1e-9:
                fallback_command = command.copy()
                fallback_command[fallback_command.index("-ss") + 1] = format_time(fallback_target)
                fallback_completed = run_command(
                    fallback_command, label=f"ffmpeg 抽帧回退 {fallback_target:.6f}s"
                )
                if (
                    fallback_completed.returncode == 0
                    and output_path.exists()
                    and output_path.stat().st_size > 0
                ):
                    used_target = fallback_target
                    completed = fallback_completed
                    stderr = trim_diagnostic(fallback_completed.stderr)

        ok = completed.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0
        frame_record: dict[str, Any] = {
            "index": index,
            "source": item.get("source"),
            "requested_seconds": item.get("requested_seconds"),
            "time_seconds": target,
            "used_time_seconds": used_target if ok else None,
            "status": "passed" if ok else "error",
            "path": str(output_path.relative_to(out_dir)) if ok else None,
            "absolute_path": str(output_path) if ok else None,
            "size_bytes": output_path.stat().st_size if ok else None,
        }
        if stderr:
            frame_record["diagnostic"] = stderr
        if not ok:
            any_error = True
            detail = f"；stderr：{stderr}" if stderr else ""
            frame_record["message"] = (
                f"抽取 {target:.6f}s PNG 失败（退出码 {completed.returncode}）{detail}"
            )
        frames.append(frame_record)
    return {
        "status": "error" if any_error else "passed",
        "requested_count": len(plan),
        "successful_count": sum(1 for frame in frames if frame["status"] == "passed"),
        "frames": frames,
        "frame_paths": [frame["path"] for frame in frames if frame.get("path")],
        "message": "抽帧 PNG 已生成" if not any_error else "至少一个抽帧 PNG 生成失败",
    }


def check_duration(
    expected: float | None,
    actual: float | None,
    fps: Fraction | None,
) -> dict[str, Any]:
    if expected is None:
        return {"status": "not_checked", "reason": "未指定时长要求"}
    tolerance = max(0.1, 1 / float(fps)) if fps is not None else 0.1
    if actual is None:
        return {
            "status": "not_checked",
            "reason": "ffprobe 未提供可用时长，无法核验",
            "expected_seconds": expected,
            "actual_seconds": None,
            "tolerance_seconds": tolerance,
        }
    difference = abs(actual - expected)
    return {
        "status": "passed" if difference <= tolerance else "failed",
        "expected_seconds": expected,
        "actual_seconds": actual,
        "difference_seconds": difference,
        "tolerance_seconds": tolerance,
        "tolerance_rule": "max(0.1, 1/fps)；fps 缺失时使用 0.1 秒下限",
    }


def check_dimension(
    name: str, expected: int | None, actual: int | None
) -> dict[str, Any]:
    if expected is None:
        return {"status": "not_checked", "reason": f"未指定{name}要求"}
    if actual is None:
        return {
            "status": "not_checked",
            "reason": f"ffprobe 未提供可用{name}，无法核验",
            "expected": expected,
            "actual": None,
        }
    return {
        "status": "passed" if actual == expected else "failed",
        "expected": expected,
        "actual": actual,
    }


def check_fps(expected: Fraction | None, actual: Fraction | None) -> dict[str, Any]:
    if expected is None:
        return {"status": "not_checked", "reason": "未指定帧率要求"}
    tolerance = max(0.01, float(expected) * 0.01)
    if actual is None:
        return {
            "status": "not_checked",
            "reason": "ffprobe 未提供可用帧率，无法核验",
            "expected": fraction_json(expected),
            "actual": None,
            "tolerance_fps": tolerance,
        }
    difference = abs(float(actual - expected))
    return {
        "status": "passed" if difference <= tolerance else "failed",
        "expected": fraction_json(expected),
        "actual": fraction_json(actual),
        "difference_fps": difference,
        "tolerance_fps": tolerance,
        "tolerance_rule": "max(0.01, 期望帧率的 1%)；比较前保留 fraction",
    }


def check_audio(required: bool, audio_present: bool | None, audio_count: int | None) -> dict[str, Any]:
    if not required:
        return {
            "status": "not_checked",
            "required": False,
            "audio_present": audio_present,
            "stream_count": audio_count,
            "reason": "未要求音轨；缺少音轨不作为失败",
        }
    if audio_present is None:
        return {
            "status": "not_checked",
            "required": True,
            "audio_present": None,
            "stream_count": None,
            "reason": "ffprobe 未提供可用音频流信息，无法核验",
        }
    return {
        "status": "passed" if audio_present else "failed",
        "required": True,
        "audio_present": audio_present,
        "stream_count": audio_count,
    }


def initial_report(video: Path, out_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "generated_at_utc": utc_now(),
        "input": {
            "video": str(video),
            "video_name": video.name,
            "sha256": None,
            "size_bytes": None,
        },
        "output": {"directory": str(out_dir), "report": str(out_dir / REPORT_NAME)},
        "requirements": {
            "duration_seconds": args.duration,
            "width": args.width,
            "height": args.height,
            "fps": fraction_json(parse_fraction(args.fps, "--fps")) if args.fps else None,
            "require_audio": bool(args.require_audio),
            "sample_times": args.sample_times,
        },
        "tools": {"ffmpeg": None, "ffprobe": None},
        "probe": None,
        "checks": {},
        "sampling": {"status": "not_run", "frames": [], "frame_paths": []},
        "technical_status": "not_run",
        "status": "error",
        "visual_review": "pending",
        "result": {
            "summary_zh": "尚未执行技术验收；未进行视觉验收，也未判断是否可发布。",
            "diagnostics": [],
        },
    }


def write_report(out_dir: Path, report: dict[str, Any]) -> None:
    report_path = out_dir / REPORT_NAME
    try:
        with report_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        raise InputError(f"无法写入报告 {report_path}：{exc}") from exc


def set_error_report(
    report: dict[str, Any], *, summary: str, diagnostics: list[str], status: str = "error"
) -> None:
    report["technical_status"] = "not_run" if status == "error" else "failed"
    report["status"] = status
    report["visual_review"] = "pending"
    report["result"] = {"summary_zh": summary, "diagnostics": diagnostics}


def inspect(args: argparse.Namespace) -> int:
    # 先解析不依赖输出目录的参数，使输入错误也能留下明确的 not_run/error 报告。
    expected_fps: Fraction | None = None
    try:
        video, out_dir, expected_fps = validate_args(args)
        explicit_times = parse_sample_times(args.sample_times)
    except InputError as exc:
        # 旧目录不能被触碰；只有确认目标不存在后才尝试创建错误报告。
        out_candidate = Path(args.out_dir)
        if out_candidate.exists():
            print(f"输入错误：{exc}", file=sys.stderr)
            return 2
        report = {
            "schema_version": "1.0",
            "generated_at_utc": utc_now(),
            "input": {"video": str(args.video), "sha256": None, "size_bytes": None},
            "output": {"directory": str(out_candidate), "report": str(out_candidate / REPORT_NAME)},
            "requirements": {
                "duration_seconds": args.duration,
                "width": args.width,
                "height": args.height,
                "fps": args.fps,
                "require_audio": bool(args.require_audio),
                "sample_times": args.sample_times,
            },
            "tools": {"ffmpeg": None, "ffprobe": None},
            "probe": None,
            "checks": {},
            "sampling": {"status": "not_run", "frames": [], "frame_paths": []},
            "technical_status": "not_run",
            "status": "error",
            "visual_review": "pending",
            "result": {"summary_zh": "输入参数错误，未执行技术验收。", "diagnostics": [str(exc)]},
        }
        try:
            out_candidate.mkdir(parents=True, exist_ok=False)
            write_report(out_candidate, report)
        except (OSError, InputError) as report_exc:
            print(f"输入错误：{exc}；错误报告也无法写入：{report_exc}", file=sys.stderr)
            return 2
        print(f"输入错误：{exc}；已写入错误报告：{out_candidate / REPORT_NAME}", file=sys.stderr)
        return 2

    report = initial_report(video, out_dir, args)
    report["requirements"]["fps"] = fraction_json(expected_fps)
    try:
        out_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(f"输入错误：无法创建新输出目录 {out_dir}：{exc}", file=sys.stderr)
        return 2

    try:
        sha256, size_bytes = hash_file(video)
        report["input"]["sha256"] = sha256
        report["input"]["size_bytes"] = size_bytes

        try:
            ffmpeg = resolve_tool(args.ffmpeg, "FFMPEG_PATH", "ffmpeg")
            ffprobe = resolve_tool(args.ffprobe, "FFPROBE_PATH", "ffprobe")
            report["tools"]["ffmpeg"] = ffmpeg
            report["tools"]["ffprobe"] = ffprobe
        except ToolError as exc:
            set_error_report(
                report,
                summary="未找到可用的 ffmpeg/ffprobe，未执行技术验收；未进行视觉验收。",
                diagnostics=[str(exc)],
            )
            write_report(out_dir, report)
            print(f"工具错误：{exc}；已写入错误报告：{out_dir / REPORT_NAME}", file=sys.stderr)
            return 2

        try:
            raw_probe = probe_video(ffprobe, video)
            probe = summarize_probe(raw_probe)
        except (ToolError, OperationError) as exc:
            report["checks"]["probe"] = {"status": "error", "reason": str(exc)}
            set_error_report(
                report,
                summary="ffprobe 读取失败，技术验收未完成；未进行视觉验收。",
                diagnostics=[str(exc)],
            )
            write_report(out_dir, report)
            print(f"操作错误：{exc}；已写入错误报告：{out_dir / REPORT_NAME}", file=sys.stderr)
            return 2
        report["probe"] = probe
        video_info = probe["video"]
        durations = probe["durations"]
        audio_info = probe["audio"]
        report["checks"]["probe"] = {
            "status": "passed" if video_info["present"] else "failed",
            "message": "已读取容器和流信息" if video_info["present"] else "未找到视频流",
        }
        if not video_info["present"]:
            set_error_report(
                report,
                summary="未找到视频流，技术验收失败；未进行视觉验收。",
                diagnostics=["ffprobe 未返回 codec_type=video 的流"],
                status="failed",
            )
            write_report(out_dir, report)
            print(f"技术验收失败：未找到视频流；报告：{out_dir / REPORT_NAME}", file=sys.stderr)
            return 1

        full_decode = run_full_decode(ffmpeg, video)
        report["checks"]["full_decode"] = full_decode

        sample_plan = canonical_times(explicit_times, durations["selected_seconds"], expected_fps)
        try:
            sampling = extract_samples(
                ffmpeg,
                video,
                out_dir,
                sample_plan,
                durations["selected_seconds"],
                expected_fps or (
                    Fraction(
                        video_info["frame_rate"]["numerator"],
                        video_info["frame_rate"]["denominator"],
                    )
                    if video_info.get("frame_rate")
                    else None
                ),
            )
        except (ToolError, OperationError, OSError) as exc:
            sampling = {
                "status": "error",
                "requested_count": len(sample_plan),
                "successful_count": 0,
                "frames": [],
                "frame_paths": [],
                "message": f"抽帧操作未完成：{exc}",
            }
        report["sampling"] = sampling

        checks = report["checks"]
        checks["duration"] = check_duration(
            args.duration, durations["selected_seconds"],
            Fraction(video_info["frame_rate"]["numerator"], video_info["frame_rate"]["denominator"])
            if video_info.get("frame_rate")
            else expected_fps,
        )
        checks["width"] = check_dimension("宽度", args.width, video_info.get("width"))
        checks["height"] = check_dimension("高度", args.height, video_info.get("height"))
        actual_fps = (
            Fraction(video_info["frame_rate"]["numerator"], video_info["frame_rate"]["denominator"])
            if video_info.get("frame_rate")
            else None
        )
        checks["fps"] = check_fps(expected_fps, actual_fps)
        checks["audio"] = check_audio(
            args.require_audio, audio_info.get("present"), audio_info.get("stream_count")
        )
        checks["audio_video_duration_difference"] = {
            "status": "info" if durations["audio_video_difference_checked"] else "not_checked",
            "audio_seconds": durations["audio_stream_seconds"],
            "video_seconds": durations["video_stream_seconds"],
            "difference_seconds": durations["audio_video_difference_seconds"],
            "reason": (
                "音视频流时长均可用，已记录差值"
                if durations["audio_video_difference_checked"]
                else "缺少音频或视频流时长，未用 0 伪造差值"
            ),
        }

        base_ok = (
            checks["probe"]["status"] == "passed"
            and full_decode["status"] == "passed"
            and sampling["status"] == "passed"
        )
        requested_checks: list[dict[str, Any]] = []
        if args.duration is not None:
            requested_checks.append(checks["duration"])
        if args.width is not None:
            requested_checks.append(checks["width"])
        if args.height is not None:
            requested_checks.append(checks["height"])
        if args.fps is not None:
            requested_checks.append(checks["fps"])
        if args.require_audio:
            requested_checks.append(checks["audio"])
        requirements_ok = all(check["status"] == "passed" for check in requested_checks)
        any_requirement_failed = any(check["status"] == "failed" for check in requested_checks)
        if base_ok and requirements_ok:
            report["technical_status"] = "passed"
            report["status"] = "needs_visual_review"
            report["visual_review"] = "pending"
            report["result"] = {
                "summary_zh": "技术检查通过；抽帧已生成，仍需人工视觉检查。工具未声称已听音乐、完成视觉验收或可直接发布。",
                "diagnostics": [],
            }
            write_report(out_dir, report)
            print(f"技术验收通过，待人工视觉检查；报告：{out_dir / REPORT_NAME}")
            return 0

        reason_parts: list[str] = []
        if full_decode["status"] != "passed":
            reason_parts.append("全片解码失败")
        if sampling["status"] != "passed":
            reason_parts.append("抽帧失败")
        if any_requirement_failed:
            reason_parts.append("显式要求未满足")
        if not requirements_ok and not any_requirement_failed:
            reason_parts.append("显式要求因缺少元数据而无法核验")
        report["technical_status"] = "failed"
        report["status"] = "failed"
        report["visual_review"] = "pending"
        report["result"] = {
            "summary_zh": "技术验收失败：" + "、".join(reason_parts or ["基础技术检查未通过"]) + "；未进行视觉验收。",
            "diagnostics": [
                check.get("message") or check.get("reason")
                for check in [checks["probe"], full_decode, sampling, *requested_checks]
                if (check.get("status") in {"error", "failed", "not_checked"})
                and (check.get("message") or check.get("reason"))
            ],
        }
        write_report(out_dir, report)
        print(f"技术验收失败；报告：{out_dir / REPORT_NAME}", file=sys.stderr)
        return 1
    except (InputError, ToolError, OperationError, OSError, ValueError, KeyError, TypeError) as exc:
        set_error_report(
            report,
            summary="技术验收因工具或操作错误未完成；未进行视觉验收。",
            diagnostics=[str(exc)],
        )
        try:
            write_report(out_dir, report)
        except InputError as report_exc:
            print(f"错误：{exc}；错误报告也无法写入：{report_exc}", file=sys.stderr)
            return 2
        print(f"操作错误：{exc}；已写入错误报告：{out_dir / REPORT_NAME}", file=sys.stderr)
        return 2


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv if argv is not None else sys.argv[1:])
        return inspect(args)
    except SystemExit as exc:
        # argparse 的缺参/格式错误属于输入错误；让标准帮助/错误文本照常输出。
        return int(exc.code) if isinstance(exc.code, int) else 2


if __name__ == "__main__":
    raise SystemExit(main())
