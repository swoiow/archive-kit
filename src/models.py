from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class ArchiveType(str, Enum):
    ZIP = "zip"
    SEVEN_Z = "7z"
    RAR = "rar"
    TAR = "tar"
    TAR_GZ = "tar.gz"
    TAR_XZ = "tar.xz"


class PasswordStrategy(str, Enum):
    RAISE = "raise"
    SKIP = "skip"


class TaskStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class PasswordPolicy:
    passwords: tuple[str, ...] = ()
    missing_password_strategy: PasswordStrategy = PasswordStrategy.SKIP
    invalid_password_strategy: PasswordStrategy = PasswordStrategy.SKIP


@dataclass(frozen=True)
class ArchiveEntry:
    relative_path: str
    is_dir: bool
    size: int | None = None
    compressed_size: int | None = None
    source_archive: str | None = None
    depth: int = 0
    encrypted: bool | None = None


@dataclass(frozen=True)
class DependencyIssue:
    name: str
    installed: bool
    required_for: list[str]
    hint: str | None = None
    details: str | None = None


@dataclass(frozen=True)
class BackendCapability:
    name: str
    available: bool
    details: str | None = None


@dataclass(frozen=True)
class ArchiveSupportReport:
    backend_capabilities: list[BackendCapability]
    dependency_issues: list[DependencyIssue]
    supported_types: list[str]
    preferred_executable: str | None = None


@dataclass
class ArchiveInspectResult:
    file_path: Path
    archive_type: ArchiveType
    backend_used: str
    entries: list[ArchiveEntry]
    recursive: bool
    warnings: list[str] = field(default_factory=list)
    temp_extraction_used: bool = False
    status: TaskStatus = TaskStatus.SUCCESS
    encrypted_archive: bool = False
    skipped_reason: str | None = None
    entries_count: int = 0
    encrypted_entries_count: int = 0


@dataclass
class ArchiveExtractResult:
    file_path: Path
    archive_type: ArchiveType
    backend_used: str
    output_dir: Path
    extracted_files: list[Path]
    nested_archives_processed: list[Path]
    deleted_nested_archives: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.SUCCESS
    encrypted_archive: bool = False
    skipped_reason: str | None = None
    extracted_file_count: int = 0
    nested_archives_processed_count: int = 0
    deleted_nested_archives_count: int = 0


@dataclass
class TaskReport:
    source_path: Path
    operation: str
    status: TaskStatus
    success: bool
    backend_used: str | None = None
    archive_type: ArchiveType | None = None
    output_dir: Path | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float | None = None
    entries_count: int = 0
    extracted_file_count: int = 0
    nested_archives_processed_count: int = 0
    deleted_nested_archives_count: int = 0
    encrypted_archive: bool = False
    skipped_reason: str | None = None


@dataclass
class BatchStatistics:
    warning_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    encrypted_archive_count: int = 0
    total_entries_inspected: int = 0
    total_files_extracted: int = 0
    total_nested_archives_processed: int = 0
    total_deleted_nested_archives: int = 0
    archive_type_breakdown: dict[str, int] = field(default_factory=dict)
    status_breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class BatchProcessResult:
    total_tasks: int
    success_count: int
    failed_count: int
    reports: list[TaskReport]
    statistics: BatchStatistics
    operation: str
    source_root: Path
    target_root: Path | None = None
    profile_name: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    skipped_count: int = 0


@dataclass(frozen=True)
class MemberLookupResult:
    file_path: Path
    member_path: str
    exists: bool
