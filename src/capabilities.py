from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

from .models import ArchiveSupportReport, BackendCapability, DependencyIssue


SEVEN_Z_EXECUTABLE_CANDIDATES = ["7z", "7zz", "7za"]
WINDOWS_7Z_CANDIDATES = [
    Path("C:/Program Files/7-Zip/7z.exe"),
    Path("C:/Program Files (x86)/7-Zip/7z.exe"),
]
RAR_HELPER_CANDIDATES = ["unrar", "unar", "bsdtar", "7z", "7zz", "7za"]


SUPPORTED_TYPE_NAMES = ["zip", "7z", "rar", "tar", "tar.gz", "tar.xz"]


def _find_optional_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def find_seven_zip_executable() -> str | None:
    for candidate in SEVEN_Z_EXECUTABLE_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    for candidate in WINDOWS_7Z_CANDIDATES:
        if candidate.exists():
            return str(candidate)

    return None


def find_rar_helper() -> str | None:
    for candidate in RAR_HELPER_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def probe_support() -> ArchiveSupportReport:
    seven_zip_cli = find_seven_zip_executable()
    py7zr_installed = _find_optional_module("py7zr")
    rarfile_installed = _find_optional_module("rarfile")
    rar_helper = find_rar_helper()

    backend_capabilities = [
        BackendCapability(
            name="zipfile",
            available=True,
            details="Python stdlib backend for .zip.",
        ),
        BackendCapability(
            name="tarfile",
            available=True,
            details="Python stdlib backend for .tar/.tar.gz/.tar.xz.",
        ),
        BackendCapability(
            name="7zcli",
            available=seven_zip_cli is not None,
            details=seven_zip_cli or "7z executable not found.",
        ),
        BackendCapability(
            name="py7zr",
            available=py7zr_installed,
            details="Optional Python backend for .7z.",
        ),
        BackendCapability(
            name="rarfile",
            available=rarfile_installed,
            details=(
                f"Optional Python backend for .rar. Helper: {rar_helper}"
                if rarfile_installed
                else "Optional Python backend for .rar is not installed."
            ),
        ),
    ]

    issues: list[DependencyIssue] = []
    if seven_zip_cli is None:
        issues.append(
            DependencyIssue(
                name="7z-cli",
                installed=False,
                required_for=["preferred extraction backend for .7z and .rar"],
                hint="Install 7-Zip or ensure 7z/7zz/7za is on PATH.",
            )
        )
    if not py7zr_installed:
        issues.append(
            DependencyIssue(
                name="py7zr",
                installed=False,
                required_for=["Python fallback backend for .7z"],
                hint="pip install py7zr",
            )
        )
    if not rarfile_installed:
        issues.append(
            DependencyIssue(
                name="rarfile",
                installed=False,
                required_for=["Python fallback backend for .rar"],
                hint="pip install rarfile",
            )
        )
    elif rar_helper is None:
        issues.append(
            DependencyIssue(
                name="rar-helper",
                installed=False,
                required_for=["some rarfile extraction scenarios"],
                hint="Install unrar, unar, bsdtar, or 7z.",
                details="rarfile is installed, but no helper executable was found.",
            )
        )

    return ArchiveSupportReport(
        backend_capabilities=backend_capabilities,
        dependency_issues=issues,
        supported_types=SUPPORTED_TYPE_NAMES,
        preferred_executable=seven_zip_cli,
    )
