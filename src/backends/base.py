from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import ArchiveEntry, ArchiveType, PasswordPolicy


class ArchiveBackend(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def supports(self, archive_type: ArchiveType) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(
        self,
        archive_path: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[ArchiveEntry]:
        raise NotImplementedError

    @abstractmethod
    def extract(
        self,
        archive_path: Path,
        output_dir: Path,
        password_policy: PasswordPolicy | None = None,
    ) -> list[str]:
        raise NotImplementedError
