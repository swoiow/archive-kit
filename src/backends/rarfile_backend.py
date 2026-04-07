from __future__ import annotations

import shutil
from pathlib import Path

from ..capabilities import probe_support
from ..errors import (
    ExtractionFailedError,
    InspectionFailedError,
    InvalidPasswordError,
    MissingDependencyError,
    PasswordRequiredError,
)
from ..models import ArchiveEntry, ArchiveType, PasswordPolicy, PasswordStrategy
from ..utils.encoding import fix_filename
from ..utils.filesystem import safe_join
from .base import ArchiveBackend


class RarfileBackend(ArchiveBackend):
    name = "rarfile"

    def is_available(self) -> bool:
        report = probe_support()
        return any(item.name == self.name and item.available for item in report.backend_capabilities)

    def supports(self, archive_type: ArchiveType) -> bool:
        return archive_type == ArchiveType.RAR

    def inspect(
        self,
        archive_path: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[ArchiveEntry]:
        del password_policy
        if not self.is_available():
            raise MissingDependencyError("rarfile is not installed. Run: pip install rarfile")

        try:
            from rarfile import RarFile  # type: ignore
        except ImportError as exc:
            raise MissingDependencyError("rarfile is not installed. Run: pip install rarfile") from exc

        try:
            with RarFile(archive_path) as archive:
                entries: list[ArchiveEntry] = []
                for item in archive.infolist():
                    fixed_name = fix_filename(item.filename)
                    needs_password = False
                    checker = getattr(item, "needs_password", None)
                    if callable(checker):
                        try:
                            needs_password = bool(checker())
                        except Exception:
                            needs_password = False
                    entries.append(
                        ArchiveEntry(
                            relative_path=fixed_name,
                            is_dir=item.isdir(),
                            size=item.file_size,
                            compressed_size=item.compress_size,
                            source_archive=archive_path.name,
                            depth=0,
                            encrypted=needs_password,
                        )
                    )
                return entries
        except Exception as exc:
            raise InspectionFailedError(f"Failed to inspect rar archive: {archive_path}") from exc

    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        active_policy = password_policy or PasswordPolicy()
        if not self.is_available():
            raise MissingDependencyError("rarfile is not installed. Run: pip install rarfile")

        try:
            from rarfile import RarFile  # type: ignore
        except ImportError as exc:
            raise MissingDependencyError("rarfile is not installed. Run: pip install rarfile") from exc

        warnings: list[str] = []
        try:
            with RarFile(archive_path) as archive:
                for item in archive.infolist():
                    fixed_name = fix_filename(item.filename)
                    destination = safe_join(output_dir, fixed_name)
                    if item.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)

                    needs_password = False
                    checker = getattr(item, "needs_password", None)
                    if callable(checker):
                        try:
                            needs_password = bool(checker())
                        except Exception:
                            needs_password = False

                    if not needs_password:
                        with archive.open(item) as src, destination.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                        continue

                    if not active_policy.passwords:
                        if active_policy.missing_password_strategy == PasswordStrategy.RAISE:
                            raise PasswordRequiredError(f"Encrypted rar member requires password: {fixed_name}")
                        warnings.append(f"Skipped encrypted rar member without password: {fixed_name}")
                        continue

                    extracted = False
                    for password in active_policy.passwords:
                        try:
                            with archive.open(item, pwd=password) as src, destination.open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                            extracted = True
                            break
                        except Exception:
                            continue

                    if not extracted:
                        if active_policy.invalid_password_strategy == PasswordStrategy.RAISE:
                            raise InvalidPasswordError(f"Invalid password for encrypted rar member: {fixed_name}")
                        warnings.append(f"Skipped encrypted rar member due to invalid password(s): {fixed_name}")
            return warnings
        except (PasswordRequiredError, InvalidPasswordError):
            raise
        except Exception as exc:
            raise ExtractionFailedError(f"Failed to extract rar archive: {archive_path}") from exc
