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

try:
    from . import external, analysis, measurements
except ImportError:
    import external
    import analysis
    import measurements

OPERATIONS = (
    'post.source_add', 'post.source_select', 'post.source_repair',
    'post.comparison_edit', 'post.mapping_validate', 'post.sample',
    'post.filter_edit', 'post.measurement_edit', 'post.measurement_capture',
    'post.measurement_snapshot', 'post.measurement_open',
    'post.apply', 'post.show_analysis', 'post.reset', 'post.undo', 'post.redo', 'post.export',
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
                'label': record.get('label') or record['reader_name'], 'source_revision': record['source_revision'],
                'reader_name': record['reader_name'], 'metadata': deepcopy(record.get('metadata', {})),
                'native_metadata': deepcopy(record.get('native_metadata')), 'available': native is not None})
        objects = deepcopy(list(self.state['objects'].values()))
        for obj in objects:
            record = self.applied(obj)
            if record:
                bundle = self.bundles.get(record['id'], {})
                obj['retained_values_only'] = bool(bundle.get('retained_only'))
                try:
                    obj['current_inputs_differ'] = self.source_stamps(self._refs(obj['kind'], record['recipe'])) != record['bindings']
                except (ValueError, RuntimeError, OSError):
                    obj['current_inputs_differ'] = True
        return {'sources': sources, 'objects': objects,
                'active_object': self.state.get('active_object'), 'restore_issues': deepcopy(self.restore_issues),
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
                if analysis.graph_signature(bundle) != bundle['retained_graph']:
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
            if self.source_stamps(refs, revisions) != record['bindings']:
                raise ValueError('INPUT_CHANGED: this result belongs to an earlier native input; restore it or validate a new revision')
            if analysis.graph_signature(bundle) != record['graph']:
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
        selected = []
        visited = set()
        containers = {'.pvd', '.vtm', '.vtpc', '.vtpd', '.pvtu', '.pvtp', '.pvtr', '.pvti', '.pvts'}
        leaves = {'.vtu', '.vtp', '.vtr', '.vti', '.vts', '.csv'}
        def visit(file, root, depth=0):
            path = str(file)
            if path in visited: return
            if depth > 16: raise ValueError('Retained native dependency nesting exceeds 16 levels')
            if len(visited) >= 4096: raise ValueError('Retained native dependency set exceeds 4096 files')
            pin = baseline.get(path)
            if pin is None:
                raise ValueError('RETAINED_READER_CHANGED: actual reader dependency has no exact saved pin: ' + path)
            self._verify_result_pins([pin])  # Verify container before reading its references.
            visited.add(path); selected.append(deepcopy(pin))
            extension = file.suffix.lower()
            if extension in leaves: return
            if extension not in containers:
                raise ValueError('Unsupported retained native reader dependency format: ' + extension)
            if file.stat().st_size > 8 * 1024 * 1024:
                raise ValueError('Retained native container metadata exceeds 8 MiB')
            text = file.read_text(encoding='utf-8-sig')
            if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
                raise ValueError('Retained native XML declarations/entities are unsupported')
            try:
                xml = ET.fromstring(text)
            except ET.ParseError as error:
                raise ValueError('Invalid retained native container XML') from error
            if xml.tag != 'VTKFile': raise ValueError('Retained native container must be VTK XML')
            for node in xml.iter():
                reference = node.get('file')
                if reference is None: continue
                relative = Path(reference)
                if not reference or relative.is_absolute() or '..' in relative.parts or '\\' in reference or ':' in reference:
                    raise ValueError('Retained native dependencies must be contained relative files')
                child = (file.parent / relative).resolve(strict=True)
                if not child.is_relative_to(root): raise ValueError('Retained native dependency escapes its input set')
                visit(child, root, depth+1)
        for entry in entries: visit(entry, entry.parent)
        if binding is not None and visited != set(baseline):
            raise ValueError('RETAINED_READER_CHANGED: native dependency list differs from its exact saved pins')
        return {'reader_name': name, 'reader_type': kind, 'input_paths': actual_paths, 'files': selected}

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
        handlers = {
            'post.source_add': self.add_source, 'post.source_select': self.select_source,
            'post.source_repair': self.repair_source, 'post.comparison_edit': self.edit_comparison,
            'post.mapping_validate': self.validate, 'post.sample': self.sample,
            'post.filter_edit': self.edit_filter, 'post.measurement_edit': self.edit_measurement,
            'post.measurement_snapshot': self.measurement_snapshot,
            'post.measurement_open': self.measurement_open,
            'post.measurement_capture': self.capture_selection, 'post.apply': self.apply,
            'post.show_analysis': self.show_analysis,
            'post.reset': self.reset, 'post.undo': self.undo, 'post.redo': self.redo,
            'post.export': self.export,
        }
        return handlers[operation](**arguments)

    def add_source(self, *, input_id, receipt, label_text=None):
        if receipt.get('id') != input_id:
            raise ValueError('Registered reader receipt differs from the requested input')
        if label_text is not None and (not isinstance(label_text, str) or len(label_text) > 256):
            raise ValueError('Use a short source display name')
        source, record = external.admit_result(receipt['path'], input_id, receipt['source_pins'], receipt.get('native_metadata'))
        ref = 'S' + uuid.uuid4().hex
        record.update(source_ref=ref, label=label_text or Path(receipt['path']).name)
        self.document['sources'][ref] = record
        self._touch()
        return {'source_ref': ref, 'record': deepcopy(record), 'active_source_preserved': True}

    def select_source(self, *, source_ref, view_id=None, show=True):
        source = self.resolve(source_ref)
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
            obj = {'id': object_ref, 'kind': kind, 'title': title or kind.title(), 'draft': draft,
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
            name = 'CAE ' + obj['kind'] + ' | ' + object_ref + ' | ' + uuid.uuid4().hex[:8]
            if obj['kind'] == 'comparison':
                for side in ('a', 'b'):
                    self._declared_side(draft[side])
                bundle = analysis.build_comparison(self.resolve(draft['a']['source_ref']), self.resolve(draft['b']['source_ref']), draft, name)
            elif obj['kind'] == 'filter':
                bundle = analysis.create_filter(self.resolve(draft['source_ref']), draft['filter'], draft.get('settings', {}), name)
            else:
                self._declared_measurement(draft)
                bundle = measurements.build_measurement(self.resolve(draft['source_ref']), draft, name)
            identifier = 'V' + uuid.uuid4().hex
            self.bundles[identifier] = bundle
            summary = clone(bundle.get('summary', {}))
            preview = {'id': identifier, 'key': key, 'recipe': deepcopy(draft),
                       'source_name': label(bundle['source']), 'proxy_names': [label(proxy) for proxy in bundle['proxies']],
                       'summary': summary, 'graph': analysis.graph_signature(bundle),
                       'bindings': self.source_stamps(self._refs(obj['kind'], draft))}
            preview['dependencies'] = {ref: self.applied(self.object(ref))['id']
                for ref in self._refs(obj['kind'], draft) if ref not in self.document['sources']}
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

    def _declared_side(self, side):
        if side.get('source_ref') not in self.document['sources']:
            raise ValueError('Comparison currently uses explicitly registered original readers')
        metadata = self.document['sources'][side['source_ref']].get('native_metadata')
        if metadata is None:
            return  # User must supply every meaning in the recipe; no guessed defaults.
        row = next((row for row in metadata['arrays'] if (row['association'], row['name']) == (side.get('association'), side.get('array'))), None)
        if row is None:
            raise ValueError('Chosen array has no matching declaration in its source receipt')
        for name in ('units', 'frame', 'measure', 'quantity'):
            if name in row and row[name] != side.get(name):
                raise ValueError('Comparison ' + name + ' conflicts with the retained source declaration')
        for name in ('coordinate_units', 'coordinate_frame'):
            if metadata[name] != side.get(name):
                raise ValueError('Comparison ' + name + ' conflicts with the retained source declaration')
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
        record = self.document['sources'].get(draft.get('source_ref'))
        metadata = record.get('native_metadata') if record is not None else None
        if metadata is None:
            return
        declaration = next((row for row in metadata['arrays']
            if (row['association'], row['name']) == (draft.get('association'), draft.get('array'))), None)
        if declaration is None:
            raise ValueError('The selected source has no matching retained measurement declaration')
        for name in fields:
            original = metadata.get(name) if name.startswith('coordinate_') else declaration.get(name)
            if draft.get(name) and original is not None and draft[name] != original:
                raise ValueError('Measurement ' + name + ' conflicts with the retained source declaration')
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
            'result_files': deepcopy(saved['result_files']),
            'result_sha256': saved['result_sha256']}
        verify_origin(origin)
        rows, total = [], None
        while total is None or len(rows) < total:
            page = measurements.sample_data(bundle['source'], offset=len(rows), limit=1000)
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

    def sample(self, *, object_ref, preview=True, offset=0, limit=100, point_index=None):
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj, preview=preview)
        if preview and self._key(obj) != record['key']:
            raise ValueError('STALE_PREVIEW: input, clock or mapping settings changed; validate again')
        if obj['kind'] == 'comparison':
            result = analysis.sample_page(bundle, offset=offset, limit=limit, point_index=point_index)
        else:
            result = measurements.sample_data(bundle['source'], offset=offset, limit=limit, point_index=point_index)
        if point_index is not None:
            # An explicit point query selects this exact output only. Preview
            # selection never creates a view or displays a hidden pipeline.
            measurements.highlight_point(bundle['source'], point_index)
            obj['selection'] = deepcopy(result.get('rows', []))
            obj['selection_revision'] = record['id']
            obj['selection_hash'] = digest(obj['selection'])
            self._touch()
        return {**result, 'object_ref': object_ref, 'revision': record['id'], 'preview': preview}

    def restore_selection(self):
        """Restore the active applied pick only after checking its actual row."""
        obj = self.state['objects'].get(self.state.get('active_object'))
        if obj is None:
            return False
        record = self.applied(obj)
        rows = obj.get('selection')
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
                actual = measurements.sample_data(bundle['source'], point_index=point_index)
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
        if (obj['kind'] == 'measurement' and record['recipe'].get('measurement') in ('time', 'path')
                or obj['kind'] == 'filter' and record['recipe'].get('filter') == 'PlotOverLine'):
            return 'XYChartView'
        return 'SpreadSheetView' if obj['kind'] == 'measurement' else 'RenderView'

    def show_analysis(self, *, object_ref, view_id=None):
        obj = self.object(object_ref)
        record, bundle = self._bundle(obj)
        self.show(obj, record, bundle, view_id=view_id)
        self.state['active_object'] = object_ref
        self._touch()
        return deepcopy(record)

    def show(self, obj, record, bundle, *, view_id=None):
        source = bundle['source']
        before_source, before_view = p.GetActiveSource(), p.GetActiveView()
        before_name = record.get('view_name')
        before_names = deepcopy(record.get('view_names'))
        layout = created_view = None
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
                layout = p.CreateLayout(name='CAE analysis | ' + obj['id'])
                created_view = view = p.CreateView(required_view)
                p.AssignViewToLayout(view=view, layout=layout, hint=0)
                record['view_name'] = next((name for name, item in self._views() if external._same_proxy(item, view)), None)
            display = p.Show(source, view, 'SpreadSheetRepresentation') if view.GetXMLName() == 'SpreadSheetView' else p.Show(source, view)
            if view.GetXMLName() == 'XYChartView':
                display.UseIndexForXAxis = 0
                display.XArrayName = 'Time' if record['recipe'].get('measurement') == 'time' else 'arc_length'
                array = record['recipe'].get('array') or record['recipe'].get('settings', {}).get('array')
                if array:
                    display.SeriesVisibility = [array]
            if obj['kind'] == 'comparison' and view.GetXMLName() == 'RenderView':
                arrays = bundle.get('summary', {}).get('arrays', {})
                array = arrays.get('delta', 'CAE_delta') if isinstance(arrays, dict) else 'CAE_delta'
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

    def prepare_save(self, document, folder):
        self.prepare_for_save()
        document['analysis'] = deepcopy(self.state)
        for obj in document['analysis']['objects'].values():
            for record in obj['history']:
                bundle = self.bundles.get(record['id'])
                if bundle is None:
                    raise ValueError('PIPELINE_CHANGED: restore or validate the edited analysis before saving')
                reader_binding = self._verify_record(obj, record, bundle)
                artifact = measurements.save_native_data(bundle['source'], folder / record['id'], 'result')
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

    def export(self, *, object_ref, format='vtu'):
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

    def capture_selection(self, *, source_ref, array, title=None):
        if source_ref not in self.document['sources']:
            raise ValueError('Original point selection requires an admitted original reader')
        source = self.resolve(source_ref)
        indices = measurements.capture_point_selection(source)
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
