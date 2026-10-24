"""把《梅雨有数》交付目录打成可审查 ZIP。

打包器只读取 root 下明确允许的顶层文件和目录。它不跟随符号链接，
也不会把 ZIP 自身或开发环境放进包内。``reports/package_manifest.json``
记录包内文件的 SHA-256 与字节数；清单自身记录字节数但明确不自哈希，
ZIP 的摘要由外部 QA 记录。
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable
import zipfile


PACKAGE_ROOT_NAME = "meiyu"
MANIFEST_RELATIVE_PATH = Path("reports/package_manifest.json")

ALLOWED_TOP_LEVEL_FILES = frozenset(
    {
        "app.py",
        "demo.html",
        "index.html",
        "README.md",
        "README.en.md",
        "LICENSE",
        "requirements.txt",
        "requirements-decision.txt",
        "setup.ps1",
        "setup-decision.ps1",
        "start.ps1",
        "start.cmd",
        "start-decision.ps1",
        "start-decision.cmd",
        ".gitignore",
        ".gitattributes",
    }
)
ALLOWED_TOP_LEVEL_DIRECTORIES = frozenset(
    {
        "src",
        "tests",
        "config",
        "data",
        "artifacts",
        "reports",
        "docs",
        "external",
        "media",
        "templates",
        "tools",
        "en",
        "presentations",
        ".streamlit",
    }
)
EXCLUDED_RELATIVE_DIRECTORIES = frozenset({"reports/internal", "reports/续接核验_20261015"})

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "node_modules",
    }
)
EXCLUDED_FILE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "secrets.toml",
        ".coverage",
        "coverage.xml",
        ".DS_Store",
        "Thumbs.db",
    }
)
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".tmp", ".temp", ".swp", ".swo", ".bak"})
PRIVATE_KEY_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx", ".der"})
PRIVATE_KEY_NAMES = frozenset({"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "private_key"})
TEMP_NAME_RE = re.compile(r"(?:^~\$|~$|^\.#[^/]+$)")


class PackagingError(RuntimeError):
    """输入目录或包边界不满足发布规则。"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PackagingError(f"无法读取文件：{path}") from exc
    return digest.hexdigest()


def _inside_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_private_or_temporary(name: str) -> bool:
    lowered = name.lower()
    if name in EXCLUDED_FILE_NAMES or lowered in EXCLUDED_FILE_NAMES or lowered == ".env" or lowered.startswith(".env."):
        return True
    if lowered.endswith(tuple(EXCLUDED_SUFFIXES | PRIVATE_KEY_SUFFIXES)):
        return True
    if lowered in PRIVATE_KEY_NAMES:
        return True
    if TEMP_NAME_RE.search(name):
        return True
    return False


def _iter_allowed_files(root: Path, output_path: Path | None = None) -> tuple[list[Path], dict[str, list[str]]]:
    """Return regular files under the explicit allow-list without following links."""

    root = root.resolve()
    output_resolved = output_path.resolve(strict=False) if output_path is not None else None
    files: list[Path] = []
    excluded: dict[str, list[str]] = {"top_level": [], "directories": [], "files": [], "symlinks": []}

    def accept_file(path: Path, relative: Path) -> None:
        if path.is_symlink():
            excluded["symlinks"].append(relative.as_posix())
            return
        resolved = path.resolve(strict=False)
        if not _inside_root(resolved, root):
            raise PackagingError(f"文件解析后越出 root，拒绝打包：{relative.as_posix()}")
        if output_resolved is not None and resolved == output_resolved:
            excluded["files"].append(f"{relative.as_posix()} (output zip)")
            return
        if _is_private_or_temporary(path.name):
            excluded["files"].append(relative.as_posix())
            return
        if not path.is_file():
            excluded["files"].append(relative.as_posix())
            return
        files.append(path)

    def walk_directory(directory: Path, relative_directory: Path) -> None:
        if directory.is_symlink():
            excluded["symlinks"].append(relative_directory.as_posix())
            return
        resolved_directory = directory.resolve(strict=False)
        if not _inside_root(resolved_directory, root):
            raise PackagingError(f"目录解析后越出 root，拒绝打包：{relative_directory.as_posix()}")
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise PackagingError(f"无法遍历目录：{directory}") from exc
        for entry in entries:
            relative = relative_directory / entry.name
            if entry.is_symlink():
                excluded["symlinks"].append(relative.as_posix())
                continue
            if entry.is_dir():
                if relative.as_posix() in EXCLUDED_RELATIVE_DIRECTORIES or entry.name in EXCLUDED_DIRECTORY_NAMES or _is_private_or_temporary(entry.name):
                    excluded["directories"].append(relative.as_posix())
                    continue
                walk_directory(entry, relative)
            else:
                accept_file(entry, relative)

    try:
        top_entries = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except OSError as exc:
        raise PackagingError(f"无法遍历 root：{root}") from exc
    for entry in top_entries:
        name = entry.name
        if entry.is_symlink():
            excluded["symlinks"].append(name)
            continue
        if entry.is_file():
            if name in ALLOWED_TOP_LEVEL_FILES:
                accept_file(entry, Path(name))
            else:
                excluded["top_level"].append(name)
        elif entry.is_dir():
            if name in ALLOWED_TOP_LEVEL_DIRECTORIES:
                walk_directory(entry, Path(name))
            else:
                excluded["top_level"].append(name)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix()), excluded


def _manifest_entry(root: Path, path: Path) -> dict[str, Any]:
    relative = path.relative_to(root).as_posix()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PackagingError(f"无法读取文件大小：{path}") from exc
    return {"path": relative, "bytes": int(size), "sha256": _sha256(path)}


def _write_manifest(root: Path, files: Iterable[Path], excluded: dict[str, list[str]]) -> Path:
    manifest_path = root / MANIFEST_RELATIVE_PATH
    if manifest_path.is_symlink():
        raise PackagingError(f"清单路径是符号链接，拒绝覆盖：{manifest_path}")
    entries = [_manifest_entry(root, path) for path in files if path != manifest_path]
    self_entry = {
        "path": MANIFEST_RELATIVE_PATH.as_posix(),
        "bytes": None,
        "sha256": None,
        "self_manifest": True,
    }
    entries.append(self_entry)
    entries.sort(key=lambda item: item["path"])
    manifest = {
        "schema_version": "meiyu-package-v1",
        "package_root": PACKAGE_ROOT_NAME,
        "generated_at_utc": _utc_now(),
        "file_count": len(entries),
        "hash_algorithm": "SHA-256",
        "hash_policy": "逐文件记录字节数与SHA-256；本文件列出但不自哈希，ZIP摘要由外部QA记录。",
        "allowed_top_level_files": sorted(ALLOWED_TOP_LEVEL_FILES),
        "allowed_top_level_directories": sorted(ALLOWED_TOP_LEVEL_DIRECTORIES),
        "excluded": excluded,
        "files": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(8):
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        actual_bytes = manifest_path.stat().st_size
        if self_entry["bytes"] == actual_bytes:
            break
        self_entry["bytes"] = actual_bytes
    else:
        raise PackagingError("无法稳定记录 package_manifest.json 的字节数。")
    return manifest_path


def build_package(root: Path, output: Path) -> dict[str, Any]:
    """Create one ``meiyu/`` rooted ZIP and its source package manifest."""

    root = Path(root).expanduser().resolve()
    output = Path(output).expanduser().resolve(strict=False)
    if output.suffix.lower() != ".zip":
        raise PackagingError("output 必须以 .zip 结尾，不能覆盖源码或数据文件。")
    if not root.is_dir():
        raise PackagingError(f"root 不是目录：{root}")
    if output == root or output.is_dir():
        raise PackagingError(f"output 必须是 ZIP 文件路径：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    files, excluded = _iter_allowed_files(root, output)
    manifest_path = _write_manifest(root, files, excluded)
    files, excluded_after = _iter_allowed_files(root, output)
    # The newly written manifest is the only expected addition. If an input
    # changes during preparation, fail instead of producing a partial audit.
    expected_paths = {path.relative_to(root).as_posix() for path in files}
    manifest_relative = MANIFEST_RELATIVE_PATH.as_posix()
    if manifest_relative not in expected_paths:
        raise PackagingError("写入后找不到 package_manifest.json。")
    if excluded_after != excluded:
        excluded = excluded_after
        manifest_path = _write_manifest(root, [path for path in files if path != manifest_path], excluded)
        files, excluded = _iter_allowed_files(root, output)
    if output.exists():
        try:
            output.unlink()
        except OSError as exc:
            raise PackagingError(f"无法覆盖已有 ZIP：{output}") from exc
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            archive.write(path, arcname=f"{PACKAGE_ROOT_NAME}/{relative}")
    zip_sha256 = _sha256(output)
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "root": str(root),
        "output": str(output),
        "zip_sha256": zip_sha256,
        "zip_bytes": output.stat().st_size,
        "file_count": len(files),
        "manifest_path": str(manifest_path),
        "manifest_file_count": manifest_data.get("file_count"),
        "excluded": excluded,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="打包梅雨有数交付目录")
    parser.add_argument("--root", type=Path, required=True, help="交付目录")
    parser.add_argument("--output", type=Path, required=True, help="候选 ZIP 路径")
    args = parser.parse_args(argv)
    try:
        result = build_package(args.root, args.output)
    except (OSError, PackagingError, ValueError, zipfile.BadZipFile) as exc:
        print(f"打包失败：{exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
