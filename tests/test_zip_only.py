from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from archive_kit import (
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


class ArchiveKitZipTests(unittest.TestCase):
    def test_inspect_unpack_and_batch_unpack(self) -> None:
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
            self.assertTrue((root / "batch-output" / "top" / "docs" / "readme.txt").exists())

            payload = batch_result_to_dict(batch_result)
            self.assertEqual(payload["failed_count"], 0)
            report_path = write_batch_report_json(batch_result, root / "batch-output" / "report.json")
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["success_count"], 2)


if __name__ == "__main__":
    unittest.main()
