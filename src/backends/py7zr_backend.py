from __future__ import annotations

from pathlib import Path

from ..capabilities import probe_support
from ..errors import (
    ArchiveSkippedError,
    ExtractionFailedError,
    InspectionFailedError,
    InvalidPasswordError,
    MissingDependencyError,
    PasswordRequiredError,
)
from ..models import ArchiveEntry, ArchiveType, PasswordPolicy, PasswordStrategy
from .base import ArchiveBackend


class Py7zrBackend(ArchiveBackend):
    name = "py7zr"

    def is_available(self) -> bool:
        report = probe_support()
        return any(item.name == self.name and item.available for item in report.backend_capabilities)

    def supports(self, archive_type: ArchiveType) -> bool:
        return archive_type == ArchiveType.SEVEN_Z

    def inspect(
        self,
        archive_path: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[ArchiveEntry]:
        if not self.is_available():
            raise MissingDependencyError("py7zr is not installed. Run: pip install py7zr")

        try:
            import py7zr  # type: ignore
        except ImportError as exc:
            raise MissingDependencyError("py7zr is not installed. Run: pip install py7zr") from exc

        active_policy = password_policy or PasswordPolicy()
        candidates = [None]
        if active_policy.passwords:
            candidates.extend(active_policy.passwords)

        errors: list[str] = []
        for candidate in candidates:
            try:
                with py7zr.SevenZipFile(archive_path, mode="r", password=candidate) as archive:
                    entries: list[ArchiveEntry] = []
                    for item in archive.list():
                        entries.append(
                            ArchiveEntry(
                                relative_path=item.filename,
                                is_dir=item.is_directory,
                                size=item.uncompressed,
                                compressed_size=item.compressed,
                                source_archive=archive_path.name,
                                depth=0,
                                encrypted=None,
                            )
                        )
                    return entries
            except Exception as exc:
                errors.append(str(exc))
                continue

        if active_policy.passwords:
            if active_policy.invalid_password_strategy == PasswordStrategy.SKIP:
                raise ArchiveSkippedError(
                    f"Skipped password-protected 7z during inspect due to invalid password(s): {archive_path.name}",
                    encrypted=True,
                    backend_name=self.name,
                )
            raise InvalidPasswordError(f"Invalid password for 7z archive: {archive_path}")

        if active_policy.missing_password_strategy == PasswordStrategy.SKIP:
            raise ArchiveSkippedError(
                f"Skipped password-protected 7z during inspect without password: {archive_path.name}",
                encrypted=True,
                backend_name=self.name,
            )
        raise PasswordRequiredError(f"Password required for 7z archive: {archive_path}")

    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        if not self.is_available():
            raise MissingDependencyError("py7zr is not installed. Run: pip install py7zr")

        try:
            import py7zr  # type: ignore
        except ImportError as exc:
            raise MissingDependencyError("py7zr is not installed. Run: pip install py7zr") from exc

        active_policy = password_policy or PasswordPolicy()
        candidates = [None]
        if active_policy.passwords:
            candidates.extend(active_policy.passwords)

        errors: list[str] = []
        for candidate in candidates:
            try:
                with py7zr.SevenZipFile(archive_path, mode="r", password=candidate) as archive:
                    archive.extractall(path=output_dir)
                return []
            except Exception as exc:
                errors.append(str(exc))
                continue

        if active_policy.passwords:
            if active_policy.invalid_password_strategy == PasswordStrategy.SKIP:
                raise ArchiveSkippedError(
                    f"Skipped password-protected 7z due to invalid password(s): {archive_path.name}",
                    encrypted=True,
                    backend_name=self.name,
                )
            raise InvalidPasswordError(
                f"Invalid password for 7z archive: {archive_path}. Details: {' | '.join(errors)}"
            )

        if active_policy.missing_password_strategy == PasswordStrategy.SKIP:
            raise ArchiveSkippedError(
                f"Skipped password-protected 7z without password: {archive_path.name}",
                encrypted=True,
                backend_name=self.name,
            )
        raise PasswordRequiredError(f"Password required for 7z archive: {archive_path}. Details: {' | '.join(errors)}")
