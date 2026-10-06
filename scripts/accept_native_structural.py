"""Actual native CAD/face/partial-BC mechanics with an affine reference.

Uses the already retained public G1 box as input. Preserves every earlier
attempt. One declared mesh tests the new user flow, never a mandatory sweep.
"""
from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from caelab import Lab
from caelab.storage import load_json, save_json, source_identity


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(args):
    root = Path(args.store).resolve()
    if root.exists():
        raise ValueError('Prepare requires a fresh store; existing native attempts are preserved')
    source = Path(args.source).resolve()
    original = digest(source)
    if original != '7ab8a9d194150317d644c0312713d5e85b4878140f35a919b6753fd03a3ee415':
        raise ValueError('This analytical acceptance uses the retained public G1 box, not company geometry')
    lab = Lab(root)
    lab.create_study('S-native-mechanics', '내 CAD 면 선택과 선형 정적 해석',
                     '면에 지정한 인장 합력과 부분 구속이 완전한 affine 변위장을 재현하는가?',
                     '공개 box의 등방성 단축 인장 참조', '동일 CAD/조건/전체장/원본 보존')
    imported = lab.import_native_model(source)
    model = imported['design']
    candidates = lab.discover_parameters('fixture.freecad', model)
    chosen = [item for item in candidates if item['native']['path'].endswith('|property|Length')]
    if len(chosen) != 1:
        raise ValueError('The retained G1 public box has no unambiguous editable Length')
    lab.register_parameter('S-native-mechanics', 'fixture.freecad', model, chosen[0]['native']['path'],
                           'length', '길이', 10, 24)
    parent = lab.run_experiment(study_id='S-native-mechanics', experiment_id='E-native-box16',
                                backend='fixture.freecad', model=model, values={'length': 16})
    save_json(root / 'acceptance-preparation.json', {'source': str(source), 'source_sha256': original,
        'model': model, 'parent_experiment_id': parent['experiment_id'], 'parent_status': parent['status'],
        'producer': source_identity(ROOT)})
    if digest(source) != original or parent['status'] != 'COMPLETED_REVIEW_REQUIRED':
        raise ValueError('Actual native CAD preparation failed; retained records are not changed')
    print(json.dumps({'stage': 'CAD_READY', 'model': model, 'parent': parent['experiment_id']}), flush=True)


def solve(args):
    root = Path(args.store).resolve()
    lab = Lab(root)
    parent = load_json(root / 'acceptance-preparation.json')['parent_experiment_id']
    described = lab.describe_analysis_conditions(parent)
    catalog = described['catalog']
    body = next(item for item in catalog['selections'] if item['id'] == 'B-final')
    if any(abs(actual-want) > 1e-7 for actual,want in zip([*body['bounds_mm']['min'], *body['bounds_mm']['max']],
                                                       [0,0,0,16,10,8])):
        raise ValueError('This reference requires the retained axis-aligned 16x10x8 mm box')
    faces = [item for item in catalog['selections'] if item.get('kind') == 'native_face']
    def plane(axis, coordinate):
        selected = [item for item in faces if abs(item['bounds_mm']['min'][axis] - coordinate) < 1e-7
                    and abs(item['bounds_mm']['max'][axis] - coordinate) < 1e-7]
        if len(selected) != 1:
            raise ValueError('A reference face must have one verified native geometric identity')
        return selected[0]['id']
    boundaries = [{'id': 'BC'+str(axis+1), 'selection_id': plane(axis, 0), 'type': 'displacement',
        'components': {name: 0.}, 'unit': 'mm', 'coordinate_system': 'global',
        'source': 'ANALYTICAL_REFERENCE: symmetry plane, remaining displacement components are free'}
        for axis,name in enumerate(('UX','UY','UZ'))]
    declaration = {'analysis_type': 'linear_static', 'units': {'length': 'mm','force': 'N','stress': 'MPa'},
        'coordinate_system': 'global', 'materials': [{'id':'M1','selection_id':'B-final',
        'law':'isotropic_linear_elastic','young_modulus_MPa':210000.,'poisson_ratio':.3,
        'source': {'category':'ASSUMED','description':'ANALYTICAL_REFERENCE: assumed E=210000 MPa, nu=0.3; unqualified'}}],
        'boundary_conditions': boundaries, 'loads':[{'id':'L1','selection_id':plane(0,16),'type':'resultant_force',
        'components':{'FX':150.,'FY':0.,'FZ':0.},'unit':'N','coordinate_system':'global',
        'source':'ANALYTICAL_REFERENCE: uniform +X traction on native end face, 150N resultant, not measured'}],
        'contact': {'mode':'none','source':'Single solid reference; no assembly/contact qualification'},
        'mesh':{'mode':'selected','max_size_mm':4.}}
    identifier = 'C-native-box-'+args.tag
    condition = lab.save_analysis_conditions(conditions_id=identifier, experiment_id=parent,
        cad_revision=described['source']['cad_revision'], catalog_revision=described['catalog_revision'],
        backend='structure.calculix.native', declaration=declaration)
    if condition['support']['status'] != 'SUPPORTED_DECLARED_INPUTS':
        raise ValueError('Actual native conditions are unsupported: '+str(condition['support']))
    producer = source_identity(ROOT)
    result = lab.run_analysis(parent_experiment_id=parent, experiment_id='E-native-box-'+args.tag,
                             backend='structure.calculix.native', conditions_id=identifier)
    save_json(root / ('acceptance-run-'+args.tag+'.json'), {'producer':producer,'experiment_id':result['experiment_id'],
        'conditions_id':identifier,'status':result['status'], 'metrics':result['metrics'],
        'decision':result['decision'], 'solver_status':result['solver_status']})
    print(json.dumps({'stage':'SOLVE_RECORDED','experiment':result['experiment_id'],'status':result['status'],
                      'checks':[(v['type'],v['status']) for v in result['validations']]}),flush=True)
    if result['status'] != 'COMPLETED_REVIEW_REQUIRED':
        raise ValueError('Native solve did not pass; every failed attempt remains retained')
    field = load_json(root / 'experiments' / result['experiment_id'] / 'simulation/field.json')
    strain = 150./(10*8*210000.)
    absolute = max(abs(a-b) for node in field['nodes'] for a,b in zip(node['displacement_mm'],
        [strain*node['position_mm'][0], -.3*strain*node['position_mm'][1], -.3*strain*node['position_mm'][2]]))
    normalized = absolute / (strain * 16.)
    reference = {'type':'affine_uniaxial_3D_elasticity','source':'sigma_x=F/A; U=[sigma_x*x/E,-nu*sigma_x*y/E,-nu*sigma_x*z/E]',
        'material':'ASSUMED_NOT_QUALIFIED','node_count':field['node_count'],'element_count':field['element_count'],
        'maximum_absolute_component_error_mm':absolute,'maximum_normalized_component_error':normalized,
        'limit':1e-5,'status':'PASS' if normalized <= 1e-5 else 'FAIL','mesh_sweep':'NOT_REQUIRED',
        'physical':'UNKNOWN','decision':'NOT_RELEASED','producer':producer}
    save_json(root / ('acceptance-reference-'+args.tag+'.json'), reference)
    print(json.dumps(reference),flush=True)
    assert reference['status'] == 'PASS', 'The full affine reference failed; threshold is unchanged'


if __name__ == '__main__':
    parser=ArgumentParser()
    parser.add_argument('--store',required=True)
    parser.add_argument('--source', default=str(ROOT / 'tests/fixtures/native_single_solid/public_box.FCStd'))
    parser.add_argument('--stage',choices=('prepare','solve','all'),default='all')
    parser.add_argument('--tag',default='r01')
    args=parser.parse_args()
    if args.stage in ('prepare','all'): prepare(args)
    if args.stage in ('solve','all'): solve(args)
