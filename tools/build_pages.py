"""构建 GitHub Pages 静态文件和最新宣传片归档。

脚本只使用 Python 标准库。它把项目入口、历史演示、60 秒宣传片和字幕
复制到 site/，并把宣传片的可编辑源码和交付素材保留在 media/latest/。
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


VIDEO_NAME = "梅雨有数_60秒纯配乐动态文字.mp4"
PROMO_DIR_NAME = "梅雨有数_纯配乐动态文字版_20261019"
EXPECTED_VIDEO_SIZE = 10_282_564
EXPECTED_VIDEO_SHA256 = "e0770b609bb0375ed164afd61e30bd1342689a3cc2481e3f90d51b7b10932b7b"
RECURSIVE_DELETE_PATHS = (Path("media/latest"), Path("site/promo"), Path("site/media"))
FILE_DELETE_PATHS = (Path("site/index.html"), Path("site/demo.html"), Path("site/.nojekyll"))
SOURCE_NOTE_OLD = "新版代码和影片为本地交付，未自动发布到公开仓库。".encode("utf-8")
SOURCE_NOTE_NEW = "新版代码和影片在制作时按本地交付保存；当前公开发布状态以项目主 README 的“在线演示”说明为准。".encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)


def update_source_note(path: Path) -> None:
    """兼容旧来源说明；新来源说明自行写入以 README 为准的状态。"""

    data = path.read_bytes()
    if SOURCE_NOTE_OLD in data:
        data = data.replace(SOURCE_NOTE_OLD, SOURCE_NOTE_NEW, 1)
        path.write_bytes(data)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _checked_delete_target(root: Path, path: Path, recursive: bool) -> Path:
    """检查 resolve 后的删除目标，拒绝越界路径和非固定生成位置。"""

    root_resolved = root.resolve(strict=False)
    target_resolved = path.resolve(strict=False)
    if not _is_within(target_resolved, root_resolved):
        raise RuntimeError(f"拒绝删除项目根目录外的路径：{path} -> {target_resolved}")

    allowed = RECURSIVE_DELETE_PATHS if recursive else FILE_DELETE_PATHS
    allowed_positions = {root_resolved / relative for relative in allowed}
    if target_resolved not in allowed_positions:
        kind = "递归目录" if recursive else "生成文件"
        raise RuntimeError(f"拒绝删除非允许的{kind}：{path} -> {target_resolved}")
    return target_resolved


def remove_path(root: Path, path: Path, *, recursive: bool) -> None:
    _checked_delete_target(root, path, recursive)
    if path.is_dir() and not path.is_symlink():
        if not recursive:
            raise RuntimeError(f"拒绝把目录当作生成文件删除：{path}")
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def default_promo_dir(root: Path) -> Path:
    """在当前交付目录布局中找到宣传片目录。"""

    bases = ([root.parents[2]] if len(root.parents) > 2 else []) + [root.parent, root]
    candidates = [base / "outputs" / PROMO_DIR_NAME / "宣传片" for base in bases]
    for candidate in candidates:
        if (candidate / VIDEO_NAME).is_file() and (candidate / "source").is_dir():
            return candidate
    searched = "\n".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"找不到宣传片目录，已检查：\n{searched}")


def resolve_promo_dir(root: Path, requested: Path | None) -> Path | None:
    """优先读取交付输出；仓库已有 latest/ 时允许脱离外部输出重建。"""

    if requested is not None:
        return _validate_promo_dir(root, requested.resolve(strict=False))
    try:
        return _validate_promo_dir(root, default_promo_dir(root))
    except FileNotFoundError:
        latest = root / "media" / "latest"
        required = (latest / "promo60-music.mp4", latest / "cover.png", latest / "subtitles.srt")
        if all(path.is_file() for path in required):
            return None
        raise


def _validate_promo_dir(root: Path, promo_dir: Path) -> Path:
    """拒绝把待复制的宣传片源指向将被清理的 latest 或其父子路径。"""

    latest = (root / "media" / "latest").resolve(strict=False)
    promo = promo_dir.resolve(strict=False)
    if _is_within(promo, latest) or _is_within(latest, promo):
        raise ValueError(
            "--promo-dir 不能等于、位于或包含 media/latest，避免复制前清理源文件："
            f"{promo}"
        )
    return promo


def srt_to_vtt(source: Path) -> bytes:
    """把 UTF-8 SRT 转成 UTF-8 WebVTT，保留原字幕文字和时间范围。"""

    text = source.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[str] = []
    for raw_block in text.strip().split("\n\n"):
        lines = raw_block.split("\n")
        if not lines:
            continue
        time_line = 0
        if len(lines) > 1 and "-->" in lines[1]:
            time_line = 1
        if "-->" not in lines[time_line]:
            continue
        lines[time_line] = lines[time_line].replace(",", ".")
        blocks.append("\n".join(lines))
    return ("WEBVTT\n\n" + "\n\n".join(blocks) + "\n").encode("utf-8")


def promo_page() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <meta name="date" content="2026-10-19">
  <title>梅雨有数 · 60 秒纯配乐动态文字宣传片</title>
  <style>
    :root { color-scheme: light; --ink: #173c35; --green: #286c60; --paper: #f1f1e9; --line: #d7dfd1; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font-family: "Segoe UI", "Microsoft YaHei", sans-serif; line-height: 1.7; }
    main { width: min(960px, calc(100% - 32px)); margin: 0 auto; padding: 40px 0 56px; }
    header { display: flex; justify-content: space-between; gap: 24px; align-items: baseline; margin-bottom: 20px; }
    h1 { margin: 0; font-size: clamp(24px, 4vw, 38px); letter-spacing: .04em; }
    header p { margin: 0; color: #61766b; font-size: 14px; }
    .card { background: #fffef8; border: 1px solid var(--line); border-radius: 16px; padding: 16px; box-shadow: 0 16px 42px #173c3512; }
    video { display: block; width: 100%; height: auto; border-radius: 10px; background: #102d2d; }
    .links { display: flex; flex-wrap: wrap; gap: 14px 22px; margin: 20px 0 0; }
    .view-tip { margin: 10px 0 0; color: #61766b; font-size: 13px; }
    a { color: var(--green); }
    .note { border-top: 1px solid var(--line); margin-top: 24px; padding-top: 20px; color: #5e7368; font-size: 14px; }
    .note p { margin: 8px 0; }
    .tag { display: inline-block; margin-right: 8px; padding: 2px 9px; border-radius: 999px; background: #e2ecdc; color: var(--green); font-size: 12px; }
    @media (max-width: 640px) { main { width: min(100% - 20px, 960px); padding-top: 22px; } header { display: block; } header p { margin-top: 6px; } .card { padding: 9px; } }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>梅雨有数</h1>
        <p>60 秒纯配乐 · 动态文字 · 无配音</p>
      </div>
      <p><time datetime="2026-10-19">2026 年 10 月 19 日</time></p>
    </header>
    <section class="card" aria-label="梅雨有数 60 秒纯配乐动态文字宣传片">
      <video controls playsinline preload="metadata" poster="../media/promo60-music-cover.png" aria-describedby="viewing-tip">
        <source src="../media/promo60-music.mp4" type="video/mp4">
        <track kind="captions" srclang="zh-CN" label="可选文字轨" src="../media/promo60-music.vtt">
        当前浏览器不支持 HTML5 视频，请下载 MP4 文件查看。
      </video>
    </section>
    <p class="view-tip" id="viewing-tip">手机建议横屏或全屏观看，文字更清楚。</p>
    <nav class="links" aria-label="页面链接">
      <a href="../index.html">返回应用</a>
      <a href="../demo.html">查看历史演示</a>
      <a href="native.html">打开原生动画预览</a>
    </nav>
    <section class="note">
      <p><span class="tag">影片</span>本版包含 12 段动态文字和 7 个场景，只使用原创器乐，不含配音。画面中的文字是影片内容，播放器另外提供可选文字轨。</p>
      <p><span class="tag">日期</span>影片和制作素材对应 2026 年 10 月 19 日。影片不请求实时天气；在线播放会加载影片文件。应用页面按页面自身规则检查天气，并复用有效缓存。关闭页面后不会留下 Python 后台。</p>
      <p>完整人工听审尚未检查，技术检查不能代替人工看完和听完。源码和来源说明保留在仓库的 <code>media/latest/</code>。</p>
    </section>
  </main>
</body>
</html>
"""


def excluded_source_file(path: Path) -> bool:
    parts = {part.casefold() for part in path.parts}
    return (
        "__pycache__" in parts
        or path.suffix.casefold() in {".pyc", ".wav", ".h264"}
    )


def copy_latest_materials(root: Path, promo_dir: Path, latest: Path) -> None:
    remove_path(root, latest, recursive=True)
    latest.mkdir(parents=True, exist_ok=True)

    source = promo_dir / "source"
    for item in source.rglob("*"):
        if not item.is_file() or excluded_source_file(item.relative_to(source)):
            continue
        copy_file(item, latest / "source" / item.relative_to(source))

    top_level = {
        VIDEO_NAME: "promo60-music.mp4",
        "封面.png": "cover.png",
        "原创配乐.mp3": "soundtrack.mp3",
        "原创配乐.mid": "score.mid",
        "动态文字.srt": "subtitles.srt",
        "来源说明.md": "source-note.md",
        "预览.html": "preview.html",
    }
    for source_name, target_name in top_level.items():
        copy_file(promo_dir / source_name, latest / target_name)
    update_source_note(latest / "source-note.md")
    (latest / "subtitles.vtt").write_bytes(srt_to_vtt(promo_dir / "动态文字.srt"))


def build_pages(root: Path, promo_dir: Path | None) -> dict[str, str]:
    site = root / "site"
    latest = root / "media" / "latest"
    if promo_dir is not None:
        promo_dir = _validate_promo_dir(root, promo_dir)
    video = promo_dir / VIDEO_NAME if promo_dir is not None else latest / "promo60-music.mp4"
    if video.stat().st_size != EXPECTED_VIDEO_SIZE:
        raise ValueError(f"影片大小不符：{video.stat().st_size}，预期 {EXPECTED_VIDEO_SIZE}")
    video_hash = sha256(video)
    if video_hash != EXPECTED_VIDEO_SHA256:
        raise ValueError(f"影片 SHA-256 不符：{video_hash}，预期 {EXPECTED_VIDEO_SHA256}")

    if promo_dir is not None:
        copy_latest_materials(root, promo_dir, latest)
    elif not (latest / "subtitles.vtt").is_file():
        (latest / "subtitles.vtt").write_bytes(srt_to_vtt(latest / "subtitles.srt"))
    remove_path(root, site / "index.html", recursive=False)
    remove_path(root, site / "demo.html", recursive=False)
    remove_path(root, site / ".nojekyll", recursive=False)
    remove_path(root, site / "promo", recursive=True)
    remove_path(root, site / "media", recursive=True)
    site.mkdir(parents=True, exist_ok=True)

    copy_file(root / "index.html", site / "index.html")
    copy_file(root / "demo.html", site / "demo.html")
    copy_file(latest / "promo60-music.mp4", site / "media" / "promo60-music.mp4")
    copy_file(latest / "cover.png", site / "media" / "promo60-music-cover.png")
    (site / "media" / "promo60-music.vtt").write_bytes((latest / "subtitles.vtt").read_bytes())
    (site / ".nojekyll").write_bytes(b"")
    (site / "promo" / "index.html").parent.mkdir(parents=True, exist_ok=True)
    (site / "promo" / "index.html").write_text(promo_page(), encoding="utf-8", newline="\n")
    copy_file(latest / "preview.html", site / "promo" / "native.html")

    return {
        "video_size": str(video.stat().st_size),
        "video_sha256": video_hash,
        "site": str(site),
        "latest": str(latest),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构建梅雨有数 GitHub Pages 静态文件")
    parser.add_argument(
        "--promo-dir",
        type=Path,
        help="宣传片目录；默认按当前交付目录布局自动查找",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="项目根目录，默认是脚本所在项目",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    promo_dir = resolve_promo_dir(root, args.promo_dir)
    result = build_pages(root, promo_dir)
    print(f"已生成 {result['site']}")
    print(f"已保存 {result['latest']}")
    print(f"影片 {result['video_size']} 字节，SHA-256 {result['video_sha256']}")


if __name__ == "__main__":
    main()
