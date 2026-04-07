from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from ..errors import ExtractionFailedError, InspectionFailedError, InvalidPasswordError, PasswordRequiredError
from ..models import ArchiveEntry, ArchiveType, PasswordPolicy, PasswordStrategy
from ..utils.encoding import fix_filename
from ..utils.filesystem import safe_join
from .base import ArchiveBackend


class ZipfileBackend(ArchiveBackend):
    name = "zipfile"

    def is_available(self) -> bool:
        return True

    def supports(self, archive_type: ArchiveType) -> bool:
        return archive_type == ArchiveType.ZIP

    def inspect(
        self,
        archive_path: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[ArchiveEntry]:
        del password_policy
        try:
            with ZipFile(archive_path) as archive:
                entries: list[ArchiveEntry] = []
                for item in archive.infolist():
                    fixed_name = fix_filename(item.filename)
                    entries.append(
                        ArchiveEntry(
                            relative_path=fixed_name,
                            is_dir=item.is_dir(),
                            size=item.file_size,
                            compressed_size=item.compress_size,
                            source_archive=archive_path.name,
                            depth=0,
                            encrypted=bool(item.flag_bits & 0x1),
                        )
                    )
                return entries
        except BadZipFile as exc:
            raise InspectionFailedError(f"Bad zip file: {archive_path}") from exc

    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        active_policy = password_policy or PasswordPolicy()
        warnings: list[str] = []
        try:
            with ZipFile(archive_path) as archive:
                for item in archive.infolist():
                    fixed_name = fix_filename(item.filename)
                    destination = safe_join(output_dir, fixed_name)
                    if item.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue

                    destination.parent.mkdir(parents=True, exist_ok=True)
                    encrypted = bool(item.flag_bits & 0x1)
                    if not encrypted:
                        with archive.open(item) as src, destination.open("wb") as dst:
                            shutil.copyfileobj(src, dst)
                        continue

                    if not active_policy.passwords:
                        if active_policy.missing_password_strategy == PasswordStrategy.RAISE:
                            raise PasswordRequiredError(f"Encrypted zip member requires password: {fixed_name}")
                        warnings.append(f"Skipped encrypted zip member without password: {fixed_name}")
                        continue

                    extracted = False
                    for password in active_policy.passwords:
                        try:
                            with archive.open(item, pwd=password.encode("utf-8")) as src, destination.open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                            extracted = True
                            break
                        except RuntimeError:
                            continue

                    if not extracted:
                        if active_policy.invalid_password_strategy == PasswordStrategy.RAISE:
                            raise InvalidPasswordError(f"Invalid password for encrypted zip member: {fixed_name}")
                        warnings.append(f"Skipped encrypted zip member due to invalid password(s): {fixed_name}")
                return warnings
        except BadZipFile as exc:
            raise ExtractionFailedError(f"Bad zip file: {archive_path}") from exc
