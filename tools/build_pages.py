"""从仓库中的最终交付素材生成 GitHub Pages，无需外部制作目录。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def english_release(root: Path, site: Path) -> dict:
    """Copy the English edition beside the original Chinese routes."""
    media = root / "media" / "en"
    info = json.loads((media / "video-info.json").read_text(encoding="utf-8"))
    video = media / info["video"]
    with video.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != info["sha256"] or video.stat().st_size != info["bytes"]:
        raise ValueError("English video differs from video-info.json")
    required = [root / "en" / "index.html", root / "en" / "demo.html",
                root / "en" / "materials" / "index.html", root / "templates" / "promo.en.html",
                media / "cover.png", media / "preview.html",
                root / "presentations" / "en" / "meiyu-prepare-pitch.pptx",
                root / "presentations" / "en" / "meiyu-prepare-pitch.pdf"]
    required += [root / "docs" / "en" / f"{name}.pdf" for name in
                 ("project-description", "data-ai-statement", "90-day-validation-plan")]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    shutil.copytree(root / "en", site / "en", dirs_exist_ok=True)
    shutil.copytree(root / "docs" / "en", site / "en" / "docs", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    target = site / "en" / "presentation"
    target.mkdir(parents=True, exist_ok=True)
    for filename in ("meiyu-prepare-pitch.pptx", "meiyu-prepare-pitch.pdf", "speaker-notes.md"):
        shutil.copyfile(root / "presentations" / "en" / filename, target / filename)
    (site / "en" / "promo").mkdir(parents=True, exist_ok=True)
    (site / "media" / "en").mkdir(parents=True, exist_ok=True)
    for source, destination in {
        video: site / "media" / "en" / info["video"],
        media / "cover.png": site / "media" / "en" / "cover.png",
        media / "preview.html": site / "en" / "promo" / "native.html",
        root / "templates" / "promo.en.html": site / "en" / "promo" / "index.html",
    }.items():
        shutil.copyfile(source, destination)
    storyboard = json.loads((media / "source" / "storyboard.json").read_text(encoding="utf-8"))
    captions = ["WEBVTT", ""]
    for number, cue in enumerate(storyboard["text_cues"], 1):
        if not 0 <= cue["start"] < cue["end"] <= info["duration_seconds"]:
            raise ValueError("English caption time is outside the video")
        captions.extend([str(number), f"{timestamp(cue['start'])} --> {timestamp(cue['end'])}", cue["text"], ""])
    (site / "media" / "en" / "captions.vtt").write_text("\n".join(captions), encoding="utf-8", newline="\n")
    return {"video_bytes": info["bytes"], "video_sha256": digest, "duration_seconds": info["duration_seconds"]}


def build_pages(root: Path) -> dict:
    root = root.resolve(strict=True)
    latest = root / "media" / "latest"
    info = json.loads((latest / "video-info.json").read_text(encoding="utf-8"))
    video = latest / info["video"]
    with video.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if video.stat().st_size != info["bytes"] or digest != info["sha256"]:
        raise ValueError("影片大小或 SHA-256 与 video-info.json 不符")

    required = [root / "index.html", root / "demo.html", root / "templates" / "promo.html",
                latest / "cover.png", latest / "preview.html", latest / "source" / "storyboard.json"]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    storyboard = json.loads(required[-1].read_text(encoding="utf-8"))
    captions = ["WEBVTT", ""]
    for number, cue in enumerate(storyboard["text_cues"], start=1):
        start, end = float(cue["start"]), float(cue["end"])
        if not 0 <= start < end <= info["duration_seconds"]:
            raise ValueError(f"字幕 {number} 时间越界")
        captions.extend([str(number), f"{timestamp(start)} --> {timestamp(end)}", cue["text"], ""])

    site = root / "site"
    if site.resolve(strict=False) != root / "site" or site.is_symlink():
        raise ValueError("拒绝清理非项目内的 site 生成目录")
    if site.exists():
        shutil.rmtree(site)
    (site / "promo").mkdir(parents=True)
    (site / "media").mkdir()
    copies = {
        root / "index.html": site / "index.html",
        root / "demo.html": site / "demo.html",
        root / "templates" / "promo.html": site / "promo" / "index.html",
        video: site / "media" / info["video"],
        latest / "cover.png": site / "media" / "promo-full-cover.png",
        latest / "preview.html": site / "promo" / "native.html",
    }
    for source, target in copies.items():
        shutil.copyfile(source, target)
    (site / "media" / "promo-full.vtt").write_text("\n".join(captions), encoding="utf-8", newline="\n")
    (site / ".nojekyll").touch()
    result = {"site": str(site), "video_bytes": info["bytes"], "video_sha256": digest,
              "duration_seconds": info["duration_seconds"], "captions": len(storyboard["text_cues"])}
    if (root / "en" / "index.html").is_file():
        result["english"] = english_release(root, site)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建梅雨有数最终交付版静态站点")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(build_pages(parser.parse_args().root), ensure_ascii=False, indent=2))
