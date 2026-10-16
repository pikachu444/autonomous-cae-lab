"""Editable analysis records owned by the current native Post session.

All data, filters and views are ParaView objects. This module keeps the small
editable recipe/selection records that Save State alone cannot explain.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import uuid
import xml.etree.ElementTree as ET

from paraview import simple as p
from caelab import post_comparison as physical

try:
    from . import external, analysis, measurements, contact_views, naming
except ImportError:
    import external
    import analysis
    import measurements
    import contact_views
    import naming

OPERATIONS = (
    'post.source_add', 'post.source_select', 'post.source_repair',
    'post.comparison_edit', 'post.curve_catalog', 'post.mapping_validate', 'post.sample',
    'post.filter_edit', 'post.measurement_edit', 'post.measurement_capture',
    'post.measurement_snapshot', 'post.measurement_open', 'post.contact_inspect', 'post.contact_measurement',
    'post.apply', 'post.show_analysis', 'post.reset', 'post.undo', 'post.redo', 'post.export',
    'post.report_image_verify',
    'post.curve_origin_read', 'post.curve_origin_verify', 'post.curve_origin_select',
)


def clone(value):
    return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def label(proxy):
    matches = [name for (name, _), item in p.GetSources().items() if external._same_proxy(proxy, item)]
    if len(matches) != 1:
        raise ValueError('STALE_TARGET: the native pipeline object is missing or ambiguously registered')
    return matches[0]


def source_revision(record):
    entry = Path(record['entry_path'])
    return digest({'format': entry.suffix.lower(), 'files': sorted([
        {'relative': Path(row['path']).relative_to(entry.parent).as_posix(),
         'sha256': row['sha256'], 'bytes': row['bytes']} for row in record['source_pins']], key=lambda row: row['relative'])})


def _number(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    return value


def _identifier(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix) or not value.replace('-', '').isalnum():
        raise ValueError('Choose an exact ' + prefix + ' reference from this analysis')
    return value


class Workspace:
    def __init__(self, owner, document):
        self.owner = owner
        self.document = document
        self.state = document.setdefault('analysis', {'version': 1, 'objects': {}, 'active_object': None})
        if self.state.get('version') != 1 or not isinstance(self.state.get('objects'), dict):
            raise ValueError('Unsupported saved Post analysis version; the saved project is preserved')
        self.bundles = {}
        self.last_preview = {}
        self._new_history_keys = set()
        self.restore_issues = []
        for key, record in self.document.get('sources', {}).items():
            record.setdefault('source_ref', key)
            record.setdefault('source_revision', source_revision(record))
        # Loaded pipelines keep their registration names, not session-global IDs.
        for obj in self.state['objects'].values():
            if 'redo_stack' not in obj:
                obj['redo_stack'] = [obj['redo']] if obj.get('redo') else []
            obj.pop('redo', None)
            for revision in obj.get('history', []):
                unavailable = next((row for row in document.get('native_history_availability', {}).get('histories', [])
                    if row['history']['object_ref'] == obj['id'] and row['history']['revision_id'] == revision['id']
                    and row['state'] == 'UNAVAILABLE_DECLARED'), None)
                if unavailable is not None:
                    from caelab.native_post_dependencies import digest as history_digest
                    if history_digest(revision) != unavailable['record_sha256']:
                        raise ValueError('SNAPSHOT_CHANGED: unavailable history record differs')
                    self.restore_issues.append({'object_ref': obj['id'], 'revision': revision['id'],
                        'message': '과거 기록·원값 미확인: 보존한 분석 파일을 복구하세요.'})
                    continue
                cached = p.FindSource(revision.get('retained_source_name', '')) if revision.get('retained_source_name') else None
                if cached is not None:
                    bundle = {'source': cached, 'proxies': [cached],
                        'summary': deepcopy(revision.get('summary', {})), 'retained_only': True,
                        'retained_graph': deepcopy(revision['retained_graph'])}
                    try:
                        self._verify_record(obj, revision, bundle)
                        self.bundles[revision['id']] = bundle
                    except (OSError, ValueError, RuntimeError) as error:
                        self.restore_issues.append({'object_ref': obj['id'], 'revision': revision['id'], 'message': str(error)})
                    continue
                proxy = p.FindSource(revision['source_name'])
                if (proxy is not None and revision.get('summary', {}).get('comparison_version') == 2
                        and revision.get('result_file') and proxy.GetXMLName() in
                        {'XMLUnstructuredGridReader', 'XMLPolyDataReader'}
                        and external.reader_input_files(proxy) == [Path(revision['result_file']).resolve()]):
                    bundle = {'source': proxy, 'proxies': [proxy],
                              'summary': deepcopy(revision.get('summary', {})), 'retained_only': True}
                    bundle['retained_graph'] = analysis.graph_signature(bundle)
                    reopened = dict(revision); reopened.pop('retained_reader', None)
                    binding = self._verify_record(obj, reopened, bundle)
                    self.bundles[revision['id']] = bundle
                    revision.update(retained_source_name=revision['source_name'],
                                    retained_graph=deepcopy(bundle['retained_graph']), retained_reader=binding)
                    continue
                if proxy is None:
                    if revision.get('result_file') and revision.get('result_files'):
                        try:
                            for item in revision['result_files']:
                                path = Path(item['path'])
                                if not path.is_file() or path.stat().st_size != item['bytes'] or external.sha(path) != item['sha256']:
                                    raise ValueError('Retained analysis file changed')
                            before = p.GetActiveSource()
                            cached = None
                            try:
                                cached = p.OpenDataFile(revision['result_file'])
                                name = 'CAE retained | ' + revision['id']
                                p.RenameSource(name, cached)
                                cached.UpdatePipeline()
                            except Exception:
                                if cached is not None: p.Delete(cached)
                                raise
                            finally:
                                p.SetActiveSource(before)
                            bundle = {'source': cached, 'proxies': [cached],
                                'summary': deepcopy(revision.get('summary', {})), 'retained_only': True}
                            bundle['retained_graph'] = analysis.graph_signature(bundle)
                            # This newly opened fallback consumes the new export,
                            # not the older retained reader saved in native PVSM.
                            reopened = dict(revision)
                            reopened.pop('retained_reader', None)
                            binding = self._verify_record(obj, reopened, bundle)
                            self.bundles[revision['id']] = bundle
                            revision.update(retained_source_name=name, retained_graph=deepcopy(bundle['retained_graph']),
                                            retained_reader=binding)
                            self.restore_issues.append({'object_ref': obj['id'], 'revision': revision['id'],
                                'message': 'Retained values available; repair source and explicitly validate/apply to edit this pipeline.'})
                            continue
                        except (OSError, ValueError, RuntimeError) as error:
                            if cached is not None and revision['id'] not in self.bundles:
                                p.Delete(cached)
                            self.restore_issues.append({'object_ref': obj['id'], 'message': str(error)})
                    self.restore_issues.append({'object_ref': obj['id'], 'message': 'Saved native pipeline is missing; repair sources before use'})
                    continue
                proxies = [p.FindSource(name) for name in revision['proxy_names']]
                if any(item is None for item in proxies):
                    self.restore_issues.append({'object_ref': obj['id'], 'message': 'Saved native filter dependency is missing'})
                    continue
                self.bundles[revision['id']] = {'source': proxy, 'proxies': proxies,
                    'summary': deepcopy(revision.get('summary', {}))}

    def describe(self):
        sources = []
        for ref, record in self.document.get('sources', {}).items():
            native = p.FindSource(record['reader_name'])
            sources.append({'source_ref': ref, 'input_id': record.get('input_id'),
                'entry_name': Path(record['entry_path']).name,
                'files': [{'relative': Path(pin['path']).relative_to(Path(record['entry_path']).parent).as_posix(),
                    'bytes': pin['bytes'], 'sha256': pin['sha256']} for pin in record['source_pins']],
                'label': record.get('label') or record['reader_name'], 'source_revision': record['source_revision'],
                'reader_name': record['reader_name'], 'metadata': deepcopy(record.get('metadata', {})),
                'native_metadata': deepcopy(record.get('native_metadata')), 'available': native is not None})
        objects = deepcopy(list(self.state['objects'].values()))
        for obj in objects:
            record = self.applied(obj)
            if record:
                bundle = self.bundles.get(record['id'], {})
                obj['retained_values_only'] = bool(bundle.get('retained_only'))
                obj['output_metadata'] = physical.retained_declarations(record.get('summary', {}).get('declarations'))
                try:
                    from apps.desktop_post.portable_project import compare_history_inputs
                    checked = compare_history_inputs(self, obj, record, mode='current')
                    obj['current_inputs_differ'] = checked['state'] != 'SAME'
                    obj['input_comparison_status'] = checked['state']
                    obj['input_comparison_issues'] = checked['issues']
                except (ValueError, RuntimeError, OSError):
                    obj['current_inputs_differ'] = True
        return {'sources': sources, 'objects': objects,
                'active_object': self.state.get('active_object'), 'contact_selection': deepcopy(self.state.get('contact_selection')),
                'restore_issues': deepcopy(self.restore_issues),
                'repair': deepcopy(self.document.get('repair', [])), 'scope': 'Selected analysis object only; native source/view properties are separate'}

    def resolve(self, ref, revision_id=None):
        if ref in self.document.get('sources', {}):
            record = self.document['sources'][ref]
            proxy = p.FindSource(record['reader_name'])
        else:
            obj = self.object(ref)
            revision = (next((row for row in obj['history'] if row['id'] == revision_id), None)
                        if revision_id is not None else self.applied(obj))
            if revision is None:
                raise ValueError('NOT_APPLIED: apply the selected upstream analysis first')
            bundle = self.bundles.get(revision['id'])
            proxy = bundle['source'] if bundle is not None else p.FindSource(revision['source_name'])
        if proxy is None:
            raise ValueError('SOURCE_UNAVAILABLE: repair or reopen the exact original source')
        return proxy

    def object(self, ref):
        if not isinstance(ref, str) or ref not in self.state['objects']:
            raise ValueError('STALE_TARGET: choose an exact analysis object')
        return self.state['objects'][ref]

    @staticmethod
    def applied(obj):
        position = obj.get('position', -1)
        return obj['history'][position] if 0 <= position < len(obj.get('history', [])) else None

    def _touch(self):
        self.owner.generation += 1

    def pending(self, refs, revisions=None):
        """Do not apply or reset unchecked edits on any target dependency."""
        visited = set()
        def visit(proxy):
            name = label(proxy)
            if name in visited:
                return
            visited.add(name)
            _, unchecked = self.owner.native_properties(proxy)
            if unchecked:
                raise ValueError('BUSY_EDIT: ' + name + ' has unapplied native properties: ' + ', '.join(unchecked))
            for propname in proxy.ListProperties():
                prop = proxy.GetProperty(propname)
                if hasattr(prop, 'GetData'):
                    value = prop.GetData()
                    for item in value if isinstance(value, (list, tuple)) else [value]:
                        if hasattr(item, 'SMProxy') and any(external._same_proxy(item, source) for source in p.GetSources().values()):
                            visit(item)
        for ref in refs:
            visit(self.resolve(ref, (revisions or {}).get(ref)))

    def source_stamps(self, refs, revisions=None):
        stamps = {}
        for ref in sorted(set(refs)):
            source = self.resolve(ref, (revisions or {}).get(ref))
            props, pending = self.owner.native_properties(source)
            if pending:
                raise ValueError('BUSY_EDIT: the selected native input has unapplied edits')
            runtime_names = {self.owner.proxy_id(proxy): name for (name, _), proxy in p.GetSources().items()}
            def stable(value):
                if isinstance(value, dict):
                    if set(value) == {'proxy_id'}:
                        return {'native_name': runtime_names.get(value['proxy_id'], 'UNRESOLVED')}
                    return {key: stable(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [stable(item) for item in value]
                return value
            record = self.document.get('sources', {}).get(ref)
            # File paths are checked separately against exact pins. Relocating
            # identical bytes can repair location without changing field meaning.
            if record:
                from paraview import servermanager
                filename_property = servermanager.vtkSMCoreUtilities.GetFileNameProperty(source.SMProxy)
                props.pop(filename_property, None)
            revision = None if record else (next((row for row in self.object(ref)['history']
                if row['id'] == revisions[ref]), None) if revisions and ref in revisions else self.applied(self.object(ref)))
            # Save paths and view bookkeeping do not change the input's native
            # meaning. Only the immutable applied identity participates here.
            identity = None if revision is None else {key: revision[key] for key in ('id', 'recipe', 'graph', 'bindings')}
            stamps[ref] = {'properties': stable(props), 'revision': source_revision(record) if record else digest(identity),
                           'metadata': record.get('native_metadata_sha256') if record else None}
        return stamps

    def _graph_on_basis(self, actual, expected, obj, record):
        if getattr(self.owner, 'portable_binding', None) is None:
            return actual
        from apps.desktop_post.portable_project import _history_basis, verified_history_slots, _is_new_history
        if _is_new_history(self, obj, record):
            return actual
        from caelab.native_post_dependencies import graph_on_source_basis
        basis = _history_basis(self, obj, record)
        proof = verified_history_slots(self, obj, record, mode='retained')
        return graph_on_source_basis(actual, expected_graph=expected,
            history_basis=basis, verified_slots=proof)

    def _verify_inputs(self, refs, checking=None, revisions=None):
        """Verify only the selected originals and every applied upstream graph."""
        checking = set() if checking is None else checking
        originals = {}
        for ref in set(refs):
            if ref in self.document.get('sources', {}):
                originals[ref] = self.document['sources'][ref]
                continue
            upstream = self.object(ref)
            revision = (next((row for row in upstream['history'] if row['id'] == revisions[ref]), None)
                        if revisions and ref in revisions else self.applied(upstream))
            if revision is None or revision['id'] not in self.bundles:
                raise ValueError('NO_RESULT: the selected upstream analysis has no retained applied result')
            self._verify_record(upstream, revision, self.bundles[revision['id']], checking=checking)
        selected = {'sources': originals}
        external.verify_sources(self.owner.project_path, selected)
        external.verify_readers(selected)

    def _key(self, obj):
        draft = obj['draft']
        refs = ([draft['a']['source_ref'], draft['b']['source_ref']] if obj['kind'] == 'comparison'
                else [draft['source_ref']])
        self.pending(refs)
        self._verify_inputs(refs)
        return digest({'draft': draft, 'sources': self.source_stamps(refs),
                       'scene_time': float(p.GetAnimationScene().AnimationTime)})

    def _discard_preview(self, obj):
        preview = obj.get('preview')
        if preview and all(row['id'] != preview['id'] for row in obj['history']):
            bundle = self.bundles.pop(preview['id'], None)
            if bundle is not None:
                analysis.cleanup(bundle)
        obj['preview'] = None

    @staticmethod
    def _refs(kind, draft):
        return [draft['a']['source_ref'], draft['b']['source_ref']] if kind == 'comparison' else [draft['source_ref']]

    def _verify_record(self, obj, record, bundle, *, checking=None):
        checking = set() if checking is None else checking
        if record['id'] in checking:
            raise ValueError('DEPENDENCY_CYCLE: analysis inputs must form an acyclic applied graph')
        checking.add(record['id'])
        try:
            if bundle.get('retained_only'):
                if self._graph_on_basis(analysis.graph_signature(bundle), bundle['retained_graph'], obj, record) != bundle['retained_graph']:
                    raise ValueError('RETAINED_READER_CHANGED: reopen the unchanged saved analysis values')
                binding = self._retained_reader_binding(record, bundle['source'])
                self._verify_result_pins(record.get('result_files', []))
                if obj['kind'] == 'comparison':
                    actual = analysis.output_fingerprint(bundle)
                    if any(actual[key] != record['summary'][key] for key in actual):
                        raise ValueError('RESULT_CHANGED: retained values/mask differ')
                return binding
            refs = self._refs(obj['kind'], record['recipe'])
            revisions = self._retained_dependencies(record, refs)
            self.pending(refs, revisions)
            self._verify_inputs(refs, checking, revisions)
            from apps.desktop_post.portable_project import compare_history_inputs
            compared = compare_history_inputs(self, obj, record, mode='retained')
            if compared['state'] != 'SAME':
                prefix = 'SOURCE_UNAVAILABLE' if compared['state'] == 'UNAVAILABLE' else 'INPUT_CHANGED'
                raise ValueError(prefix + ': this result belongs to an earlier native input: ' + '; '.join(compared['issues']))
            if self._graph_on_basis(analysis.graph_signature(bundle), record['graph'], obj, record) != record['graph']:
                raise ValueError('PIPELINE_CHANGED: native properties differ from the retained recipe')
            if obj['kind'] == 'comparison':
                actual = analysis.output_fingerprint(bundle)
                if any(actual[key] != record['summary'][key] for key in actual):
                    raise ValueError('RESULT_CHANGED: native values/mask differ from the retained comparison')
        finally:
            checking.remove(record['id'])

    @staticmethod
    def _verify_result_pins(files):
        for item in files:
            path = Path(item['path'])
            if not path.is_file() or path.stat().st_size != item['bytes'] or external.sha(path) != item['sha256']:
                raise ValueError('RETAINED_DATA_CHANGED: saved analysis bytes differ: ' + str(path))

    def _retained_reader_binding(self, record, reader):
        """Bind hashes to this reader's exact entries and native XML dependencies.

        New exports do not retarget an existing native reader. Legacy projects
        may have overwritten result_files; their native PVSM reader pins remain
        usable only for the exact saved registration/type/input path list.
        """
        name, kind = label(reader), reader.GetXMLName()
        entries = external.reader_input_files(reader)
        if not entries:
            raise ValueError('RETAINED_READER_CHANGED: retained output must have exact native reader files')
        actual_paths = [str(path) for path in entries]
        binding = record.get('retained_reader')
        baseline = {}
        def add(item):
            path = str(Path(item['path']).resolve(strict=True))
            previous = baseline.get(path)
            if previous and (previous['sha256'], previous['bytes']) != (item['sha256'], item['bytes']):
                raise ValueError('RETAINED_DATA_CHANGED: conflicting saved pins for ' + path)
            baseline[path] = {**item, 'path': path}
        if binding is not None:
            expected = [str(Path(path).resolve(strict=True)) for path in binding['input_paths']]
            if (binding['reader_name'] != name or binding['reader_type'] != kind or expected != actual_paths):
                raise ValueError('RETAINED_READER_CHANGED: native FileName paths differ from their retained pins')
            for item in binding['files']: add(item)
        else:
            for item in record.get('result_files', []): add(item)
            saved = [row for row in self.document.get('native_readers', []) if row['reader_name'] == name]
            if (len(saved) == 1 and saved[0]['reader_type'] == kind
                    and [str(Path(path).resolve()) for path in saved[0]['input_paths']] == actual_paths):
                for path, sha256 in self.document.get('native_reader_files', {}).items():
                    file = Path(path)
                    if file.is_file():
                        add({'path': path, 'bytes': file.stat().st_size, 'sha256': sha256})
        from caelab.native_post_dependencies import inspect_dataset
        selected = {}
        for entry in entries:
            try:
                checked = inspect_dataset(entry, baseline_pins=list(baseline.values()),
                    approved_roots=[entry.parent], limits={})
            except ValueError as error:
                raise ValueError('RETAINED_DATA_CHANGED: ' + str(error)) from error
            if not checked['complete']:
                raise ValueError('RETAINED_READER_CHANGED: actual dependency has no exact saved pin')
            for pin in checked['files']:
                selected[pin['path']] = pin
        if binding is not None and set(selected) != set(baseline):
            raise ValueError('RETAINED_READER_CHANGED: native dependency list differs from its exact saved pins')
        return {'reader_name': name, 'reader_type': kind, 'input_paths': actual_paths, 'files': list(selected.values())}

    def _retained_dependencies(self, record, refs):
        """Resolve this result's input revisions, never the current editor cursor."""
        revisions = {}
        for ref in refs:
            if ref in self.document.get('sources', {}):
                continue
            expected = record['bindings'][ref]['revision']
            matches = [row for row in self.object(ref)['history'] if digest({key: row[key]
                       for key in ('id', 'recipe', 'graph', 'bindings')}) == expected]
            pinned = record.get('dependencies', {}).get(ref)
            if len(matches) != 1 or pinned is not None and matches[0]['id'] != pinned:
                raise ValueError('INPUT_CHANGED: the retained dependency revision is missing or ambiguous')
            revisions[ref] = matches[0]['id']
        return revisions

    def dispatch(self, operation, arguments):
        if operation not in OPERATIONS:
            raise ValueError('Unsupported Post workspace command')
        if not isinstance(arguments, dict):
            raise ValueError('Arguments must be an object')
        if operation.startswith('post.curve_origin_'):
            try:
                from . import curve_origin_native
            except ImportError:
                import curve_origin_native
            handler = {'post.curve_origin_read': curve_origin_native.read,
                       'post.curve_origin_verify': curve_origin_native.verify,
                       'post.curve_origin_select': curve_origin_native.select}[operation]
            if operation != 'post.curve_origin_read':
                if 'origin_target' not in arguments or 'target' in arguments:
                    raise ValueError('The original row requires an explicit origin_target argument')
                arguments = dict(arguments)
                arguments['target'] = arguments.pop('origin_target')
            return handler(self, **arguments)
        handlers = {
            'post.source_add': self.add_source, 'post.source_select': self.select_source,
            'post.source_repair': self.repair_source, 'post.comparison_edit': self.edit_comparison,
            'post.curve_catalog': self.curve_catalog,
            'post.mapping_validate': self.validate, 'post.sample': self.sample,
            'post.filter_edit': self.edit_filter, 'post.measurement_edit': self.edit_measurement,
            'post.measurement_snapshot': self.measurement_snapshot,
            'post.measurement_open': self.measurement_open,
            'post.contact_inspect': lambda **args: contact_views.inspect(self, **args),
            'post.contact_measurement': lambda **args: contact_views.create_measurement(self, **args),
            'post.measurement_capture': self.capture_selection, 'post.apply': self.apply,
            'post.show_analysis': self.show_analysis,
            'post.reset': self.reset, 'post.undo': self.undo, 'post.redo': self.redo,
            'post.export': self.export,
            'post.report_image_verify': self.report_image_verify,
        }
        return handlers[operation](**arguments)

    def report_image_verify(self, *, origin, expected_view_generation):
        try:
            from .report_image_origin_native import verify_live
        except ImportError:
            from report_image_origin_native import verify_live
        return verify_live(self, origin=origin, expected_view_generation=expected_view_generation)

    def curve_catalog(self):
        from .curve_native import catalog
        return catalog(self)

    def add_source(self, *, input_id, receipt, label_text=None):
        if receipt.get('id') != input_id:
            raise ValueError('Registered reader receipt differs from the requested input')
        if label_text is not None and (not isinstance(label_text, str) or len(label_text) > 256):
            raise ValueError('Use a short source display name')
        source, record = external.admit_result(receipt['path'], input_id, receipt['source_pins'], receipt.get('native_metadata'), receipt.get('registration_origin'), display_name=label_text)
        ref = 'S' + uuid.uuid4().hex
        record.update(source_ref=ref, label=label_text or Path(receipt['path']).name)
        self.document['sources'][ref] = record
        self._touch()
        return {'source_ref': ref, 'record': deepcopy(record), 'active_source_preserved': True}

    def select_source(self, *, source_ref, view_id=None, show=True, compare_with=None):
        source = self.resolve(source_ref)
        if (self.document['sources'].get(source_ref, {}).get('native_metadata') or {}).get('curve'):
            if compare_with is not None:
                raise ValueError('곡선 비교에서 두 원곡선을 선택하세요.')
            view = next((v for v in p.GetViews() if self.owner.proxy_id(v) == view_id), None) if view_id else None
            if view_id and (view is None or view.GetXMLName() != 'XYChartView'):
                raise ValueError('시험 곡선에는 차트 뷰를 선택하세요.')
            if show:
                if view is None:
                    layout = p.CreateLayout(name='시험 곡선')
                    view = p.CreateView('XYChartView')
                    p.AssignViewToLayout(view=view, layout=layout, hint=0)
                display = p.Show(source, view)
                display.AttributeType = 'Row Data'; display.UseIndexForXAxis = 0
                display.XArrayName = 'axis'; display.SeriesVisibility = ['value']
                display.SeriesLineStyle = ['value', '0']
                display.SeriesMarkerStyle = ['value', '4']
                p.Render(view)
            p.SetActiveSource(source)
            return {'source_ref': source_ref, 'native_name': label(source)}
        if compare_with is not None:
            other = self.resolve(compare_with)
            previous = p.GetActiveSource(), p.GetActiveView()
            layout, views = None, []
            try:
                layout = p.CreateLayout(name='원본 결과 비교')
                first = p.CreateView('RenderView'); views.append(first)
                p.AssignViewToLayout(view=first, layout=layout, hint=0)
                layout.SplitHorizontal(0, 0.5)
                second = p.CreateView('RenderView'); views.append(second)
                p.AssignViewToLayout(view=second, layout=layout, hint=2)
                for native, view in zip((source, other), views):
                    p.Show(native, view); p.ResetCamera(view); p.Render(view)
                self._touch()
                return {'source_ref': source_ref, 'compare_with': compare_with, 'mode': 'original_side_by_side'}
            except BaseException:
                for view in reversed(views): p.Delete(view)
                if layout is not None: p.RemoveLayout(layout)
                raise
            finally:
                p.SetActiveSource(previous[0]); p.SetActiveView(previous[1])
        view = next((v for v in p.GetViews() if self.owner.proxy_id(v) == view_id), None) if view_id else p.GetActiveView()
        if show and (view is None or view.GetXMLName() != 'RenderView'):
            raise ValueError('Select a native Render View before displaying this source')
        p.SetActiveSource(source)
        if show:
            p.Show(source, view)
            p.Render(view)
        return {'source_ref': source_ref, 'native_name': label(source)}

    def _edit(self, kind, draft, object_ref=None, title=None):
        draft = clone(draft)
        if len(json.dumps(draft).encode()) > 128 * 1024:
            raise ValueError('Analysis draft exceeds 128 KiB')
        if object_ref is None:
            object_ref = 'A' + uuid.uuid4().hex
            obj = {'id': object_ref, 'kind': kind, 'title': title or naming.operation_name(kind, draft), 'draft': draft,
                   'history': [], 'position': -1, 'preview': None, 'selection': [], 'diagnostics': []}
            self.state['objects'][object_ref] = obj
        else:
            obj = self.object(object_ref)
            if obj['kind'] != kind:
                raise ValueError('The selected analysis belongs to a different editor')
            self._discard_preview(obj)
            obj['draft'] = draft
            if title is not None:
                obj['title'] = str(title)[:256]
            obj['preview'] = None
        self.state['active_object'] = object_ref
        obj['diagnostics'] = []
        self._touch()
        return deepcopy(obj)

    def edit_comparison(self, *, draft, object_ref=None, title=None):
        return self._edit('comparison', draft, object_ref, title)

    def edit_filter(self, *, draft, object_ref=None, title=None):
        return self._edit('filter', draft, object_ref, title)

    def edit_measurement(self, *, draft, object_ref=None, title=None):
        return self._edit('measurement', draft, object_ref, title)

    def validate(self, *, object_ref):
        obj = self.object(object_ref)
        self._discard_preview(obj)
        previous_source, previous_view = p.GetActiveSource(), p.GetActiveView()
        bundle = None
        try:
            key = self._key(obj)
            draft = obj['draft']
            name = obj['title']
            if obj['kind'] == 'comparison' and draft.get('version') == 3:
                from .curve_native import build
                bundle = build(self, draft, name)
            elif obj['kind'] == 'comparison':
                for side in ('a', 'b'):
                    self._declared_side(draft[side])
                if draft.get('version') != 2 and any(draft[side].get('observable') is not None for side in ('a', 'b')):
                    raise ValueError('저장 성분의 재비교는 물리량 비교 편집기에서 작성하세요.')
                bundle = analysis.build_comparison(self.resolve(draft['a']['source_ref']), self.resolve(draft['b']['source_ref']), draft, name)
            elif obj['kind'] == 'filter':
                bundle = analysis.create_filter(self.resolve(draft['source_ref']), draft['filter'], draft.get('settings', {}), name)
            elif draft.get('measurement') == 'contact_force':
                bundle = contact_views.build_measurement(self, draft, name)
            else:
                self._declared_measurement(draft)
                declaration = self._output_declaration(draft['source_ref'])
                source = self.resolve(draft['source_ref'])
                selected = next((row for row in (declaration or {}).get('arrays', [])
                    if (row['name'], row['association']) == (draft.get('array'), draft.get('association'))), None)
                prefix = []
                try:
                    if declaration and 'frozen_clock' in declaration:
                        from .comparison_native import _filter
                        source = _filter(source, 'frozen', {}, name, prefix)
                    if selected and selected.get('validity_masks') and draft.get('measurement') not in ('surface_average','surface_time','gauge_time'):
                        from .comparison_native import _filter
                        source = _filter(source, 'quality_only', {'array': draft['array'],
                            'masks': selected['validity_masks'], 'validity_policy': selected.get('validity_policy')}, name, prefix)
                    measurement_draft = deepcopy(draft)
                    if selected and draft.get('measurement') in ('surface_average','surface_time','gauge_time'):
                        measurement_draft['validity_masks'] = deepcopy(selected.get('validity_masks', []))
                        measurement_draft['validity_policy'] = selected.get('validity_policy')
                    bundle = measurements.build_measurement(source, measurement_draft, name)
                    bundle['proxies'] = prefix + bundle['proxies']
                except BaseException:
                    analysis.cleanup({'proxies': prefix})
                    raise
                if draft['source_ref'] not in self.document['sources']:
                    bundle['summary']['sample_semantics'] = 'derived_values_at_saved_measurement_locations'
                    bundle['summary']['input_declaration'] = deepcopy(declaration)
                if selected:
                    bundle['summary']['selected_declaration'] = deepcopy(selected)
                if selected and draft.get('measurement') in ('point', 'path'):
                    result_declaration = deepcopy(declaration)
                    result_array = deepcopy(selected)
                    if selected.get('observable') in (None, physical.UNKNOWN_OBSERVABLE) and draft.get('observable') is not None:
                        result_array['observable'] = deepcopy(draft['observable'])
                    if draft['measurement'] == 'path':
                        # Quality was applied to the physical values BEFORE path
                        # interpolation; removed mask arrays are not claimed as outputs.
                        result_array['validity_masks'] = ['vtkValidPointMask']
                        if result_array.get('validity_policy') == 'declared_array':
                            result_array['spatial_mask'] = 'vtkValidPointMask'
                    result_declaration['arrays'] = [result_array]
                    result_declaration['frozen_clock'] = deepcopy(declaration.get('frozen_clock')) if 'frozen_clock' in declaration else (
                        {'value': draft['time'], 'unit': draft.get('time_units'), 'semantics': draft.get('time_origin')}
                        if draft.get('time') is not None else None)
                    result_declaration['time'] = None
                    bundle['summary']['declarations'] = result_declaration
            identifier = 'V' + uuid.uuid4().hex
            self.bundles[identifier] = bundle
            summary = clone(bundle.get('summary', {}))
            preview = {'id': identifier, 'key': key, 'recipe': deepcopy(draft),
                       'source_name': label(bundle['source']), 'proxy_names': [label(proxy) for proxy in bundle['proxies']],
                       'summary': summary, 'graph': analysis.graph_signature(bundle),
                       'bindings': self.source_stamps(self._refs(obj['kind'], draft))}
            preview['dependencies'] = {ref: self.applied(self.object(ref))['id']
                for ref in self._refs(obj['kind'], draft) if ref not in self.document['sources']}
            from caelab.native_post_dependencies import history_key
            self._new_history_keys.add(tuple(history_key(obj['id'], preview).values()))
            obj['preview'] = preview
            obj['diagnostics'] = []
            self.last_preview[object_ref] = identifier
            self._touch()
            return deepcopy(preview)
        except Exception as error:
            if bundle is not None:
                analysis.cleanup(bundle)
            obj['preview'] = None
            obj['diagnostics'] = [{'path': 'draft', 'message': str(error), 'blocks_apply': True}]
            self._touch()
            raise
        finally:
            p.SetActiveSource(previous_source)
            p.SetActiveView(previous_view)

    def _output_declaration(self, ref):
        if ref in self.document['sources']:
            return deepcopy(self.document['sources'][ref].get('native_metadata'))
        obj = self.object(ref)
        record, bundle = self._bundle(obj)  # Exact applied graph/result, not arbitrary lineage.
        summary = record.get('summary', {})
        if summary.get('declarations'):
            return physical.retained_declarations(summary['declarations'])
        recipe = record['recipe']
        if obj['kind'] != 'measurement' or recipe.get('measurement') not in ('point', 'path'):
            return None  # Verified legacy/arbitrary filter: meanings remain user-declared, never inherited by guess.
        row = {key: recipe.get(key) for key in ('quantity', 'units', 'measure', 'frame')}
        row.update(name=recipe.get('array'), association='POINTS',
                   observable=deepcopy(recipe.get('observable', physical.UNKNOWN_OBSERVABLE)))
        return {'arrays': [row], **{key: recipe.get(key) for key in ('coordinate_units', 'coordinate_frame')},
                'time': {'unit': recipe.get('time_units'), 'semantics': recipe.get('time_origin')}
                    if recipe.get('time') is not None else None,
                'frozen_clock': {'value': recipe['time'], 'unit': recipe.get('time_units'), 'semantics': recipe.get('time_origin')}
                    if recipe.get('time') is not None else None, 'derived_revision': record['id']}

    def _declared_side(self, side):
        metadata = self._output_declaration(side.get('source_ref'))
        if metadata and 'frozen_clock' in metadata:
            if 'frozen_clock' not in side or side['frozen_clock'] != metadata['frozen_clock']:
                raise ValueError('저장된 측정의 실제 고정 시각을 그대로 선택하세요.')
        elif 'frozen_clock' in side:
            raise ValueError('원 reader를 저장된 고정 측정으로 재표기할 수 없습니다.')
        if metadata is None:
            if side.get('validity_policy') is not None:
                raise ValueError('배열별 유효성 정책은 확인된 저장 선언에서만 사용할 수 있습니다.')
            return  # User must supply every meaning in the recipe; no guessed defaults.
        row = next((row for row in metadata['arrays'] if (row['association'], row['name']) == (side.get('association'), side.get('array'))), None)
        if row is None:
            raise ValueError('Chosen array has no matching declaration in its source receipt')
        if side.get('validity_policy') is not None and side['validity_policy'] != row.get('validity_policy'):
            raise ValueError('Comparison validity policy conflicts with the retained source declaration')
        for name in ('units', 'frame', 'measure', 'quantity'):
            if row.get(name) is not None and row[name] != side.get(name):
                raise ValueError('Comparison ' + name + ' conflicts with the retained source declaration')
        for name in ('coordinate_units', 'coordinate_frame'):
            if metadata.get(name) is not None and metadata[name] != side.get(name):
                raise ValueError('Comparison ' + name + ' conflicts with the retained source declaration')
        for key in ('layout', 'temperature_kind', 'validity_masks', 'validity_policy', 'spatial_mask'):
            if key in row and row[key] is not None and row[key] != side.get(key):
                raise ValueError('Comparison ' + key + ' conflicts with the retained source declaration')
        if row.get('observable') == physical.UNKNOWN_OBSERVABLE:
            physical.validate_observable(side.get('observable'))
        elif row.get('observable') is not None and row['observable'] != side.get('observable'):
            raise ValueError('Comparison observable conflicts with the retained source declaration')
        if 'frozen_clock' in metadata:
            sampling = side.get('sampling', {'mode': 'exact', 'time': side.get('time')})
            if sampling != {'mode': 'exact', 'time': None}:
                raise ValueError('저장 측정의 고정 시각은 native 시간 탐색으로 바꿀 수 없습니다.')
        clock = metadata.get('time')
        if clock and clock['unit'] != side.get('time_units'):
            raise ValueError('Comparison clock unit conflicts with the source declaration')
        if clock and clock['semantics'] != side.get('time_origin'):
            raise ValueError('Comparison clock semantics/origin conflicts with the source declaration')

    def _declared_measurement(self, draft):
        fields = ('quantity', 'units', 'measure', 'frame', 'coordinate_units', 'coordinate_frame')
        for name in fields:
            if draft.get(name) is not None and not isinstance(draft[name], str):
                raise ValueError('Measurement ' + name + ' must be explicit text or unknown')
        metadata = self._output_declaration(draft.get('source_ref'))
        if metadata is None:
            if draft.get('validity_policy') is not None:
                raise ValueError('배열별 유효성 정책은 확인된 저장 선언에서만 사용할 수 있습니다.')
            return
        if 'frozen_clock' in metadata:
            if draft.get('measurement') in ('time','surface_time','gauge_time') or draft.get('time') is not None:
                raise ValueError('저장된 고정 결과에서는 점 또는 경로를 선택하세요. 원 표본 시각을 다시 지정하거나 시간 이력으로 늘리지 않습니다.')
            clock = metadata['frozen_clock']
            if clock:
                for field, key in (('time_units', 'unit'), ('time_origin', 'semantics')):
                    if draft.get(field) is not None and draft[field] != clock[key]:
                        raise ValueError('저장된 고정 결과의 시각 의미와 측정 선언이 다릅니다.')
        declaration = next((row for row in metadata['arrays']
            if (row['association'], row['name']) == (draft.get('association'), draft.get('array'))), None)
        if declaration is None:
            raise ValueError('The selected source has no matching retained measurement declaration')
        if draft.get('validity_policy') is not None and draft['validity_policy'] != declaration.get('validity_policy'):
            raise ValueError('Measurement validity policy conflicts with the retained source declaration')
        for name in (*fields, 'layout', 'temperature_kind', 'validity_masks', 'validity_policy', 'spatial_mask'):
            original = metadata.get(name) if name.startswith('coordinate_') else declaration.get(name)
            if draft.get(name) and original is not None and draft[name] != original:
                raise ValueError('Measurement ' + name + ' conflicts with the retained source declaration')
        if draft.get('observable') is not None:
            original = declaration.get('observable')
            if original == physical.UNKNOWN_OBSERVABLE:
                if draft['observable'] != physical.UNKNOWN_OBSERVABLE:
                    physical.validate_observable(draft['observable'])
            elif original is not None and original != draft['observable']:
                raise ValueError('Measurement observable conflicts with the retained source declaration')
        clock = metadata.get('time')
        if clock and clock['unit'] != draft.get('time_units'):
            raise ValueError('Measurement clock unit conflicts with the retained source declaration')
        if clock and clock['semantics'] != draft.get('time_origin'):
            raise ValueError('Measurement clock semantics/origin conflicts with the retained source declaration')

    def _bundle(self, obj, *, preview=False):
        record = obj.get('preview') if preview else self.applied(obj)
        if record is None or record['id'] not in self.bundles:
            raise ValueError('NO_RESULT: validate a draft or select a retained applied result')
        bundle = self.bundles[record['id']]
        self._verify_record(obj, record, bundle)
        return record, bundle

    def measurement_snapshot(self, *, object_ref):
        """Export all rows of one applied SAVED measurement, without changing it."""
        from caelab.post_observation import MAX_BYTES, MAX_ROWS, file_pin, saved_record, verify_origin
        import os
        self.owner.assert_thread()
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj)
        if obj['kind'] != 'measurement' or record['recipe'] != obj.get('draft'):
            raise ValueError('Apply and save the selected measurement before using it in Numerical')
        path = self.owner.project_path.resolve(strict=True)
        project_pin = file_pin(path)
        if project_pin['bytes'] > MAX_BYTES:
            raise ValueError('Saved Post manifest exceeds the bounded handoff size')
        project = json.loads(path.read_text(encoding='utf-8-sig'))
        _, saved = saved_record(project, object_ref, record['id'])
        if saved['recipe'] != record['recipe']:
            raise ValueError('Save this exact applied measurement before handing it off')
        origin = {'kind': 'post_measurement', 'document_id': self.owner.document_id,
            'session_id': self.owner.session_id, 'pid': os.getpid(),
            'project': project_pin,
            'workspace': file_pin(path.parent / project['workspace_file']),
            'object_ref': object_ref, 'revision': record['id'],
            'recipe_sha256': digest(saved['recipe']),
            'result_files_sha256': digest(saved['result_files']),
            'result_sha256': saved['result_sha256']}
        verify_origin(origin)
        rows, total = [], None
        while total is None or len(rows) < total:
            page = contact_views.annotate(measurements.sample_data(bundle['source'], offset=len(rows), limit=1000, declarations=saved['summary'].get('declarations')), saved['summary'])
            count = page.get('total', page.get('count'))
            if type(count) is not int or not 1 <= count <= MAX_ROWS:
                raise ValueError('Use a measurement with 1–20000 saved rows; no partial curve is handed off')
            if total is not None and count != total:
                raise ValueError('Native measurement size changed while reading')
            total = count
            chunk = page.get('rows', [])
            if not chunk or len(rows) + len(chunk) > total:
                raise ValueError('Native measurement returned an incomplete page')
            rows.extend(chunk)
            if len(json.dumps(rows, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_BYTES:
                raise ValueError('Native measurement exceeds the bounded extraction size')
        self._verify_record(obj, record, bundle)
        verify_origin(origin)
        snapshot = {'complete': True, 'origin': origin, 'recipe': deepcopy(saved['recipe']),
                    'summary': deepcopy(saved['summary']), 'rows': rows}
        data = json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(data) > MAX_BYTES:
            raise ValueError('Native measurement exceeds the bounded extraction size')
        folder = Path(project['project_root']) / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / ('measurement-' + uuid.uuid4().hex + '.json')
        with output.open('xb') as stream:
            stream.write(data)
        # Only a small receipt travels through the existing native command broker.
        return {'origin': origin, 'snapshot': file_pin(output), 'rows': total}

    def measurement_open(self, *, origin):
        """Show the pinned measurement only in its unchanged live saved project."""
        from caelab.post_observation import verify_origin, check_pin
        _, _, saved = verify_origin(origin)
        if (origin['document_id'] != self.owner.document_id
                or self.owner.project_path.resolve() != check_pin(origin['project'])):
            raise ValueError('The live Post window is on another saved project; its edits were preserved')
        obj = self.object(origin['object_ref'])
        record, bundle = self._bundle(obj)
        if record['id'] != origin['revision'] or record['recipe'] != saved['recipe']:
            raise ValueError('The live measurement moved to another revision; its edits were preserved')
        self.show(obj, record, bundle)
        self.state['active_object'] = obj['id']
        self.restore_selection()
        self._touch()
        return {'status': 'SHOWN', 'object_ref': obj['id'], 'revision': record['id']}

    def sample(self, *, object_ref, preview=True, offset=0, limit=100, point_index=None, row_index=None, expected_revision=None):
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj, preview=preview)
        if expected_revision is not None and record['id'] != expected_revision:
            raise ValueError('STALE_SAMPLE: 선택한 표·곡선 이후 결과가 바뀌었습니다. 현재 결과를 다시 읽으세요.')
        if preview and self._key(obj) != record['key']:
            raise ValueError('STALE_PREVIEW: input, clock or mapping settings changed; validate again')
        if obj['kind'] == 'comparison' and record['recipe'].get('version') == 3:
            from .curve_native import sample
            result = sample(bundle, offset=offset, limit=limit, row_index=row_index, point_index=point_index)
        elif row_index is not None and obj['kind'] == 'measurement' and record['recipe'].get('measurement') in ('surface_average','surface_time','gauge_time'):
            if type(row_index) is not int or row_index < 0 or point_index is not None:
                raise ValueError('측정 표의 행 번호를 선택하세요. 공간 점 번호와 함께 사용할 수 없습니다.')
            result = measurements.sample_data(bundle['source'], offset=row_index, limit=1)
            if (len(result.get('rows', [])) != 1 or result['rows'][0].get('row') != row_index
                    or result['rows'][0].get('block') != []):
                raise ValueError('선택한 행이 현재 측정 표에 없습니다. 표를 다시 읽으세요.')
        elif row_index is not None:
            raise ValueError('이 분석은 시간표 행 선택을 지원하지 않습니다.')
        elif obj['kind'] == 'comparison':
            result = analysis.sample_page(bundle, offset=offset, limit=limit, point_index=point_index)
        else:
            result = measurements.sample_data(bundle['source'], offset=offset, limit=limit, point_index=point_index,
                                              declarations=record.get('summary', {}).get('declarations'))
        result = contact_views.annotate(result, record.get('summary', {}))
        if row_index is not None:
            obj.pop('selection_context', None)
            obj['selection'] = deepcopy(result.get('rows', []))
            obj['selection_revision'] = record['id']
            obj['selection_hash'] = digest(obj['selection'])
            self._touch()
        if point_index is not None:
            # An explicit point query selects this exact output only. Preview
            # selection never creates a view or displays a hidden pipeline.
            measurements.highlight_point(bundle['source'], point_index)
            obj.pop('selection_context', None)
            obj['selection'] = deepcopy(result.get('rows', []))
            obj['selection_revision'] = record['id']
            obj['selection_hash'] = digest(obj['selection'])
            self._touch()
        return {**result, 'object_ref': object_ref, 'revision': record['id'], 'preview': preview}

    def restore_selection(self):
        """Restore the active applied pick only after checking its actual row."""
        contact_views.restore(self)
        obj = self.state['objects'].get(self.state.get('active_object'))
        if obj is None:
            return False
        if obj.get('selection_context', {}).get('kind') == 'post_curve_origin':
            try:
                try:
                    from .curve_origin_native import restore
                except ImportError:
                    from curve_origin_native import restore
                return restore(self, obj)
            except (ValueError, RuntimeError, OSError) as error:
                self.restore_issues.append({'object_ref': obj['id'], 'message': str(error)})
                return False
        record = self.applied(obj)
        rows = obj.get('selection')
        if record and obj['kind'] == 'measurement' and record['recipe'].get('measurement') in ('surface_average','surface_time','gauge_time') and rows:
            if (obj.get('selection_revision') != record['id'] or not isinstance(rows, list) or len(rows) != 1
                    or not isinstance(rows[0], dict) or type(rows[0].get('row')) is not int
                    or rows[0]['row'] < 0 or rows[0].get('block') != []):
                return False
            try:
                _, bundle = self._bundle(obj)
                actual = measurements.sample_data(bundle['source'], offset=rows[0]['row'], limit=1)
                if digest(actual['rows']) != obj.get('selection_hash') or digest(rows) != obj.get('selection_hash'):
                    raise ValueError('저장된 측정 행과 현재 원표가 다릅니다.')
                return True
            except (ValueError, RuntimeError, OSError) as error:
                self.restore_issues.append({'object_ref': obj['id'], 'message': str(error)})
                return False
        if record and record['recipe'].get('version') == 3 and rows:
            if (obj.get('selection_revision') != record['id'] or len(rows) != 1
                    or type(rows[0].get('row_index')) is not int):
                return False
            try:
                from .curve_native import sample
                _, bundle = self._bundle(obj)
                actual = sample(bundle, row_index=rows[0]['row_index'])
                if digest(actual['rows']) != obj.get('selection_hash') or digest(rows) != obj.get('selection_hash'):
                    raise ValueError('Saved curve row differs from retained values')
                return True
            except (ValueError, RuntimeError, OSError) as error:
                self.restore_issues.append({'object_ref': obj['id'], 'message': str(error)})
                return False
        if (record is None or obj.get('selection_revision') != record['id']
                or not isinstance(rows, list) or len(rows) != 1
                or not isinstance(rows[0], dict) or type(rows[0].get('point_index')) is not int
                or not isinstance(obj.get('selection_hash'), str)):
            return False
        try:
            if digest(rows) != obj['selection_hash']:
                raise ValueError('Saved selected sample identity changed')
            _, bundle = self._bundle(obj)
            point_index = rows[0]['point_index']
            if obj['kind'] == 'comparison':
                actual = analysis.sample_page(bundle, point_index=point_index)
            else:
                actual = measurements.sample_data(bundle['source'], point_index=point_index,
                                                  declarations=record.get('summary', {}).get('declarations'))
            if digest(actual.get('rows', [])) != obj['selection_hash']:
                raise ValueError('Native selected sample differs from its saved row')
            measurements.highlight_point(bundle['source'], point_index)
            return True
        except (ValueError, RuntimeError, OSError) as error:
            self.restore_issues.append({'object_ref': obj['id'], 'message': 'Selection was not restored: ' + str(error)})
            return False

    def apply(self, *, object_ref, show=True, view_id=None):
        if type(show) is not bool:
            raise ValueError('Show must be an explicit boolean')
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj, preview=True)
        if self._key(obj) != record['key']:
            raise ValueError('STALE_PREVIEW: input, clock or mapping settings changed; validate again')
        old = self.applied(obj)
        if old and old['id'] == record['id']:
            return deepcopy(old)
        if any(item['id'] == record['id'] for item in obj['history']):
            raise ValueError('STALE_PREVIEW: this revision is already retained; validate the draft again before applying')
        # Truncating Undo branches would delete prior analysis. Keep every revision;
        # record the active history position explicitly instead.
        record = deepcopy(record)
        record['previous'] = None if old is None else old['id']
        if view_id is None and old is not None:
            old_view = next((view for name, view in self._views() if name == old.get('view_name')), None)
            if old_view is not None and old_view.GetXMLName() == self.view_type(obj, record):
                record['view_name'] = old['view_name']
        if show:
            self.show(obj, record, bundle, view_id=view_id)
        self._visibility(old, False)
        obj['history'].append(record)
        obj['position'] = len(obj['history']) - 1
        obj['redo_stack'] = []
        self._touch()
        return deepcopy(record)

    @staticmethod
    def view_type(obj, record):
        if obj['kind'] == 'comparison' and record['recipe'].get('version') == 3:
            return 'XYChartView'
        if (obj['kind'] == 'measurement' and record['recipe'].get('measurement') in ('time', 'path', 'contact_force', 'surface_time', 'gauge_time')
                or obj['kind'] == 'filter' and record['recipe'].get('filter') == 'PlotOverLine'):
            return 'XYChartView'
        return 'SpreadSheetView' if obj['kind'] == 'measurement' else 'RenderView'

    def show_analysis(self, *, object_ref, view_id=None, array=None):
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj)
        if array is not None:
            allowed = set(record.get('summary', {}).get('arrays', {}).values())
            if record.get('summary', {}).get('comparison_version') == 2:
                allowed.update(('A_source_value', 'B_source_sampled'))
            if obj['kind'] != 'comparison' or array not in allowed:
                raise ValueError('이 보존 비교에서 읽을 실제 배열을 선택하세요.')
        self.show(obj, record, bundle, view_id=view_id, array=array)
        self.state['active_object'] = object_ref
        self._touch()
        return deepcopy(record)

    def _result_render_view(self, obj, record, active_view):
        """Only split the current layout where this result's exact input is visible."""
        if active_view is None:
            return None
        layout = p.GetLayout(active_view)
        if layout is None or layout.SMProxy.GetMaximizedCell() != -1:
            return None
        if layout.GetViewLocation(active_view) != 0:
            return None  # Preserve an already split model instead of shrinking it again.
        refs = self._refs(obj['kind'], record['recipe'])
        revisions = self._retained_dependencies(record, refs)
        inputs = [self.resolve(ref, revisions.get(ref)) for ref in refs]
        renders = [view for _, view in self._views()
            if view.GetXMLName() == 'RenderView' and layout.GetViewLocation(view) >= 0
            and any(getattr(display, 'Visibility', 0) and getattr(display, 'Input', None) is not None
                and any(external._same_proxy(display.Input, source) for source in inputs)
                for display in getattr(view, 'Representations', []))]
        if any(external._same_proxy(active_view, view) for view in renders):
            return layout, active_view
        return (layout, renders[0]) if len(renders) == 1 else None

    def show(self, obj, record, bundle, *, view_id=None, array=None):
        source = bundle['source']
        before_source, before_view = p.GetActiveSource(), p.GetActiveView()
        before_name = record.get('view_name')
        before_names = deepcopy(record.get('view_names'))
        layout = created_view = split_layout = None
        split_slot = None
        view = None
        required_view = self.view_type(obj, record)
        if view_id is not None:
            if not isinstance(view_id, str):
                raise ValueError('Choose an exact native view ID from the current owner')
            view = next((item for name, item in self._views() if self.owner.proxy_id(item) == view_id), None)
            if view is None or view.GetXMLName() != required_view:
                raise ValueError('Choose an existing native ' + required_view + ' for this result')
            record['view_name'] = next(name for name, item in self._views() if external._same_proxy(item, view))
        elif record.get('view_name'):
            view = next((view for name, view in self._views() if name == record['view_name']), None)
            if view is not None and view.GetXMLName() != required_view:
                raise ValueError('The saved result view has a different native type')
        previous_display = next((item for item in getattr(view, 'Representations', [])
            if getattr(item, 'Input', None) is not None and external._same_proxy(item.Input, source)), None) if view else None
        previous_visibility = getattr(previous_display, 'Visibility', None)
        try:
            if view is None:
                placement = (self._result_render_view(obj, record, before_view)
                    if required_view in ('SpreadSheetView', 'XYChartView') else None)
                if placement is not None:
                    candidate_layout, render_view = placement
                    location = candidate_layout.GetViewLocation(render_view)
                    top = candidate_layout.SplitViewVertical(render_view, 0.68)
                    if top != 2 * location + 1:
                        raise RuntimeError('모델 아래에 결과 화면을 배치하지 못했습니다. 기존 화면은 유지합니다.')
                    split_layout, split_slot = candidate_layout, top + 1
                    created_view = view = p.CreateView(required_view)
                    if not split_layout.AssignView(split_slot, view):
                        raise RuntimeError('분할한 아래 화면에 결과를 표시하지 못했습니다.')
                else:
                    layout = p.CreateLayout(name='CAE analysis | ' + obj['id'])
                    created_view = view = p.CreateView(required_view)
                    p.AssignViewToLayout(view=view, layout=layout, hint=0)
                record['view_name'] = next((name for name, item in self._views() if external._same_proxy(item, view)), None)
            display = p.Show(source, view, 'SpreadSheetRepresentation') if view.GetXMLName() == 'SpreadSheetView' else p.Show(source, view)
            if view.GetXMLName() == 'XYChartView' and record['recipe'].get('version') == 3:
                display.AttributeType = 'Row Data'
                display.UseIndexForXAxis = 0
                display.XArrayName = 'aligned_x'
                display.SeriesVisibility = ['aligned_a', 'aligned_b', 'aligned_delta']
                if record['summary'].get('blocked'):
                    display.XArrayName = 'a_x'
                    display.SeriesVisibility = ['a_y']
                # Markers avoid inventing a line across missing source intervals.
                visible = ['a_y'] if record['summary'].get('blocked') else ['aligned_a', 'aligned_b', 'aligned_delta']
                display.SeriesLineStyle = [item for series in visible for item in (series, '0')]
                display.SeriesMarkerStyle = [item for series in visible for item in (series, '4')]
            elif view.GetXMLName() == 'XYChartView':
                display.UseIndexForXAxis = 0
                measurement = record['recipe'].get('measurement')
                display.XArrayName = {'time': 'Time', 'surface_time':'Time', 'gauge_time':'Time', 'contact_force': record['recipe'].get('axis_name','load_parameter')}.get(measurement, 'arc_length')
                if measurement in ('contact_force','surface_time','gauge_time'):
                    display.AttributeType = 'Row Data'
                array = (record['summary']['array'] if measurement in ('surface_average','surface_time','gauge_time') else
                         record['recipe'].get('array') or record['recipe'].get('settings', {}).get('array'))
                if array:
                    display.SeriesVisibility = [array]
                    if measurement in ('surface_average','surface_time','gauge_time'):
                        display.SeriesLineStyle = [array,'0']
                        display.SeriesMarkerStyle = [array,'4']
                    if obj['kind'] == 'measurement' and measurement in ('surface_time', 'gauge_time'):
                        title = {'surface_time': 'Surface average',
                                 'gauge_time': 'Projected relative displacement'}[measurement]
                        summary = record.get('summary', {})
                        units = [summary.get(key, record['recipe'].get(key)) for key in ('units', 'time_units')]
                        units = [value.strip() if isinstance(value, str) and value.strip()
                                 and value.strip().lower() not in ('unknown', 'undeclared', 'unspecified')
                                 else 'unit unknown' for value in units]
                        response = title + ' [' + units[0] + ']'
                        display.SeriesLabel = [array, response]
                        axis_unit = '[' + ('?' if units[0] == 'unit unknown' else units[0]) + ']'
                        # ParaView 6.2 axis-title defaults are empty; keep explicit user titles.
                        shared = any(not external._same_proxy(item, display) and getattr(item, 'Visibility', 0)
                                     and getattr(item, 'Input', None) is not None for item in view.Representations)
                        if not shared and not view.LeftAxisTitle:
                            view.LeftAxisTitle = axis_unit
                        if not shared and not view.BottomAxisTitle:
                            view.BottomAxisTitle = 'Time [' + units[1] + ']'
            if obj['kind'] == 'comparison' and view.GetXMLName() == 'RenderView':
                arrays = bundle.get('summary', {}).get('arrays', {})
                array = array or (arrays.get('delta', 'CAE_delta') if isinstance(arrays, dict) else 'CAE_delta')
                if array in source.PointData.keys():
                    p.ColorBy(display, ('POINTS', array))
                    display.RescaleTransferFunctionToDataRange(True, False)
                    display.SetScalarBarVisibility(view, True)
            if created_view is not None and view.GetXMLName() == 'RenderView':
                p.ResetCamera(view)
            p.SetActiveSource(source)
            p.SetActiveView(view)
            p.Render(view)
            # A user may explicitly show this one output in several existing
            # views (for example, overlay a path curve). Undo must hide only
            # representations opened by these commands, in every such view.
            names = record.setdefault('view_names', [])
            for name in (before_name, record.get('view_name')):
                if name is not None and name not in names:
                    names.append(name)
        except Exception:
            failures = []
            def cleanup(action):
                try:
                    action()
                except Exception as error:
                    failures.append(str(error))
            if view is not None and created_view is None:
                if previous_display is not None and previous_visibility is not None:
                    cleanup(lambda: setattr(previous_display, 'Visibility', previous_visibility))
                else:
                    cleanup(lambda: p.Hide(source, view))
            if split_layout is not None:
                def restore_split():
                    if created_view is not None:
                        split_layout.SMProxy.RemoveView(created_view.SMProxy)
                    if not split_layout.SMProxy.Collapse(split_slot):
                        raise RuntimeError('새 결과의 빈 화면을 닫지 못했습니다.')
                cleanup(restore_split)
            if created_view is not None:
                cleanup(lambda: p.Delete(created_view))
            if layout is not None:
                cleanup(lambda: p.RemoveLayout(layout))
            cleanup(lambda: p.SetActiveSource(before_source))
            cleanup(lambda: p.SetActiveView(before_view))
            if before_name is None:
                record.pop('view_name', None)
            else:
                record['view_name'] = before_name
            if before_names is None:
                record.pop('view_names', None)
            else:
                record['view_names'] = before_names
            if failures:
                obj['diagnostics'].append({'path': 'native_view', 'message': 'Failed Apply cleanup: ' + '; '.join(failures), 'blocks_apply': True})
            raise

    @staticmethod
    def _views():
        from paraview import servermanager
        return [(name, proxy) for (name, _), proxy in servermanager.ProxyManager().GetProxiesInGroup('views').items()]

    def _visibility(self, record, visible):
        if record is None or record['id'] not in self.bundles:
            return
        source = self.bundles[record['id']]['source']
        names = set(record.get('view_names', []))
        if record.get('view_name'):
            names.add(record['view_name'])
        for name, view in self._views():
            if name not in names:
                continue
            for display in list(getattr(view, 'Representations', [])):
                candidate = getattr(display, 'Input', None)
                if candidate is not None and external._same_proxy(candidate, source):
                    display.Visibility = int(visible)
        p.RenderAllViews()

    def reset(self, *, object_ref):
        obj = self.object(object_ref)
        old = self.applied(obj)
        if old:
            obj['draft'] = deepcopy(old['recipe'])
        self._discard_preview(obj)
        obj['diagnostics'] = []
        self._touch()
        return deepcopy(obj)

    def undo(self, *, object_ref):
        obj = self.object(object_ref)
        current = self.applied(obj)
        if current is None:
            raise ValueError('Nothing to undo for this analysis object')
        self._bundle(obj)  # Do not undo native user changes under an old recipe.
        previous = current.get('previous')
        position = next((i for i, item in enumerate(obj['history']) if item['id'] == previous), -1)
        if previous is not None:
            if position < 0 or previous not in self.bundles:
                raise ValueError('Saved previous revision is unavailable')
            self._verify_record(obj, obj['history'][position], self.bundles[previous])
        self._visibility(current, False)
        obj.setdefault('redo_stack', []).append(current['id'])
        obj['position'] = position
        self._visibility(self.applied(obj), True)
        self._discard_preview(obj)
        self._touch()
        return deepcopy(obj)

    def redo(self, *, object_ref):
        obj = self.object(object_ref)
        identifier = obj.get('redo_stack', [])[-1] if obj.get('redo_stack') else None
        if identifier is None:
            raise ValueError('Nothing to redo for this analysis object')
        current = self.applied(obj)
        position = next((i for i, item in enumerate(obj['history']) if item['id'] == identifier), None)
        if position is None:
            raise ValueError('Saved redo revision is unavailable')
        if identifier not in self.bundles:
            raise ValueError('Saved redo native pipeline is unavailable')
        if current is not None:
            self._bundle(obj)
        self._verify_record(obj, obj['history'][position], self.bundles[identifier])
        self._visibility(current, False)
        obj['redo_stack'].pop()
        obj['position'] = position
        self._visibility(self.applied(obj), True)
        self._discard_preview(obj)
        self._touch()
        return deepcopy(obj)

    def prepare_for_save(self):
        """Discard transient previews before the owner captures save generation."""
        # Unapplied validation pipelines are transient. Keeping them in PVSM
        # after dropping their recipe record would restore unowned native nodes.
        # An applied preview shares a retained history bundle and is preserved.
        changed = False
        for obj in self.state['objects'].values():
            if obj.get('preview') is not None:
                self._discard_preview(obj)
                changed = True
        if changed:
            self._touch()
        return changed

    def prepare_save(self, document, folder, *, _history_plan=None):
        self.prepare_for_save()
        document['analysis'] = deepcopy(self.state)
        if _history_plan is not None:
            from apps.desktop_post.portable_project import preserve_history_for_save
            preserve_history_for_save(self.owner, document, folder, _history_plan)
        for obj in document['analysis']['objects'].values():
            for record in obj['history']:
                bundle = self.bundles.get(record['id'])
                if bundle is None:
                    if _history_plan is not None and any(row['history']['object_ref'] == obj['id']
                            and row['history']['revision_id'] == record['id'] and row['state'] == 'UNAVAILABLE_DECLARED'
                            for row in _history_plan.histories):
                        continue
                    raise ValueError('PIPELINE_CHANGED: restore or validate the edited analysis before saving')
                reader_binding = self._verify_record(obj, record, bundle)
                artifact = measurements.save_native_data(bundle['source'], folder / record['id'], 'result',
                    **({'table_xml': True} if record['summary'].get('comparison_version') == 3 else {}))
                record['result_file'] = artifact['entry']
                record['result_files'] = artifact['files']
                if reader_binding is not None:
                    record['retained_reader'] = reader_binding
                    pins = {str(Path(item['path']).resolve()): item for item in record['result_files']}
                    for item in reader_binding['files']:
                        previous = pins.get(item['path'])
                        if previous and previous != item:
                            raise ValueError('RETAINED_DATA_CHANGED: native export conflicts with a reader pin')
                        pins[item['path']] = deepcopy(item)
                    record['result_files'] = list(pins.values())
                record['result_sha256'] = external.sha(artifact['entry'])
            # Drafts survive save. A preview is intentionally revalidated after
            # restart; retained applied/history data is never silently recomputed.
            obj['preview'] = None
        return document

    def export(self, *, object_ref, format='vtu', report_snapshot=False):
        if type(report_snapshot) is not bool:
            raise ValueError('보고서 캡처 선택은 참/거짓이어야 합니다.')
        if report_snapshot:
            if format != 'png':
                raise ValueError('보고서 이미지는 PNG 형식으로 캡처하세요.')
            try:
                from .report_image_native import capture
            except ImportError:
                from report_image_native import capture
            return capture(self, object_ref)
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj)
        if format not in ('vtu', 'csv', 'png'):
            raise ValueError('Choose VTU data, CSV table or PNG view export')
        folder = Path(self.document['project_root']) / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / (object_ref + '-' + uuid.uuid4().hex[:8] + '.' + format)
        if format == 'png':
            view = next((view for name, view in self._views() if name == record.get('view_name')), None)
            if view is None:
                raise ValueError('The selected analysis has no retained view to export; apply/show it first')
            p.SaveScreenshot(str(output), view)
        else:
            p.SaveData(str(output), proxy=bundle['source'])
        if not output.is_file():
            raise RuntimeError('Native export produced no file')
        return {'file': str(output), 'sha256': external.sha(output), 'revision': record['id'], 'analysis_saved': False}

    def capture_selection(self, *, source_ref, array, title=None, measurement='point', reference_time=None, offset=0, limit=200):
        if measurement not in ('point', 'gauge', 'gauge_time', 'surface_time', 'surface_average'):
            raise ValueError('Choose an original point or two-point relative-displacement capture')
        if source_ref not in self.document['sources']:
            raise ValueError('Original point selection requires an admitted original reader')
        source = self.resolve(source_ref)
        if measurement in ('gauge','gauge_time','surface_time','surface_average'):
            self.pending([source_ref]); self._verify_inputs([source_ref])
        if measurement in ('surface_time','surface_average'):
            try:
                from .measurement_histories import surface_options
            except ImportError:
                from measurement_histories import surface_options
            return surface_options(source, reference_time if reference_time is not None else external.set_time(source), offset=offset, limit=limit)
        indices = measurements.capture_point_selection(source) if measurement == 'point' else []
        draft = {'source_ref': source_ref, 'measurement': 'point',
                 'array': array, 'association': 'POINTS', 'point_indices': indices}
        metadata = self.document['sources'][source_ref].get('native_metadata') or {}
        declared = next((row for row in metadata.get('arrays', [])
                         if row['association'] == 'POINTS' and row['name'] == array), {})
        draft.update({key: deepcopy(declared[key]) for key in ('quantity', 'units', 'measure', 'frame') if key in declared})
        draft.update({key: deepcopy(metadata[key]) for key in ('coordinate_units', 'coordinate_frame') if key in metadata})
        clock = metadata.get('time')
        if clock:
            draft.update(time_units=clock['unit'], time_origin=clock['semantics'],
                         time=external.set_time(source))
        if measurement in ('gauge','gauge_time'):
            if external.times(source):
                draft['time'] = external.set_time(source)
            draft.update(measurement='gauge', **measurements.capture_gauge_points(source))
            if measurement == 'gauge_time':
                times = external.times(source)
                if not times:raise ValueError('Static data has no physical gauge time history')
                if reference_time is not None and reference_time != draft['time']:
                    raise ValueError('Select the reference frame before capturing its two original points')
                draft.update(measurement='gauge_time', reference_time=draft.pop('time'), time_range=[times[0],times[-1]])
        return self.edit_measurement(draft=draft, title=title)

    def repair_source(self, *, source_ref, input_id, receipt):
        try:
            from .source_repair import repair_source
        except ImportError:
            from source_repair import repair_source
        result = repair_source(self.owner, source_ref, input_id, receipt)
        current = self.owner.workspace
        if current is self:
            # A live reader relocation retains the exact native graph and the
            # editor's draft/Undo state; replacing the document does not replace
            # this state object behind the GUI's back.
            self.document['analysis'] = self.state
            self.restore_issues = []
        current._touch()
        return result
