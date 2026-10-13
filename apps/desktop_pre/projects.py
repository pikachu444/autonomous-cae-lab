"""Managed editable FCStd graph saving on the native document's GUI thread."""
from copy import deepcopy
import os
import shutil
import tempfile
from pathlib import Path
import uuid

from caelab import native_cad
from caelab.storage import canonical_hash, load_json, save_json, utc_now

OPERATIONS = ('pre.project.inspect', 'pre.project.save', 'pre.project.open', 'pre.links.record')
OPENED = {}


def remember_open(doc, manifest, source):
    """Only the actual native opener can attach the verified restored context."""
    OPENED[doc.Name] = (doc, deepcopy(manifest), str(source))


def _linked(value):
    if hasattr(value, 'Document') and hasattr(value, 'Name'):
        return [value]
    if isinstance(value, (list, tuple)):
        return [obj for item in value for obj in _linked(item)]
    return []



def _native_copy_uses_short_path(path):
    return os.name == 'nt'


def save_native_copy(doc, destination):
    """Keep native SaveCopy below legacy Win32 path limits, then retain bytes.

    The actual project graph relocation still uses the live document/link
    targets in Project.save. No user filename or native document is renamed.
    A failed transfer keeps its short native copy for recovery.
    """
    destination = Path(destination)
    if not _native_copy_uses_short_path(destination):
        doc.saveCopy(str(destination))
        return
    folder = Path(tempfile.mkdtemp(prefix='cae-copy-'))
    native = folder / 'model.FCStd'
    if len(str(native)) >= 180:
        raise OSError('Native temporary path is too long: ' + str(folder))
    try:
        doc.saveCopy(str(native))
        if not native.is_file():
            raise OSError('Native saveCopy produced no file')
        staged = destination.with_name('.copy-' + uuid.uuid4().hex + '.FCStd')
        shutil.copyfile(native, staged)
        if native_cad.sha(native) != native_cad.sha(staged):
            raise OSError('Retained native copy differs from short staging')
        os.replace(staged, destination)
    except Exception as error:
        raise OSError('Native copy failed; short staging retained at ' + str(folder) + ': ' + str(error)) from error
    shutil.rmtree(folder)


class Project:
    def __init__(self, owner):
        self.owner = owner
        self.path = None
        self.last_save = None
        self.last_failure = None
        self.in_save = False
        self._dependency_events = {}
        self._dependency_documents = {}
        self._saved_graph_version = None

    def attach_opened(self):
        opened = OPENED.pop(self.owner.doc.Name, None)
        if opened and opened[0] is self.owner.doc:
            manifest, source = opened[1:]
            if manifest.get('kind') == native_cad.KIND and not manifest.get('new_design_branch'):
                self.last_save = {'revision': manifest['revision'], 'opened_source': source,
                                  'unavailable_dependencies': manifest.get('unavailable_dependencies', [])}
                self.owner.saved_generation = self.owner.generation
                self._saved_graph_version = self.graph_version()
            # Save targets a new managed copy until the human chooses Save As.
            # Opening a retained input never changes its original .caepre.

    def descriptor(self):
        return {'project_file': str(self.path) if self.path else None,
                'saved': deepcopy(self.last_save), 'save_error': self.last_failure,
                'dirty': not self.is_saved(), 'graph_version': self.graph_version(),
                'links': deepcopy(self.owner.read_metadata().get('links', [])),
                'restore_error': getattr(self.owner, 'recovery_error', None)}

    def graph_version(self):
        """The live input includes every loaded external native document.

        Object identity is deliberately session-local: replacing an open child
        with a new document is not the old saved graph. Reconnecting transport
        to these same objects preserves this token and their generations.
        """
        rows = []
        try:
            docs = self._documents()
        except (ValueError, RuntimeError, ReferenceError, AttributeError) as error:
            # A closed/broken child must make the project dirty without making
            # the status/close UI itself unusable. Save still checks the graph.
            return canonical_hash({'unavailable': str(error), 'generation': self.owner.generation,
                                   'events': self._dependency_events})
        # Keep only the current graph. A component unlinked from this assembly
        # must not keep dirtying it when that unrelated document is edited.
        self._dependency_documents = {doc.Name: id(doc) for doc in docs if doc is not self.owner.doc}
        for doc in docs:
            other = self.owner if doc is self.owner.doc else getattr(self.owner, 'find_owner', lambda _: None)(doc)
            rows.append({'name': doc.Name, 'object': id(doc),
                'generation': other.generation if other is not None else 0,
                'closed': bool(getattr(other, 'closed', False)),
                'events': self._dependency_events.get(doc.Name, 0)})
        return canonical_hash(sorted(rows, key=lambda row: row['name']))

    def is_saved(self):
        if self.owner.saved_generation != self.owner.generation or self._saved_graph_version is None:
            return False
        try:
            return self._saved_graph_version == self.graph_version()
        except (ValueError, RuntimeError, ReferenceError, AttributeError):
            return False

    def connection_state(self):
        return {'dependency_events': dict(self._dependency_events),
                'dependency_documents': dict(self._dependency_documents),
                'saved_graph_version': self._saved_graph_version}

    def restore_connection_state(self, state):
        self._dependency_events = dict(state.get('dependency_events', {}))
        self._dependency_documents = dict(state.get('dependency_documents', {}))
        self._saved_graph_version = state.get('saved_graph_version')

    def note_dependency_change(self, doc, *, removed=False):
        if doc is self.owner.doc:
            return
        known = self._dependency_documents.get(doc.Name) == id(doc)
        try:
            docs = self._documents()
            linked = any(doc is item for item in docs)
            self._dependency_documents = {item.Name: id(item) for item in docs if item is not self.owner.doc}
        except (ValueError, RuntimeError, ReferenceError, AttributeError):
            linked = known
        if not linked and not (removed and known):
            return
        other = getattr(self.owner, 'find_owner', lambda _: None)(doc)
        if getattr(other, '_preview_depth', 0):
            return  # Actual motion preview is restored, not a design edit.
        self._dependency_events[doc.Name] = self._dependency_events.get(doc.Name, 0) + 1
        self.owner.generation += 1

    def _documents(self):
        root = self.owner.doc
        docs, pending = [], [root]
        while pending:
            doc = pending.pop(0)
            if any(doc is old for old in docs):
                continue
            docs.append(doc)
            pending.extend(list(getattr(doc, 'OutList', [])))
            for obj in doc.Objects:
                for name in obj.PropertiesList:
                    if 'PropertyXLink' in obj.getTypeIdOfProperty(name):
                        pending.extend(link.Document for link in _linked(getattr(obj, name)))
            if len(docs) > native_cad.MAX_FILES:
                raise ValueError('Native project dependency graph exceeds 1024 documents')
        return docs

    def save(self, path=None):
        owner = self.owner
        owner.assert_thread()
        if self.in_save:
            raise ValueError('SAVE_IN_PROGRESS: the current native save must finish')
        path = Path(path or self.path or (owner.export_root / owner.document_id / 'design.caepre')).resolve()
        if path.suffix.lower() != '.caepre':
            raise ValueError('Lab Save uses .caepre; native FCStd export is a separate command')
        owner.before_design_action('save')
        self.in_save = True
        try:
            metadata = owner.read_metadata()
            metadata['document_id'] = owner.document_id
            if metadata != owner.read_metadata():
                owner._transaction('Initialize Lab project identity', lambda: owner.write_metadata(metadata))
            docs = self._documents()
            linked_owners = []
            for doc in docs:
                other = getattr(owner, 'find_owner', lambda doc: None)(doc)
                if other is not None and other is not owner:
                    other.before_design_action('linked project save')
                    linked_owners.append((other, other.generation))
            generations = owner.generation
            graph_version = self.graph_version()
            revision = 'R' + uuid.uuid4().hex
            stage = owner.export_root / owner.document_id / 'project_staging' / revision
            stage.mkdir(parents=True, exist_ok=False)
            names = {doc.Name: 'documents/' + doc.Name + '.FCStd' for doc in docs}
            originals = {Path(doc.FileName).resolve(): doc.Name for doc in docs if doc.FileName}
            files, records, missing = {}, [], []
            for doc in docs:
                # Cross-document modifications must be inspected before copying.
                # An active native task in any linked document cannot be saved
                # as though its uncommitted editor controls were applied.
                gdoc = owner.Gui.getDocument(doc.Name) if hasattr(owner.Gui, 'getDocument') else None
                if gdoc is not None and gdoc.getInEdit():
                    raise ValueError('BUSY_EDIT: finish/cancel the linked document task before saving')
                native = stage / ('source-' + doc.Name + '.FCStd')
                save_native_copy(doc, native)
                if not native.is_file():
                    raise ValueError('Native saveCopy did not produce the editable document')
                destination = stage / names[doc.Name]
                def relocate(link, doc=doc):
                    obj = doc.getObject(link['object_id'])
                    targets = []
                    if obj is not None and link['property'] in obj.PropertiesList:
                        targets = _linked(getattr(obj, link['property']))
                    matches = [item for item in targets if item.Name == link['target_name']]
                    external = [item for item in matches if item.Document is not doc]
                    target_name = None
                    if len(external) == 1:
                        target_name = external[0].Document.Name
                    elif link['file']:
                        if doc.FileName:
                            try:
                                target_name = originals.get(native_cad.logical_file(Path(doc.FileName).parent, link['file']))
                            except ValueError:
                                pass
                    elif not external:
                        return None  # Native intra-document link.
                    if target_name in names:
                        return Path(names[target_name]).name
                    # Invalid drafts are saved. Keep the exact failed reference
                    # in the manifest but make it unable to open an unrelated
                    # host file during restore.
                    replacement = 'missing-' + canonical_hash({**link, 'document': doc.Name})[:20] + '.FCStd'
                    missing.append({**link, 'document': doc.Name, 'replacement': 'documents/' + replacement})
                    return replacement
                native_cad.relocate(native, destination, relocate)
                files[names[doc.Name]] = destination
                records.append({'file': names[doc.Name], 'native_name': doc.Name, 'label': doc.Label,
                    'original_file': doc.FileName or None, 'native_copy_sha256': native_cad.sha(native),
                    'sha256': native_cad.sha(destination), 'bytes': destination.stat().st_size})
            if owner.generation != generations or self.graph_version() != graph_version or any(other.closed or other.generation != generation
                                                      for other, generation in linked_owners):
                raise ValueError('INPUT_CHANGED: native document or linked document changed while preparing its save')
            manifest = {'kind': native_cad.KIND, 'schema_version': 1, 'document_id': owner.document_id,
                'revision': revision, 'parent_revision': (self.last_save or {}).get('revision'),
                'entry': names[owner.doc.Name], 'documents': records, 'unavailable_dependencies': missing,
                'metadata': owner.read_metadata(), 'saved_generation': generations, 'saved_utc': utc_now(),
                'saved_dependencies': [{'native_name': doc.Name,
                    'generation': (getattr(owner, 'find_owner', lambda _: None)(doc).generation
                                   if getattr(owner, 'find_owner', lambda _: None)(doc) is not None else None)}
                    for doc in docs if doc is not owner.doc],
                'engineering_release': 'UNKNOWN', 'design_pose_restored': True}
            save_json(stage / 'project.json', manifest)
            # Publish an immutable revision first. Failure to publish the user's
            # selected .caepre keeps both that revision and the previous save.
            retained = stage / 'retained.caepre'
            native_cad.publish_project(retained, manifest, files)
            saved = native_cad.publish_project(path, manifest, files)
            saved['retained_project'] = str(retained)
            self.path, self.last_save, self.last_failure = path, saved, None
            owner.saved_generation = generations
            self._saved_graph_version = graph_version
            return {**saved, 'document_id': owner.document_id, 'unavailable_dependencies': missing}
        except Exception as error:
            self.last_failure = str(error)
            raise
        finally:
            self.in_save = False

    def open(self, receipt):
        if not isinstance(receipt, dict) or receipt.get('kind') != 'native_design':
            raise ValueError('Open a registered editable CAD/project input')
        source = Path(receipt['path']).resolve(strict=True)
        if native_cad.sha(source) != receipt.get('sha256'):
            raise ValueError('Registered native design entry changed')
        for row in receipt.get('files', []):
            if native_cad.sha(row['path']) != row['sha256']:
                raise ValueError('Registered native Link dependency changed')
        folder = self.owner.export_root / 'editable_imports' / ('I' + uuid.uuid4().hex)
        if source.suffix.lower() == '.caepre':
            manifest, entry = native_cad.unpack_project(source, folder)
        else:
            from pathlib import PurePosixPath
            registered = receipt.get('files', [])
            locations = receipt.get('native_metadata', {}).get('original_locations', {})
            original = {row['path']: locations[row['relative']] for row in registered if row['relative'] in locations}
            manifest, entry = native_cad.working_copy(source, folder, registered=registered, original_locations=original)
        doc = self.owner.App.openDocument(str(entry))
        doc.UndoMode = 1
        branch = receipt.get('candidate_branch')
        if branch:
            from . import metadata
            data = metadata.read(doc)
            data.update(document_id='P' + uuid.uuid4().hex, candidate_branch=deepcopy(branch))
            metadata.write(doc, data)
            manifest = {**deepcopy(manifest), 'new_design_branch': True}
        remember_open(doc, manifest, source)
        # The connection creates a distinct native owner for the new document;
        # it never switches a current owner's document pointer behind the GUI.
        return {'native_document': doc.Name, 'working_file': doc.FileName,
                'input_id': receipt['id'], 'saved_document_id': manifest.get('document_id'),
                'unavailable_dependencies': manifest.get('unavailable_dependencies', [])}

    def dispatch(self, operation, args, target):
        if target:
            raise ValueError('Project commands do not accept an object target')
        if operation == 'pre.project.inspect':
            if args:
                raise ValueError('Project inspection takes no arguments')
            return self.descriptor()
        if operation == 'pre.project.save':
            if args:
                raise ValueError('Use the native Save As dialog to choose a new path; remote save uses the managed destination')
            return self.save()
        if operation == 'pre.project.open':
            if set(args) != {'input_id', 'receipt'} or args['receipt'].get('id') != args['input_id']:
                raise ValueError('Open needs the service-resolved registered design receipt')
            return self.open(args['receipt'])
        if operation == 'pre.links.record':
            if set(args) != {'job_id', 'link'} or args['link'].get('job_id') != args['job_id']:
                raise ValueError('Record a verified exact native job link')
            metadata = self.owner.read_metadata()
            links = metadata.setdefault('links', [])
            previous = next((row for row in links if row['job_id'] == args['job_id']), None)
            if previous != args['link']:
                if previous is not None:
                    metadata.setdefault('link_history', []).append(deepcopy(previous))
                    links.remove(previous)
                links.append(deepcopy(args['link']))
                self.owner._transaction('Retain calculation connection', lambda: self.owner.write_metadata(metadata))
            return {'links': deepcopy(links)}
        raise ValueError('Unsupported project command')
