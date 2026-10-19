"""Pinned source preparation only: stdlib fixtures, no installation/native tools."""
from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("upstream_source", REPO / "scripts/prepare_fixture_upstream.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)


class UpstreamSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="upstream-source-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "한글 공백"
        self.root = self.base / "source"
        self.root.mkdir(parents=True)
        (self.root / "pyproject.toml").write_text("# source marker", encoding="utf-8")
        self.target = self.root / "plugins/fixture_design/upstream"
        self.cache = self.base / "runtime/cache"
        self.archive = self.base / "source.zip"

    def make_archive(self, extra=()):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for name in source.REQUIRED:
                archive.writestr(source.PREFIX + "/" + name, ("original " + name).encode())
            for name, content in extra:
                archive.writestr(name, content)
        return hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def prepare(self):
        return source.prepare(self.root, self.cache, self.archive)

    def test_missing_and_empty_target_prepare_exact_bytes_then_preserve_user_edits(self):
        for empty in (False, True):
            with self.subTest(empty=empty):
                self.root = self.base / ("empty" if empty else "missing")
                self.root.mkdir()
                (self.root / "pyproject.toml").touch()
                self.target = self.root / "plugins/fixture_design/upstream"
                if empty:
                    self.target.mkdir(parents=True)
                sha = self.make_archive([(source.PREFIX + "/LICENSE.txt", b"original fixture notice")])
                with patch.object(source, "SHA256", sha):
                    self.assertEqual(self.prepare()["status"], "PINNED_SOURCE_PREPARED")
                with zipfile.ZipFile(self.archive) as archive:
                    for entry in archive.infolist():
                        relative = entry.filename.removeprefix(source.PREFIX + "/")
                        self.assertEqual((self.target / relative).read_bytes(), archive.read(entry))
                self.assertFalse((self.target / ".git").exists())
                (self.target / "fixturelab/core.py").write_bytes(b"user edit")
                (self.target / ".git").write_bytes(b"gitdir: existing checkout metadata")
                (self.target / "untracked.txt").write_bytes(b"user file")
                before = {p.relative_to(self.target): p.read_bytes() for p in self.target.rglob("*") if p.is_file()}
                with patch.object(source, "download", side_effect=AssertionError("must not download")):
                    self.assertEqual(self.prepare()["status"], "EXISTING_REUSED_UNCHANGED")
                self.assertEqual(before, {p.relative_to(self.target): p.read_bytes()
                                         for p in self.target.rglob("*") if p.is_file()})

    def test_incomplete_nonempty_directory_and_non_directory_are_preserved(self):
        self.target.mkdir(parents=True)
        sentinel = self.target / "README.md"
        sentinel.write_bytes(b"user partial checkout")
        with patch.object(source, "download", side_effect=AssertionError("must not download")):
            with self.assertRaisesRegex(ValueError, "incomplete.*preserved"):
                self.prepare()
        self.assertEqual(sentinel.read_bytes(), b"user partial checkout")
        sentinel.unlink()
        self.target.rmdir()
        self.target.write_bytes(b"do not overwrite")
        with self.assertRaisesRegex(ValueError, "not a directory"):
            self.prepare()
        self.assertEqual(self.target.read_bytes(), b"do not overwrite")

    def test_wrong_hash_preserves_archive_and_empty_target_then_retry_succeeds(self):
        sha = self.make_archive()
        self.target.mkdir(parents=True)
        original = self.archive.read_bytes()
        with patch.object(source, "SHA256", "0" * 64):
            with self.assertRaisesRegex(RuntimeError, "checksum differs"):
                self.prepare()
        self.assertEqual(self.archive.read_bytes(), original)
        self.assertEqual(list(self.target.iterdir()), [])
        with patch.object(source, "SHA256", sha):
            self.assertEqual(self.prepare()["status"], "PINNED_SOURCE_PREPARED")

    def test_failed_download_retains_partial_and_retry_uses_new_folder(self):
        sha = self.make_archive()
        def failed(url, timeout):
            class Broken(io.BytesIO):
                def read(self, size):
                    if self.tell():
                        raise OSError("controlled connection loss")
                    return super().read(size)
            return Broken(b"partial input")
        with patch.object(source, "urlopen", failed):
            with self.assertRaisesRegex(RuntimeError, "connection loss"):
                source.prepare(self.root, self.cache)
        partial = next(self.cache.glob("*/source.zip.partial"))
        self.assertEqual(partial.read_bytes(), b"partial input")
        self.assertFalse(self.target.exists())
        raw = self.archive.read_bytes()
        with patch.object(source, "SHA256", sha), patch.object(source, "urlopen", return_value=io.BytesIO(raw)):
            self.assertEqual(source.prepare(self.root, self.cache)["status"], "PINNED_SOURCE_PREPARED")
        self.assertEqual(partial.read_bytes(), b"partial input")

    def test_unsafe_archive_members_are_rejected_before_target_creation(self):
        for name in ("../escape.py", source.PREFIX + "/../escape.py", source.PREFIX + "/file:stream",
                     source.PREFIX + "/CON.py", source.PREFIX + "/.git/config",
                     source.PREFIX + "/fixturelab/CORE.py"):
            with self.subTest(name=name):
                sha = self.make_archive([(name, b"unsafe")])
                with patch.object(source, "SHA256", sha):
                    with self.assertRaisesRegex(RuntimeError, "Unsafe|Duplicate"):
                        self.prepare()
                self.assertFalse(self.target.exists())

    def test_extraction_failure_never_exposes_partial_sources_and_preserves_stage(self):
        sha = self.make_archive()
        def broken(data, output):
            output.write(b"partial source")
            raise OSError("controlled disk failure")
        with patch.object(source, "SHA256", sha), patch.object(source.shutil, "copyfileobj", broken):
            with self.assertRaisesRegex(RuntimeError, "disk failure"):
                self.prepare()
        self.assertFalse(self.target.exists())
        stages = list(self.target.parent.glob(".upstream-source-*"))
        self.assertEqual(len(stages), 1)
        self.assertEqual(next(p for p in stages[0].rglob("*") if p.is_file()).read_bytes(), b"partial source")
        with patch.object(source, "SHA256", sha):
            self.assertEqual(self.prepare()["status"], "PINNED_SOURCE_PREPARED")
        self.assertTrue(stages[0].exists())

    def test_installer_prepares_sources_before_editable_install(self):
        installer = (REPO / "scripts/install-windows.ps1").read_text(encoding="utf-8-sig")
        call = "Invoke-Checked $python @('-X','utf8',(Join-Path $PSScriptRoot 'prepare_fixture_upstream.py')"
        self.assertIn(call, installer)
        self.assertLess(installer.index("$pyVersion ="), installer.index(call))
        self.assertLess(installer.index(call), installer.index("Invoke-Checked $uv @('pip','install'"))
        self.assertNotIn("git submodule", installer)


if __name__ == "__main__":
    unittest.main()
