"""Live owner tests with captured pinned primitives and native-shaped doubles.

Only the pure worker primitives are executed; no FreeCAD import, native process
or geometry kernel is used. Captured unchanged from worker commit
3e48bf6138f495299f45b1af254bfb4aaff307b8, blob f4cb12781f8ab86241b3cd293d585c14eb1ef4dd.
"""
from copy import deepcopy
import json
import threading
from types import SimpleNamespace as NS

import pytest

from apps.desktop_pre.bridge import Owner, OPERATIONS
from apps.desktop_pre.parameters import Parameters
from caelab.native_commands import CAPABILITIES, NativeCommands

PINNED_PRIMITIVES = r'''def _signature(shape):
    b=shape.BoundBox
    # Boolean results can be Part.Compound even when they hold exactly one
    # valid solid. FreeCAD exposes CenterOfMass on the enclosed Part.Solid.
    c=shape.Solids[0].CenterOfMass
    return (shape.Volume,shape.Area,b.XMin,b.XMax,b.YMin,b.YMax,b.ZMin,b.ZMax,
            c.x,c.y,c.z)


def _changes_shape(before,after):
    return any(abs(a-b)>max(1e-6,1e-7*max(abs(a),abs(b))) for a,b in zip(before,after))


def _config(doc):
    obj=doc.getObject('FixtureConfiguration')
    if obj is None:
        obj=doc.addObject('App::DocumentObjectGroup','FixtureConfiguration')
        obj.Label='Fixture parameter definitions'
        obj.addProperty('App::PropertyString','Definition','Fixture')
        obj.Definition=json.dumps({'parameters':[],'final':None})
    return obj


def _save_registry(doc,registry):
    _config(doc).Definition=json.dumps(registry,ensure_ascii=False,sort_keys=True)


def _targets(doc):
    items=[]
    for obj in doc.Objects:
        for prop in obj.PropertiesList:
            kind=obj.getTypeIdOfProperty(prop)
            if kind not in ('App::PropertyLength','App::PropertyDistance'):
                continue
            value=getattr(obj,prop)
            items.append({'key':obj.Name+'|property|'+prop,'object':obj.Name,
                          'object_label':obj.Label,'dimension':prop,'kind':'property',
                          'value':float(value.Value),'unit':'mm'})
        if obj.TypeId=='Sketcher::SketchObject':
            for i,c in enumerate(obj.Constraints):
                if c.Type not in ('Distance','DistanceX','DistanceY','Radius','Diameter') or not obj.getDriving(i):
                    continue
                items.append({'key':obj.Name+'|constraint|'+str(i),'object':obj.Name,
                              'object_label':obj.Label,'dimension':c.Name or f'{c.Type} #{i+1}',
                              'kind':'constraint','value':float(c.Value),'unit':'mm'})
    return items


def _datum(doc,entry):
    obj=doc.getObject(entry['object'])
    if obj is None:raise ValueError('A registered CAD feature was deleted')
    if entry['kind']=='property':
        if obj.getTypeIdOfProperty(entry['property']) not in ('App::PropertyLength','App::PropertyDistance'):
            raise ValueError('The CAD property no longer has a length unit')
        return obj,entry['property']
    if 'constraint_index' in entry:
        index=entry['constraint_index']
        if obj.TypeId=='Sketcher::SketchObject' and 0<=index<len(obj.Constraints) and obj.getDriving(index):
            return obj,index
        raise ValueError('Selected sketch dimension is not driving')
    for i,c in enumerate(obj.Constraints):
        if c.Name==entry['constraint'] and obj.getDriving(i):return obj,i
    raise ValueError('The named driving sketch constraint was deleted')


def _assign(doc,entry,value):
    obj,key=_datum(doc,entry)
    if entry['kind']=='property':setattr(obj,key,App.Units.Quantity(f'{value} mm'))
    else:obj.setDatum(key,App.Units.Quantity(f'{value} mm'))


def _read(doc,entry):
    obj,key=_datum(doc,entry)
    return float(getattr(obj,key).Value) if entry['kind']=='property' else float(obj.Constraints[key].Value)

'''


class Quantity:
    def __init__(self, text):
        number, unit = str(text).split()
        assert unit == 'mm'
        self.Value = float(number)


class NativeObject:
    def __init__(self, doc, name, kind='App::DocumentObjectGroup'):
        self.Document, self.Name, self.Label, self.TypeId = doc, name, name, kind
        self.PropertiesList, self.State, self.ExpressionEngine = [], [], []
        self.types, self.modes = {}, {}
    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name in self.__dict__.get('PropertiesList', []):
            self.Document.owner.slotChangedObject(self, name)
    def addProperty(self, kind, name, *args):
        self.PropertiesList.append(name)
        self.types[name] = kind
        setattr(self, name, '')
        return self
    def setEditorMode(self, name, mode):
        self.modes[name] = ['ReadOnly'] if mode == 1 else []
    def getEditorMode(self, name):
        return self.modes.get(name, [])
    def getTypeIdOfProperty(self, name):
        return self.types[name]


class NativeDoc:
    Name, Label, FileName = 'LiveDesign', 'Controlled native design', ''
    UndoCount, RedoCount = 0, 0
    def __init__(self):
        self.Objects, self.transactions = [], []
        self.owner = None
        self.restore_fails = False
    def getObject(self, name):
        return next((obj for obj in self.Objects if obj.Name == name), None)
    def addObject(self, kind, name):
        obj = NativeObject(self, name, kind)
        self.Objects.append(obj)
        self.owner.slotCreatedObject(obj)
        return obj
    def openTransaction(self, title):
        self.transactions.append(('open', title))
        self.snapshot = [(obj, {name: deepcopy(getattr(obj, name)) for name in obj.PropertiesList})
                         for obj in self.Objects]
    def commitTransaction(self):
        self.transactions.append(('commit',))
    def abortTransaction(self):
        self.transactions.append(('abort',))
        if not self.restore_fails:
            self.Objects[:] = [obj for obj, _ in self.snapshot]
            for obj, fields in self.snapshot:
                for name, value in fields.items():
                    setattr(obj, name, value)
            self.recompute()
    def recompute(self):
        self.transactions.append(('recompute',))
        value = self.getObject('Pad').Length.Value
        shape = self.getObject('Pad').Shape
        shape.Volume, shape.Area = value * 4., value * 2.
        shape.BoundBox = NS(XMin=0., XMax=value, YMin=0., YMax=2., ZMin=0., ZMax=2.)
        shape.Solids[0].CenterOfMass = NS(x=value / 2., y=1., z=1.)


@pytest.fixture
def live(tmp_path):
    doc = NativeDoc()
    owner = Owner.__new__(Owner)
    doc.owner = owner
    owner.doc, owner.document_id, owner.session_id = doc, 'Plive', 'Slive'
    owner.export_root = tmp_path
    owner.generation = owner.view_generation = 0
    owner.saved_generation, owner.recovery_error = None, None
    owner.closed, owner._preview_depth, owner._selection = False, 0, None
    owner.completed, owner.binding_diagnostics = {}, {}
    owner.thread_id = threading.get_ident()
    owner.mesh_bindings = NS(slotChangedObject=lambda *args: None)
    owner.motion = NS(descriptor=lambda: {}, before_design_action=lambda reason: None)
    owner.fem = NS(_pending={})
    owner.fem_descriptor = lambda: {'mesh_busy': False}
    owner.project = NS(descriptor=lambda: {}, is_saved=lambda: False)
    owner.Gui = NS(Selection=NS(getSelectionEx=lambda name: []), Control=NS(activeDialog=lambda: False),
                   activeDocument=lambda: NS(getInEdit=lambda: False))
    app = NS(Units=NS(Quantity=Quantity))
    owner.App = app
    pad = NativeObject(doc, 'Pad', 'Part::Box')
    pad.addProperty('App::PropertyLength', 'Length')
    pad.Length = Quantity('10 mm')
    pad.Shape = NS(Volume=40., Area=20., Solids=[NS(CenterOfMass=NS(x=5., y=1., z=1.))],
                   BoundBox=NS(XMin=0., XMax=10., YMin=0., YMax=2., ZMin=0., ZMax=2.),
                   isValid=lambda: True, isNull=lambda: False)
    doc.Objects.append(pad)
    worker = NS()
    namespace = {'App': app, 'json': json}
    exec(PINNED_PRIMITIVES, namespace)
    for name, value in namespace.items():
        if name.startswith('_') and callable(value):
            setattr(worker, name, value)
    owner.parameters = Parameters(owner, worker)
    owner.generation = 0
    return NS(owner=owner, doc=doc, pad=pad, worker=worker, parameters=owner.parameters)


def command(live, operation, arguments, identifier='Cfixture'):
    return {'command_id': identifier, 'document_id': live.owner.document_id,
        'session_id': live.owner.session_id, 'expected_generation': live.owner.generation,
        'operation': operation, 'arguments': deepcopy(arguments), 'target': {}}


def probed(live):
    found = live.parameters.discover()
    row = found['candidates'][0]
    proof = live.parameters.probe({'selector': row['key'], 'source_stamp': found['source_stamp'],
        'effect_object_id': 'Pad', 'trial_value': 12., 'unit': 'mm'})
    return found, row, proof


def registration(found, row, proof):
    return {'selector': row['key'], 'source_stamp': found['source_stamp'], 'proof_id': proof['proof_id'],
            'parameter_id': 'pad_length', 'label': 'Pad length', 'lower': 8., 'upper': 16., 'mode': 'free'}


def test_live_discovery_is_read_only_and_probe_restores_actual_datum_and_signature(live):
    before_objects = list(live.doc.Objects)
    found, row, proof = probed(live)
    assert found['units'] == 'mm' and row['key'] == 'Pad|property|Length'
    assert live.doc.Objects == before_objects
    assert live.doc.getObject('FixtureConfiguration') is None
    assert proof['changed'] and proof['restored'] and proof['error'] is None
    assert live.pad.Length.Value == 10. and live.pad.Shape.Volume == 40.
    assert live.owner.generation == 0 and live.owner.view_generation == 1
    assert ('abort',) in live.doc.transactions and ('commit',) not in live.doc.transactions


def test_live_registration_uses_native_pinned_registry_bounds_and_receipt_is_idempotent(live):
    found, row, proof = probed(live)
    request = command(live, 'pre.parameters.register', registration(found, row, proof))
    outcome = live.owner.dispatch(request)
    assert outcome['status'] == 'COMPLETED', outcome
    registry = live.parameters.registry()
    entry = registry['parameters'][0]
    assert entry['min'] == 8. and entry['max'] == 16.
    assert 'minimum' not in entry and 'maximum' not in entry
    generation, transactions = live.owner.generation, deepcopy(live.doc.transactions)
    assert live.owner.dispatch(deepcopy(request)) == outcome
    assert live.owner.generation == generation and live.doc.transactions == transactions
    assert len(live.parameters.registry()['parameters']) == 1
    assert live.pad.Length.Value == 10.


def test_existing_pinned_registry_updates_bounds_and_value_without_replacing_other_entries(live):
    entry = {'name': 'old_length', 'label': 'Existing native length', 'min': 5., 'max': 20.,
             'unit': 'mm', 'object': 'Pad', 'kind': 'property', 'property': 'Length', 'key': 'Pad|property|Length'}
    live.worker._save_registry(live.doc, {'parameters': [entry], 'final': 'Pad'})
    request = command(live, 'pre.parameters.update', {'parameter_id': 'old_length', 'value': 13., 'unit': 'mm'})
    outcome = live.owner.dispatch(request)
    assert outcome['status'] == 'COMPLETED', outcome
    assert live.parameters.registry()['parameters'][0] == entry
    assert live.parameters.registry()['final'] == 'Pad' and live.pad.Length.Value == 13.
    assert outcome['result']['parameters'][0]['current_value'] == 13.


def test_stale_effect_proof_cannot_register_after_human_native_change(live):
    found, row, proof = probed(live)
    live.pad.Length = Quantity('11 mm')
    outcome = live.owner.dispatch(command(live, 'pre.parameters.register', registration(found, row, proof)))
    assert outcome['status'] == 'FAILED'
    assert 'STALE' in outcome['error']['message']
    assert live.doc.getObject('FixtureConfiguration') is None and live.pad.Length.Value == 11.


def test_expression_driven_target_is_not_writable_and_probe_never_assigns(live):
    live.pad.ExpressionEngine = [('Length', 'Spreadsheet.length')]
    found = live.parameters.discover()
    assert not found['candidates'][0]['writable']
    with pytest.raises(ValueError, match='Expression-driven'):
        live.parameters.probe({'selector': found['candidates'][0]['key'], 'source_stamp': found['source_stamp'],
            'effect_object_id': 'Pad', 'trial_value': 12., 'unit': 'mm'})
    assert live.pad.Length.Value == 10. and live.doc.transactions == []


def test_probe_restore_failure_blocks_future_save_and_keeps_no_success_proof(live):
    found = live.parameters.discover()
    original = live.worker._assign
    def assign(doc, entry, value):
        if value == 10.:
            raise RuntimeError('Controlled original-datum restore failure')
        original(doc, entry, value)
    live.worker._assign = assign
    live.doc.restore_fails = True
    outcome = live.owner.dispatch(command(live, 'pre.parameters.probe', {
        'selector': found['candidates'][0]['key'], 'source_stamp': found['source_stamp'],
        'effect_object_id': 'Pad', 'trial_value': 12., 'unit': 'mm'}))
    assert outcome['status'] == 'FAILED'
    assert live.parameters.proofs == {}
    assert live.owner.recovery_error and 'PARAMETER_RESTORE_FAILED' in live.owner.recovery_error
    with pytest.raises(ValueError, match='PARAMETER_RESTORE_FAILED'):
        live.owner.before_design_action('save')


def test_real_owner_capabilities_are_admitted_by_actual_service_registry(live, tmp_path):
    descriptor = live.owner.descriptor()
    assert set(descriptor['capabilities']) == set(OPERATIONS)
    assert set(OPERATIONS) <= CAPABILITIES['pre']
    service = NativeCommands(tmp_path / 'service', 'Sservice')
    service.register(host_id='Hfixture', session_id=live.owner.session_id, application='freecad', version='1.1.4',
                     execution_mode='gui', documents=[descriptor], registration_nonce='fixture-native-registration-nonce')
    read = service.read(live.owner.document_id)
    assert read['kind'] == 'pre' and read['connected']
    assert {'pre.project.save', 'pre.parameters.probe', 'pre.parameters.register', 'pre.parameters.rebind'} <= set(read['capabilities'])
