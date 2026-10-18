"""Child-only CPython identity for the admitted generated deletion sensor."""
import math
import os
from pathlib import Path
import struct
import sys
import sysconfig

from ..contracts import CapabilityUnavailable
from ..evaluation import file_hash
from ..storage import canonical_hash


def runtime(environment):
    if (os.name!='nt' or sys.implementation.name!='cpython' or sys.version_info[:2]!=(3,12)
            or struct.calcsize('P')!=8 or sysconfig.get_config_var('Py_DEBUG')
            or sysconfig.get_config_var('Py_GIL_DISABLED')):
        raise CapabilityUnavailable('Generated sensor requires the selected Windows x64 release CPython 3.12 runtime')
    home=Path(sys.base_prefix).resolve()
    dll=home/'python312.dll'
    if not dll.is_file() or dll.is_symlink():
        raise CapabilityUnavailable('Selected CPython DLL is unavailable')
    files={}
    for directory in ('Lib','DLLs'):
        for path in sorted((home/directory).rglob('*')):
            if path.is_symlink():raise CapabilityUnavailable('Linked Python runtime dependency is unsupported')
            if path.is_file() and path.suffix.lower() in ('.py','.pyd','.dll'):
                files[path.relative_to(home).as_posix()]=file_hash(path)
    for name in ('python312.dll','python3.dll','vcruntime140.dll','vcruntime140_1.dll'):
        path=home/name
        if path.is_file():files[name]=file_hash(path)
    for name in ('Lib/encodings/__init__.py','Lib/json/__init__.py','Lib/ctypes/__init__.py','Lib/hashlib.py'):
        if name not in files:raise CapabilityUnavailable('Selected CPython standard library is incomplete: '+name)
    math_file=getattr(math,'__file__',None)
    math_origin=math.__spec__.origin
    if math_file is None and math_origin!='built-in':
        raise CapabilityUnavailable('Selected math module has no verifiable origin')
    identity={'implementation':'cpython','version':sys.version,'pointer_bits':64,
        'base_prefix':str(home),'prefix':str(home),'dll_path':str(dll),'dll_sha256':file_hash(dll),
        'math_file':str(Path(math_file).resolve()) if math_file else None,
        'math_origin':math_origin,'math_sha256':file_hash(math_file) if math_file else None,
        'dependency_sha256':canonical_hash(files),'dependencies':files}
    env={**environment,'RAD_PYTHON_PATH':str(dll),'PYTHONHOME':str(home),
         'PYTHONPATH':os.pathsep.join((str(home/'Lib'),str(home/'DLLs'))),
         'PYTHONNOUSERSITE':'1','PYTHONSAFEPATH':'1',
         'PATH':os.pathsep.join((str(home),str(home/'DLLs'),environment.get('PATH','')))}
    env.pop('PYTHONSTARTUP',None)
    return env,identity


def verify_observed(rows,expected):
    """Actual native callback loaded-module identity, not an installation claim."""
    selected=[row for row in rows if row.get('phase')=='ENGINE' and row.get('ordinal')==1]
    if len(selected)!=1:raise ValueError('Native Python runtime observation is missing or ambiguous')
    row=selected[0]
    if row.get('runtime_error'):raise ValueError('Native Python runtime observation failed: '+row['runtime_error'])
    actual=row.get('python',{})
    paths={'prefix','base_prefix','dll_path','math_file'}
    keys=('implementation','version','pointer_bits','prefix','base_prefix','dll_path','dll_sha256',
          'math_file','math_origin','math_sha256')
    for key in keys:
        a,b=actual.get(key),expected.get(key)
        if key in paths and a is not None and b is not None:
            a,b=os.path.normcase(os.path.realpath(a)),os.path.normcase(os.path.realpath(b))
        if a!=b:raise ValueError('Native Python runtime identity differs: '+key)
    return {'status':'PASS','source':'NATIVE_CALLBACK_LOADED_MODULE',
            'dll_path':actual['dll_path'],'dll_sha256':actual['dll_sha256'],
            'dependency_sha256':expected['dependency_sha256']}


def audit_generated_sensor(trace,engine_output,policy,expected):
    from ..impact_reclosure_policy import audit_trace
    audit=audit_trace(trace,engine_output,policy)
    try:audit['python_runtime']=verify_observed(audit['trace_rows'],expected)
    except (ValueError,KeyError,TypeError,OSError) as error:
        audit['python_runtime']={'status':'UNKNOWN','reason':str(error)}
    return audit
