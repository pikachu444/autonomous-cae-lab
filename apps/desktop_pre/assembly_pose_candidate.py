"""M4 independent editable model preparation on the existing native owner thread.

The Qt timer advances bounded native preparation stages, just as the existing
FEM owner waits for meshing. It is not a scheduler: no solver/job is submitted.
Original native graphs are copied with Project's existing save/relocation code.
CAD definitions are recursively copied once; every occurrence gets its own
ordinary Link and native SubShapeBinder, independent of Assembly recompute.
"""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json
import re
import uuid

from caelab import native_cad
from caelab.storage import load_json, save_json, utc_now
from . import metadata
from .assembly_pose_geometry import (select_frame, placement, same_pose, assert_same_shape,
                                     _local_digest, definition_at_link, RECOVERY)
from .motion import _pose
from .motion_occurrence import world_placement
from .projects import save_native_copy, exact_shape_serialization, remember_open, _linked
from .occurrence_fem import OPTIONS

KEY = 'assembly_pose_candidate'
OPERATIONS = ('pre.assembly_candidate.create', 'pre.assembly_candidate.inspect',
              'pre.assembly_candidate.cancel', 'pre.assembly_candidate.open',
              'pre.assembly_candidate.mesh', 'pre.assembly_candidate.material')
READ_ONLY = {'pre.assembly_candidate.inspect'}
TERMINAL = {'READY', 'FAILED', 'CANCELLED', 'INTERRUPTED'}
_PREPARING = []  # Native GUI lifecycle only, not model storage or another owner.


def in_preparation(doc):
    return any(doc is item for item in _PREPARING)


def _hold(doc):
    if not in_preparation(doc):
        _PREPARING.append(doc)


def _release(doc):
    _PREPARING[:] = [item for item in _PREPARING if item is not doc]


def _property(obj, kind, name, value):
    obj.addProperty(kind, name, '선택 자세')
    setattr(obj, name, value)
    obj.setEditorMode(name, 2)  # Relationship diagnostics stay out of ordinary property editing.


@contextmanager
def _snapshot_guard(owner, documents):
    """saveCopy must not trigger the original owner's design-pose restoration."""
    owners, seen = [], set()
    for doc in documents:
        other = owner if doc is owner.doc else getattr(owner, 'find_owner', lambda _: None)(doc)
        if other is not None and id(other) not in seen:
            if other.project.in_save or other.fem._pending:
                raise ValueError('참조 문서의 저장이나 메시 작업이 진행 중입니다. 그 작업을 마친 뒤 다시 만드세요.')
            owners.append((other, other.project.in_save)); seen.add(id(other))
        gdoc = owner.Gui.getDocument(doc.Name) if hasattr(owner.Gui, 'getDocument') else None
        if gdoc is not None and gdoc.getInEdit():
            raise ValueError('참조 문서에서 열린 편집을 완료하거나 취소하세요.')
    try:
        for other, _ in owners:
            other.project.in_save = True
        yield
    finally:
        for other, prior in owners:
            other.project.in_save = prior


def snapshot_source(owner, folder, selection, check):
    """Yield after each native document copy; retain a normal .caepre graph.

    The user's FileName, project save destination, generations and metadata are
    never changed. A selected result still pending only in RAM is not disguised
    as a saved source: M3 normally records it immediately in motion_paths.
    """
    docs = owner.project._documents()
    result = owner.read_metadata().get('motion_paths', {}).get(selection['calculation_id'])
    if not result or result.get('poses', {}).get('sha256') != selection['pose_sha256']:
        raise ValueError('이 운동 결과를 먼저 저장한 뒤 해석 모델을 만드세요. 원결과를 자동으로 바꾸지 않습니다.')
    stage = folder / 'source'
    stage.mkdir(parents=True, exist_ok=False)
    names = {doc.Name: 'documents/' + doc.Name + '.FCStd' for doc in docs}
    original_files = {Path(doc.FileName).resolve(): doc.Name for doc in docs if doc.FileName}
    records, files = [], {}
    from .assembly_pose_source import retained_design_poses
    design_poses = retained_design_poses(owner, docs, names)
    for doc in docs:
        check()
        native = stage / ('source-' + doc.Name + '.FCStd')
        with _snapshot_guard(owner, docs):
            save_native_copy(doc, native, App=owner.App)
        check()
        if not native.is_file():
            raise ValueError('원 조립의 편집 가능한 사본이 만들어지지 않았습니다.')
        destination = stage / names[doc.Name]

        def relocate(link, doc=doc):
            obj = doc.getObject(link['object_id'])
            targets = _linked(getattr(obj, link['property'])) if obj is not None and link['property'] in obj.PropertiesList else []
            external = [item for item in targets if item.Document is not doc and item.Name == link['target_name']]
            if len(external) > 1:
                raise ValueError('원부품 파일의 참조가 모호합니다. ' + RECOVERY)
            name = external[0].Document.Name if external else None
            if name is None and link['file'] and doc.FileName:
                name = original_files.get(native_cad.logical_file(Path(doc.FileName).parent, link['file']))
            if name in names:
                return Path(names[name]).name
            if link['file']:
                raise ValueError('참조 부품 파일이 없습니다. 원부품 파일을 복구하고 다시 만드세요.')
            return None

        native_cad.relocate(native, destination, relocate)
        files[names[doc.Name]] = destination
        records.append({'file': names[doc.Name], 'native_name': doc.Name, 'label': doc.Label,
                        'original_file': doc.FileName or None, 'sha256': native_cad.sha(destination),
                        'native_copy_sha256': native_cad.sha(native), 'bytes': destination.stat().st_size})
        yield '원 조립 보존', len(records), len(docs)
    check()
    manifest = {'kind': native_cad.KIND, 'schema_version': 1, 'document_id': owner.document_id,
                'revision': 'R'+uuid.uuid4().hex, 'entry': names[owner.doc.Name],
                'documents': records, 'metadata': owner.read_metadata(), 'unavailable_dependencies': [],
                'saved_generation': owner.generation, 'saved_utc': utc_now(),
                'engineering_release': 'UNKNOWN', 'design_pose_restored': not owner.motion._preview,
                'retained_view_only': bool(owner.motion._preview),
                'assembly_pose_source': {'version': 1, 'restore_design': design_poses}}
    native_cad.publish_project(folder / 'source.caepre', manifest, files)
    yield '원 조립 보존', len(docs), len(docs)


def _object(doc, name, label):
    obj = doc.getObject(name) if isinstance(name, str) else None
    if obj is None:
        raise ValueError(label + ': 참조 객체가 없습니다. 저장 사본을 별도로 열거나 삭제한 객체를 복구하세요.')
    return obj


def _source_identity(data, row):
    """Persist source identity separately from geometric equivalence (M4 only).

    Names refer to the retained SOURCE, not the transient document name assigned
    by FreeCAD on cold open. The private object names bind that source occurrence
    to precisely one Link and Binder. Labels and editable CAD values are absent.
    """
    path = row['path']
    if (not isinstance(path, list) or len(path) < 2 or len(set(path)) != len(path)
            or not all(isinstance(name, str) and name for name in path)
            or path[0] != data['assembly_id'] or path[-1] != row['occurrence_id']):
        raise ValueError('원 조립의 부품 경로가 바뀌었습니다. 보존한 원 조립에서 다시 만드세요.')
    keys = ('source_document', 'source_id', 'source_type', 'occurrence_id',
            'copied_source_id', 'link_id', 'body_id')
    if any(not isinstance(row.get(key), str) or not row[key] for key in keys):
        raise ValueError('원 조립과 해석 부품의 정확한 연결 정보가 없습니다.')
    if not isinstance(data.get('source_document_id'), str) or not data['source_document_id']:
        raise ValueError('원 조립 문서의 연결 정보가 없습니다.')
    return json.dumps({'source_document_id': data['source_document_id'],
                       'path': path, **{key: row[key] for key in keys}},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _unit_link(link):
    scale = getattr(link, 'ScaleVector', None)
    return (int(getattr(link, 'ElementCount', 0)) == 0
            and float(getattr(link, 'Scale', 1.)) == 1.
            and (scale is None or all(float(getattr(scale, key)) == 1. for key in ('x', 'y', 'z'))))


def validate_model(owner, *, exact=False):
    """Read-only retained-open check. Never refresh binders/rebind/remesh/solve.

    The report separates the persisted lifecycle from read-only model validity.
    ``ready`` admits M4 FEM actions, NOT solver success or complete FEM inputs.
    exact=True is exclusively preparation/readback, never ordinary admission.
    Failed/partial drafts remain inspectable, editable and saveable.
    """
    stored = owner.read_metadata()
    if KEY not in stored:
        return None
    data = stored[KEY]
    errors, rows = [], []
    if not isinstance(data, dict) or data.get('version') != 1:
        return _model_report(data, ['이 선택 자세 모델의 저장 형식을 지원하지 않습니다. 원파일을 보존하세요.'], [])
    try:
        analysis = _object(owner.doc, data['analysis_id'], '해석')
        if analysis.TypeId != 'Fem::FemAnalysis':
            raise ValueError('해석 객체의 종류가 바뀌었습니다.')
        if not data['bodies']:
            raise ValueError('해석 부품 준비가 끝나지 않았습니다. 보존한 원 조립에서 다시 만드세요.')
        used_paths, used_bodies, used_links = set(), set(), set()
        allowed = set()
        for row in data['bodies']:
            identity = _source_identity(data, row)
            path = tuple(row['path'])
            if path in used_paths or row['body_id'] in used_bodies or row['link_id'] in used_links:
                raise ValueError('서로 다른 부품 배치가 같은 해석 대상으로 연결되었습니다.')
            used_paths.add(path); used_bodies.add(row['body_id']); used_links.add(row['link_id'])
            body = _object(owner.doc, row['body_id'], row['label'])
            link = _object(owner.doc, row['link_id'], row['label'])
            source = _object(owner.doc, row['copied_source_id'], row['label'])
            if (body.TypeId != 'PartDesign::SubShapeBinder' or link.TypeId != 'App::Link'
                    or link.LinkedObject is not source or bool(link.LinkTransform) or not _unit_link(link)
                    or source.TypeId != row['source_type']
                    or [(obj, tuple(subs)) for obj, subs in body.Support] != [(link, ('',))]
                    or any(getattr(body, key) != value for key, value in OPTIONS.items())
                    or not same_pose(_pose(body.Placement), [0., 0., 0., 0., 0., 0., 1.])
                    or float(body.Offset) != 0. or getattr(body, 'ExpressionEngine', [])
                    or list(body.SourceOccurrencePath) != row['path']
                    or body.SourcePart is not source or body.PoseOccurrence is not link
                    or getattr(body, 'SourceIdentity', None) != identity
                    or not same_pose(_pose(body.SelectedWorldPose), row['world_pose'])):
                raise ValueError(row['label'] + ': 부품과 해석 형상의 연결이 바뀌었습니다. 해당 객체를 복구하세요.')
            if source.Document is not owner.doc or link.Document is not owner.doc:
                raise ValueError('원 조립의 살아 있는 부품을 참조하고 있습니다. 독립 사본을 다시 여세요.')
            if body.Shape.isNull() or not body.Shape.isValid() or len(body.Shape.Solids) != 1:
                raise ValueError(row['label'] + ': 형상이 비어 있거나 유효한 솔리드가 아닙니다.')
            # The path is an immutable SOURCE correspondence. Candidate groups
            # have no transform; the Link alone carries the frozen world pose.
            if body.getParentGeoFeatureGroup() is not None or link.getParentGeoFeatureGroup() is not None:
                raise ValueError(row['label'] + ': 해석 형상의 상위 배치가 추가되었습니다. 원래 그룹으로 복구하세요.')
            if exact:
                if not same_pose(_pose(link.Placement), row['world_pose']):
                    raise ValueError(row['label'] + ': 저장한 프레임과 실제 배치가 다릅니다.')
                if _local_digest(owner, source.Shape) != row['geometry']:
                    raise ValueError(row['label'] + ': 저장하는 동안 CAD 원형상이 바뀌었습니다.')
            import Part
            # Never trust a cached Link/Binder pair that agrees only with itself.
            # The current editable private CAD must agree as well, including on
            # exact=False after CAD edits and on a no-recompute cold read.
            current = definition_at_link(source, link)
            native_link = Part.getShape(link, transform=True)
            assert_same_shape(owner, native_link, current, row['label'])
            assert_same_shape(owner, body.Shape, current, row['label'])
            for mesh in (obj for obj in analysis.Group if hasattr(obj, 'FemMesh') and getattr(obj, 'Shape', None) is body):
                allowed.add(mesh.Name)
            rows.append({'path': row['path'], 'label': row['label'], 'body_id': body.Name,
                         'link_id': link.Name, 'source_id': source.Name,
                         'pose_edited': not same_pose(_pose(link.Placement), row['world_pose'])})
        # A truncated metadata list must not hide another retained occurrence.
        # Native identity properties already exist in 02; no format migration or
        # rewriting of source, mesh or face fingerprints is needed.
        retained_bodies = {obj.Name for obj in owner.doc.Objects
                           if obj.TypeId == 'PartDesign::SubShapeBinder'
                           and 'SourceIdentity' in getattr(obj, 'PropertiesList', ())}
        if retained_bodies != used_bodies:
            raise ValueError('저장한 부품 목록과 실제 해석 부품이 다릅니다. 준비 사본을 확인하세요.')
        permitted_bodies = set(used_bodies)
        for obj in analysis.Group:
            for ref in getattr(obj, 'References', []):
                if ref[0].Name not in permitted_bodies or ref[0].Document is not owner.doc:
                    raise ValueError(obj.Label + ': 원부품 대신 선택 자세의 해석 형상을 선택하세요.')
            if hasattr(obj, 'FemMesh') and getattr(obj, 'Shape', None) is not None and obj.Shape.Name not in permitted_bodies:
                raise ValueError(obj.Label + ': 메시가 선택 자세의 해석 형상을 가리키지 않습니다.')
        if list(getattr(owner.doc, 'OutList', [])):
            raise ValueError('독립 모델에 외부 문서 연결이 남아 있습니다. 원파일을 보존하고 참조 부품을 복구하세요.')
        if exact and any(obj.TypeId.startswith('Assembly::') for obj in owner.doc.Objects):
            raise ValueError('해석 모델에 운동 계산 객체가 들어왔습니다. 원 조립은 보존했습니다.')
    except (ValueError, RuntimeError, AttributeError, TypeError, KeyError) as error:
        errors.append(str(error))
    return _model_report(data, errors, rows)


def _model_report(data, errors, rows):
    data = data if isinstance(data, dict) else {}
    state = data.get('state', 'DRAFT')
    if not isinstance(state, str):
        state = 'UNKNOWN'
    complete = state == 'READY'
    ready = complete and not errors
    if errors:
        reason = errors[0]
    elif state == 'PREPARING':
        reason = '준비가 끝나지 않은 사본입니다. 수정·저장은 가능하지만 메시와 해석에는 사용할 수 없습니다.'
    elif not complete:
        reason = '준비를 마치지 못한 사본입니다. 수정·저장은 가능하며 원 조립 사본에서 다시 만들 수 있습니다.'
    else:
        reason = ''
    return {'state': 'INVALID' if errors else state, 'preparation_state': state,
            'preparation_complete': complete, 'geometry_valid': not errors,
            'ready': ready, 'blocked_reason': reason, 'errors': errors,
            'bodies': rows, 'frame': data.get('frame'), 'time': data.get('time'),
            'frame_kind': data.get('frame_kind'), 'analysis_id': data.get('analysis_id')}


def require_valid(owner, *, exact=False):
    report = validate_model(owner, exact=exact)
    if report is None:
        raise ValueError('선택 자세에서 만든 해석 모델을 여세요.')
    if report['errors']:
        raise ValueError(report['errors'][0])
    # PREPARING is required by the private initial save/reopen path. It is not
    # an exception for mesh/input/run callers: they must use exact=False.
    if exact:
        if report['preparation_state'] not in {'PREPARING', 'READY'}:
            raise ValueError(report['blocked_reason'])
    elif not report['ready']:
        raise ValueError(report['blocked_reason'])
    return report


class PoseCandidates:
    """Per-document native preparation lifecycle; the main bridge retains commands."""
    def __init__(self, owner):
        self.owner = owner
        self.current = None
        self._work = None
        self._timer = None
        self._candidate = None
        self._document = None
        self._cancelled = False
        self._folder = None
        self._selection = None
        self._version = None
        self._scene = None
        self._source_poses = []
        self._source_filenames = []
        self._previous_active = None
        self._model_cache = None

    @property
    def busy(self):
        return self._work is not None

    def _root(self):
        return self.owner.export_root / self.owner.document_id / 'assembly_candidates'

    def descriptor(self):
        history = []
        root = self._root()
        for file in sorted(root.glob('A*/candidate-preparation.json'), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
            try:
                row = load_json(file)
                if self.current and row.get('id') == self.current['id']:
                    row = deepcopy(self.current)
                elif row.get('state') not in TERMINAL:
                    row = dict(row, state='INTERRUPTED', message='이전 준비가 중단되었습니다. 저장된 사본을 열어 확인하세요.')
                history.append(row)
            except (OSError, ValueError):
                continue  # A damaged attempt never prevents opening the original CAD.
        if self.current and not any(row.get('id') == self.current['id'] for row in history):
            history.insert(0, deepcopy(self.current))
        # Preparation writes metadata directly and can change state without an
        # owner generation increment. Never keep a READY button from that cache.
        data = self.owner.read_metadata()
        stamp = (self.owner.generation, KEY in data, data.get(KEY))
        if self._model_cache is None or self._model_cache[0] != stamp:
            self._model_cache = (deepcopy(stamp), validate_model(self.owner) if KEY in data else None)
        return {'busy': self.busy, 'current': deepcopy(self.current), 'history': history,
                'model': deepcopy(self._model_cache[1])}

    def _record(self, **updates):
        self.current.update(updates, updated_utc=utc_now())
        save_json(self._folder / 'candidate-preparation.json', self.current)

    def _check(self):
        if self._cancelled:
            raise PreparationCancelled('해석 모델 만들기를 취소했습니다. 준비된 사본은 유지됩니다.')
        if self.owner.closed or self.owner.generation != self._version:
            raise ValueError('준비 중 원 조립이 닫히거나 편집되었습니다. 새 편집과 준비한 사본을 모두 보존했습니다.')
        if any(self.owner.doc.getObject(obj.Name) is not obj or not same_pose(_pose(getattr(obj, prop)), expected)
               for obj, prop, expected in self._source_poses):
            raise ValueError('준비 중 원문서의 표시 자세가 바뀌었습니다. 새 자세를 덮어쓰지 않고 준비를 중단했습니다.')
        if any(doc.FileName != name for doc, name in self._source_filenames):
            raise ValueError('준비 중 원부품의 저장 위치가 바뀌었습니다. 원문서와 준비 사본을 보존했습니다.')
        if self.owner.project.graph_version() != self._graph:
            raise ValueError('준비 중 참조 부품이 바뀌었습니다. 원본과 사본을 보존했습니다.')
        if self.owner.motion._scene(self.owner._object(self._selection['assembly_id'])) != self._scene:
            raise ValueError('준비 중 조립 자세나 관절 참조가 바뀌었습니다. 원본과 사본을 보존했습니다.')

    def start(self, args, target, *, automatic=True):
        self.owner.assert_thread()
        if self.busy:
            raise ValueError('해석 모델을 만드는 중입니다. 완료하거나 취소한 뒤 다시 만드세요.')
        if set(args) != {'calculation_id', 'frame'} or set(target) != {'assembly_id'}:
            raise ValueError('운동 결과와 프레임 하나를 선택하세요.')
        self._folder = self._root() / ('A'+uuid.uuid4().hex)
        self._folder.mkdir(parents=True, exist_ok=False)
        self.current = {'id': self._folder.name, 'state': 'PREPARING', 'phase': 'CHECK',
                        'message': '선택 자세 확인', 'created_utc': utc_now(),
                        'folder': str(self._folder), 'source_document_id': self.owner.document_id,
                        'assembly_id': target['assembly_id'], **deepcopy(args),
                        'engineering_release': 'UNKNOWN', 'mesh_execution': 'NOT_PERFORMED',
                        'solver_execution': 'NOT_PERFORMED'}
        self._cancelled = False
        self._candidate = self._document = None
        self._record()
        try:
            if self.owner.fem._pending or self.owner.recovery_error:
                raise ValueError(self.owner.recovery_error or '메시 작업을 마친 뒤 해석 모델을 만드세요.')
            self._selection = select_frame(self.owner, target['assembly_id'], args['calculation_id'], args['frame'])
            # Stop only view playback, not restore/recompute/adopt the source.
            if self.owner.motion._timer:
                self.owner.motion._timer.stop()
                if self.owner.motion._state == 'PLAYING':
                    self.owner.motion._state = 'PAUSED'
            self._version = self.owner.generation
            self._graph = self.owner.project.graph_version()
            self._source_poses = [(self.owner._object(row['id']), 'Placement', _pose(self.owner._object(row['id']).Placement))
                                  for row in self._selection['identity']['bindings']]
            self._source_poses += [(obj, prop, _pose(getattr(obj, prop)))
                                  for obj in self.owner.motion._joints(self.owner._object(target['assembly_id']))
                                  for prop in ('Placement1', 'Placement2') if hasattr(obj, prop)]
            self._source_filenames = [(doc, doc.FileName) for doc in self.owner.project._documents()]
            self._scene = self.owner.motion._scene(self.owner._object(target['assembly_id']))
            self._previous_active = getattr(self.owner.App, 'ActiveDocument', None)
            self._record(selection=self._selection, phase='COPY_SOURCE', message='원 조립 보존')
            self._work = self._prepare()
            if automatic:
                QtCore = getattr(self.owner, 'QtCore', None)
                if QtCore is None:
                    from PySide import QtCore
                if self._timer is None:
                    self._timer = QtCore.QTimer()
                    self._timer.setInterval(0)
                    self._timer.timeout.connect(self.advance)
                self._timer.start()
        except Exception as error:
            self._work = None
            self._record(state='FAILED', message=str(error), error_type=type(error).__name__)
        return deepcopy(self.current)

    def advance(self):
        if not self.busy:
            return
        self.owner.assert_thread()
        try:
            self._check()
            phase, done, total = next(self._work)
            self._record(message=phase, completed=done, total=total)
        except StopIteration:
            self._finish('READY', '해석 모델을 만들었습니다.')
        except PreparationCancelled as error:
            self._finish('CANCELLED', str(error))
        except Exception as error:
            self._finish('FAILED', str(error), error_type=type(error).__name__)

    def _prepare(self):
        owner, App, Gui = self.owner, self.owner.App, self.owner.Gui
        import Part
        import ObjectsFem
        selection = self._selection
        yield from snapshot_source(owner, self._folder, selection, self._check)
        self._record(source_project=str(self._folder/'source.caepre'),
                     source_sha256=native_cad.sha(self._folder/'source.caepre'))
        self._check()
        assembly = owner._object(selection['assembly_id'])
        # Native exact occurrence shape in WORLD coordinates is observed before
        # copying. This guards LinkTransform/context semantics, not just counts.
        root, prefix = assembly, ''
        if getattr(assembly, 'Parents', None):
            root, prefix = assembly.Parents[0]
        expected = {}
        sources, source_keys = [], []
        for row in selection['leaves']:
            obj = owner._object(row['occurrence_id'])
            current_world = world_placement(assembly, obj)
            if current_world is None:
                raise ValueError('부품의 세계 배치를 읽을 수 없습니다.')
            subname = prefix + '.'.join(row['path'][1:]) + '.'
            shape = Part.getShape(root, subname, transform=True)
            shape = shape.copy()
            delta = placement(App, row['world_pose']).multiply(current_world.inverse())
            shape.Placement = delta.multiply(shape.Placement)
            expected[row['occurrence_id']] = shape
            source = obj.getLinkedObject() if obj.isDerivedFrom('App::Link') else obj
            key = (source.Document.Name, source.Name)
            if key not in source_keys:
                source_keys.append(key); sources.append(source)
        document = App.newDocument('PoseAnalysis')
        self._document = document
        _hold(document)
        document.Label = selection['assembly_label'] + ' — 프레임 ' + str(selection['frame'])
        document.UndoMode = 1
        # Identity must exist before risky native geometry work: saving an
        # invalid draft must not initialize identity through a recompute.
        self._write_model([], None, 'PREPARING')
        self._record(phase='COPY_PARTS', message='부품 형상 복사', native_document=document.Name)
        # A single native recursive copy preserves shared CAD dependencies.
        copied = document.copyObject(sources, True)
        copied = list(copied) if isinstance(copied, (list, tuple)) else [copied]
        if len(copied) != len(sources):
            raise ValueError('CAD 원부품 복사의 대응 수가 다릅니다. 준비한 문서를 보존했습니다.')
        copied_map = dict(zip(source_keys, copied))
        if list(getattr(document, 'OutList', [])):
            raise ValueError('복사된 CAD에 원문서 참조가 남았습니다. 외부 참조를 독립 부품으로 복구한 뒤 다시 만드세요.')
        if any(obj.TypeId.startswith('Assembly::') for obj in document.Objects):
            raise ValueError('원부품의 의존성에 운동 객체가 있습니다. 해당 부품을 독립 CAD로 복구하세요.')
        definitions = document.addObject('App::DocumentObjectGroup', 'SourceParts')
        definitions.Label = 'CAD 원부품'
        for original, clone in zip(sources, copied):
            definitions.addObject(clone)
            if original.TypeId != clone.TypeId or _local_digest(owner, original.Shape) != _local_digest(owner, clone.Shape):
                raise ValueError(original.Label + ': 편집 가능한 CAD 복사의 형상이 다릅니다.')
        posed = document.addObject('App::DocumentObjectGroup', 'PoseParts')
        posed.Label = '선택 자세의 부품'
        groups = {(selection['assembly_id'],): posed}
        analysis = ObjectsFem.makeAnalysis(document, 'Analysis')
        analysis.Label = '해석'
        analysis_id = analysis.Name
        # Solver settings object only. No executable discovery and no solve.
        solver = ObjectsFem.makeSolverCalculiXCcxTools(document, 'SolverCcx')
        analysis.addObject(solver)
        records = []
        self._write_model(records, analysis_id, 'PREPARING')
        self._record(phase='CREATE_OCCURRENCES')
        yield '부품 형상 복사', len(copied), len(copied)
        for index, row in enumerate(selection['leaves'], 1):
            self._check()
            original = owner._object(row['occurrence_id'])
            source = original.getLinkedObject() if original.isDerivedFrom('App::Link') else original
            clone = copied_map[(source.Document.Name, source.Name)]
            parent = posed
            for length in range(2, len(row['path'])):
                key = tuple(row['path'][:length])
                if key not in groups:
                    group = document.addObject('App::DocumentObjectGroup', 'PoseGroup')
                    group.Label = owner._object(key[-1]).Label
                    parent.addObject(group); groups[key] = group
                parent = groups[key]
            link = document.addObject('App::Link', 'PoseOccurrence')
            link.setLink(clone)
            link.LinkTransform = False
            link.Placement = placement(App, row['world_pose'])
            link.Label = row['label'] + ' — 배치'
            definitions.addObject(link)
            body = document.addObject('PartDesign::SubShapeBinder', 'PoseBody')
            for name, value in OPTIONS.items():
                setattr(body, name, value)
            body.Support = [(link, ('',))]
            body.Label = row['label'].split(' / ')[-1]
            parent.addObject(body)
            _property(body, 'App::PropertyStringList', 'SourceOccurrencePath', row['path'])
            _property(body, 'App::PropertyLink', 'SourcePart', clone)
            _property(body, 'App::PropertyLink', 'PoseOccurrence', link)
            _property(body, 'App::PropertyPlacement', 'SelectedWorldPose', placement(App, row['world_pose']))
            record = {**deepcopy(row), 'body_id': body.Name, 'link_id': link.Name,
                      'copied_source_id': clone.Name}
            _property(body, 'App::PropertyString', 'SourceIdentity',
                      _source_identity({'source_document_id': owner.document_id,
                                        'assembly_id': selection['assembly_id']}, record))
            if body.recompute() is not True:
                raise ValueError(row['label'] + ': 해석 형상을 만들지 못했습니다.')
            document.recompute()
            assert_same_shape(owner, Part.getShape(link, transform=True), expected[row['occurrence_id']], row['label'])
            assert_same_shape(owner, body.Shape, expected[row['occurrence_id']], row['label'])
            records.append(record)
            self._write_model(records, analysis_id, 'PREPARING')
            # Geometry is selected by the native tree/viewport, not a surrogate list.
            for obj in document.Objects:
                if hasattr(obj, 'ViewObject') and hasattr(obj.ViewObject, 'Visibility'):
                    obj.ViewObject.Visibility = (obj.Name in {entry['body_id'] for entry in records}
                        or any(obj is group for group in groups.values()))
            yield '부품 배치', index, len(selection['leaves'])
        from .bridge import Owner
        self._candidate = Owner(document, owner.export_root, App=App, Gui=Gui)
        self._candidate.QtCore = getattr(owner, 'QtCore', None)
        require_valid(self._candidate, exact=True)
        self._record(phase='SAVE', message='편집 모델 저장')
        with exact_shape_serialization(App):
            prepared = self._candidate.project.save(self._folder/'prepared.caepre')
        self._record(prepared_project=prepared['path'], prepared_sha256=prepared['sha256'])
        yield '편집 모델 저장', 1, 1
        self._check()
        self._record(phase='REOPEN', message='저장 자세 확인')
        self._roundtrip(prepared['path'])
        require_valid(self._candidate, exact=True)  # Read only, no native motion/solve/rebind.
        self._write_model(records, analysis_id, 'READY')
        with exact_shape_serialization(App):
            result = self._candidate.project.save(self._folder/'model.caepre')
        self._record(project=result['path'], project_sha256=result['sha256'],
                     phase='VERIFY', message='해석 대상 확인')
        self._roundtrip(result['path'])
        require_valid(self._candidate, exact=True)
        # No native recompute on the retained read. Meshes/conditions are still
        # genuinely absent; the user creates them in the existing FEM owner.
        self._record(native_document=self._document.Name, analysis_id=self._selection_analysis())
        yield '해석 대상 확인', len(records), len(records)

    def _selection_analysis(self):
        return metadata.read(self._document)[KEY]['analysis_id']

    def _write_model(self, records, analysis_id, state):
        previous = metadata.read(self._document)
        value = previous.get(KEY, {})
        value.update(version=1, state=state, analysis_id=analysis_id,
                     **{key: deepcopy(self._selection[key]) for key in
                        ('assembly_id', 'assembly_label', 'calculation_id', 'frame', 'time', 'frame_kind',
                         'clock', 'coordinate_unit', 'coordinate_frame', 'pose_sha256', 'physics', 'ground_to_support')},
                     source_document_id=self.owner.document_id, source_project='source.caepre',
                     source_sha256=self.current.get('source_sha256'), bodies=deepcopy(records))
        previous.update(document_id=previous.get('document_id') or 'P'+uuid.uuid4().hex)
        previous[KEY] = value
        metadata.write(self._document, previous)

    def _roundtrip(self, project):
        """Only private preparation documents may be closed and reopened."""
        App, Gui = self.owner.App, self.owner.Gui
        document = self._document
        self._candidate.close(); self._candidate = None
        App.closeDocument(document.Name); _release(document)
        self._document = None
        folder = self._folder / ('readback-'+uuid.uuid4().hex[:8])
        manifest, entry = native_cad.unpack_project(project, folder)
        if manifest.get('unavailable_dependencies'):
            raise ValueError('저장한 해석 모델의 참조 부품 파일이 없습니다.')
        existing = list(App.listDocuments().values())
        restored = App.openDocument(str(entry))
        self._document = restored; _hold(restored)
        if any(restored is doc for doc in existing) or Path(restored.FileName).resolve() != entry.resolve():
            raise ValueError('저장 확인에서 다른 열린 문서를 사용했습니다. 원문서를 보존하세요.')
        restored.UndoMode = 1
        remember_open(restored, manifest, project)
        from .bridge import Owner
        self._candidate = Owner(restored, self.owner.export_root, App=App, Gui=Gui)
        self._candidate.project.path = Path(project)
        self._candidate.QtCore = getattr(self.owner, 'QtCore', None)

    def _finish(self, state, message, **extra):
        if self._timer:
            self._timer.stop()
        work, self._work = self._work, None
        if work is not None:
            work.close()
        try:
            if state != 'READY' and self._document is not None:
                if self._candidate is None:
                    from .bridge import Owner
                    self._candidate = Owner(self._document, self.owner.export_root, App=self.owner.App, Gui=self.owner.Gui)
                data = self._candidate.read_metadata()
                if KEY in data:
                    data[KEY].update(state=state, preparation_error=message)
                    self._candidate.write_metadata(data)
                with exact_shape_serialization(self.owner.App):
                    draft = self._candidate.project.save(self._folder/'draft.caepre')
                extra.update(draft_project=draft['path'], draft_sha256=draft['sha256'])
            if self._candidate is not None:
                self._candidate.close()
                self._candidate = None
            if self._document is not None:
                _release(self._document)
                if state == 'READY':
                    manifest = native_cad.inspect_project(self.current['project'])
                    remember_open(self._document, manifest, self.current['project'])
                    self.owner.App.setActiveDocument(self._document.Name)
                elif self._previous_active is not None and self._previous_active.Name in self.owner.App.listDocuments():
                    self.owner.App.setActiveDocument(self._previous_active.Name)
        except Exception as error:
            extra['retention_error'] = str(error)
            state = 'FAILED' if state == 'READY' else state
            message += ' 사본 저장/열기 확인이 필요합니다: ' + str(error)
        finally:
            if self._candidate is not None:
                try:
                    self._candidate.close()
                except Exception as error:
                    extra.setdefault('retention_error', str(error))
                self._candidate = None
            if self._document is not None:
                _release(self._document)
            if state != 'READY' and self._previous_active is not None:
                try:
                    if self._previous_active.Name in self.owner.App.listDocuments():
                        self.owner.App.setActiveDocument(self._previous_active.Name)
                except (RuntimeError, ReferenceError):
                    pass
            self._record(state=state, message=message, finished_utc=utc_now(), **extra)

    def cancel(self):
        self.owner.assert_thread()
        if self.busy:
            self._cancelled = True
            self._record(message='취소 중 — 현재 native 복사를 마친 뒤 사본을 보존합니다.')
        return deepcopy(self.current)

    def close(self):
        if self.busy:
            self._cancelled = True
            self._finish('CANCELLED', '원문서가 닫혀 준비를 중단했습니다. 준비한 사본은 유지됩니다.')

    def open_attempt(self, identifier, which):
        if not isinstance(identifier, str) or not re.fullmatch(r'A[0-9a-f]{32}', identifier):
            raise ValueError('목록에서 저장한 해석 모델을 선택하세요.')
        if which not in {'model', 'draft', 'source'}:
            raise ValueError('해석 모델, 준비 사본 또는 원 조립을 선택하세요.')
        folder = self._root()/identifier
        record = load_json(folder/'candidate-preparation.json')
        field = {'model': 'project', 'draft': 'draft_project', 'source': 'source_project'}[which]
        filename = {'model': 'model.caepre', 'draft': 'draft.caepre', 'source': 'source.caepre'}[which]
        digest_key = {'model': 'project_sha256', 'draft': 'draft_sha256', 'source': 'source_sha256'}[which]
        # Reopening may fail after prepared.caepre was safely committed and
        # the private document was closed. Expose that explicit recovery copy;
        # never substitute it for the requested final model or original source.
        if which == 'draft' and not record.get(field) and record.get('prepared_project'):
            field, filename, digest_key = 'prepared_project', 'prepared.caepre', 'prepared_sha256'
        file = folder/filename
        if not record.get(field) or not file.is_file():
            raise ValueError('저장 파일이 없습니다. 파일 열기에서 보관한 .caepre를 직접 선택하세요. 원 조립은 유지됩니다.')
        if native_cad.sha(file) != record.get(digest_key):
            raise ValueError('보관 파일이 바뀌었습니다. 파일 열기로 그 파일을 별도로 확인하세요. 자동 대체하지 않습니다.')
        receipt = {'id': identifier, 'kind': 'native_design', 'path': str(file), 'sha256': record[digest_key]}
        return self.owner.project.open(receipt)

    def dispatch(self, operation, args, target):
        self.owner.assert_thread()
        if operation == 'pre.assembly_candidate.create':
            return self.start(args, target)
        if operation == 'pre.assembly_candidate.inspect':
            if args or target:
                raise ValueError('목록 조회에는 추가 입력이 필요하지 않습니다.')
            return self.descriptor()
        if operation == 'pre.assembly_candidate.cancel':
            if args or target:
                raise ValueError('현재 준비 작업만 취소할 수 있습니다.')
            return self.cancel()
        if operation == 'pre.assembly_candidate.open':
            if set(args) != {'attempt_id', 'which'} or target:
                raise ValueError('저장 목록에서 열 대상을 선택하세요.')
            return self.open_attempt(args['attempt_id'], args['which'])
        if operation in {'pre.assembly_candidate.mesh', 'pre.assembly_candidate.material'}:
            self.owner.before_design_action(operation)
            if args or set(target) != {'object_id'}:
                raise ValueError('해석할 부품 하나를 선택하세요.')
            return prepare_fem_object(self.owner, target['object_id'], operation.rsplit('.', 1)[1])
        raise ValueError('지원하지 않는 선택 자세 작업입니다.')


class PreparationCancelled(Exception):
    pass


def prepare_fem_object(owner, body_id, kind):
    """Create native editable mesh/material objects; no mesher or solver runs."""
    import ObjectsFem
    report = require_valid(owner)
    row = next((row for row in report['bodies'] if row['body_id'] == body_id), None)
    if row is None:
        raise ValueError('선택 자세의 해석 부품을 트리나 모델에서 선택하세요.')
    analysis = owner._object(report['analysis_id'])
    body = owner._object(body_id)
    created = {}
    if kind == 'mesh':
        existing = [obj for obj in analysis.Group if hasattr(obj, 'FemMesh') and getattr(obj, 'Shape', None) is body]
        if len(existing) > 1:
            raise ValueError('이 부품에 메시가 여러 개입니다. 사용할 메시를 해석 트리에서 직접 선택하세요.')
        if existing:
            return {'object_id': existing[0].Name, 'body_id': body_id, 'created': False}
        def change():
            mesh = ObjectsFem.makeMeshGmsh(owner.doc, 'PoseMesh')
            mesh.Label = body.Label + ' — 메시'
            mesh.Shape = body
            analysis.addObject(mesh)
            # This is an empty settings object, not a generated mesh. The
            # existing FEM completion observer records the association only
            # after nonempty native mesh data arrives; do not stamp/rebind now.
            created['object_id'] = mesh.Name
        owner._transaction('선택 부품의 메시 설정', change)
    elif kind == 'material':
        existing = [obj for obj in analysis.Group if hasattr(obj, 'Material') and
                    any(ref[0] is body for ref in getattr(obj, 'References', []))]
        if len(existing) > 1:
            raise ValueError('이 부품에 재료가 여러 개입니다. 사용할 재료를 해석 트리에서 직접 선택하세요.')
        if existing:
            return {'object_id': existing[0].Name, 'body_id': body_id, 'created': False}
        def change():
            material = ObjectsFem.makeMaterialSolid(owner.doc, 'PoseMaterial')
            material.Label = body.Label + ' — 재료'
            material.References = [(body, ('',))]
            # No guessed material values: the existing native material task is
            # opened by the UI. An incomplete material is an editable draft.
            material.Material = {}
            analysis.addObject(material)
            created['object_id'] = material.Name
        owner._transaction('선택 부품의 재료', change)
    else:
        raise ValueError('메시 또는 재료를 선택하세요.')
    return {**created, 'body_id': body_id, 'created': True, 'executed': False}


def selected_body(owner):
    """Exact native viewport/tree selection, never a previous panel row or label."""
    data = owner.read_metadata().get(KEY, {})
    bodies = {row['body_id']: row for row in data.get('bodies', [])}
    found = set()
    for selection in owner.Gui.Selection.getSelectionEx(owner.doc.Name):
        obj = selection.Object
        candidates = [obj]
        # A native group selection can carry a precise child subpath. Resolve
        # that path, not LinkedObject and not a similarly named other Link.
        for sub in selection.SubElementNames or ():
            pieces = sub.split('.')
            for length in range(1, len(pieces)):
                if hasattr(obj, 'getSubObject'):
                    target = obj.getSubObject('.'.join(pieces[:length])+'.', 1)
                    if target is not None: candidates.append(target)
        for obj in candidates:
            if getattr(obj, 'Document', None) is owner.doc and obj.Name in bodies:
                found.add(obj.Name)
    return next(iter(found)) if len(found) == 1 else None
