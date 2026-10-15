"""Opt-in owned Windows native acceptance. No native execution on import.

Uses scripts/native_check.py's existing Job runner, never taskkill/name matching,
never starts another scheduler. Three fresh processes: compute, valid cold read,
invalid-draft cold read. A process receipt alone is NOT a test success.
"""
from copy import deepcopy
import argparse
import json
import math
import os
from pathlib import Path
import runpy
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
FACTORY = Path(__file__).with_name('create_relations.py')


def _json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def _fresh_folder(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()): raise FileExistsError('검사 폴더는 비어 있어야 합니다: '+str(path))
    return path


def _release(owner):
    if owner is None: return
    try: owner.motion.close()
    finally:
        owner.App.removeDocumentObserver(owner); owner.closed = True


def _expected(case, oracle):
    # Reference file is arithmetic expectation, not native data. A=60 affects X
    # as well as C; its explicitly retained 2 mm/deg coefficient gives 125*t.
    return {'A': (60 if case=='changed' else 30)*oracle['time_s'], 'B': oracle['B_deg'],
        'C': oracle[{'linear': 'C_linear_deg', 'changed': 'C_linear_after_A60_deg', 'nonlinear': 'C_nonlinear_deg'}[case]],
        'L': oracle['L_mm'], 'X': 125*oracle['time_s'] if case=='changed' else oracle['X_mixed_mm']}


def _measure_case(owner, context, result, case, report):
    from apps.desktop_pre.motion import _pose
    from apps.desktop_pre.motion_history import unpack_poses
    from apps.desktop_pre.motion_occurrence import world_placement
    App, motion = owner.App, owner.motion
    assembly = context['assembly']; target = context['target']
    original = deepcopy(owner.read_metadata()['motion_paths'][result['id']])
    payload = unpack_poses(original['poses'], result['frame_count'])
    epsilon = original['definition_snapshot']['native_error_tolerance']
    oracle = json.loads(Path(__file__).with_name('reference-oracle.json').read_text(encoding='utf-8'))['rows']
    times = [None]+[r['time_s'] for r in oracle]
    if original['frame_times'] != times: raise AssertionError('실제 native frame 시각이 oracle 시각과 다릅니다.')
    if result.get('constraint_check', {}).get('state') != 'PASSED':
        raise AssertionError('native 상태만으로 통과시키지 않습니다. 관절·구동 검사가 통과해야 합니다.')
    entry = {'case': case, 'result': result, 'native_frame_samples': [], 'maximum_trace_error_mm': 0.,
        'maximum_native_pose_difference': 0., 'maximum_coordinate_error_rad_or_mm': 0.}
    report['cases'].append(entry)
    try:
        for index, time in enumerate(times):
            with owner.preview_changes(), motion._native_scope(assembly):
                status = assembly.updateForFrame(index)  # direct native replay, NO replacement calculation
                if isinstance(status, int) and status != 0: raise RuntimeError('native updateForFrame: '+str(status))
            motion._remember()
            direct = [_pose(owner._object(binding['id']).Placement) for binding in payload['bindings']]
            difference = max(abs(a-b) for p, q in zip(direct, payload['frames'][index]) for a,b in zip(p,q))
            entry['maximum_native_pose_difference'] = max(entry['maximum_native_pose_difference'], difference)
            if difference != 0.: raise AssertionError('같은 native 출력의 보존 pose와 직접 replay가 다릅니다.')
            sample = {'frame': index, 'time_s': time, 'frame_kind': 'design' if time is None else 'physical',
                      'coordinates': {}, 'traces': {}}
            entry['native_frame_samples'].append(sample)
            expected = None if time is None else _expected(case, oracle[index-1])
            for name, joint in context['joints'].items():
                pair = [world_placement(assembly, getattr(joint, 'Reference'+str(side))[0]).multiply(
                    getattr(joint, 'Placement'+str(side))) for side in (1,2)]
                relative = pair[0].inverse().multiply(pair[1])
                if name in ('A', 'B', 'C'):
                    x = relative.Rotation.multVec(App.Vector(1,0,0))
                    observed = math.atan2(x.y,x.x); unit = 'rad'
                    requested = None if expected is None else math.radians(expected[name])
                    error = 0. if requested is None else abs(math.remainder(observed-requested, 2*math.pi))
                else:
                    observed = float(relative.Base.z); unit = 'mm'
                    requested = None if expected is None else expected[name]
                    error = 0. if requested is None else abs(observed-requested)
                sample['coordinates'][name] = {'observed': observed, 'expected': requested, 'unit': unit}
                entry['maximum_coordinate_error_rad_or_mm'] = max(entry['maximum_coordinate_error_rad_or_mm'], error)
                if error > epsilon: raise AssertionError(name+': native 좌표와 독립 기대값 불일치. 허용값은 유지합니다.')
            for trace in original['definition_snapshot']['traces']:
                name = 'C' if trace['occurrence_id'] == context['moving']['C'].Name else 'X'
                world = world_placement(assembly, owner._object(trace['occurrence_id'])).multVec(App.Vector(*trace['point']))
                observed = [float(world.x), float(world.y), float(world.z)]
                stored = original['paths'][trace['id']]['rows'][index]
                if stored['time'] != time or stored['point'] != observed:
                    raise AssertionError('같은 native 시각의 world trace가 보존 경로와 다릅니다.')
                expected_world = None
                if expected is not None:
                    if name == 'C':
                        angle = math.radians(expected['C'])
                        local = App.Vector(20*math.cos(angle), context['origins']['C'][1]+20*math.sin(angle), 0)
                    else: local = App.Vector(20, context['origins']['X'][1], expected['X'])
                    p = context['root_design'].multVec(local); expected_world = [p.x,p.y,p.z]
                    error = math.sqrt(sum((a-b)**2 for a,b in zip(observed,expected_world)))
                    entry['maximum_trace_error_mm'] = max(entry['maximum_trace_error_mm'],error)
                    if error > epsilon: raise AssertionError('선택 로컬 점의 world trace 불일치. 허용값은 유지합니다.')
                sample['traces'][trace['id']] = {'observed_mm': observed, 'expected_mm': expected_world}
    finally:
        motion._remember(); motion._restore()
    if owner.read_metadata()['motion_paths'][result['id']] != original: raise AssertionError('원 native 결과를 변경했습니다.')
    # Read through the existing public path command as well as its retained data.
    for trace_id, path in original['paths'].items():
        page = motion.dispatch('pre.motion.path', {'calculation_id':result['id'], 'trace_id':trace_id, 'start':0, 'count':result['frame_count']}, target)
        if page['rows'] != path['rows']: raise AssertionError('공개 경로 명령과 원 경로가 다릅니다.')
    return original


def compute(output, report):
    from apps.desktop_pre.bridge import Owner
    factory = runpy.run_path(str(FACTORY))
    context = factory['build_document'](); owner = Owner(context['doc'], output/'workspace')
    motion, target = owner.motion, context['target']; previous = {}
    try:
        for case in ('linear','changed','nonlinear'):
            definition, configured = factory['configure'](owner,context,case)
            if configured.get('executed') is not False: raise AssertionError('configure가 계산으로 보고됐습니다.')
            result = motion.dispatch('pre.motion.calculate', {}, target)
            original = _measure_case(owner,context,result,case,report)
            for key,value in previous.items():
                if owner.read_metadata()['motion_paths'][key] != value: raise AssertionError('재입력 후 기존 결과 변경')
            previous[result['id']] = original
            _json(output/'compute-progress.json', report)
        final = result['id']
        valid_editor = factory['editor_for'](definition)
        motion.dispatch('pre.motion.save_editor', {'editor':valid_editor}, target)
        owner.project.save(output/'valid.caepre')
        _json(output/'valid-expected.json', {'definition':definition, 'editor':valid_editor, 'paths':previous, 'last_result':final})
        invalid = factory['editor_for'](definition,invalid=True)
        motion.dispatch('pre.motion.save_editor', {'editor':invalid}, target)
        owner.project.save(output/'raw.caepre')
        _json(output/'raw-expected.json', {'definition':definition, 'editor':invalid, 'paths':previous, 'last_result':final})
        report['saved'] = ['valid.caepre','raw.caepre']
    except BaseException:
        try: owner.project.save(output/'failed.caepre')
        except Exception as save_error: report['failure_save_error'] = str(save_error)
        _json(output/'failed-metadata.json', owner.read_metadata())
        raise
    finally:
        _release(owner)  # release only this example owner; no other document/process


def cold_read(output, source_root, kind, report):
    import FreeCAD as App
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre import projects
    from caelab import native_cad
    source = source_root/(kind+'.caepre'); source_hash = native_cad.sha(source)
    expected = json.loads((source_root/(kind+'-expected.json')).read_text(encoding='utf-8'))
    # Same reader as Project.open; test uses a direct local file, not a forged
    # registered input receipt. Native project registry/core are unchanged.
    manifest, entry = native_cad.unpack_project(source, output/'working-copy')
    doc = App.openDocument(str(entry)); doc.UndoMode = 1
    projects.restore_document_labels(doc,manifest); projects.remember_open(doc,manifest,source)
    owner = Owner(doc,output/'workspace'); motion = owner.motion
    target = {'assembly_id':owner.read_metadata()['motion']['assembly_id']}
    before = deepcopy(owner.read_metadata())
    try:
        view = motion.descriptor()
        if view['calculation'] is not None: raise AssertionError('읽기가 새 계산을 만들었습니다.')
        if before['motion']['definition'] != expected['definition']: raise AssertionError('선언 관계가 달라졌습니다.')
        if before['motion_editors'][target['assembly_id']] != expected['editor']: raise AssertionError('초안/선택 복원 불일치')
        if before['motion_paths'] != expected['paths']: raise AssertionError('원 결과/경로/pose 복원 불일치')
        for key,result in expected['paths'].items():
            for trace_id,path in result['paths'].items():
                value = motion.dispatch('pre.motion.path', {'calculation_id':key, 'trace_id':trace_id,'start':0,'count':result['frame_count']}, target)
                if value['rows'] != path['rows']: raise AssertionError('cold read 경로 불일치')
        if owner.read_metadata() != before: raise AssertionError('읽기만으로 원 자료를 변경했습니다.')
        report['read_only_metadata_unchanged'] = True
        last = expected['last_result']; record = expected['paths'][last]
        if kind=='raw':
            blocked = []
            for op,args in (('calculate',{}),('frame',{'calculation_id':last,'frame':3}),
                            ('play',{'calculation_id':last,'direction':1}),('adopt_pose',{'calculation_id':last,'frame':3})):
                try: motion.dispatch('pre.motion.'+op,args,target)
                except ValueError as error:
                    if '편집' not in str(error): raise
                    blocked.append(op)
                else: raise AssertionError('미완성 관계식인데 '+op+' 허용')
            report['draft_blocks'] = blocked
            if owner.read_metadata() != before: raise AssertionError('차단한 작업이 원 자료를 변경했습니다.')
        else:
            for frame,time in enumerate(record['frame_times']):
                value = motion.dispatch('pre.motion.frame',{'calculation_id':last,'frame':frame},target)
                if value['time'] != time: raise AssertionError('보존 프레임의 실제 시각 불일치')
            motion.before_design_action('cold read restore')
        # Explicit repair/re-apply and re-save, not a hidden calculation.
        configured = motion.dispatch('pre.motion.configure', {'definition':deepcopy(expected['definition'])}, target)
        if configured.get('executed') is not False: raise AssertionError('재적용에서 숨은 계산')
        factory = runpy.run_path(str(FACTORY))
        motion.dispatch('pre.motion.save_editor', {'editor':factory['editor_for'](expected['definition'])},target)
        owner.project.save(output/'repaired.caepre')
        if owner.read_metadata()['motion_paths'] != expected['paths']: raise AssertionError('복구 저장 후 원 결과 변경')
        if native_cad.sha(source) != source_hash: raise AssertionError('원 .caepre 바이트를 덮어썼습니다.')
        report['original_project_sha256'] = source_hash
        report['original_results_unchanged'] = True
    finally:
        _release(owner)


def child(request_path):
    """Called only by the fresh-process macro generated by run()."""
    import FreeCAD as App
    request = json.loads(Path(request_path).read_text(encoding='utf-8'))
    output = Path(request['output']); owned = False
    report = {'phase':request['phase'], 'pid':os.getpid(), 'completed':False, 'cases':[],
        'freecad_version':list(App.Version()), 'kind':'actual-native-execution', 'exception':None}
    code = 1
    try:
        # Prevent an accidentally redirected/imported macro from closing a user's
        # running FreeCAD. The generated private user config must be this process'.
        configured = App.ConfigGet('UserParameter')
        if not configured or Path(configured).resolve() != Path(request['user_config']).resolve():
            raise RuntimeError('검사 전용 native 프로세스임을 확인하지 못했습니다. 사용자 창은 닫지 않습니다.')
        if App.listDocuments(): raise RuntimeError('기존 문서가 있는 프로세스에서는 실행하지 않습니다.')
        owned = True
        if request['phase']=='compute': compute(output,report)
        else: cold_read(output,Path(request['source_root']),request['phase'],report)
        report['completed'] = True; code = 0
    except BaseException as error:
        report['exception'] = str(error); report['traceback'] = traceback.format_exc()
    finally:
        _json(output/'result.json',report)
        if owned:
            from PySide import QtCore
            # Timer is ONLY an owned test-process exit; no application scheduler.
            QtCore.QTimer.singleShot(0, lambda: QtCore.QCoreApplication.exit(code))
    return report


def run(executable, output_directory, timeout_seconds=180):
    if os.name != 'nt': raise OSError('실제 native 검사는 Windows owned Job runner에서만 실행합니다.')
    executable = Path(executable).resolve(strict=True)
    if executable.name.lower() != 'freecad.exe': raise ValueError('FreeCAD GUI의 FreeCAD.exe를 지정하세요.')
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0: raise ValueError('양수 timeout을 지정하세요.')
    output = _fresh_folder(output_directory)
    runner = runpy.run_path(str(ROOT/'scripts'/'native_check.py'))['run_native_check']
    results = {'completed':False, 'phases':[]}
    try:
        for phase in ('compute','valid','raw'):
            folder = output/phase; folder.mkdir()
            user_config = folder/'user.cfg'
            request = folder/'request.json'
            _json(request, {'phase':phase,'output':str(folder),'source_root':str(output/'compute'),'user_config':str(user_config)})
            macro = folder/'run.FCMacro'
            macro.write_text('import sys, runpy\n'+'sys.path.insert(0, '+repr(str(ROOT))+')\n'+
                'runpy.run_path('+repr(str(Path(__file__).resolve()))+')["child"]('+repr(str(request))+')\n',encoding='utf-8')
            receipt = runner([str(executable),'--user-cfg',str(user_config),'--system-cfg',str(folder/'system.cfg'),str(macro)],
                folder/'job',float(timeout_seconds),cwd=ROOT)
            child_report = json.loads((folder/'result.json').read_text(encoding='utf-8')) if (folder/'result.json').is_file() else None
            results['phases'].append({'phase':phase,'receipt':receipt.receipt,'exit_code':receipt.exit_code,
                'timed_out':receipt.timed_out,'cleanup':receipt.cleanup,'result':child_report})
            if (receipt.exit_code != 0 or receipt.timed_out or receipt.cleanup != 'job_empty' or
                    not child_report or not child_report.get('completed') or child_report.get('pid') != receipt.pid):
                raise RuntimeError('native '+phase+' 검사 실패/미확인. 해당 프로세스 로그와 원파일을 보존했습니다.')
        results['completed'] = True
    except BaseException as error:
        results['error'] = str(error)
        raise
    finally: _json(output/'acceptance.json',results)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description='M1 관계식 전용 Windows native 수용 검사')
    parser.add_argument('--freecad',required=True); parser.add_argument('--output-dir',required=True)
    parser.add_argument('--timeout',type=float,default=180)
    args = parser.parse_args(argv)
    run(args.freecad,args.output_dir,args.timeout)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
