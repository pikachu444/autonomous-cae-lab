"""Prepare the recorded fixture sources in an empty checkout/ZIP only (stdlib)."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
from urllib.request import urlopen
import uuid
import zipfile

PIN = "3e48bf6138f495299f45b1af254bfb4aaff307b8"
URL = "https://codeload.github.com/pikachu444/auto-fixture-design/zip/" + PIN
SHA256 = "404f402a3da1469f9bb2a430b46b0c474de31e8e60e3dfbd4935a9a93fe4c481"
PREFIX = "auto-fixture-design-" + PIN
# Runtime sources used by the existing fixture adapters, not a byte/pin verdict
# on a pre-existing user checkout. Existing edits are intentionally preserved.
REQUIRED = (
    "fixturelab/__init__.py", "fixturelab/core.py", "fixturelab/cad.py",
    "fixturelab/freecad_worker.py", "fixturelab/functional_checks.py",
    "fixturelab/handcheck.py", "fixturelab/model_cad.py", "fixturelab/native_cad.py",
    "fixturelab/pipeline.py", "fixturelab/render.py", "fixturelab/server.py",
    "fixturelab/surface_viewer.js", "fixturelab/ui.html", "legacy/src/fixture.py",
    "examples/bend_4mm.json", "examples/printed_material_ASSUMED.json",
    "models/film_tray.py", "models/roller_support.py", "scripts/run_structural_screen.py",
)


def plain_path(path: Path) -> None:
    # Same no-reparse installation boundary as install-opencourant-windows.ps1.
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked source/cache paths are not supported: " + str(item))


def complete_source(path: Path) -> None:
    missing = [name for name in REQUIRED if not (path / name).is_file()]
    if missing:
        raise ValueError("Existing upstream is incomplete and was preserved; missing " +
                         ", ".join(missing[:3]) + ". Move that folder aside explicitly before retrying: " + str(path))
    for name in REQUIRED:
        plain_path(path / name)


def download(destination: Path) -> None:
    with urlopen(URL, timeout=30) as response, destination.open("xb") as output:
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > 16 * 1024**2:
                raise ValueError("Source archive exceeds the expected download bound")
            output.write(chunk)


def members(archive: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    # Reuse the Windows ZIP path/type rules of the maintained optional installer.
    rows, seen, files = [], set(), set()
    entries = archive.infolist()
    if len(entries) > 4096 or sum(row.file_size for row in entries) > 128 * 1024**2:
        raise ValueError("Source archive exceeds the expected extraction bounds")
    for row in entries:
        name = row.filename.rstrip("/")
        parts = name.split("/")
        if (parts[0] != PREFIX or "\\" in name or any(c in name for c in ':<>"|?*') or
                any(not part or part in (".", "..", ".git") or part.endswith((".", " ")) or
                    part.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
                                                  *[f"LPT{i}" for i in range(1, 10)]} for part in parts)):
            raise ValueError("Unsafe source ZIP path: " + row.filename)
        mode = row.external_attr >> 16
        if ((row.external_attr & 0x400) or stat.S_ISLNK(mode) or
                stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR) or row.flag_bits & 1):
            raise ValueError("Linked, special or encrypted source ZIP entry: " + row.filename)
        key = name.casefold()
        if key in seen:
            raise ValueError("Duplicate source ZIP path: " + row.filename)
        seen.add(key)
        if not row.is_dir():
            if len(parts) == 1:
                raise ValueError("Source ZIP root is not a directory")
            files.add(key)
        rows.append((row, PurePosixPath(*parts[1:])))
    if any(any(parent.as_posix().casefold() in files for parent in PurePosixPath(name).parents)
           for name in seen):
        raise ValueError("Conflicting source ZIP file/directory paths")
    expected = {PREFIX.casefold() + "/" + name.casefold() for name in REQUIRED}
    if not expected <= files:
        raise ValueError("Pinned source ZIP lacks required fixture sources")
    return rows


def prepare(source_root: Path, cache_root: Path, archive_path: Path | None = None) -> dict:
    root = Path(os.path.abspath(source_root))
    cache = Path(os.path.abspath(cache_root))
    target = root / "plugins/fixture_design/upstream"
    plain_path(target)
    if not (root / "pyproject.toml").is_file():
        raise ValueError("Project source root is unavailable: " + str(root))
    if target.exists():
        if not target.is_dir():
            raise ValueError("Existing upstream is not a directory and was preserved: " + str(target))
        if any(target.iterdir()):
            complete_source(target)
            return {"status": "EXISTING_REUSED_UNCHANGED", "path": str(target)}
    plain_path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    attempt = cache / ("upstream-source-" + uuid.uuid4().hex)
    attempt.mkdir()
    stage = target.parent / (".upstream-source-" + uuid.uuid4().hex)
    try:
        archive_path = Path(os.path.abspath(archive_path)) if archive_path else attempt / "source.zip.partial"
        plain_path(archive_path)
        if archive_path == attempt / "source.zip.partial":
            download(archive_path)
        if archive_path.stat().st_size > 16 * 1024**2 or hashlib.sha256(archive_path.read_bytes()).hexdigest() != SHA256:
            raise ValueError("Pinned upstream source archive checksum differs: " + str(archive_path))
        with zipfile.ZipFile(archive_path) as archive:
            layout = members(archive)
            target.parent.mkdir(parents=True, exist_ok=True)
            stage.mkdir()
            for row, relative in layout:
                destination = stage.joinpath(*relative.parts)
                if row.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(row) as data, destination.open("xb") as output:
                        shutil.copyfileobj(data, output)
        complete_source(stage)
        plain_path(target)
        plain_path(stage)
        if not target.resolve().is_relative_to(root.resolve()) or stage.parent != target.parent:
            raise ValueError("Source promotion must remain inside the selected source root")
        if target.exists():
            target.rmdir()  # Only an empty directory; a concurrent user edit makes this fail.
        stage.rename(target)  # Same parent/volume; partial extraction is never the live upstream.
        return {"status": "PINNED_SOURCE_PREPARED", "path": str(target), "pin": PIN,
                "archive_sha256": SHA256, "archive": str(archive_path)}
    except Exception as error:
        raise RuntimeError(f"{error}. Original download/staging is retained; retry uses a new folder. "
                           f"Download: {attempt}; staging: {stage}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, help="Existing official pinned source ZIP; never modified")
    args = parser.parse_args()
    try:
        result = prepare(args.source_root, args.cache_root, args.archive)
        print("기존 구성 소스를 그대로 사용합니다." if result["status"] == "EXISTING_REUSED_UNCHANGED"
              else "필요한 구성 소스를 준비했습니다.")
        return 0
    except (OSError, ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
