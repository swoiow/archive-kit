from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from ..detector import detect_archive_suffix
from ..errors import ArchiveSecurityError


ARCHIVE_SUFFIX_PATTERNS = {".zip", ".7z", ".rar", ".tar", ".tar.gz", ".tar.xz", ".tgz", ".txz"}


def path_looks_like_archive(path: Path) -> bool:
    lower_name = path.name.lower()
    return any(lower_name.endswith(suffix) for suffix in ARCHIVE_SUFFIX_PATTERNS)


def strip_archive_suffix(path: Path) -> Path:
    suffix = detect_archive_suffix(path)
    stripped_name = path.name[: -len(suffix)]
    return path.with_name(stripped_name)


def ensure_output_dir(path: Path, overwrite: bool) -> None:
    if path.exists():
        if path.is_dir() and not any(path.iterdir()):
            return
        if not overwrite:
            raise FileExistsError(f"Output directory already exists: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def safe_join(root: Path, member_name: str) -> Path:
    destination = (root / member_name).resolve()
    if root.resolve() not in destination.parents and destination != root.resolve():
        raise ArchiveSecurityError(f"Unsafe archive member path: {member_name}")
    return destination


def set_tree_writable(root: Path) -> None:
    for current_root, _, files in os.walk(root):
        current_root_path = Path(current_root)
        for filename in files:
            file_path = current_root_path / filename
            try:
                os.chmod(file_path, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                continue


def list_relative_files(root: Path) -> list[Path]:
    bucket: list[Path] = []
    for current_root, _, files in os.walk(root):
        current_root_path = Path(current_root)
        for filename in files:
            bucket.append((current_root_path / filename).relative_to(root))
    return sorted(bucket)


def iter_archive_files(root: Path) -> list[Path]:
    bucket: list[Path] = []
    for current_root, _, files in os.walk(root):
        current_root_path = Path(current_root)
        for filename in files:
            file_path = current_root_path / filename
            if path_looks_like_archive(file_path):
                bucket.append(file_path)
    return sorted(bucket)
