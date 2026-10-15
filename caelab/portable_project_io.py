"""Bounded, no-follow file operations for an explicitly selected working copy.

This is not a document store. Document publication/verification remains with
MaterialDocuments and its concrete Data/Numerical owners.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from typing import Any
import zipfile

from .evaluation import file_hash
from .storage import load_json, save_json

MAX_FILES = 100_000
MAX_BYTES = 20 * 1024**3
MAX_JSON_BYTES = 16 * 1024**2
_RESERVED = re.compile(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', re.I)


@dataclass(frozen=True)
class Issue:
    code: str
    location: str
    message: str
    recovery: str
    document_id: str | None = None


class PortableProjectError(ValueError):
    """Actionable failure; never converts missing evidence into a success."""
    def __init__(self, issues: list[Issue] | Issue):
        self.issues = [issues] if isinstance(issues, Issue) else issues
        super().__init__('\n'.join(f'{i.message}\n위치: {i.location}\n복구: {i.recovery}' for i in self.issues))

    def as_dict(self) -> dict[str, Any]:
        return {'status': 'BLOCKED', 'issues': [asdict(i) for i in self.issues],
                'executed': False, 'engineering_release': 'NOT_RELEASED'}


def fail(code: str, location: Any, message: str, recovery: str,
         document_id: str | None = None) -> None:
    raise PortableProjectError(Issue(code, str(location), message, recovery, document_id))


def relative_name(value: str) -> str:
    """Accept one portable POSIX relative name, including Korean and spaces.

    Windows ADS, drive/UNC paths, reserved device names and aliases differing
    only by trailing spaces/dots are refused on *every* operating system.
    """
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or any(ord(c) < 32 or c in '*?<>|"' for c in value)):
        fail('UNSAFE_PATH', value, '사본 안의 상대 경로가 아닙니다.', '원본의 경로 기록을 확인하세요.')
    path = PurePosixPath(value)
    if (not path.parts or path.is_absolute() or value != path.as_posix() or any(p in ('', '.', '..')
            or p.endswith((' ', '.')) or _RESERVED.match(p) for p in path.parts)):
        fail('UNSAFE_PATH', value, '이동 가능한 안전한 파일 경로가 아닙니다.', '상대 경로의 원본 자료를 선택하세요.')
    return value


def no_links(path: Path) -> None:
    """Refuse symlinks, junctions and Windows reparse points in existing parents."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400):
            fail('LINK_REFUSED', part, '링크/재분석 경로는 자동 수집하지 않습니다.', '실제 폴더나 파일을 명시적으로 선택하세요.')


def inside(root: Path, relative: str, *, must_exist: bool = True) -> Path:
    relative_name(relative)
    root = Path(os.path.abspath(root))
    target = root.joinpath(*PurePosixPath(relative).parts)
    no_links(target)
    if not target.resolve().is_relative_to(root.resolve()):
        fail('PATH_ESCAPE', relative, '자료 경로가 사본 폴더를 벗어납니다.', '올바른 사본을 다시 선택하세요.')
    if must_exist and not target.is_file():
        fail('MISSING_ASSET', target, '필수 파일이 없습니다.', '같은 원본 파일을 명시적으로 찾아 복구하거나 새 사본을 만드세요.')
    return target


def json_file(path: Path) -> Any:
    no_links(path)
    if not path.is_file():
        fail('MISSING_ASSET', path, '필수 기록이 없습니다.', '원본 기록을 복구한 뒤 다시 시도하세요.')
    if path.stat().st_size > MAX_JSON_BYTES:
        fail('JSON_TOO_LARGE', path, '기록의 읽기 한도를 넘었습니다.', '이 파일의 형식과 크기를 확인하세요.')
    return load_json(path)


def fingerprint_file(path: Path) -> dict[str, Any]:
    no_links(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        fail('NOT_REGULAR_FILE', path, '일반 파일이 아닙니다.', '실제 보존 파일을 선택하세요.')
    digest = file_hash(path)
    after = path.stat()
    if (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        fail('SOURCE_CHANGED', path, '읽는 동안 파일이 변경되었습니다.', '편집/저장을 마친 뒤 포함 자료를 다시 확인하세요.')
    return {'sha256': digest, 'bytes': info.st_size}


def copy_verified(source: Path, target: Path, expected: dict[str, Any]) -> None:
    no_links(source); no_links(target)
    before = fingerprint_file(source)
    if before != {'sha256': expected['sha256'], 'bytes': expected['bytes']}:
        fail('SOURCE_CHANGED', source, '확인한 원본 파일과 다릅니다.', '포함 자료를 다시 확인한 뒤 새 사본을 만드세요.')
    target.parent.mkdir(parents=True, exist_ok=True)
    # O_EXCL protects the new output, O_NOFOLLOW protects the selected input.
    fd = os.open(source, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as incoming, target.open('xb') as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        outgoing.flush(); os.fsync(outgoing.fileno())
    if fingerprint_file(source) != before or fingerprint_file(target) != before:
        fail('SOURCE_CHANGED', source, '복사 도중 원본이 바뀌었습니다.', '기존 사본은 그대로 두고 포함 자료부터 다시 확인하세요.')


def _portable_aliases(names: list[str]) -> None:
    spellings: dict[str, str] = {}
    for name in names:
        path = PurePosixPath(relative_name(name))
        for part in (path, *path.parents):
            if part.as_posix() == '.':
                continue
            key, spelling = part.as_posix().casefold(), part.as_posix()
            if key in spellings and spellings[key] != spelling:
                fail('DUPLICATE_PATH', name, '폴더/파일 이름의 대소문자 경로가 충돌합니다.',
                     '같은 폴더에는 한 가지 정확한 철자를 사용하세요.')
            spellings[key] = spelling


def verify_inventory(root: Path, files: list[dict[str, Any]]) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    total = 0
    if not isinstance(files, list) or len(files) > MAX_FILES:
        fail('INVALID_INVENTORY', root, '파일 목록이 잘못되었거나 한도를 넘었습니다.', '정상 사본을 다시 선택하세요.')
    _portable_aliases([row['path'] for row in files])
    for row in files:
        name = relative_name(row['path'])
        if name.casefold() in seen:
            fail('DUPLICATE_PATH', name, '대소문자만 다른 중복 파일입니다.', '이동 가능한 원본 파일 이름을 사용하세요.')
        seen.add(name.casefold())
        if type(row.get('bytes')) is not int or row['bytes'] < 0 or not re.fullmatch('[0-9a-f]{64}', str(row.get('sha256'))):
            fail('INVALID_INVENTORY', name, '파일 크기/식별 기록이 잘못되었습니다.', '정상 사본의 기록을 사용하세요.')
        total += row['bytes']
        if total > MAX_BYTES:
            fail('SIZE_LIMIT', root, '사본 읽기 한도를 넘었습니다.', '자료를 명시적으로 나누어 저장하세요.')
        try:
            path = inside(root, name)
            if fingerprint_file(path) != {'bytes': row['bytes'], 'sha256': row['sha256']}:
                issues.append(Issue('ASSET_CHANGED', str(path), '보존 파일이 원래 내용과 다릅니다.',
                                    '동일한 파일을 선택해 복구하세요. 변경된 파일은 자동 대체하지 않습니다.'))
        except PortableProjectError as error:
            issues.extend(error.issues)
    return issues


def extract_archive(archive: str | Path, destination: str | Path) -> Path:
    """Extract a product archive only into a new directory; never follow links.

    Call verify_project() before opening its documents. No zip member is ever
    interpreted as a command, absolute file location or provider configuration.
    """
    archive, destination = Path(archive), Path(destination)
    no_links(archive); no_links(destination)
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        seen: set[str] = set()
        total = 0
        if len(entries) > MAX_FILES:
            fail('SIZE_LIMIT', archive, '압축 파일의 항목 수가 한도를 넘었습니다.', '정상 제품 사본을 선택하세요.')
        for entry in entries:
            # ZipInfo may normalize backslashes on Windows and truncate NUL.
            # Validate the actual central-directory spelling BEFORE publication.
            raw = entry.orig_filename
            relative_name(raw[:-1] if raw.endswith('/') else raw)
            if raw != entry.filename:
                fail('UNSAFE_ARCHIVE', raw, '압축 경로의 원래 철자와 해석된 이름이 다릅니다.',
                     'POSIX 상대 이름으로 만든 정상 사본을 선택하세요.')
            name = entry.filename[:-1] if entry.is_dir() else entry.filename
            relative_name(name)
            key = name.casefold()
            mode = entry.external_attr >> 16
            if key in seen or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                fail('UNSAFE_ARCHIVE', name, '중복 또는 링크/특수 파일은 풀지 않습니다.', '정상 제품 사본을 선택하세요.')
            if entry.flag_bits & 1:
                fail('ENCRYPTED_ARCHIVE', name, '암호 자료는 자동으로 수집/해제하지 않습니다.', '사용자가 명시적으로 준비한 파일을 선택하세요.')
            seen.add(key); total += entry.file_size
            if total > MAX_BYTES:
                fail('SIZE_LIMIT', archive, '압축 해제 크기가 한도를 넘었습니다.', '한도 안의 제품 사본을 선택하세요.')
        _portable_aliases([e.filename[:-1] if e.is_dir() else e.filename for e in entries])
        # Parent/child path collisions fail before creating any output.
        file_names = {e.filename.casefold() for e in entries if not e.is_dir()}
        for entry in entries:
            if any(p.as_posix().casefold() in file_names for p in PurePosixPath(entry.filename).parents if str(p) != '.'):
                fail('UNSAFE_ARCHIVE', entry.filename, '파일/폴더 경로가 충돌합니다.', '정상 압축 파일을 선택하세요.')
        destination.mkdir(parents=False, exist_ok=False)
        try:
            for entry in entries:
                path = inside(destination, (entry.filename[:-1] if entry.is_dir() else entry.filename), must_exist=False)
                if entry.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(entry) as incoming, path.open('xb') as outgoing:
                        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        except BaseException:
            shutil.rmtree(destination)
            raise
    return destination
