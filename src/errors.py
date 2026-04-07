class ArchiveError(Exception):
    """Base error for archive processing."""


class UnsupportedArchiveError(ArchiveError):
    """Raised when an archive type is not supported."""


class MissingDependencyError(ArchiveError):
    """Raised when a required optional dependency or executable is unavailable."""


class InspectionFailedError(ArchiveError):
    """Raised when archive inspection fails."""


class ExtractionFailedError(ArchiveError):
    """Raised when archive extraction fails."""


class ArchiveSecurityError(ArchiveError):
    """Raised when an archive entry attempts path traversal."""


class PasswordRequiredError(ArchiveError):
    """Raised when an encrypted archive requires a password but none was supplied."""


class InvalidPasswordError(ArchiveError):
    """Raised when supplied archive passwords are invalid."""


class ArchiveSkippedError(ArchiveError):
    """Raised when archive handling is intentionally skipped by policy."""

    def __init__(self, message: str, *, encrypted: bool = False, backend_name: str | None = None) -> None:
        super().__init__(message)
        self.encrypted = encrypted
        self.backend_name = backend_name
