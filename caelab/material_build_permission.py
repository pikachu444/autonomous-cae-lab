"""Local operator source approval. HTTP can inspect, never grant this authority.

Permission records live outside the document/upload/result store. The exact
UTF-8 source is reviewed locally; its digest is an internal identity, not a GUI
field. This is operator consent to native code, not a C++ sandbox.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile
import uuid
from filelock import FileLock

KIND='autonomous-cae-lab.material-build-authority'


def directory():
    if os.name=='nt':
        base=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')
    else:
        base=Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config')
    return base/'AutonomousCAELab'/'material-build'


def _read(path):
    raw=Path(path).read_bytes()
    if len(raw)>2*1024*1024:raise ValueError('법칙 빌드 권한 파일 크기를 확인하세요.')
    value=json.loads(raw.decode('utf-8'))
    if not isinstance(value,dict):raise ValueError('법칙 빌드 권한 파일 형식을 확인하세요.')
    return value


def _write(path,value):
    raw=(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
    if len(raw)>2*1024*1024:raise ValueError('빌드 허용 기록이 가득 찼습니다. 로컬 운영자에게 기존 기록 정리를 요청하세요.')
    fd,name=tempfile.mkstemp(prefix='.permission-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def context():
    """Fixed operator directory only. No caller path, source, or grant accepted."""
    folder=directory()
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    with FileLock(str(folder/'authority.lock'),timeout=5):
        path=folder/'authority.json'
        if not path.exists():
            _write(path,{'kind':KIND,'authority_id':uuid.uuid4().hex})
        marker=_read(path)
        if marker.get('kind')!=KIND or not re.fullmatch(r'[0-9a-f]{32}',str(marker.get('authority_id',''))):
            raise ValueError('로컬 법칙 빌드 권한 폴더가 올바르지 않습니다.')
    return {**marker,'directory':str(folder.resolve()),'platform':os.name,
            'wsl_distribution':os.environ.get('WSL_DISTRO_NAME'),
            'grant_via_http':False}


def verify_local(folder,remote_context):
    """Confirm the GUI has OS file access to the actual service authority."""
    folder=Path(folder)
    marker=_read(folder/'authority.json')
    expected={key:remote_context.get(key) for key in ('kind','authority_id')}
    if marker!=expected or marker.get('kind')!=KIND:
        raise ValueError('현재 서비스와 다른 빌드 권한 폴더입니다. 변경하지 않았습니다.')
    return folder


def accessible_directory(remote_context):
    candidates=[directory()]
    # Windows Qt may access the existing WSL user's folder without shelling out.
    distro=remote_context.get('wsl_distribution')
    posix=remote_context.get('directory','')
    if (os.name=='nt' and remote_context.get('platform')=='posix' and isinstance(distro,str)
            and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',distro) and isinstance(posix,str)
            and posix.startswith('/') and '..' not in Path(posix).parts and '\\' not in posix):
        candidates.extend(Path('\\\\'+host+'\\'+distro+posix.replace('/','\\'))
                          for host in ('wsl.localhost','wsl$'))
    for candidate in candidates:
        try:return verify_local(candidate,remote_context)
        except (OSError,ValueError):pass
    return None


def approve_local(folder,remote_context,source,behaviour):
    """Called by native UI after Review/Confirm, never by a service route."""
    if not isinstance(source,str) or not 1<=len(source.encode('utf-8'))<=48*1024 or '\x00' in source:
        raise ValueError('빌드할 원문을 확인하세요.')
    if not isinstance(behaviour,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',behaviour):
        raise ValueError('법칙 이름을 확인하세요.')
    digest=hashlib.sha256(source.encode('utf-8')).hexdigest()
    folder=verify_local(folder,remote_context)
    with FileLock(str(folder/'permissions.lock'),timeout=5):
        verify_local(folder,remote_context)
        path=folder/'permissions.json'
        value=_read(path) if path.exists() else {'sources':{}}
        if set(value)!={'sources'} or not isinstance(value['sources'],dict):
            raise ValueError('빌드 허용 기록 형식을 확인하세요.')
        if digest not in value['sources'] and len(value['sources'])>=1024:
            raise ValueError('로컬 운영자의 빌드 허용 기록이 가득 찼습니다.')
        value['sources'][digest]={'behaviour':behaviour,'source':source}
        _write(path,value)
    return digest


def is_admitted(source,behaviour):
    """Exact bytes AND declared exported behavior. No remote config fallback."""
    path=directory()/'permissions.json'
    if not path.is_file():return False
    value=_read(path)
    digest=hashlib.sha256(source.encode('utf-8')).hexdigest()
    row=value.get('sources',{}).get(digest)
    return isinstance(row,dict) and row.get('source')==source and row.get('behaviour')==behaviour
