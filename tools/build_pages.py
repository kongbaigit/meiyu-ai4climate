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
    return {"site": str(site), "video_bytes": info["bytes"], "video_sha256": digest,
            "duration_seconds": info["duration_seconds"], "captions": len(storyboard["text_cues"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="构建梅雨有数最终交付版静态站点")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(build_pages(parser.parse_args().root), ensure_ascii=False, indent=2))
