"""为宣传片旁白生成逐句边界和 MP3 音频。

脚本只读取同目录上一级的 narration.json，并把音频及其机器可读元数据写入
source/audio。文本始终原样传给 edge-tts，不在脚本中改写文案。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PYDEPS = Path(
    r"C:\Users\kongbai\Documents\Codex\2026-10-12\zong\work\promo_20261019\pydeps"
)
DEFAULT_FFPROBE = Path(
    r"C:\Users\kongbai\Documents\Codex\2026-10-12\gei-w\work\film-v2\tools\ffprobe.exe"
)
DEFAULT_FFMPEG = Path(
    r"C:\Users\kongbai\Documents\Codex\2026-10-12\zong\work\meiyu\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
)
BOUNDARY = "SentenceBoundary"
SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent)
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_edge_tts(deps: Path | None):
    """优先使用运行时已安装的 edge_tts，再回退到本地依赖目录。"""

    try:
        import edge_tts  # type: ignore

        return edge_tts
    except ModuleNotFoundError as first_error:
        if deps is None:
            raise first_error
        deps_text = str(deps)
        if deps_text not in sys.path:
            sys.path.insert(0, deps_text)
        try:
            import edge_tts  # type: ignore

            return edge_tts
        except ModuleNotFoundError:
            raise first_error


def resolve_ffprobe(explicit: Path | None) -> Path | str:
    candidates: list[Path | str] = []
    if explicit is not None:
        candidates.append(explicit)
    candidates.append(DEFAULT_FFPROBE)
    candidates.append("ffprobe")
    for candidate in candidates:
        if isinstance(candidate, Path):
            if candidate.is_file():
                return candidate
        else:
            try:
                completed = subprocess.run(
                    [candidate, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if completed.returncode == 0:
                return candidate
    raise FileNotFoundError(
        "找不到 ffprobe；请确保默认路径存在，或通过 --ffprobe 指定可执行文件。"
    )


def probe_duration(ffprobe: Path | str, audio_path: Path) -> float:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        details = completed.stderr.strip() or f"exit {completed.returncode}"
        raise RuntimeError(f"ffprobe 无法读取 {audio_path.name}: {details}")
    value = completed.stdout.strip()
    try:
        duration = float(value)
    except ValueError as error:
        raise RuntimeError(f"ffprobe 返回无效时长 {value!r}：{audio_path.name}") from error
    if duration <= 0:
        raise RuntimeError(f"ffprobe 返回非正时长 {duration}：{audio_path.name}")
    return duration


def load_narration(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    narration = json.loads(raw.decode("utf-8"))
    if not isinstance(narration, dict):
        raise ValueError("narration.json 顶层必须是对象")
    voice = narration.get("voice")
    rate = narration.get("rate")
    scenes = narration.get("scenes")
    if not isinstance(voice, str) or not voice:
        raise ValueError("narration.json 缺少 voice")
    if not isinstance(rate, str) or not rate:
        raise ValueError("narration.json 缺少 rate")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("narration.json 缺少 scenes")
    previous_end = 0.0
    ids: set[str] = set()
    for scene in scenes:
        if not isinstance(scene, dict):
            raise ValueError("每个场景必须是对象")
        scene_id = scene.get("id")
        text = scene.get("text")
        start = scene.get("start")
        end = scene.get("end")
        if not isinstance(scene_id, str) or not scene_id or scene_id in ids:
            raise ValueError(f"场景 id 无效或重复：{scene_id!r}")
        if not isinstance(text, str) or not text:
            raise ValueError(f"场景 {scene_id} 的 text 必须是非空字符串")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            raise ValueError(f"场景 {scene_id} 缺少数值 start/end")
        if float(start) < previous_end or float(end) <= float(start):
            raise ValueError(f"场景 {scene_id} 的时间范围不连续或为空")
        previous_end = float(end)
        ids.add(scene_id)
    return narration, sha256_bytes(raw)


def request_for(scene: dict[str, Any], narration: dict[str, Any]) -> dict[str, str]:
    return {
        "text": scene["text"],
        "voice": narration["voice"],
        "rate": narration["rate"],
        "boundary": BOUNDARY,
    }


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def cached_metadata(
    metadata_path: Path,
    audio_path: Path,
    request: dict[str, str],
    narration_sha256: str,
) -> dict[str, Any] | None:
    metadata = read_json(metadata_path)
    if metadata is None or not audio_path.is_file():
        return None
    if metadata.get("request") != request:
        return None
    if metadata.get("source", {}).get("narration_sha256") != narration_sha256:
        return None
    stored_hash = metadata.get("audio", {}).get("sha256")
    if not isinstance(stored_hash, str):
        return None
    try:
        actual_hash = sha256_file(audio_path)
    except OSError:
        return None
    if actual_hash != stored_hash:
        return None
    if not isinstance(metadata.get("boundaries"), list):
        return None
    return metadata


def normalize_boundary(chunk: dict[str, Any]) -> dict[str, Any] | None:
    chunk_type = str(chunk.get("type", ""))
    if chunk_type.lower() != "sentenceboundary":
        return None
    try:
        offset = int(chunk["offset"])
        duration = int(chunk["duration"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"SentenceBoundary 缺少有效 offset/duration：{chunk!r}") from error
    text = chunk.get("text")
    if not isinstance(text, str):
        raise ValueError(f"SentenceBoundary 缺少有效 text：{chunk!r}")
    start_seconds = offset / 10_000_000
    end_seconds = (offset + duration) / 10_000_000
    return {
        "offset_100ns": offset,
        "duration_100ns": duration,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "text": text,
    }


async def generate_audio(
    edge_tts_module: Any,
    scene: dict[str, Any],
    narration: dict[str, Any],
    audio_path: Path,
    metadata_path: Path,
    narration_sha256: str,
    ffprobe: Path | str,
    semaphore: asyncio.Semaphore,
    edge_tts_version: str,
) -> dict[str, Any]:
    request = request_for(scene, narration)
    async with semaphore:
        communicate = edge_tts_module.Communicate(
            request["text"],
            request["voice"],
            rate=request["rate"],
            boundary=BOUNDARY,
        )
        audio_parts: list[bytes] = []
        boundaries: list[dict[str, Any]] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                data = chunk.get("data")
                if data:
                    audio_parts.append(bytes(data))
            else:
                boundary = normalize_boundary(chunk)
                if boundary is not None:
                    boundaries.append(boundary)
        audio_data = b"".join(audio_parts)
        if not audio_data:
            raise RuntimeError(f"edge-tts 未返回音频：{scene['id']}")
        write_bytes_atomic(audio_path, audio_data)
        audio_hash = sha256_bytes(audio_data)
        duration = probe_duration(ffprobe, audio_path)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "scene_id": scene["id"],
            "label": scene.get("label"),
            "scene_start": scene["start"],
            "scene_end": scene["end"],
            "request": request,
            "source": {
                "narration_path": str(
                    Path("source") / "narration.json"
                ),
                "narration_sha256": narration_sha256,
            },
            "audio": {
                "path": str(audio_path),
                "sha256": audio_hash,
                "bytes": len(audio_data),
                "duration_seconds": duration,
            },
            "boundaries": boundaries,
            "edge_tts_version": edge_tts_version,
            "cache": {"reused": False, "reason": "request_or_file_not_cached"},
            "generated_at_utc": utc_now(),
        }
        write_json_atomic(metadata_path, metadata)
        return metadata


def finalize_cached_metadata(
    metadata: dict[str, Any],
    audio_path: Path,
    scene: dict[str, Any],
    ffprobe: Path | str,
    edge_tts_version: str,
) -> dict[str, Any]:
    actual_hash = sha256_file(audio_path)
    duration = probe_duration(ffprobe, audio_path)
    metadata = dict(metadata)
    metadata["scene_id"] = scene["id"]
    metadata["label"] = scene.get("label")
    metadata["scene_start"] = scene["start"]
    metadata["scene_end"] = scene["end"]
    audio = dict(metadata.get("audio", {}))
    audio["path"] = str(audio_path)
    audio["sha256"] = actual_hash
    audio["bytes"] = audio_path.stat().st_size
    audio["duration_seconds"] = duration
    metadata["audio"] = audio
    metadata["edge_tts_version"] = edge_tts_version
    metadata["cache"] = {"reused": True, "reason": "request_and_file_hash_match"}
    return metadata


async def synthesize(
    root: Path,
    deps: Path | None,
    max_concurrency: int,
    explicit_ffprobe: Path | None,
) -> int:
    narration_path = root / "narration.json"
    audio_dir = root / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    narration, narration_sha256 = load_narration(narration_path)
    ffprobe = resolve_ffprobe(explicit_ffprobe)
    edge_tts_module = load_edge_tts(deps)
    edge_tts_version = importlib.metadata.version("edge-tts")
    semaphore = asyncio.Semaphore(max_concurrency)
    results: list[dict[str, Any] | None] = [None] * len(narration["scenes"])
    pending: list[tuple[int, dict[str, Any], Path, Path, dict[str, str]]] = []

    for index, scene in enumerate(narration["scenes"]):
        request = request_for(scene, narration)
        audio_path = audio_dir / f"voice_{scene['id']}.mp3"
        metadata_path = audio_dir / f"voice_{scene['id']}.json"
        cached = cached_metadata(
            metadata_path, audio_path, request, narration_sha256
        )
        if cached is not None:
            try:
                finalized = finalize_cached_metadata(
                    cached, audio_path, scene, ffprobe, edge_tts_version
                )
                write_json_atomic(metadata_path, finalized)
                results[index] = finalized
                print(f"reused {scene['id']}: {finalized['audio']['duration_seconds']:.3f}s")
                continue
            except (OSError, RuntimeError) as error:
                print(f"cache invalid {scene['id']}: {error}", file=sys.stderr)
        pending.append((index, scene, audio_path, metadata_path, request))

    async def run_one(
        index: int,
        scene: dict[str, Any],
        audio_path: Path,
        metadata_path: Path,
        request: dict[str, str],
    ) -> tuple[int, dict[str, Any] | None, str | None]:
        del request
        try:
            metadata = await generate_audio(
                edge_tts_module,
                scene,
                narration,
                audio_path,
                metadata_path,
                narration_sha256,
                ffprobe,
                semaphore,
                edge_tts_version,
            )
            print(f"generated {scene['id']}: {metadata['audio']['duration_seconds']:.3f}s")
            return index, metadata, None
        except Exception as error:  # noqa: BLE001 - aggregate and report each scene
            return index, None, f"{type(error).__name__}: {error}"

    generated = await asyncio.gather(*(run_one(*item) for item in pending))
    failures: list[dict[str, str]] = []
    for index, metadata, error in generated:
        if metadata is None:
            scene = narration["scenes"][index]
            failures.append({"scene_id": scene["id"], "error": error or "unknown error"})
        else:
            results[index] = metadata

    outputs: list[dict[str, Any]] = []
    overlong: list[dict[str, Any]] = []
    total_duration = 0.0
    for index, scene in enumerate(narration["scenes"]):
        metadata = results[index]
        if metadata is None:
            continue
        audio = metadata["audio"]
        duration = float(audio["duration_seconds"])
        total_duration += duration
        threshold = float(scene["end"]) - float(scene["start"]) - 1.0
        is_overlong = not duration < threshold
        output = {
            "scene_id": scene["id"],
            "audio_path": str(audio["path"]),
            "metadata_path": str(audio_dir / f"voice_{scene['id']}.json"),
            "sha256": audio["sha256"],
            "bytes": audio["bytes"],
            "duration_seconds": duration,
            "scene_window_seconds": float(scene["end"]) - float(scene["start"]),
            "max_allowed_duration_seconds": threshold,
            "overlong": is_overlong,
            "boundary_count": len(metadata.get("boundaries", [])),
            "cache_reused": metadata.get("cache", {}).get("reused", False),
        }
        outputs.append(output)
        if is_overlong:
            overlong.append(output)

    aggregate = {
        "schema_version": SCHEMA_VERSION,
        "narration_path": str(narration_path),
        "narration_sha256": narration_sha256,
        "voice": narration["voice"],
        "rate": narration["rate"],
        "boundary": BOUNDARY,
        "max_concurrency": max_concurrency,
        "edge_tts_version": edge_tts_version,
        "python": sys.executable,
        "generated_at_utc": utc_now(),
        "scene_count": len(narration["scenes"]),
        "completed_count": len(outputs),
        "total_audio_duration_seconds": total_duration,
        "narration_duration_seconds": narration.get("duration"),
        "outputs": outputs,
        "overlong_items": overlong,
        "failures": failures,
    }
    write_json_atomic(audio_dir / "voice_generation.json", aggregate)
    print(
        f"completed={len(outputs)}/{len(narration['scenes'])} "
        f"total_audio={total_duration:.3f}s overlong={len(overlong)} failures={len(failures)}"
    )
    return 2 if failures else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成梅雨有数宣传片旁白音频")
    parser.add_argument("--root", required=True, type=Path, help="source 源码目录")
    parser.add_argument(
        "--deps",
        type=Path,
        default=DEFAULT_PYDEPS,
        help="edge-tts 依赖目录（运行时未安装时回退）",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=2,
        help="最大并发请求数，最多为 2",
    )
    parser.add_argument(
        "--ffprobe",
        type=Path,
        default=None,
        help="可选的 ffprobe 路径",
    )
    args = parser.parse_args()
    if args.max_concurrency < 1 or args.max_concurrency > 2:
        parser.error("--max-concurrency 必须在 1 到 2 之间")
    return args


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(
            synthesize(
                root=args.root.resolve(),
                deps=args.deps.resolve() if args.deps else None,
                max_concurrency=args.max_concurrency,
                explicit_ffprobe=args.ffprobe.resolve() if args.ffprobe else None,
            )
        )
    except Exception as error:  # noqa: BLE001 - CLI emits a concise truthful failure
        print(f"synthesize failed: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
