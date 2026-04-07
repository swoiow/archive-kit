from __future__ import annotations

import subprocess

from cells.log import get_logger

from ..errors import ExtractionFailedError


_LOG = get_logger(__name__)


def run_command(args: list[str], timeout_seconds: float = 300.0) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            args,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        _LOG.error("archive.command.timeout", timeout_seconds=timeout_seconds)
        # Command arguments can contain passwords.
        raise ExtractionFailedError(f"Archive command timed out after {timeout_seconds:g} seconds.") from None
    if completed.returncode != 0:
        _LOG.debug("archive.command.failed", return_code=completed.returncode)
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        details = stderr or stdout or f"Exit code {completed.returncode}"
        raise ExtractionFailedError(details)
    return completed
