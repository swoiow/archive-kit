from __future__ import annotations

import io
import sys
import tarfile
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from archive_kit import (
    batch_inspect,
    batch_unpack,
    inspect_one,
    list_member_paths,
    member_exists,
    read_member_bytes,
    unpack_one,
    write_batch_report_json,
)
from archive_kit.backends.sevenzip_cli_backend import SevenZipCliBackend
from archive_kit.engine import ArchiveEngine
from archive_kit.errors import (
    ArchiveSecurityError,
    ArchiveSkippedError,
    ExtractionFailedError,
    InvalidPasswordError,
    MissingDependencyError,
    PasswordRequiredError,
)
from archive_kit.profiles import BALANCED_PROFILE
from archive_kit.utils.process import run_command
from cells import json


def zip_bytes(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class ArchiveRegressionTests(unittest.TestCase):
    def test_deep_inspection_retains_temporary_files_and_archive_lineage(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            leaf = zip_bytes({"docs/leaf.txt": "hello"})
            middle = zip_bytes({"inner/deep.zip": leaf})
            archive = root / "top.zip"
            archive.write_bytes(zip_bytes({"bundles/middle.zip": middle}))
            result = inspect_one(archive, recursive=True)
            entries = {(entry.source_archive, entry.relative_path, entry.depth) for entry in result.entries}
            self.assertIn(("bundles/middle.zip", "inner/deep.zip", 1), entries)
            self.assertIn(
                ("bundles/middle.zip!/inner/deep.zip", "docs/leaf.txt", 2),
                entries,
            )
            self.assertTrue(result.temp_extraction_used)
            limited = inspect_one(
                archive,
                recursive=True,
                profile=replace(BALANCED_PROFILE, max_depth=1),
            )
            self.assertEqual(max(entry.depth for entry in limited.entries), 1)
            output = unpack_one(archive, root / "output")
            self.assertEqual(
                (output.output_dir / "bundles/middle/inner/deep/docs/leaf.txt").read_text(encoding="utf-8"),
                "hello",
            )

    def test_member_lookup_matches_root_member_read_scope(self) -> None:
        with TemporaryDirectory() as temporary:
            archive = Path(temporary) / "top.zip"
            archive.write_bytes(zip_bytes({"nested.zip": zip_bytes({"leaf.txt": "hello"})}))
            self.assertIn("leaf.txt", list_member_paths(archive, recursive=True))
            self.assertFalse(member_exists(archive, "leaf.txt").exists)
            self.assertTrue(member_exists(archive, "nested.zip").exists)
            with self.assertRaises(FileNotFoundError):
                read_member_bytes(archive, "leaf.txt")

    def test_invalid_source_and_archive_paths_raise(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "sample.zip"
            archive.write_bytes(zip_bytes({"leaf.txt": "hello"}))
            for batch in (batch_inspect, batch_unpack):
                with self.subTest(batch=batch.__name__):
                    with self.assertRaises(FileNotFoundError):
                        batch(root / "missing")
                    with self.assertRaises(NotADirectoryError):
                        batch(archive)
            for operation in (inspect_one, unpack_one):
                with self.subTest(operation=operation.__name__), self.assertRaises(FileNotFoundError):
                    operation(root / "missing.zip")
            (root / "empty").mkdir()
            self.assertEqual(batch_inspect(root / "empty").total_tasks, 0)

    def test_password_errors_propagate_without_fallback_and_cleanup(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "sample.zip"
            archive.write_bytes(zip_bytes({"leaf.txt": "hello"}))
            engine = ArchiveEngine()
            for error_type in (PasswordRequiredError, InvalidPasswordError):
                with self.subTest(error=error_type.__name__):
                    with (
                        patch.object(
                            engine.backends["zipfile"],
                            "extract",
                            side_effect=error_type("password policy rejected"),
                        ),
                        patch.object(engine.backends["7zcli"], "extract") as fallback,
                    ):
                        output = root / "output"
                        with self.assertRaises(error_type):
                            engine.extract_archive(archive, output)
                        fallback.assert_not_called()
                        self.assertFalse(output.exists())
                    with (
                        patch.object(
                            engine.backends["zipfile"],
                            "inspect",
                            side_effect=error_type("password policy rejected"),
                        ),
                        self.assertRaises(error_type),
                    ):
                        engine.inspect_archive(archive, recursive=False)

    def test_path_traversal_is_rejected_without_fallback(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            zip_path = root / "unsafe.zip"
            zip_path.write_bytes(zip_bytes({"../escape.txt": "unsafe"}))
            tar_path = root / "unsafe.tar"
            with tarfile.open(tar_path, "w") as archive:
                member = tarfile.TarInfo("../escape.txt")
                member.size = 6
                archive.addfile(member, io.BytesIO(b"unsafe"))
            engine = ArchiveEngine()
            for archive_path in (zip_path, tar_path):
                with (
                    self.subTest(archive=archive_path.name),
                    patch.object(engine.backends["7zcli"], "extract") as fallback,
                ):
                    with self.assertRaises(ArchiveSecurityError):
                        engine.extract_archive(archive_path, root / "output")
                    fallback.assert_not_called()
                    self.assertFalse((root / "escape.txt").exists())
                    self.assertFalse((root / "output").exists())

    def test_output_cannot_delete_source_and_existing_output_is_preserved(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "sample.zip"
            archive.write_bytes(zip_bytes({"leaf.txt": "hello"}))
            marker = root / "keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(ArchiveSecurityError):
                unpack_one(archive, root, profile="aggressive")
            self.assertTrue(archive.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            output = root / "output"
            output.mkdir()
            (output / "keep.txt").write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                unpack_one(archive, output, profile="safe")
            self.assertTrue((output / "keep.txt").exists())

    def test_missing_optional_backend_raises_dependency_error(self) -> None:
        with TemporaryDirectory() as temporary:
            archive = Path(temporary) / "sample.7z"
            archive.write_bytes(b"unused")
            engine = ArchiveEngine()
            with (
                patch.object(engine.backends["py7zr"], "is_available", return_value=False),
                patch.object(engine.backends["7zcli"], "is_available", return_value=False),
            ):
                with self.assertRaises(MissingDependencyError):
                    engine.inspect_archive(archive)
                with self.assertRaises(MissingDependencyError):
                    engine.extract_archive(archive)

    def test_json_report_preserves_formatting_options(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "中文.zip"
            archive.write_bytes(zip_bytes({"note.txt": "hello"}))
            result = batch_inspect(root, profile="safe")
            destination = write_batch_report_json(result, root / "report.json", indent=4, ensure_ascii=True)
            encoded = destination.read_text(encoding="utf-8")
            self.assertIn("\\u4e2d", encoded)
            self.assertIn('\n    "total_tasks"', encoded)
            decoded = json.loads(encoded)
            self.assertEqual(decoded["total_tasks"], 1)
            self.assertEqual(decoded["reports"][0]["status"], "success")
            self.assertIsInstance(decoded["started_at"], str)

    def test_command_timeout_is_bounded_and_does_not_disclose_arguments(self) -> None:
        with self.assertRaises(ExtractionFailedError) as raised:
            run_command(
                [sys.executable, "-c", "import time; time.sleep(5)", "secret"],
                timeout_seconds=0.1,
            )
        self.assertIn("timed out", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))

    def test_command_has_no_interactive_stdin(self) -> None:
        completed = run_command([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"])
        self.assertEqual(completed.stdout.strip(), "''")

    def test_recursive_inspection_reports_password_skip_as_result(self) -> None:
        with TemporaryDirectory() as temporary:
            archive = Path(temporary) / "sample.zip"
            archive.write_bytes(zip_bytes({"note.txt": "hello"}))
            engine = ArchiveEngine()
            with patch.object(
                engine.backends["zipfile"],
                "extract",
                side_effect=ArchiveSkippedError("encrypted archive skipped", encrypted=True),
            ):
                result = engine.inspect_archive(archive, recursive=True)
            self.assertEqual(result.status.value, "skipped")
            self.assertEqual(result.skipped_reason, "encrypted archive skipped")
            self.assertEqual(result.entries_count, 1)
            self.assertTrue(result.encrypted_archive)

    def test_batch_records_corrupt_archive_and_continues(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "bad.zip").write_bytes(b"not an archive")
            (root / "good.zip").write_bytes(zip_bytes({"note.txt": "hello"}))
            result = batch_inspect(root, profile="safe")
            self.assertEqual(result.total_tasks, 2)
            self.assertEqual(result.failed_count, 1)
            self.assertEqual(result.success_count, 1)
            self.assertEqual(result.statistics.error_count, 1)

    def test_sevenzip_parser_retains_member_named_after_archive(self) -> None:
        listing = (
            "Path = sample.7z\nType = 7z\n\n----------\n"
            "Path = sample.7z\nSize = 12\nEncrypted = -\n\n"
            "Path = folder\nFolder = +\nSize = 0\n\n"
        )
        entries = SevenZipCliBackend._parse_slt_entries("sample.7z", listing)
        self.assertEqual([entry.relative_path for entry in entries], ["sample.7z", "folder"])
        self.assertTrue(entries[1].is_dir)
        self.assertFalse(SevenZipCliBackend._contains_password_error(["Headers Error"]))


if __name__ == "__main__":
    unittest.main()
