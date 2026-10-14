"""Opt-in Windows FreeCAD GUI check. Nothing executes on import.

Run from FreeCAD's Python console in a separate test instance with the repository
on sys.path. No CLI simulation substitute, no new solver and no tolerance change.
Evidence contains raw native statuses, including unexpected success/failure.
"""
from copy import deepcopy
import json
from pathlib import Path
import runpy
import uuid


def run(output_directory):
    import FreeCAD as App
    from apps.desktop_pre.bridge import Owner
    from apps.desktop_pre.motion import _pose
    from apps.desktop_pre.motion_history import unpack_poses
    from apps.desktop_pre.motion_occurrence import world_placement
    from apps.desktop_pre.projects import save_native_copy
    factory = runpy.run_path(str(Path(__file__).with_name('create_four_bar.py')))
    root = Path(output_directory)/('m3-'+uuid.uuid4().hex[:12])
    root.mkdir(parents=True, exist_ok=False)
    report = {'freecad_version': list(App.Version()), 'cases': [], 'checks': {}, 'root': str(root)}
    context = factory['build_document'](); owner = Owner(context['doc'], root)
    target = context['target']; motion = owner.motion; first = None
    fresh_owner = None
    def write():
        (root/'native-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        (root/'attempts.json').write_text(json.dumps(owner.read_metadata().get('motion_attempts', []),
                                                    ensure_ascii=False, indent=2), encoding='utf-8')
    def calculate(case):
        factory['set_case'](owner, context, case)
        try:
            result = motion.dispatch('pre.motion.calculate', {}, target)
            report['cases'].append({'case': case, 'result': result, 'exception': None})
            return result
        except Exception as error:
            report['cases'].append({'case': case, 'exception': str(error),
                                   'attempt': deepcopy(motion.descriptor()['attempts'][-1])})
            return None
        finally: write()
    try:
        factory['configure'](owner, context)
        first = calculate('normal')
        if first is None: raise AssertionError('정상 4R의 native 계산이 실패했습니다. 원자료를 확인하세요.')
        if first.get('constraint_check', {}).get('state') != 'PASSED':
            raise AssertionError('정상 4R의 관절·구동 충족 검사가 통과하지 않았습니다.')
        simulation = owner._object(owner.read_metadata()['motion']['simulation_id'])
        report['checks']['native_motion_property_types'] = {key: simulation.Group[0].getTypeIdOfProperty(key)
            for key in ('Joint', 'MotionType', 'Formula')}
        report['checks']['normal_constraint_check'] = deepcopy(first['constraint_check'])
        saved = deepcopy(owner.read_metadata()['motion_paths'][first['id']])
        poses = unpack_poses(saved['poses'], first['frame_count'])
        # The baseline is direct native replay of the SAME native result. This
        # checks the adapter, not a second analytical/approximate motion solver.
        max_pose_difference = 0.
        max_path_difference = 0.
        trace = saved['definition_snapshot']['traces'][0]
        try:
            for index in range(first['frame_count']):
                with owner.preview_changes(), motion._native_scope(context['assembly']):
                    status = context['assembly'].updateForFrame(index)
                    if isinstance(status, int) and status != 0: raise RuntimeError(str(status))
                motion._remember()
                direct = [_pose(owner._object(binding['id']).Placement) for binding in poses['bindings']]
                max_pose_difference = max(max_pose_difference, max(abs(a-b) for left, right in
                    zip(direct, poses['frames'][index]) for a, b in zip(left, right)))
                point = world_placement(context['assembly'], owner._object(trace['occurrence_id'])).multVec(App.Vector(*trace['point']))
                recorded = saved['paths'][trace['id']]['rows'][index]['point']
                max_path_difference = max(max_path_difference, max(abs(a-b) for a,b in zip((point.x,point.y,point.z), recorded)))
        finally:
            motion._remember(); motion._restore()
        report['checks']['same_native_frame_max_difference'] = max_pose_difference
        report['checks']['same_native_path_max_difference_mm'] = max_path_difference
        if max_pose_difference != 0. or max_path_difference != 0.:
            raise AssertionError('같은 native 프레임에서 읽은 배치/경로가 다릅니다. 허용치를 늘리지 않습니다.')
        # Exact duplicated input must be rejected BEFORE any new native call.
        duplicate = deepcopy(context['definition']); duplicate['drives'].append(deepcopy(duplicate['drives'][0]))
        try: motion.dispatch('pre.motion.configure', {'definition': duplicate}, target)
        except ValueError as error: report['checks']['duplicate_rejected'] = str(error)
        else: raise AssertionError('중복 구동 입력이 허용됐습니다.')
        for case in ('overconstrained', 'unreachable', 'singular'):
            calculate(case)
            report['checks'][case+'_old_result_unchanged'] = owner.read_metadata()['motion_paths'][first['id']] == saved
        # Preserve the ACTUAL native status, including zero with broken closure.
        # A check rejection is not a native error code or a singularity diagnosis.
        report['checks']['singular_diagnosis'] = 'UNKNOWN'
        # Save AFTER the failure cases, BEFORE repaired calculation or path reads.
        motion.before_design_action('save failed example')
        path = root/'after-failures.FCStd'
        save_native_copy(owner.doc, path, App=App)
        # This native copy retains metadata and exact shapes. .caepre interactive
        # save/reopen is additionally required through the installed CAE menu.
        with factory['no_automatic_solve'](App):
            document = App.openDocument(str(path))
            fresh_owner = Owner(document, root/'reopened')
        reopened = fresh_owner.motion
        frozen = reopened.dispatch('pre.motion.path', {'calculation_id': first['id'],
            'trace_id': trace['id'], 'start': 0, 'count': min(first['frame_count'], 200)}, target)
        if frozen['rows'] != saved['paths'][trace['id']]['rows'][:200]: raise AssertionError('재열기 경로가 바뀌었습니다.')
        native_frames_before = document.getObject(target['assembly_id']).numberOfFrames()
        frame = reopened.dispatch('pre.motion.frame', {'calculation_id': first['id'], 'frame': first['frame_count']-1}, target)
        report['checks']['cold_frame_retained'] = frame.get('retained') is True
        report['checks']['cold_native_frame_count_unchanged'] = document.getObject(target['assembly_id']).numberOfFrames() == native_frames_before
        reopened.before_design_action('restore reopened design')
        # Synchronous commands, before Qt can dispatch the first timer tick.
        reopened.dispatch('pre.motion.play', {'calculation_id': first['id'], 'direction': 1}, target)
        reopened.dispatch('pre.motion.path', {'calculation_id': first['id'],
            'trace_id': trace['id'], 'start': 0, 'count': 1}, target)
        if reopened._timer.isActive() or reopened._preview:
            raise AssertionError('저장 경로 읽기 후 재생이 멈추지 않았습니다.')
        reopened._tick()  # A queued callback must also be harmless.
        report['checks']['path_stops_before_first_tick'] = not reopened._preview
        reopened.before_design_action('draft gate check')
        editor = {'view': {'joint_id': context['joints']['A'].Name, 'drive_row': 0, 'trace_row': 0},
            'joint_draft': None, 'definition_draft': {'time': {'start': '0', 'end': '1', 'step': '0.05'},
            'fps': 20, 'tolerance': '1e', 'drives': [], 'traces': []}}
        reopened.dispatch('pre.motion.save_editor', {'editor': editor}, target)
        for operation, args in (('frame', {'frame': 1}), ('play', {'direction': 1})):
            try: reopened.dispatch('pre.motion.'+operation, {'calculation_id': first['id'], **args}, target)
            except ValueError: pass
            else: raise AssertionError('미적용 편집의 3D '+operation+'이 허용됐습니다.')
        reopened.dispatch('pre.motion.path', {'calculation_id': first['id'],
            'trace_id': trace['id'], 'start': 0, 'count': 1}, target)
        report['checks']['draft_gate_before_selection'] = reopened._calculation is None and reopened._replay is None
        editor['definition_draft'] = None
        reopened.dispatch('pre.motion.save_editor', {'editor': editor}, target)
        repaired = calculate('normal')
        if repaired is None: raise AssertionError('수정 후 정상 4R 재계산이 실패했습니다.')
        report['checks']['repair_new_result'] = repaired['id'] != first['id']
        if repaired.get('constraint_check', {}).get('state') != 'PASSED':
            raise AssertionError('수정 후 결과의 관절·구동 검사가 통과하지 않았습니다.')
        for case in ('overconstrained', 'unreachable', 'singular'):
            row = next(row for row in report['cases'] if row['case'] == case)
            if row['exception'] is None:
                raise AssertionError(case+'를 사용 가능한 성공으로 게시했습니다. 원입력과 결과를 보존하세요.')
            attempt = row['attempt']
            if attempt['state'] != 'FAILED' or attempt.get('previous_success_id') != first['id']:
                raise AssertionError(case+': 실패 시도/직전 성공 연결이 다릅니다.')
            if attempt['native_status'] == 0:
                raw = owner.read_metadata()['motion_paths'][attempt['raw_result_id']]
                if raw.get('accepted') is not False or raw['constraint_check']['state'] != 'FAILED':
                    raise AssertionError(case+': native 0 출력의 실제 불일치가 기록되지 않았습니다.')
                report['checks'][case+'_observations'] = deepcopy(raw['constraint_check'])
            if not report['checks'][case+'_old_result_unchanged']:
                raise AssertionError(case+': 이전 성공 원자료가 변경됐습니다.')
        if owner.read_metadata()['motion_paths'][first['id']] != saved:
            raise AssertionError('수정 후 이전 성공 원자료가 변경됐습니다.')
        report['completed'] = True
    except Exception as error:
        report['completed'] = False; report['error'] = str(error)
        raise
    finally:
        write()
        # Do not erase failed models or files, and do not close a user's window.
        for item in (fresh_owner, owner):
            if item is not None:
                try: item.motion.before_design_action('finish native check')
                finally: App.removeDocumentObserver(item); item.closed = True
    return report
