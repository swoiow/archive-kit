from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveProfile:
    name: str
    allow_cli_fallback: bool
    recursive_extract: bool
    recursive_inspect: bool
    overwrite: bool
    delete_nested_archives_after_extract: bool
    chmod_writable: bool
    max_depth: int | None


SAFE_PROFILE = ArchiveProfile(
    name="safe",
    allow_cli_fallback=False,
    recursive_extract=False,
    recursive_inspect=False,
    overwrite=False,
    delete_nested_archives_after_extract=False,
    chmod_writable=False,
    max_depth=1,
)

BALANCED_PROFILE = ArchiveProfile(
    name="balanced",
    allow_cli_fallback=True,
    recursive_extract=True,
    recursive_inspect=True,
    overwrite=False,
    delete_nested_archives_after_extract=False,
    chmod_writable=True,
    max_depth=8,
)

AGGRESSIVE_PROFILE = ArchiveProfile(
    name="aggressive",
    allow_cli_fallback=True,
    recursive_extract=True,
    recursive_inspect=True,
    overwrite=True,
    delete_nested_archives_after_extract=True,
    chmod_writable=True,
    max_depth=None,
)

PROFILES = {
    SAFE_PROFILE.name: SAFE_PROFILE,
    BALANCED_PROFILE.name: BALANCED_PROFILE,
    AGGRESSIVE_PROFILE.name: AGGRESSIVE_PROFILE,
}


def get_profile(profile: str | ArchiveProfile | None) -> ArchiveProfile:
    if profile is None:
        return BALANCED_PROFILE
    if isinstance(profile, ArchiveProfile):
        return profile
    try:
        return PROFILES[profile]
    except KeyError as exc:
        allowed = ", ".join(sorted(PROFILES))
        raise ValueError(f"Unsupported profile: {profile}. Allowed profiles: {allowed}.") from exc
