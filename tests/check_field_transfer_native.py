"""Installed pvpython: real VTU readers, Post owner preview/apply/save/cold.

Manufactured fields, no solver/provider. Run under scripts/native_check.py.
"""
from copy import deepcopy
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--create', type=Path)
    parser.add_argument('--reopen', type=Path)
    args = parser.parse_args()
    from paraview import simple as p
    from apps.desktop_post import external, analysis
    from apps.desktop_post.bridge import Owner
    from caelab import post_comparison as physical
    from caelab import field_transfer_contract as transfer
    if args.reopen:
        receipt = json.loads(args.reopen.read_text(encoding='utf-8'))
        project = Path(receipt['project'])
        document = json.loads(project.read_text(encoding='utf-8-sig'))
        unchanged = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (project, project.parent / document['workspace_file'])}
        os.environ['CAE_POST_PROJECT'] = str(project)
        # Read-only reopening must not recreate comparison graphs/calculations.
        def forbidden(*a, **kw): raise AssertionError('Cold read attempted a new mapping/check')
        transfer.conservation_check = forbidden
        transfer.coverage_check = forbidden
        external.restore_workspace(project, json.loads(project.read_text(encoding='utf-8-sig')))
        owner = Owner(); workspace = owner.workspace
        assert not workspace.restore_issues, workspace.restore_issues
        assert not any(source.GetXMLName() in ('ProgrammableFilter', 'ResampleWithDataset')
                       for source in p.GetSources().values()), 'An executable comparison graph survived cold read'
        for item in receipt['comparisons']:
            rows = workspace.sample(object_ref=item['object_ref'], preview=False, limit=1000)['rows']
            assert rows == item['rows']
            record = workspace.applied(workspace.object(item['object_ref']))
            assert record['summary']['field_transfer'] == item['field_transfer']
            assert record['recipe'] == item['recipe']
            assert workspace.bundles[record['id']]['retained_only']
        # The load-only PVSM substitution retains view IDs/properties and the
        # user's active selection. It must never rewrite either original file.
        server = ET.parse(project.parent / document['workspace_file']).getroot().find('ServerManagerState')
        registrations = server.find("ProxyCollection[@name='views']")
        from paraview import servermanager
        views = servermanager.ProxyManager().GetProxiesInGroup('views')
        for item in registrations.findall('Item') if registrations is not None else []:
            native = next(view for (name, _), view in views.items() if name == item.get('name'))
            proxy = server.find("Proxy[@id='" + item.get('id') + "']")
            for name in ('CameraPosition', 'CameraFocalPoint', 'CameraViewUp', 'CameraParallelScale'):
                prop = proxy.find("Property[@name='" + name + "']")
                if prop is not None:
                    saved = [float(node.get('value')) for node in prop.findall('Element')]
                    actual = getattr(native, name)
                    actual = list(actual) if hasattr(actual, '__iter__') else [actual]
                    assert actual == saved, (name, actual, saved)
        selected = document.get('active_selection', {}).get('source_name')
        assert selected is None or external._same_proxy(p.FindSource(selected), p.GetActiveSource())
        assert unchanged == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in unchanged}
        assert receipt['source_hashes'] == {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                                           for name in receipt['source_hashes']}
        print('PASS actual saved native rows/components/masks/clock/checks; cold mapping calls zero')
        return
    import numpy as np
    from examples.post_comparison import array
    root = args.create.resolve(); root.mkdir(parents=True, exist_ok=False)
    source = root/'input'; source.mkdir()
    points = [[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    refined = points + [[.1,.2,.15]]
    cells = [[0,1,2,3]]
    split = [[0,1,2,4],[0,1,4,3],[0,4,2,3],[4,1,2,3]]
    rotation = np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    def write(name, xyz, topology, fields, cell_fields=None):
        data = ''.join(array(n, values, components) for n, values, components in fields)
        data += array('NativeNodeId', list(range(101,101+len(xyz))), dtype='Int64')
        data += array('required', [1]*len(xyz), dtype='UInt8')
        cell_data = ''.join(array(n, values, components) for n, values, components in cell_fields or [])
        connectivity = array('connectivity', topology, dtype='Int64')
        connectivity += array('offsets', [4*(i+1) for i in range(len(topology))], dtype='Int64')
        connectivity += array('types', [10]*len(topology), dtype='UInt8')
        (source/name).write_text('<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">'
            '<UnstructuredGrid><Piece NumberOfPoints="'+str(len(xyz))+'" NumberOfCells="'+str(len(topology))+'">'
            '<Points>'+array('Points',xyz,3)+'</Points><Cells>'+connectivity+'</Cells><PointData>'+data+
            '</PointData><CellData>'+cell_data+'</CellData></Piece></UnstructuredGrid></VTKFile>', encoding='utf-8')
    def vector(xyz, t): return [[1+x+t, 2-y+2*t, 3+z] for x,y,z in xyz]
    target = vector(refined,1.)
    write('a.vtu',refined,split,[('force',target,3),('stress',[[2,3,4,.2,.1,0]]*5,6)])
    for name,t in [('b0.vtu',0.),('b2.vtu',2.)]:
        values = (np.asarray(vector(points,t)) @ rotation / 1000.).tolist()
        write(name,points,cells,[('force',values,3),('quality',[1,1,1,1],1)])
    (source/'b.pvd').write_text('<VTKFile type="Collection" version="0.1" byte_order="LittleEndian"><Collection>'
        '<DataSet timestep="0" file="b0.vtu"/><DataSet timestep="2" file="b2.vtu"/>'
        '</Collection></VTKFile>',encoding='utf-8')
    tensor = np.array([[2.,.2,0.],[.2,3.,.1],[0.,.1,4.]])
    rotated = rotation.T @ tensor @ rotation * 1e6
    six = [rotated[0,0],rotated[1,1],rotated[2,2],rotated[0,1],rotated[1,2],rotated[0,2]]
    write('tensor.vtu',points,cells,[],[('stress',[six],6)])
    for suffix, scale in [('0', .5), ('2', 1.5)]:
        write('tensor'+suffix+'.vtu',points,cells,[],[('stress',[[v*scale for v in six]],6)])
    (source/'tensor.pvd').write_text('<VTKFile type="Collection"><Collection>'
        '<DataSet timestep="0" file="tensor0.vtu"/><DataSet timestep="2" file="tensor2.vtu"/>'
        '</Collection></VTKFile>',encoding='utf-8')
    write('invalid.vtu',points,cells,[('force',vector(points,1.),3),('quality',[1,0,1,1],1)])
    write('nonconservative.vtu',refined,split,[],[('density',[[v] for v in [1,1,1,4]],1)])
    external.open_result(source/'a.vtu',root/'project')
    owner=Owner(); workspace=owner.workspace
    def admit(name,ref):
        proxy, record = external.admit_result(source/name)
        record.update(source_ref=ref,label=name)
        workspace.document['sources'][ref]=record
    for name,ref in [('b.pvd','Bvector'),('tensor.pvd','Btensor'),('invalid.vtu','Binvalid'),('nonconservative.vtu','Bdensity')]:admit(name,ref)
    base_side={'source_ref':'result','array':'force','association':'POINTS','quantity':'force',
        'units':'N','measure':'force','frame':'global','coordinate_units':'m','coordinate_frame':'global',
        'layout':{'kind':'vector','components':['x','y','z']}, 'sampling':{'mode':'exact','time':None},
        'time':None,'time_units':None,'time_origin':None,'validity_masks':[]}
    recipe={'version':2,'a':deepcopy(base_side),'b':deepcopy(base_side),'method':'linear_tetra_b_to_a','tolerance':0.,
        'target':{'units':'N'},'selection':'y','difference':'selected_difference','percent':'disabled',
        'clock':{'value':1.,'unit':'s','semantics':'physical_time'},
        'alignment':{'geometry_rotation':physical.IDENTITY,'response_rotation':rotation.tolist(),'translation':[0.,0.,0.],
                     'geometry_declared':False,'response_declared':True},
        'coverage':{'policy':'all_a_points','array':None},'conservation':{'mode':'none'}}
    # A is an explicitly recorded physical snapshot rather than an invented time.
    # Its native PVD carries the same acquisition instant as B's interpolation.
    (source/'a.pvd').write_text('<VTKFile type="Collection"><Collection><DataSet timestep="1" file="a.vtu"/></Collection></VTKFile>',encoding='utf-8')
    admit('a.pvd','Atimed'); recipe['a'].update(source_ref='Atimed',time=1.,sampling={'mode':'exact','time':1.},time_units='s',time_origin='physical_time')
    recipe['b'].update(source_ref='Bvector',units='kN',frame='rotated',time_units='s',time_origin='physical_time',
        sampling={'mode':'linear','bracket':[0.,2.],'max_gap':2.})
    comparisons=[]
    def apply(draft,title):
        obj=workspace.edit_comparison(draft=draft,title=title)
        preview=workspace.validate(object_ref=obj['id'])
        rows=workspace.sample(object_ref=obj['id'],preview=True,limit=1000)['rows']
        assert len(rows)==5 and builtins.all(row['valid'] and abs(row['delta'])<1e-10 for row in rows),rows
        workspace.apply(object_ref=obj['id'],show=True)
        comparisons.append({'object_ref':obj['id'],'rows':rows,'field_transfer':preview['summary']['field_transfer'],
                            'recipe':draft,'summary':preview['summary']})
        return obj
    vector_obj=apply(recipe,'다른 메시의 힘 비교')
    tensor_recipe=deepcopy(recipe)
    tensor_recipe.update(target={'units':'MPa'},selection='xy',
        conservation={'mode':'check_volume_integral','absolute_tolerance':1e-12,'relative_tolerance':1e-12})
    for side in ('a','b'):
        tensor_recipe[side].update(array='stress',quantity='stress',measure='cauchy',units='MPa',
            layout={'kind':'tensor','components':['xx','yy','zz','xy','yz','xz'],'shear':'tensor','indices':'same_cartesian_basis'},
            time=None,time_units=None,time_origin=None,sampling={'mode':'exact','time':None})
    tensor_recipe['a'].update(source_ref='Atimed',time=1.,sampling={'mode':'exact','time':1.},time_units='s',time_origin='physical_time')
    tensor_recipe['b'].update(source_ref='Btensor',association='CELLS',units='Pa',projection='cell_to_point_equal_incident',
        sampling={'mode':'linear','bracket':[0.,2.],'max_gap':2.},time_units='s',time_origin='physical_time')
    apply(tensor_recipe,'셀 응력의 기저와 적분 비교')
    # Invalid new draft cannot replace the exact already applied vector result.
    applied_before=deepcopy(workspace.applied(workspace.object(vector_obj['id'])))
    bad=deepcopy(recipe);bad['b'].update(source_ref='Binvalid',units='N',frame='global',validity_masks=['quality'],
        sampling={'mode':'exact','time':None},time_units=None,time_origin=None)
    bad['a'].update(source_ref='result',sampling={'mode':'exact','time':None},time=None,time_units=None,time_origin=None)
    bad.update(clock={},alignment={'geometry_rotation':physical.IDENTITY,'response_rotation':physical.IDENTITY,
        'translation':[0,0,0],'geometry_declared':False,'response_declared':False})
    workspace.edit_comparison(draft=bad,object_ref=vector_obj['id'])
    try:workspace.validate(object_ref=vector_obj['id'])
    except ValueError as error:assert '필수 비교 영역' in str(error)
    else:raise AssertionError('Required invalid tuple was applied')
    assert workspace.applied(workspace.object(vector_obj['id']))==applied_before
    # The unweighted cell projection has a real nonzero volume-integral error.
    density=deepcopy(bad)
    density.update(coverage={'policy':'allow_partial','array':None},conservation=deepcopy(tensor_recipe['conservation']),target={'units':'1'},selection='scalar')
    for side in ('a','b'):
        density[side].update(array='density',quantity='density',measure='density',units='1',validity_masks=[],
            layout={'kind':'scalar','components':['scalar'],'scalar_semantics':'invariant'})
    # A needs a scalar to compare; use an exact point array already on A.
    density['a'].update(array='required')
    density['b'].update(source_ref='Bdensity',association='CELLS',projection='cell_to_point_equal_incident')
    obj=workspace.edit_comparison(draft=density,title='보존 오차가 있는 셀 평균')
    try:workspace.validate(object_ref=obj['id'])
    except ValueError as error:assert '적분 오차' in str(error),str(error)
    else:raise AssertionError('Nonconservative projection passed integral tolerance')
    project=owner.save_project()
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in source.iterdir()}
    receipt={'project':str(project),'comparisons':comparisons,'source_hashes':hashes,
             'solver_calls':0,'provider_calls':0,'native':'ParaView '+str(p.GetParaViewVersion()),
             'required_failure_preserved_applied':True,'nonconservative_projection_blocked':True,
             'gui':'NOT_RUN'}
    (root/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    print('PASS native vector/tensor actual VTU, time/unit/basis, different mesh/cell association, masks/integrals/save')


if __name__=='__main__':main()
