"""Find existing native applications without executing, installing or remembering them."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

TOOLS = {
    'freecad_executable': ('FreeCAD', 'CAELAB_FREECAD_EXE', ('FreeCAD', 'freecad')),
    'paraview_executable': ('ParaView', 'CAELAB_PARAVIEW_EXE', ('paraview',)),
}


def _windows_app_paths(filename):
    import winreg
    result = []
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths'+'\\'+filename,
                                    0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, '')
                    if isinstance(value, str):
                        result.append(os.path.expandvars(value.strip().strip('"')))
            except OSError:
                pass
    return result


def saved_executable(key):
    """The existing QSettings native Windows location, without importing Qt."""
    if key not in TOOLS or sys.platform != 'win32':
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\AutonomousCAELab\DesktopLaunchers') as node:
            value, _ = winreg.QueryValueEx(node, key)
            return value if isinstance(value, str) else None
    except OSError:
        return None


def discover(key, *, override=None, context=None, saved=None, environment=None, platform=None):
    """Return explicit failure, one file, or all candidates; never guess a version."""
    title, variable, commands = TOOLS[key]
    env = os.environ if environment is None else environment
    windows = (sys.platform if platform is None else platform) == 'win32'
    context = context or {}
    for value, source in ((override, '--executable'), (context.get(key), 'desktop.'+key),
                          (env.get(variable), variable)):
        if value is not None and value != '':
            path = Path(os.path.expandvars(value)).expanduser() if isinstance(value, str) else None
            valid = path is not None and path.is_file()
            return {'status': 'FOUND' if valid else 'INVALID',
                    'path': str(path.resolve()) if valid else str(value), 'source': source,
                    'candidates': [], 'stale_saved': None}
    if saved and Path(saved).is_file():
        return {'status': 'FOUND', 'path': str(Path(saved).resolve()), 'source': 'saved',
                'candidates': [], 'stale_saved': None}
    candidates = []
    seen = set()
    def add(value, source):
        path = Path(value)
        if not path.is_file():
            return
        # Automatic discovery treats a root launcher and its bin executable as one installation.
        binary = path.parent / 'bin' / path.name
        if windows and binary.is_file():
            path = binary
        path = path.resolve()
        identity = os.path.normcase(str(path))
        if identity not in seen:
            seen.add(identity)
            candidates.append({'path': str(path), 'source': source})
    names = tuple(name+'.exe' for name in commands) if windows else commands
    for directory in env.get('PATH', '').split(os.pathsep):
        if not directory:
            continue
        for name in names:
            found = shutil.which(name, path=directory)
            if found:
                add(found, 'PATH')
    if windows:
        for path in _windows_app_paths(names[0]):
            add(path, 'Windows App Paths')
        roots = [env.get('ProgramFiles') or env.get('PROGRAMFILES'),
                 env.get('ProgramFiles(x86)') or env.get('PROGRAMFILES(X86)')]
        if env.get('LOCALAPPDATA'):
            roots.append(str(Path(env['LOCALAPPDATA']) / 'Programs'))
        for root in filter(None, roots):
            for folder in Path(root).glob(title+'*'):
                if folder.is_dir():
                    for name in names:
                        add(folder / 'bin' / name, 'installed folder')
                        add(folder / name, 'installed folder')
        if key == 'paraview_executable' and env.get('CAE_POST_EXIT_PLUGIN') and env.get('CAE_POST_PARAVIEW_ROOT'):
            add(Path(env['CAE_POST_PARAVIEW_ROOT']) / 'bin/paraview.exe', 'CAE_POST_PARAVIEW_ROOT')
    status = 'FOUND' if len(candidates) == 1 else 'MULTIPLE' if candidates else 'NOT_FOUND'
    return {'status': status, 'path': candidates[0]['path'] if status == 'FOUND' else None,
            'source': candidates[0]['source'] if status == 'FOUND' else None,
            'candidates': candidates, 'stale_saved': str(saved) if saved else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-path')
    parser.add_argument('--freecad-exe')
    parser.add_argument('--paraview-exe')
    args = parser.parse_args(argv)
    context, warnings = {}, []
    if args.config_path and Path(args.config_path).is_file():
        try:
            context = json.loads(Path(args.config_path).read_text(encoding='utf-8-sig')).get('desktop', {})
            if not isinstance(context, dict):
                raise ValueError('desktop must be an object')
        except (OSError, ValueError, AttributeError) as error:
            warnings.append('설정 파일을 읽지 못했습니다: '+str(args.config_path)+' / '+str(error))
            context = {}
    tools = []
    for key, (title, _, _) in TOOLS.items():
        override = args.freecad_exe if key == 'freecad_executable' else args.paraview_exe
        tools.append({'key': key, 'tool': title, **discover(key, override=override, context=context,
                                                          saved=saved_executable(key))})
    # ASCII JSON also works with Windows PowerShell's legacy console encoding.
    print(json.dumps({'tools': tools, 'warnings': warnings}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
