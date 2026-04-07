from __future__ import annotations

import shutil
import tempfile
from collections import Counter, deque
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from cells.log import get_logger

from .backends import Py7zrBackend, RarfileBackend, SevenZipCliBackend, TarfileBackend, ZipfileBackend
from .capabilities import probe_support
from .detector import detect_archive_type
from .errors import (
    ArchiveSecurityError,
    ArchiveSkippedError,
    ExtractionFailedError,
    InspectionFailedError,
    InvalidPasswordError,
    MissingDependencyError,
    PasswordRequiredError,
)
from .models import (
    ArchiveEntry,
    ArchiveExtractResult,
    ArchiveInspectResult,
    ArchiveType,
    BatchProcessResult,
    BatchStatistics,
    MemberLookupResult,
    PasswordPolicy,
    TaskReport,
    TaskStatus,
)
from .profiles import ArchiveProfile, get_profile
from .scanner import scan_archives
from .utils.filesystem import (
    ensure_output_dir,
    iter_archive_files,
    list_relative_files,
    safe_join,
    set_tree_writable,
    strip_archive_suffix,
)


_LOG = get_logger(__name__)


class ArchiveEngine:
    def __init__(self) -> None:
        self.backends = {
            "zipfile": ZipfileBackend(),
            "tarfile": TarfileBackend(),
            "7zcli": SevenZipCliBackend(),
            "py7zr": Py7zrBackend(),
            "rarfile": RarfileBackend(),
        }

    def support_report(self):
        return probe_support()

    def inspect_archive(
        self,
        file_path: str | Path,
        recursive: bool | None = None,
        profile: str | ArchiveProfile | None = None,
        password_policy: PasswordPolicy | None = None,
    ) -> ArchiveInspectResult:
        archive_path = Path(file_path)
        active_profile = get_profile(profile)
        active_password_policy = password_policy or PasswordPolicy()
        recursive_flag = active_profile.recursive_inspect if recursive is None else recursive
        warnings: list[str] = []
        temp_extraction_used = False
        archive_type = detect_archive_type(archive_path)

        try:
            backend, entries = self._inspect_single(
                archive_path,
                active_profile,
                warnings,
                password_policy=active_password_policy,
            )
            status = TaskStatus.SUCCESS
            skipped_reason = None
            encrypted_archive = any(entry.encrypted is True for entry in entries)
        except ArchiveSkippedError as exc:
            backend_name = exc.backend_name or self._best_effort_backend_name(archive_type, active_profile)
            warnings.append(str(exc))
            return ArchiveInspectResult(
                file_path=archive_path,
                archive_type=archive_type,
                backend_used=backend_name,
                entries=[],
                recursive=recursive_flag,
                warnings=warnings,
                temp_extraction_used=False,
                status=TaskStatus.SKIPPED,
                encrypted_archive=exc.encrypted,
                skipped_reason=str(exc),
                entries_count=0,
                encrypted_entries_count=0,
            )

        if recursive_flag:
            temp_extraction_used = True
            with tempfile.TemporaryDirectory(prefix="archivekit-inspect-") as temp_dir:
                temp_root = Path(temp_dir) / "root"
                try:
                    self._extract_single(
                        archive_path,
                        temp_root,
                        active_profile,
                        warnings=warnings,
                        password_policy=active_password_policy,
                    )
                except ArchiveSkippedError as exc:
                    warnings.append(str(exc))
                    status = TaskStatus.SKIPPED
                    skipped_reason = str(exc)
                    encrypted_archive = encrypted_archive or exc.encrypted
                else:
                    nested_entries, nested_warnings = self._inspect_nested_from_directory(
                        root_dir=temp_root,
                        profile=active_profile,
                        password_policy=active_password_policy,
                    )
                    entries.extend(nested_entries)
                    warnings.extend(nested_warnings)

        encrypted_entries_count = sum(1 for entry in entries if entry.encrypted is True)
        return ArchiveInspectResult(
            file_path=archive_path,
            archive_type=archive_type,
            backend_used=backend.name,
            entries=entries,
            recursive=recursive_flag,
            warnings=warnings,
            temp_extraction_used=temp_extraction_used,
            status=status,
            encrypted_archive=encrypted_archive or encrypted_entries_count > 0,
            skipped_reason=skipped_reason,
            entries_count=len(entries),
            encrypted_entries_count=encrypted_entries_count,
        )

    def extract_archive(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        recursive: bool | None = None,
        profile: str | ArchiveProfile | None = None,
        password_policy: PasswordPolicy | None = None,
    ) -> ArchiveExtractResult:
        archive_path = Path(file_path)
        active_profile = get_profile(profile)
        active_password_policy = password_policy or PasswordPolicy()
        recursive_flag = active_profile.recursive_extract if recursive is None else recursive
        archive_type = detect_archive_type(archive_path)
        target_dir = Path(output_dir) if output_dir is not None else strip_archive_suffix(archive_path)

        warnings: list[str] = []
        try:
            backend, skipped_reason = self._extract_single(
                archive_path,
                target_dir,
                active_profile,
                warnings=warnings,
                password_policy=active_password_policy,
            )
        except ArchiveSkippedError as exc:
            backend_name = exc.backend_name or self._best_effort_backend_name(archive_type, active_profile)
            warnings.append(str(exc))
            return ArchiveExtractResult(
                file_path=archive_path,
                archive_type=archive_type,
                backend_used=backend_name,
                output_dir=target_dir,
                extracted_files=[],
                nested_archives_processed=[],
                deleted_nested_archives=[],
                warnings=warnings,
                status=TaskStatus.SKIPPED,
                encrypted_archive=exc.encrypted,
                skipped_reason=str(exc),
                extracted_file_count=0,
                nested_archives_processed_count=0,
                deleted_nested_archives_count=0,
            )

        if skipped_reason:
            warnings.append(skipped_reason)

        nested_archives_processed: list[Path] = []
        deleted_nested_archives: list[Path] = []

        if recursive_flag:
            queue = deque([(target_dir, 1)])
            while queue:
                current_root, depth = queue.popleft()
                if active_profile.max_depth is not None and depth > active_profile.max_depth:
                    warnings.append(f"Max extraction depth reached at: {current_root}")
                    continue

                nested_archives = iter_archive_files(current_root)
                for nested_archive in nested_archives:
                    nested_output = strip_archive_suffix(nested_archive)
                    try:
                        _, nested_skip_reason = self._extract_single(
                            nested_archive,
                            nested_output,
                            active_profile,
                            warnings=warnings,
                            password_policy=active_password_policy,
                        )
                        if nested_skip_reason:
                            warnings.append(nested_skip_reason)
                            continue
                    except ArchiveSkippedError as exc:
                        warnings.append(str(exc))
                        continue
                    nested_archives_processed.append(nested_archive)
                    if active_profile.delete_nested_archives_after_extract:
                        nested_archive.unlink(missing_ok=True)
                        deleted_nested_archives.append(nested_archive)
                    queue.append((nested_output, depth + 1))

        if active_profile.chmod_writable and target_dir.exists():
            set_tree_writable(target_dir)

        extracted_files = (
            [target_dir / relative_path for relative_path in list_relative_files(target_dir)]
            if target_dir.exists()
            else []
        )
        return ArchiveExtractResult(
            file_path=archive_path,
            archive_type=archive_type,
            backend_used=backend.name,
            output_dir=target_dir,
            extracted_files=extracted_files,
            nested_archives_processed=nested_archives_processed,
            deleted_nested_archives=deleted_nested_archives,
            warnings=warnings,
            status=TaskStatus.SUCCESS,
            encrypted_archive=any("encrypted" in warning.lower() for warning in warnings),
            skipped_reason=None,
            extracted_file_count=len(extracted_files),
            nested_archives_processed_count=len(nested_archives_processed),
            deleted_nested_archives_count=len(deleted_nested_archives),
        )

    def read_member_bytes(
        self,
        file_path: str | Path,
        member_path: str,
        profile: str | ArchiveProfile | None = None,
        password_policy: PasswordPolicy | None = None,
    ) -> bytes:
        archive_path = Path(file_path)
        active_profile = get_profile(profile)
        active_password_policy = password_policy or PasswordPolicy()
        with tempfile.TemporaryDirectory(prefix="archivekit-read-") as temp_dir:
            temp_root = Path(temp_dir) / "root"
            self._extract_single(
                archive_path,
                temp_root,
                active_profile,
                password_policy=active_password_policy,
            )
            destination = safe_join(temp_root, member_path)
            if not destination.exists() or not destination.is_file():
                raise FileNotFoundError(f"Archive member not found: {member_path}")
            return destination.read_bytes()

    def read_member_text(
        self,
        file_path: str | Path,
        member_path: str,
        encoding: str = "utf-8",
        errors: str = "strict",
        profile: str | ArchiveProfile | None = None,
        password_policy: PasswordPolicy | None = None,
    ) -> str:
        content = self.read_member_bytes(
            file_path=file_path,
            member_path=member_path,
            profile=profile,
            password_policy=password_policy,
        )
        return content.decode(encoding, errors=errors)

    def member_exists(
        self,
        file_path: str | Path,
        member_path: str,
        profile: str | ArchiveProfile | None = None,
        password_policy: PasswordPolicy | None = None,
    ) -> MemberLookupResult:
        entries = self.list_member_paths(
            file_path=file_path,
            recursive=False,
            profile=profile,
            password_policy=password_policy,
        )
        exists = member_path in entries
        return MemberLookupResult(file_path=Path(file_path), member_path=member_path, exists=exists)

    def list_member_paths(
        self,
        file_path: str | Path,
        recursive: bool | None = None,
        profile: str | ArchiveProfile | None = None,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        result = self.inspect_archive(
            file_path=file_path,
            recursive=recursive,
            profile=profile,
            password_policy=password_policy,
        )
        return sorted({entry.relative_path for entry in result.entries})

    def batch_unpack(
        self,
        source_dir: str | Path,
        target_dir: str | Path | None = None,
        profile: str | ArchiveProfile | None = None,
        recursive_scan: bool = True,
        password_policy: PasswordPolicy | None = None,
    ) -> BatchProcessResult:
        root = Path(source_dir)
        target_root = Path(target_dir) if target_dir is not None else None
        active_profile = get_profile(profile)
        active_password_policy = password_policy or PasswordPolicy()
        archives = scan_archives(root, recursive=recursive_scan)
        reports: list[TaskReport] = []
        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        _LOG.info("archive.batch.started", operation="extract", source_path=str(root), total_tasks=len(archives))

        for archive_path in archives:
            task_started = perf_counter()
            archive_type = detect_archive_type(archive_path)
            try:
                if target_root is not None:
                    mirrored_base = target_root / archive_path.relative_to(root)
                    output_dir = strip_archive_suffix(mirrored_base)
                else:
                    output_dir = strip_archive_suffix(archive_path)
                result = self.extract_archive(
                    file_path=archive_path,
                    output_dir=output_dir,
                    recursive=active_profile.recursive_extract,
                    profile=active_profile,
                    password_policy=active_password_policy,
                )
                reports.append(
                    TaskReport(
                        source_path=archive_path,
                        operation="extract",
                        status=result.status,
                        success=result.status == TaskStatus.SUCCESS,
                        backend_used=result.backend_used,
                        archive_type=archive_type,
                        output_dir=result.output_dir,
                        warnings=result.warnings,
                        duration_seconds=perf_counter() - task_started,
                        extracted_file_count=result.extracted_file_count,
                        nested_archives_processed_count=result.nested_archives_processed_count,
                        deleted_nested_archives_count=result.deleted_nested_archives_count,
                        encrypted_archive=result.encrypted_archive,
                        skipped_reason=result.skipped_reason,
                    )
                )
            except Exception as exc:
                _LOG.error(
                    "archive.batch.task_failed",
                    operation="extract",
                    source_path=str(archive_path),
                    error_type=type(exc).__name__,
                )
                reports.append(
                    TaskReport(
                        source_path=archive_path,
                        operation="extract",
                        status=TaskStatus.FAILED,
                        success=False,
                        archive_type=archive_type,
                        errors=[str(exc)],
                        duration_seconds=perf_counter() - task_started,
                    )
                )

        finished_at = datetime.now(timezone.utc)
        duration_seconds = perf_counter() - started_clock
        success_count = sum(1 for report in reports if report.status == TaskStatus.SUCCESS)
        failed_count = sum(1 for report in reports if report.status == TaskStatus.FAILED)
        skipped_count = sum(1 for report in reports if report.status == TaskStatus.SKIPPED)
        statistics = self._build_statistics(reports)
        _LOG.info(
            "archive.batch.completed",
            operation="extract",
            total_tasks=len(reports),
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            duration_seconds=duration_seconds,
        )
        return BatchProcessResult(
            total_tasks=len(reports),
            success_count=success_count,
            failed_count=failed_count,
            reports=reports,
            statistics=statistics,
            operation="extract",
            source_root=root,
            target_root=target_root,
            profile_name=active_profile.name,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            skipped_count=skipped_count,
        )

    def batch_inspect(
        self,
        source_dir: str | Path,
        profile: str | ArchiveProfile | None = None,
        recursive_scan: bool = True,
        password_policy: PasswordPolicy | None = None,
    ) -> BatchProcessResult:
        root = Path(source_dir)
        active_profile = get_profile(profile)
        active_password_policy = password_policy or PasswordPolicy()
        archives = scan_archives(root, recursive=recursive_scan)
        reports: list[TaskReport] = []
        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        _LOG.info("archive.batch.started", operation="inspect", source_path=str(root), total_tasks=len(archives))

        for archive_path in archives:
            task_started = perf_counter()
            archive_type = detect_archive_type(archive_path)
            try:
                result = self.inspect_archive(
                    file_path=archive_path,
                    recursive=active_profile.recursive_inspect,
                    profile=active_profile,
                    password_policy=active_password_policy,
                )
                reports.append(
                    TaskReport(
                        source_path=archive_path,
                        operation="inspect",
                        status=result.status,
                        success=result.status == TaskStatus.SUCCESS,
                        backend_used=result.backend_used,
                        archive_type=archive_type,
                        warnings=result.warnings,
                        duration_seconds=perf_counter() - task_started,
                        entries_count=result.entries_count,
                        encrypted_archive=result.encrypted_archive,
                        skipped_reason=result.skipped_reason,
                    )
                )
            except Exception as exc:
                _LOG.error(
                    "archive.batch.task_failed",
                    operation="inspect",
                    source_path=str(archive_path),
                    error_type=type(exc).__name__,
                )
                reports.append(
                    TaskReport(
                        source_path=archive_path,
                        operation="inspect",
                        status=TaskStatus.FAILED,
                        success=False,
                        archive_type=archive_type,
                        errors=[str(exc)],
                        duration_seconds=perf_counter() - task_started,
                    )
                )

        finished_at = datetime.now(timezone.utc)
        duration_seconds = perf_counter() - started_clock
        success_count = sum(1 for report in reports if report.status == TaskStatus.SUCCESS)
        failed_count = sum(1 for report in reports if report.status == TaskStatus.FAILED)
        skipped_count = sum(1 for report in reports if report.status == TaskStatus.SKIPPED)
        statistics = self._build_statistics(reports)
        _LOG.info(
            "archive.batch.completed",
            operation="inspect",
            total_tasks=len(reports),
            success_count=success_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            duration_seconds=duration_seconds,
        )
        return BatchProcessResult(
            total_tasks=len(reports),
            success_count=success_count,
            failed_count=failed_count,
            reports=reports,
            statistics=statistics,
            operation="inspect",
            source_root=root,
            target_root=None,
            profile_name=active_profile.name,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            skipped_count=skipped_count,
        )

    def _select_backend(self, archive_type: ArchiveType, profile: ArchiveProfile | None = None):
        ordered_names = self._backend_order(archive_type)
        if profile is not None and not profile.allow_cli_fallback:
            ordered_names = [name for name in ordered_names if name != "7zcli"]
        for name in ordered_names:
            backend = self.backends[name]
            if backend.supports(archive_type) and backend.is_available():
                return backend

        support = probe_support()
        issue_lines = [issue.hint or issue.name for issue in support.dependency_issues]
        joined = "; ".join(issue_lines) if issue_lines else "No compatible backend found."
        _LOG.error(
            "archive.backend.unavailable",
            archive_type=archive_type.value,
            profile=profile.name if profile else None,
        )
        raise MissingDependencyError(f"No available backend for {archive_type.value}. Suggestions: {joined}")

    def _backend_order(self, archive_type: ArchiveType) -> list[str]:
        if archive_type == ArchiveType.ZIP:
            return ["zipfile", "7zcli"]
        if archive_type == ArchiveType.SEVEN_Z:
            return ["7zcli", "py7zr"]
        if archive_type == ArchiveType.RAR:
            return ["7zcli", "rarfile"]
        if archive_type in {ArchiveType.TAR, ArchiveType.TAR_GZ, ArchiveType.TAR_XZ}:
            return ["tarfile", "7zcli"]
        raise MissingDependencyError(f"Unsupported archive type ordering: {archive_type}")

    def _best_effort_backend_name(self, archive_type: ArchiveType, profile: ArchiveProfile) -> str:
        try:
            backend = self._select_backend(archive_type, profile)
            return backend.name
        except Exception:
            return "unknown"

    def _inspect_single(
        self,
        archive_path: Path,
        profile: ArchiveProfile,
        warnings: list[str] | None = None,
        password_policy: PasswordPolicy | None = None,
    ):
        warnings = warnings if warnings is not None else []
        archive_type = detect_archive_type(archive_path)
        self._validate_archive_file(archive_path)
        self._select_backend(archive_type, profile)
        backend_errors: list[str] = []
        failed_backends: list[str] = []
        ordered_names = self._backend_order(archive_type)
        if not profile.allow_cli_fallback:
            ordered_names = [name for name in ordered_names if name != "7zcli"]

        for name in ordered_names:
            backend = self.backends[name]
            if not backend.supports(archive_type) or not backend.is_available():
                continue
            try:
                entries = backend.inspect(archive_path, password_policy=password_policy)
                if backend_errors:
                    warnings.append(f"Inspect fallback used for {archive_path.name}: {' | '.join(backend_errors)}")
                    _LOG.warning(
                        "archive.backend.fallback",
                        operation="inspect",
                        source_path=str(archive_path),
                        backend=name,
                        failed_backends=failed_backends,
                    )
                _LOG.debug(
                    "archive.inspect.completed",
                    source_path=str(archive_path),
                    backend=name,
                    entries_count=len(entries),
                )
                return backend, entries
            except ArchiveSkippedError:
                _LOG.warning("archive.skipped", operation="inspect", source_path=str(archive_path), backend=name)
                raise
            except (
                ArchiveSecurityError,
                PasswordRequiredError,
                InvalidPasswordError,
            ) as exc:
                _LOG.warning(
                    "archive.rejected",
                    operation="inspect",
                    source_path=str(archive_path),
                    backend=name,
                    error_type=type(exc).__name__,
                )
                raise
            except Exception as exc:
                failed_backends.append(name)
                _LOG.debug(
                    "archive.backend.failed",
                    operation="inspect",
                    source_path=str(archive_path),
                    backend=name,
                    error_type=type(exc).__name__,
                )
                backend_errors.append(f"{name}: {exc}")
                continue

        joined = " | ".join(backend_errors) if backend_errors else "No backend attempted."
        _LOG.error(
            "archive.failed",
            operation="inspect",
            source_path=str(archive_path),
            failed_backends=failed_backends,
        )
        raise InspectionFailedError(f"Failed to inspect {archive_path}. {joined}")

    def _extract_single(
        self,
        archive_path: Path,
        output_dir: Path,
        profile: ArchiveProfile,
        warnings: list[str] | None = None,
        password_policy: PasswordPolicy | None = None,
    ):
        warnings = warnings if warnings is not None else []
        archive_type = detect_archive_type(archive_path)
        self._validate_archive_file(archive_path)
        resolved_output = output_dir.resolve()
        resolved_archive = archive_path.resolve()
        if resolved_output == resolved_archive or resolved_output in resolved_archive.parents:
            raise ArchiveSecurityError("Output directory must not contain the source archive.")
        if output_dir.is_symlink():
            raise ArchiveSecurityError("Output directory must not be a symbolic link.")
        self._select_backend(archive_type, profile)
        backend_errors: list[str] = []
        failed_backends: list[str] = []
        ordered_names = self._backend_order(archive_type)
        if not profile.allow_cli_fallback:
            ordered_names = [name for name in ordered_names if name != "7zcli"]

        for name in ordered_names:
            backend = self.backends[name]
            if not backend.supports(archive_type) or not backend.is_available():
                continue
            ensure_output_dir(output_dir, overwrite=profile.overwrite)
            try:
                backend_warnings = backend.extract(
                    archive_path,
                    output_dir,
                    password_policy=password_policy,
                )
                if backend_errors:
                    warnings.append(f"Extraction fallback used for {archive_path.name}: {' | '.join(backend_errors)}")
                    _LOG.warning(
                        "archive.backend.fallback",
                        operation="extract",
                        source_path=str(archive_path),
                        backend=name,
                        failed_backends=failed_backends,
                    )
                warnings.extend(backend_warnings)
                if backend_warnings:
                    _LOG.warning(
                        "archive.extract.partial",
                        source_path=str(archive_path),
                        backend=name,
                        warning_count=len(backend_warnings),
                    )
                _LOG.debug("archive.extract.completed", source_path=str(archive_path), backend=name)
                return backend, None
            except (
                ArchiveSkippedError,
                ArchiveSecurityError,
                PasswordRequiredError,
                InvalidPasswordError,
            ) as exc:
                _LOG.warning(
                    "archive.skipped" if isinstance(exc, ArchiveSkippedError) else "archive.rejected",
                    operation="extract",
                    source_path=str(archive_path),
                    backend=name,
                    error_type=type(exc).__name__,
                )
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                raise
            except Exception as exc:
                failed_backends.append(name)
                _LOG.debug(
                    "archive.backend.failed",
                    operation="extract",
                    source_path=str(archive_path),
                    backend=name,
                    error_type=type(exc).__name__,
                )
                backend_errors.append(f"{name}: {exc}")
                if output_dir.exists():
                    shutil.rmtree(output_dir)
                continue

        joined = " | ".join(backend_errors) if backend_errors else "No backend attempted."
        _LOG.error(
            "archive.failed",
            operation="extract",
            source_path=str(archive_path),
            failed_backends=failed_backends,
        )
        raise ExtractionFailedError(f"Failed to extract {archive_path}. {joined}")

    def _inspect_nested_from_directory(
        self,
        root_dir: Path,
        profile: ArchiveProfile,
        password_policy: PasswordPolicy | None = None,
    ) -> tuple[list[ArchiveEntry], list[str]]:
        queue = deque((path, 1, path.relative_to(root_dir).as_posix()) for path in iter_archive_files(root_dir))

        with ExitStack() as temporary_directories:
            return self._inspect_nested_queue(queue, profile, password_policy, temporary_directories)

    def _inspect_nested_queue(
        self,
        queue: deque[tuple[Path, int, str]],
        profile: ArchiveProfile,
        password_policy: PasswordPolicy | None,
        temporary_directories: ExitStack,
    ) -> tuple[list[ArchiveEntry], list[str]]:
        nested_entries: list[ArchiveEntry] = []
        warnings: list[str] = []
        while queue:
            archive_path, depth, source_archive = queue.popleft()
            if profile.max_depth is not None and depth > profile.max_depth:
                warnings.append(f"Max inspect depth reached at: {archive_path}")
                continue

            try:
                _, entries = self._inspect_single(
                    archive_path,
                    profile,
                    warnings,
                    password_policy=password_policy,
                )
            except ArchiveSkippedError as exc:
                warnings.append(str(exc))
                continue

            for entry in entries:
                nested_entries.append(
                    ArchiveEntry(
                        relative_path=entry.relative_path,
                        is_dir=entry.is_dir,
                        size=entry.size,
                        compressed_size=entry.compressed_size,
                        source_archive=source_archive,
                        depth=depth,
                        encrypted=entry.encrypted,
                    )
                )

            if profile.max_depth is not None and depth >= profile.max_depth:
                continue
            temp_dir = temporary_directories.enter_context(tempfile.TemporaryDirectory(prefix="archivekit-nested-"))
            temp_root = Path(temp_dir) / "root"
            try:
                self._extract_single(
                    archive_path,
                    temp_root,
                    profile,
                    warnings=warnings,
                    password_policy=password_policy,
                )
            except ArchiveSkippedError as exc:
                warnings.append(str(exc))
                continue
            for child in iter_archive_files(temp_root):
                child_source = f"{source_archive}!/{child.relative_to(temp_root).as_posix()}"
                queue.append((child, depth + 1, child_source))

        return nested_entries, warnings

    @staticmethod
    def _validate_archive_file(archive_path: Path) -> None:
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")
        if not archive_path.is_file():
            raise IsADirectoryError(f"Archive must be a file: {archive_path}")

    @staticmethod
    def _build_statistics(reports: list[TaskReport]) -> BatchStatistics:
        status_counter = Counter(report.status.value for report in reports)
        type_counter = Counter(report.archive_type.value for report in reports if report.archive_type is not None)
        return BatchStatistics(
            warning_count=sum(len(report.warnings) for report in reports),
            error_count=sum(len(report.errors) for report in reports),
            skipped_count=status_counter.get(TaskStatus.SKIPPED.value, 0),
            encrypted_archive_count=sum(1 for report in reports if report.encrypted_archive),
            total_entries_inspected=sum(report.entries_count for report in reports),
            total_files_extracted=sum(report.extracted_file_count for report in reports),
            total_nested_archives_processed=sum(report.nested_archives_processed_count for report in reports),
            total_deleted_nested_archives=sum(report.deleted_nested_archives_count for report in reports),
            archive_type_breakdown=dict(type_counter),
            status_breakdown=dict(status_counter),
        )
