from __future__ import annotations

from pathlib import Path

from .utils.filesystem import path_looks_like_archive


def scan_archives(
    source_dir: str | Path,
    recursive: bool = True,
) -> list[Path]:
    root = Path(source_dir)
    if not root.exists():
        raise FileNotFoundError(f"Source directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Source must be a directory: {root}")
    if recursive:
        iterator = root.rglob("*")
    else:
        iterator = root.glob("*")

    bucket: list[Path] = []
    for path in iterator:
        if path.is_file() and path_looks_like_archive(path):
            bucket.append(path)
    return sorted(bucket)
