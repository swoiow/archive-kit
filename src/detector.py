from __future__ import annotations

from pathlib import Path

from .errors import UnsupportedArchiveError
from .models import ArchiveType


SUFFIX_PATTERNS: list[tuple[str, ArchiveType]] = [
    (".tar.gz", ArchiveType.TAR_GZ),
    (".tar.xz", ArchiveType.TAR_XZ),
    (".tgz", ArchiveType.TAR_GZ),
    (".txz", ArchiveType.TAR_XZ),
    (".zip", ArchiveType.ZIP),
    (".7z", ArchiveType.SEVEN_Z),
    (".rar", ArchiveType.RAR),
    (".tar", ArchiveType.TAR),
]


def detect_archive_type(file_path: str | Path) -> ArchiveType:
    path = Path(file_path)
    lower_name = path.name.lower()
    for suffix, archive_type in SUFFIX_PATTERNS:
        if lower_name.endswith(suffix):
            return archive_type
    supported = ", ".join(sorted(suffix for suffix, _ in SUFFIX_PATTERNS))
    raise UnsupportedArchiveError(f"Unsupported archive type for {path.name}. Supported suffixes: {supported}.")


def detect_archive_suffix(file_path: str | Path) -> str:
    path = Path(file_path)
    lower_name = path.name.lower()
    for suffix, _ in SUFFIX_PATTERNS:
        if lower_name.endswith(suffix):
            return suffix
    supported = ", ".join(sorted(suffix for suffix, _ in SUFFIX_PATTERNS))
    raise UnsupportedArchiveError(f"Unsupported archive type for {path.name}. Supported suffixes: {supported}.")
