"""Input/worker/Post routing checks; no native solver or CAD run is simulated as real."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS
from xml.etree import ElementTree as ET

import pytest

from test_frozen_fem import snapshot, native, repin
from caelab.adapters import codeaster_frozen as adapter
from caelab.adapters import codeaster_frozen_worker as worker


def native_mesh(mesh):
    # Reverse native node/cell order: output identity must not depend on ordering.
    nodes = list(reversed(mesh['nodes']))
    indexes = {r['node_id']:i for i,r in enumerate(nodes)}
    elements = list(reversed(mesh['elements']))
    coordinates = [r['position_mm'] for r in nodes]
    return NS(getCoordinates=lambda:NS(toNumpy=lambda:NS(tolist=lambda:coordinates)),
        getNumberOfNodes=lambda:len(nodes),getNumberOfCells=lambda:len(elements),
        getNodes=lambda name=None: ([indexes[n] for n in sorted({r['node_id'] for r in mesh['fixed_dofs']})] if name else list(range(len(nodes)))),
        getCells=lambda name:list(range(len(elements))),
        getConnectivity=lambda:[[indexes[n] for n in r['node_ids']] for r in elements],
        getCellTypeName=lambda index:'TETRA10')


def raw_result(mesh):
    guard = worker.check_import(native_mesh(mesh),mesh)
    tables = {}
    by_id = {r['node_id']:r for r in mesh['nodes']}
    for field in ('DEPL','REAC_NODA'):
        table = {key:[] for key in ('NOEUD','NUME_ORDRE',*worker.COORDINATE_COMPONENTS,*worker.VECTOR_COMPONENTS)}
        for index,n in enumerate(guard['node_ids_in_native_order']):
            values = [str(index+1),1,*by_id[n]['position_mm'],0.,0.,-.125 if field=='DEPL' else 2.]
            for key,value in zip(table,values):table[key].append(value)
        tables[field] = table
    table = {key:[] for key in ('MAILLE','POINT','SOUS_POINT','NUME_ORDRE',*worker.COORDINATE_COMPONENTS,*worker.STRESS_COMPONENTS)}
    by_element = {r['element_id']:r for r in mesh['elements']}
    for index,e in enumerate(guard['element_ids_in_native_order']):
        xyz = [by_id[n]['position_mm'] for n in by_element[e]['node_ids']]
        for point,coordinate in enumerate(worker._gauss_positions(xyz),1):
            values = [str(index+1),point,1,1,*coordinate,1.,2.,3.,4.,5.,6.]
            for key,value in zip(table,values):table[key].append(value)
    tables['SIEF_ELGA'] = table
    return dict(solver_status='COMPLETED',converged=True,versions={'code_aster':'17.4.0'},
        order=1,available_orders=[1],access_parameters={'NUME_ORDRE':[1],'INST':[0.]},
        native_mesh_checks=guard,tables=tables)


def test_prepare_uses_same_native_mesh_material_faces_loads_and_keeps_sources(snapshot,tmp_path):
    before = {p.name:p.read_bytes() for p in snapshot.parent.iterdir()}
    out = tmp_path/'prepared';out.mkdir()
    manifest,mesh,pins,gates,sources,budgets = adapter.prepare_input(snapshot,out)
    assert gates['rigid_body_constraint_rank'] == 6
    assert json.loads((out/'solver/mesh.json').read_text()) == mesh
    config = json.loads((out/'solver/input.json').read_text())
    assert config['material'] == manifest['material']
    assert config['node_labels']['4'] == 'N4'
    assert mesh['loads'] == [{'node_id':4,'component':3,'force_N':-10.}]
    text = (out/'solver/mesh.mail').read_text()
    # Same C3D10 order, including the last two midside nodes.
    assert 'M1 N2 N1 N3 N4 N5\nN7 N6 N9 N8 N10' in text
    assert max(map(len,text.splitlines())) <= 80
    assert {p.name:p.read_bytes() for p in snapshot.parent.iterdir()} == before
    assert 'MECA_STATIQUE' not in (out/'solver/model.comm').read_text()  # trusted worker owns syntax


def test_curved_quadratic_nodes_are_not_replaced_with_a_block(snapshot,tmp_path):
    mesh = json.loads((snapshot.parent/'mesh.json').read_text())
    changed = next(r for r in mesh['nodes'] if r['node_id']==5)
    changed['position_mm'][2] = changed['native_position_mm'][2] = .03
    path = snapshot.parent/'mesh.json';path.write_text(json.dumps(mesh));repin(snapshot,path.name)
    deck = snapshot.parent/'ExistingMesh.inp'
    deck.write_text(deck.read_text().replace('5,0.5,0.0,0.0','5,0.5,0.0,0.03'))
    # The routing double's native writer emits integer coordinate tokens.
    if '5,0.5,0.0,0.03' not in deck.read_text():
        deck.write_text(deck.read_text().replace('5,0.5,0,0','5,0.5,0,0.03'))
    repin(snapshot,deck.name)
    out = tmp_path/'curved';out.mkdir()
    _,captured,*_ = adapter.prepare_input(snapshot,out)
    result = worker.parse_result(raw_result(captured),captured)
    assert captured == mesh
    assert len(result['stress_points']) == 5
    assert not all(row['position_mm'][2] == 0 for row in result['stress_points'])
    # At the barycentre all corner shapes are -1/8 and edge shapes 1/4;
    # the one moved mid-edge shifts the z coordinate by .03/4.
    assert any(row['position_mm']==pytest.approx([.25,.25,.2575]) for row in result['stress_points'])


@pytest.mark.parametrize('change', ['missing_node','missing_point','duplicate_point','wrong_coordinate','wrong_order','wrong_units_runtime','wrong_native_topology'])
def test_incomplete_or_misassociated_native_fields_never_become_success(snapshot,change):
    _,mesh,_,_ = adapter.validate_snapshot(snapshot)
    raw = raw_result(mesh)
    if change=='missing_node':
        for values in raw['tables']['DEPL'].values():values.pop()
    elif change=='missing_point':
        for values in raw['tables']['SIEF_ELGA'].values():values.pop()
    elif change=='duplicate_point':raw['tables']['SIEF_ELGA']['POINT'][-1] = 1
    elif change=='wrong_coordinate':raw['tables']['SIEF_ELGA']['COOR_X'][0] += .01
    elif change=='wrong_order':raw['tables']['DEPL']['NUME_ORDRE'][0] = 2
    elif change=='wrong_units_runtime':raw['versions']['code_aster'] = 'unknown'
    else:raw['native_mesh_checks']['node_ids_in_native_order'][0] = 999
    with pytest.raises(ValueError):worker.parse_result(raw,mesh)


def test_native_mesh_gate_rejects_connectivity_or_support_substitution(snapshot):
    _,mesh,_,_ = adapter.validate_snapshot(snapshot)
    original = native_mesh(mesh)
    changed = deepcopy(original)
    cells = original.getConnectivity();cells[0][-1],cells[0][-2] = cells[0][-2],cells[0][-1]
    changed.getConnectivity = lambda:cells
    with pytest.raises(ValueError,match='connectivity'):worker.check_import(changed,mesh)
    changed = deepcopy(original);changed.getNodes=lambda name=None:list(range(len(mesh['nodes'])))
    with pytest.raises(ValueError,match='Fixed'):worker.check_import(changed,mesh)


def test_missing_runtime_keeps_complete_prepared_input_and_not_run(snapshot,tmp_path,monkeypatch):
    def missing(*args):raise RuntimeError('No configured existing Aster runtime')
    monkeypatch.setattr(adapter,'execute_native',missing)
    result = adapter.FrozenFemCodeAsterAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'missing')
    assert result['execution_status']=='FAILED' and result['solver_status']=='NOT_RUN'
    assert (tmp_path/'missing/solver/model.export').is_file()
    assert (tmp_path/'missing/frozen_input/editable.FCStd').is_file()
    assert 'post_artifact' not in result and result['responses']=={}


def test_completed_native_tables_use_existing_vtu_and_explicit_gauss_location(snapshot,tmp_path,monkeypatch):
    def completed(output,budgets):
        path = output/'solver'
        mesh = json.loads((path/'mesh.json').read_text())
        config = json.loads((path/'input.json').read_text())
        raw = raw_result(mesh)
        raw.update(input_sha256=adapter._sha(path/'input.json'),mail_sha256=config['mail_sha256'])
        adapter.save_json(path/'worker_result.json',raw)
        adapter.save_json(path/'native_mesh_checks.json',raw['native_mesh_checks'])
        (path/'results.med').write_bytes(b'native-output-double; not a solver result')
        return {'test_double':True}
    monkeypatch.setattr(adapter,'execute_native',completed)
    output = tmp_path/'result'
    result = adapter.FrozenFemCodeAsterAdapter().run({'snapshot_path':str(snapshot)},output=output)
    assert result['execution_status']=='SUCCEEDED',result['diagnostics']
    assert result['static']['load_parameter']==0. and result['solver_status']=='COMPLETED'
    assert result['decision']=='NOT_RELEASED' and not result['engineering_valid']
    primary,stress = result['post_artifact'],result['additional_post_artifacts'][0]
    assert primary['native_metadata']['coordinate_units']=='mm'
    assert all(r['units']=='MPa' and r['quantity']=='native_integration_point_stress'
        for r in stress['native_metadata']['arrays'] if r['name'].startswith('SI'))
    root = ET.parse(output/primary['relative'])
    assert root.find('.//Piece').get('NumberOfPoints')=='10'
    assert root.find(".//DataArray[@Name='UZ_mm']").text.split()==['-0.125']*10
    assert root.find(".//DataArray[@Name='ReactionZ_N']").text.split()==['2']*10
    assert ET.parse(output/stress['relative']).find('.//Piece').get('NumberOfPoints')=='5'


def test_post_is_not_published_after_prepared_file_changes(snapshot,tmp_path,monkeypatch):
    def changed(output,budgets):
        (output/'solver/mesh.mail').write_text('substituted mesh')
        return {}
    monkeypatch.setattr(adapter,'execute_native',changed)
    result = adapter.FrozenFemCodeAsterAdapter().run({'snapshot_path':str(snapshot)},output=tmp_path/'changed')
    assert result['execution_status']=='FAILED' and 'post_artifact' not in result
    assert 'input changed' in result['diagnostics']['reason']
