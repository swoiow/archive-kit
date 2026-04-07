from __future__ import annotations

from pathlib import Path

from ..capabilities import find_seven_zip_executable
from ..errors import (
    ArchiveSkippedError,
    ExtractionFailedError,
    InspectionFailedError,
    InvalidPasswordError,
    MissingDependencyError,
    PasswordRequiredError,
)
from ..models import ArchiveEntry, ArchiveType, PasswordPolicy, PasswordStrategy
from ..utils.process import run_command
from .base import ArchiveBackend


PASSWORD_HINTS = [
    "wrong password",
    "can not open encrypted archive",
    "enter password",
    "password is incorrect",
]


class SevenZipCliBackend(ArchiveBackend):
    name = "7zcli"

    def __init__(self) -> None:
        self.executable = find_seven_zip_executable()

    def is_available(self) -> bool:
        return self.executable is not None

    def supports(self, archive_type: ArchiveType) -> bool:
        return archive_type in {
            ArchiveType.ZIP,
            ArchiveType.SEVEN_Z,
            ArchiveType.RAR,
            ArchiveType.TAR,
            ArchiveType.TAR_GZ,
            ArchiveType.TAR_XZ,
        }

    def inspect(
        self,
        archive_path: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[ArchiveEntry]:
        if not self.executable:
            raise MissingDependencyError("7z executable was not found on PATH.")

        active_policy = password_policy or PasswordPolicy()
        candidates: list[str | None] = [None]
        if active_policy.passwords:
            candidates.extend(active_policy.passwords)

        errors: list[str] = []
        for password in candidates:
            command = [self.executable, "l", "-slt", "-sccUTF-8"]
            if password is not None:
                command.append(f"-p{password}")
            command.extend(["--", str(archive_path)])
            try:
                completed = run_command(command)
                return self._parse_slt_entries(archive_path.name, completed.stdout)
            except Exception as exc:
                errors.append(str(exc))
                continue

        if active_policy.passwords and self._contains_password_error(errors):
            if active_policy.invalid_password_strategy == PasswordStrategy.SKIP:
                raise ArchiveSkippedError(
                    f"Skipped password-protected archive during inspect due to invalid password(s): {archive_path.name}",
                    encrypted=True,
                    backend_name=self.name,
                )
            raise InvalidPasswordError(f"Invalid password for archive: {archive_path}")

        if self._contains_password_error(errors):
            if active_policy.missing_password_strategy == PasswordStrategy.SKIP:
                raise ArchiveSkippedError(
                    f"Skipped password-protected archive during inspect without password: {archive_path.name}",
                    encrypted=True,
                    backend_name=self.name,
                )
            raise PasswordRequiredError(f"Password required for archive: {archive_path}")

        raise InspectionFailedError(
            f"Failed to inspect archive via 7z CLI: {archive_path}. Details: {' | '.join(errors)}"
        )

    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        if not self.executable:
            raise MissingDependencyError("7z executable was not found on PATH.")

        active_policy = password_policy or PasswordPolicy()
        candidates: list[str | None] = [None]
        if active_policy.passwords:
            candidates.extend(active_policy.passwords)

        errors: list[str] = []
        for password in candidates:
            command = [self.executable, "x", "-y", "-sccUTF-8", f"-o{output_dir}"]
            if password is not None:
                command.append(f"-p{password}")
            command.extend(["--", str(archive_path)])
            try:
                run_command(command)
                return []
            except Exception as exc:
                errors.append(str(exc))
                continue

        if active_policy.passwords and self._contains_password_error(errors):
            if active_policy.invalid_password_strategy == PasswordStrategy.SKIP:
                raise ArchiveSkippedError(
                    f"Skipped password-protected archive due to invalid password(s): {archive_path.name}",
                    encrypted=True,
                    backend_name=self.name,
                )
            raise InvalidPasswordError(f"Invalid password for archive: {archive_path}")

        if self._contains_password_error(errors):
            if active_policy.missing_password_strategy == PasswordStrategy.SKIP:
                raise ArchiveSkippedError(
                    f"Skipped password-protected archive without password: {archive_path.name}",
                    encrypted=True,
                    backend_name=self.name,
                )
            raise PasswordRequiredError(f"Password required for archive: {archive_path}")

        raise ExtractionFailedError(
            f"Failed to extract archive via 7z CLI: {archive_path}. Details: {' | '.join(errors)}"
        )

    @staticmethod
    def _contains_password_error(errors: list[str]) -> bool:
        joined = " ".join(errors).lower()
        return any(hint in joined for hint in PASSWORD_HINTS)

    @staticmethod
    def _parse_slt_entries(source_archive: str, stdout: str) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        current: dict[str, str] = {}
        seen_header = False

        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                if "Path" in current and seen_header:
                    entries.append(SevenZipCliBackend._entry_from_block(source_archive, current))
                current = {}
                continue
            if line.startswith("----------"):
                if seen_header and "Path" in current:
                    entries.append(SevenZipCliBackend._entry_from_block(source_archive, current))
                    current = {}
                seen_header = True
                continue
            if " = " in line:
                key, value = line.split(" = ", 1)
                current[key] = value

        if seen_header and "Path" in current:
            entries.append(SevenZipCliBackend._entry_from_block(source_archive, current))

        return entries

    @staticmethod
    def _entry_from_block(source_archive: str, block: dict[str, str]) -> ArchiveEntry:
        attributes = block.get("Attributes", "")
        folder_flag = block.get("Folder", "-")
        size = block.get("Size")
        packed_size = block.get("Packed Size")
        encrypted_value = block.get("Encrypted")
        is_dir = folder_flag == "+" or attributes.startswith("D") or " D" in attributes
        encrypted: bool | None = None
        if encrypted_value is not None:
            encrypted = encrypted_value.strip() == "+"
        return ArchiveEntry(
            relative_path=block.get("Path", ""),
            is_dir=is_dir,
            size=int(size) if size and size.isdigit() else None,
            compressed_size=int(packed_size) if packed_size and packed_size.isdigit() else None,
            source_archive=source_archive,
            depth=0,
            encrypted=encrypted,
        )
