from __future__ import annotations

import io
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from archive_kit import (
    PasswordPolicy,
    PasswordStrategy,
    batch_result_to_dict,
    batch_unpack,
    inspect_one,
    list_member_paths,
    member_exists,
    read_member_text,
    unpack_one,
    write_batch_report_json,
)
from cells import json


class ArchiveKitCoreTests(unittest.TestCase):
    def test_zip_inspect_unpack_and_batch_unpack(self) -> None:
        with TemporaryDirectory(prefix="archivekit-test-") as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "input"
            source_dir.mkdir(parents=True, exist_ok=True)

            nested_zip = source_dir / "nested.zip"
            with ZipFile(nested_zip, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("child/inner.txt", "nested-hello")

            top_zip = source_dir / "top.zip"
            with ZipFile(top_zip, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("docs/readme.txt", "top-hello")
                archive.write(nested_zip, arcname="bundles/nested.zip")

            inspect_result = inspect_one(top_zip, recursive=False, profile="safe")
            relative_paths = {entry.relative_path for entry in inspect_result.entries}
            self.assertIn("docs/readme.txt", relative_paths)
            self.assertIn("bundles/nested.zip", relative_paths)

            recursive_inspect = inspect_one(top_zip, recursive=True, profile="balanced")
            nested_pairs = {
                (entry.source_archive, entry.relative_path, entry.depth) for entry in recursive_inspect.entries
            }
            self.assertIn(("bundles/nested.zip", "child/inner.txt", 1), nested_pairs)

            content = read_member_text(top_zip, "docs/readme.txt")
            self.assertEqual(content, "top-hello")
            self.assertTrue(member_exists(top_zip, "docs/readme.txt").exists)
            self.assertFalse(member_exists(top_zip, "missing.txt").exists)
            self.assertIn("docs/readme.txt", list_member_paths(top_zip, recursive=False))

            unpack_result = unpack_one(top_zip, output_dir=root / "single-output", profile="balanced")
            self.assertTrue((unpack_result.output_dir / "docs" / "readme.txt").exists())
            self.assertTrue((unpack_result.output_dir / "bundles" / "nested" / "child" / "inner.txt").exists())

            batch_result = batch_unpack(source_dir, target_dir=root / "batch-output", profile="safe")
            self.assertEqual(batch_result.failed_count, 0)
            self.assertEqual(batch_result.statistics.total_files_extracted, 3)
            self.assertTrue((root / "batch-output" / "top" / "docs" / "readme.txt").exists())

            payload = batch_result_to_dict(batch_result)
            self.assertEqual(payload["failed_count"], 0)
            self.assertEqual(payload["statistics"]["status_breakdown"]["success"], 2)
            report_path = write_batch_report_json(batch_result, root / "batch-output" / "report.json")
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["success_count"], 2)
            self.assertEqual(loaded["statistics"]["archive_type_breakdown"]["zip"], 2)

    def test_tar_gz_and_tar_xz_support(self) -> None:
        with TemporaryDirectory(prefix="archivekit-tar-") as temp_dir:
            root = Path(temp_dir)
            source_dir = root / "input"
            source_dir.mkdir(parents=True, exist_ok=True)

            tar_gz = source_dir / "alpha.tar.gz"
            with tarfile.open(tar_gz, "w:gz") as archive:
                payload = b"alpha-hello"
                info = tarfile.TarInfo(name="docs/readme.txt")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

            tar_xz = source_dir / "beta.tar.xz"
            with tarfile.open(tar_xz, "w:xz") as archive:
                payload = b"beta-hello"
                info = tarfile.TarInfo(name="data/value.txt")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

            inspect_gz = inspect_one(tar_gz, recursive=False, profile="safe")
            inspect_xz = inspect_one(tar_xz, recursive=False, profile="safe")
            self.assertEqual(inspect_gz.archive_type.value, "tar.gz")
            self.assertEqual(inspect_xz.archive_type.value, "tar.xz")
            self.assertIn("docs/readme.txt", {entry.relative_path for entry in inspect_gz.entries})
            self.assertIn("data/value.txt", {entry.relative_path for entry in inspect_xz.entries})

            unpack_gz = unpack_one(tar_gz, output_dir=root / "alpha-out", profile="balanced")
            unpack_xz = unpack_one(tar_xz, output_dir=root / "beta-out", profile="balanced")
            self.assertTrue((unpack_gz.output_dir / "docs" / "readme.txt").exists())
            self.assertTrue((unpack_xz.output_dir / "data" / "value.txt").exists())
            self.assertEqual(read_member_text(tar_gz, "docs/readme.txt"), "alpha-hello")
            self.assertEqual(read_member_text(tar_xz, "data/value.txt"), "beta-hello")

            batch_result = batch_unpack(source_dir, target_dir=root / "batch-out", profile="safe")
            self.assertEqual(batch_result.failed_count, 0)
            self.assertEqual(batch_result.statistics.archive_type_breakdown["tar.gz"], 1)
            self.assertEqual(batch_result.statistics.archive_type_breakdown["tar.xz"], 1)
            self.assertTrue((root / "batch-out" / "alpha" / "docs" / "readme.txt").exists())
            self.assertTrue((root / "batch-out" / "beta" / "data" / "value.txt").exists())

    def test_password_policy_object_is_accepted_on_non_encrypted_archives(self) -> None:
        with TemporaryDirectory(prefix="archivekit-password-") as temp_dir:
            root = Path(temp_dir)
            archive_path = root / "sample.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("note.txt", "hello")

            policy = PasswordPolicy(
                passwords=("secret",),
                missing_password_strategy=PasswordStrategy.SKIP,
                invalid_password_strategy=PasswordStrategy.SKIP,
            )
            result = inspect_one(archive_path, profile="balanced", password_policy=policy)
            self.assertEqual(result.status.value, "success")
            unpacked = unpack_one(archive_path, output_dir=root / "out", password_policy=policy)
            self.assertEqual(unpacked.status.value, "success")
            self.assertTrue((root / "out" / "note.txt").exists())


if __name__ == "__main__":
    unittest.main()
