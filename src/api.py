from __future__ import annotations

from pathlib import Path

from .capabilities import probe_support as _probe_support
from .engine import ArchiveEngine
from .models import (
    ArchiveExtractResult,
    ArchiveInspectResult,
    ArchiveSupportReport,
    BatchProcessResult,
    MemberLookupResult,
    PasswordPolicy,
)
from .profiles import ArchiveProfile
from .reporting import batch_result_to_dict, write_batch_report_json

_ENGINE = ArchiveEngine()


def probe_support() -> ArchiveSupportReport:
    return _probe_support()


def inspect_one(
    file_path: str | Path,
    recursive: bool | None = None,
    profile: str | ArchiveProfile | None = None,
    password_policy: PasswordPolicy | None = None,
) -> ArchiveInspectResult:
    return _ENGINE.inspect_archive(
        file_path=file_path,
        recursive=recursive,
        profile=profile,
        password_policy=password_policy,
    )


def unpack_one(
    file_path: str | Path,
    output_dir: str | Path | None = None,
    recursive: bool | None = None,
    profile: str | ArchiveProfile | None = None,
    password_policy: PasswordPolicy | None = None,
) -> ArchiveExtractResult:
    return _ENGINE.extract_archive(
        file_path=file_path,
        output_dir=output_dir,
        recursive=recursive,
        profile=profile,
        password_policy=password_policy,
    )


def read_member_bytes(
    file_path: str | Path,
    member_path: str,
    profile: str | ArchiveProfile | None = None,
    password_policy: PasswordPolicy | None = None,
) -> bytes:
    return _ENGINE.read_member_bytes(
        file_path=file_path,
        member_path=member_path,
        profile=profile,
        password_policy=password_policy,
    )


def read_member_text(
    file_path: str | Path,
    member_path: str,
    encoding: str = "utf-8",
    errors: str = "strict",
    profile: str | ArchiveProfile | None = None,
    password_policy: PasswordPolicy | None = None,
) -> str:
    return _ENGINE.read_member_text(
        file_path=file_path,
        member_path=member_path,
        encoding=encoding,
        errors=errors,
        profile=profile,
        password_policy=password_policy,
    )


def member_exists(
    file_path: str | Path,
    member_path: str,
    profile: str | ArchiveProfile | None = None,
    password_policy: PasswordPolicy | None = None,
) -> MemberLookupResult:
    return _ENGINE.member_exists(
        file_path=file_path,
        member_path=member_path,
        profile=profile,
        password_policy=password_policy,
    )


def list_member_paths(
    file_path: str | Path,
    recursive: bool | None = None,
    profile: str | ArchiveProfile | None = None,
    password_policy: PasswordPolicy | None = None,
) -> list[str]:
    return _ENGINE.list_member_paths(
        file_path=file_path,
        recursive=recursive,
        profile=profile,
        password_policy=password_policy,
    )


def batch_unpack(
    source_dir: str | Path,
    target_dir: str | Path | None = None,
    profile: str | ArchiveProfile | None = None,
    recursive_scan: bool = True,
    password_policy: PasswordPolicy | None = None,
) -> BatchProcessResult:
    return _ENGINE.batch_unpack(
        source_dir=source_dir,
        target_dir=target_dir,
        profile=profile,
        recursive_scan=recursive_scan,
        password_policy=password_policy,
    )


def batch_inspect(
    source_dir: str | Path,
    profile: str | ArchiveProfile | None = None,
    recursive_scan: bool = True,
    password_policy: PasswordPolicy | None = None,
) -> BatchProcessResult:
    return _ENGINE.batch_inspect(
        source_dir=source_dir,
        profile=profile,
        recursive_scan=recursive_scan,
        password_policy=password_policy,
    )


__all__ = [
    "batch_inspect",
    "batch_result_to_dict",
    "batch_unpack",
    "inspect_one",
    "list_member_paths",
    "member_exists",
    "probe_support",
    "read_member_bytes",
    "read_member_text",
    "unpack_one",
    "write_batch_report_json",
]
