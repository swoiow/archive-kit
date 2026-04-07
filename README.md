# archive-kit

[中文](README-CN.md)

A Python library for inspecting, reading, and extracting archives, including
nested archives and directory batches. Python 3.10+.

The distribution name is `archive-kit`; Python imports use `archive_kit`:

```python
from archive_kit import PasswordPolicy, PasswordStrategy, unpack_one
```

## Features

- ZIP, 7z, RAR, TAR, gzip-compressed TAR, and xz-compressed TAR.
- Case-insensitive suffix detection, including `.tgz` and `.txz` aliases.
- Recursive inspection with member sizes, encryption metadata where available,
  nesting depth, and source-archive lineage.
- Recursive extraction that preserves directories and expands nested archives
  into sibling directories.
- Member lookup and byte/text reads.
- Password candidates with independent missing-password and invalid-password policies.
- Dependency discovery, per-archive batch reports, aggregate statistics, and JSON export.

Archive creation and a command-line interface are outside the current API.

## Installation

From this checkout:

```bash
python -m pip install .
# Add the optional Python backends for 7z and RAR:
python -m pip install ".[full]"
```

The base installation uses Python's `zipfile` and `tarfile` for ZIP and TAR
formats and depends on the published `cells-json` and `cells-log` packages for
JSON reports and diagnostic logging.
The `full` extra adds `py7zr` and `rarfile`.

For the CLI backend, install 7-Zip separately. Discovery checks `7z`, `7zz`,
and `7za` on PATH, plus the usual Windows installation directories.
RAR extraction through `rarfile` may also require an external helper.

| Format | Backend preference |
| --- | --- |
| `.zip` | `zipfile`, then `7zcli` |
| `.7z` | `7zcli`, then `py7zr` |
| `.rar` | `7zcli`, then `rarfile` |
| `.tar`, `.tar.gz`, `.tgz`, `.tar.xz`, `.txz` | `tarfile`, then `7zcli` |

The `safe` profile excludes `7zcli`. Use `probe_support()` to inspect
available backends and dependency hints; its `supported_types` field lists
recognized format families, including those whose optional backend is missing.

## Quick start

```python
from archive_kit import inspect_one, member_exists, read_member_text, unpack_one

result = inspect_one("sample.zip", recursive=False)
for entry in result.entries:
    print(entry.relative_path, entry.size, entry.encrypted)

if member_exists("sample.zip", "docs/readme.txt").exists:
    print(read_member_text("sample.zip", "docs/readme.txt"))

extracted = unpack_one("sample.zip", output_dir="./output/sample", profile="balanced")
print(extracted.status.value, extracted.extracted_file_count)
print(extracted.warnings)
```

When `output_dir` is omitted, `sample.tar.gz` extracts to `sample/` beside
the archive. An extracted member `bundles/child.zip` expands to
`bundles/child/` when recursion is enabled.

## Public API

Functions below are exported from `archive_kit`. Paths accept `str` or
`pathlib.Path`.

| Function | Result and purpose |
| --- | --- |
| `probe_support()` | `ArchiveSupportReport`: backend availability and dependency hints. |
| `inspect_one(file_path, recursive=None, profile=None, password_policy=None)` | `ArchiveInspectResult`: members and inspection diagnostics. |
| `unpack_one(file_path, output_dir=None, recursive=None, profile=None, password_policy=None)` | `ArchiveExtractResult`: output paths and extraction diagnostics. |
| `list_member_paths(file_path, recursive=None, profile=None, password_policy=None)` | Sorted, deduplicated `list[str]` of member paths. |
| `member_exists(file_path, member_path, profile=None, password_policy=None)` | `MemberLookupResult`; read its `.exists` field. Checks the specified archive only. |
| `read_member_bytes(file_path, member_path, profile=None, password_policy=None)` | `bytes` from a file in the specified archive. |
| `read_member_text(file_path, member_path, encoding="utf-8", errors="strict", profile=None, password_policy=None)` | Decoded `str`; decoding follows Python's encoding/error options. |
| `batch_inspect(source_dir, profile=None, recursive_scan=True, password_policy=None)` | `BatchProcessResult` for inspection. |
| `batch_unpack(source_dir, target_dir=None, profile=None, recursive_scan=True, password_policy=None)` | `BatchProcessResult` for extraction. |
| `batch_result_to_dict(result)` | JSON-compatible dictionary; paths, enums, and timestamps become strings. |
| `write_batch_report_json(result, output_path, *, indent=2, ensure_ascii=False)` | Writes UTF-8 JSON and returns the destination `Path`. Creates parent directories and replaces an existing report. |

`profile=None` selects `balanced`. `recursive=None` takes the profile's
inspection/extraction setting; an explicit boolean overrides it.
`recursive_scan` controls directory traversal in batch operations. Nested-archive
processing in a batch follows the profile.

Member lookup and reads target the specified archive's own members. Recursive
`list_member_paths` combines paths across nested archives and can merge identical
names; use `inspect_one` when you need archive identity. Root entries have
depth 0. Nested `source_archive` values use forward slashes and `!/` to
separate archive layers, such as `bundles/middle.zip!/inner/deep.zip`.

Member reads extract the archive to a temporary directory and then read the
requested file. Recursive inspection also uses temporary extraction. These
operations write temporary data to disk and clean it up afterward.

## Profiles

| Setting | `safe` | `balanced` (default) | `aggressive` |
| --- | --- | --- | --- |
| Allow CLI backend | No | Yes | Yes |
| Recurse by default | No | Yes | Yes |
| Maximum nested depth | 1 | 8 | Unlimited |
| Replace nonempty output directory | No | No | Yes |
| Delete successfully expanded nested archives | No | No | Yes |
| Make extracted files writable | No | Yes | Yes |

`aggressive` deletes an existing nonempty output directory before extraction.
It also removes nested archive files after successfully expanding them.
The original source archive is retained. Output directories containing the
source archive, and symbolic-link output directories, are rejected.

To customize a profile:

```python
from dataclasses import replace
from archive_kit.profiles import BALANCED_PROFILE

profile = replace(BALANCED_PROFILE, name="shallow", max_depth=2)
```

## Passwords and errors

```python
from archive_kit import PasswordPolicy, PasswordStrategy, unpack_one

policy = PasswordPolicy(
    passwords=("candidate-one", "candidate-two"),
    missing_password_strategy=PasswordStrategy.SKIP,
    invalid_password_strategy=PasswordStrategy.RAISE,
)
result = unpack_one("protected.7z", output_dir="./output/protected", password_policy=policy)
print(result.status.value, result.skipped_reason, result.warnings)
```

Both password strategies default to `SKIP`, with no candidate passwords.
ZIP and RAR Python backends can skip individual encrypted members and still
return `success` with warnings. The 7z backends apply whole-archive skip policies.
Inspect `warnings` as well as `status` to detect partial work.

Single-archive operations raise failures. Password-policy rejection under
`RAISE` preserves `PasswordRequiredError` or `InvalidPasswordError` from
`archive_kit.errors`. Other errors include `UnsupportedArchiveError`,
`MissingDependencyError`, `InspectionFailedError`, `ExtractionFailedError`,
and `ArchiveSecurityError`. Invalid input paths raise filesystem exceptions;
a nonempty output directory raises `FileExistsError` unless replacement is enabled.

Batch operations collect per-archive failures and continue. An invalid source
directory raises before batch processing starts.

## Batches and reports

```python
from archive_kit import batch_inspect, batch_unpack, write_batch_report_json

inspected = batch_inspect("./input", profile="safe")
result = batch_unpack("./input", target_dir="./output", profile="balanced")
report_path = write_batch_report_json(result, "./output/archive-report.json")
print(result.total_tasks, result.success_count, result.failed_count, result.skipped_count)
print(result.statistics)
print(report_path)
```

Directory structure is mirrored:
`input/a/b/sample.tar.gz` extracts to `output/a/b/sample/`.
Without `target_dir`, each archive extracts beside its source. Processing is sequential.

Inspection results expose `entries`, `entries_count`, `backend_used`,
`encrypted_entries_count`, and `temp_extraction_used`.
Extraction results expose `output_dir`, `extracted_files`,
`nested_archives_processed`, `deleted_nested_archives`, and their counts.
Both carry `status`, `warnings`, `encrypted_archive`, and `skipped_reason`.

Batch results include individual `reports`, UTC start/end timestamps, duration,
and aggregate `statistics`: warnings/errors/skips, encryption indicators,
inspected entries, extracted files, processed/deleted nested archives, and
counts by format and status. Encryption indicators depend on backend metadata
and diagnostics; they are not proof that every member was decrypted.

## Logging

The library emits structured events through `cells.log` using logger names
under `archive_kit`. Configure logging in your application:

```python
from cells.log import LogConfig, configure_logging, shutdown_logging
from archive_kit import batch_inspect

configure_logging(LogConfig(app_name="archive-job", level="INFO"))
try:
    result = batch_inspect("./input", profile="safe")
finally:
    shutdown_logging()
```

Batch start/completion events use INFO. Fallbacks, skips, policy rejections,
and partial extraction use WARNING. Exhausted backends, batch task failures,
and command timeouts use ERROR; backend attempts and completion details use DEBUG.
Passwords, full command arguments, file contents, and exception messages are
excluded from diagnostic fields. The application owns logging configuration
and shutdown; the library does not configure sinks or create log files itself.
Result objects still contain warnings and errors for programmatic handling.

## Current limits

- Format detection uses filenames, rather than content signatures.
- No decompressed-byte, member-count, memory, or total runtime quotas are enforced.
  Each 7-Zip command has a 300-second timeout and cannot read interactive input.
- The ZIP/TAR Python backends validate member destinations; TAR links and special
  files are skipped. Optional backends retain their own extraction behavior.
- `py7zr` password-versus-corruption classification is best effort. RAR helper
  availability and archive features can vary by platform.
- Member reads load the requested file fully into memory.

## Tests

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
```

Licensed under [MIT](LICENSE).
