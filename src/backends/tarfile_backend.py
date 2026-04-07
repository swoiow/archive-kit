from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from ..errors import ArchiveSecurityError, ExtractionFailedError, InspectionFailedError
from ..models import ArchiveEntry, ArchiveType, PasswordPolicy
from ..utils.filesystem import safe_join
from .base import ArchiveBackend


class TarfileBackend(ArchiveBackend):
    name = "tarfile"

    def is_available(self) -> bool:
        return True

    def supports(self, archive_type: ArchiveType) -> bool:
        return archive_type in {ArchiveType.TAR, ArchiveType.TAR_GZ, ArchiveType.TAR_XZ}

    def inspect(
        self,
        archive_path: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[ArchiveEntry]:
        del password_policy
        try:
            with tarfile.open(archive_path, mode="r:*") as archive:
                entries: list[ArchiveEntry] = []
                for item in archive.getmembers():
                    entries.append(
                        ArchiveEntry(
                            relative_path=item.name,
                            is_dir=item.isdir(),
                            size=item.size,
                            compressed_size=None,
                            source_archive=archive_path.name,
                            depth=0,
                            encrypted=False,
                        )
                    )
                return entries
        except Exception as exc:
            raise InspectionFailedError(f"Failed to inspect tar archive: {archive_path}") from exc

    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        del password_policy
        warnings: list[str] = []
        try:
            with tarfile.open(archive_path, mode="r:*") as archive:
                for item in archive.getmembers():
                    destination = safe_join(output_dir, item.name)
                    if item.isdir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    if item.issym() or item.islnk():
                        warnings.append(f"Skipped tar link member for safety: {item.name}")
                        continue
                    if not item.isfile():
                        warnings.append(f"Skipped unsupported tar member type: {item.name}")
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    extracted = archive.extractfile(item)
                    if extracted is None:
                        warnings.append(f"Skipped unreadable tar member: {item.name}")
                        continue
                    with extracted, destination.open("wb") as dst:
                        shutil.copyfileobj(extracted, dst)
            return warnings
        except ArchiveSecurityError:
            raise
        except Exception as exc:
            raise ExtractionFailedError(f"Failed to extract tar archive: {archive_path}") from exc
