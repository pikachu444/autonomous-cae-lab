"""Explicit immutable preparation using installed native FreeCAD writer pieces."""
from io import StringIO
import json
from pathlib import Path
import shutil
import threading
from types import SimpleNamespace
import uuid

from caelab.shell_model import digest
from caelab.adapters.shell_deck import (KIND, MESH_KIND, build, native_mesh,
    sha, validate_snapshot, read_bytes)


def _native_fragments(editor, draft, prepared):
    from femsolver.calculix.write_femelement_geometry import write_femelement_geometry
    from femsolver.calculix.write_constraint_pressure import write_meshdata_constraint
    from femsolver.calculix.write_femelement_material import write_femelement_material
    geometry=editor._object(draft['geometry_id'])
    material=editor._object(draft['material_id'])
    pressure=editor._object(draft['pressure_id'])
    solver=editor._object(draft['solver_id'])
    member=SimpleNamespace(mats_linear=[{'Object':material}],mats_nonlinear=[],
                           cons_centrif=[],cons_selfweight=[])
    writer=SimpleNamespace(solver_obj=solver,analysis_type='static',member=member,
        mat_geo_sets=[{'ccx_elset':[e], 'ccx_elset_name':'ES'+str(e),
                      'mat_obj_name':material.Name,'shellthickness_obj':geometry}
                     for e in prepared['elements']])
    section=StringIO(); write_femelement_geometry(section,writer)
    elastic=StringIO(); write_femelement_material(elastic,writer)
    load=StringIO()
    # The native writer accepts resolved whole-shell element lists. Face-name
    # comments are diagnostic only; no fictitious geometric face is resolved.
    mesh=editor._object(draft['mesh_id'])
    load_record={'PressureFaces':[((mesh,('SelectedS8',)), sorted(prepared['elements']),False)]}
    write_meshdata_constraint(load,load_record,pressure,writer)
    return section.getvalue(),load.getvalue(),elastic.getvalue()


def freeze(editor, analysis_id):
    """Called by the existing native owner, synchronously on its GUI thread.

    This prepares/registerable bytes only; it never starts CalculiX. Execution
    belongs to the existing workbench JobManager via structure.calculix.shell.
    """
    from caelab.storage import save_json
    from .freeze_analysis import _serialized_coordinate_close, require_ready_model
    owner=editor.owner
    owner.assert_thread()
    if threading.current_thread() is not threading.main_thread():
        raise ValueError('Shell preparation requires the native main thread')
    if list(owner.App.Version())[:3] != ['1','1','4']:
        raise ValueError('First shell native writer profile requires FreeCAD 1.1.4')
    owner._idle()
    require_ready_model(owner.doc, owner=owner)
    editor.effective(analysis_id)
    # Same native project save/copy ownership as bridge pre.freeze.
    editor.clear_preview()
    saved=owner.project.save()
    record,prepared,fixed=editor.effective(analysis_id)
    draft=record['draft']; before=editor._native_state(draft)
    generation=owner.generation
    doc=owner.doc; filename=doc.FileName
    if doc.isTouched() or any(set(o.State)&{'Touched','Invalid','Error','Recompute'} for o in doc.Objects):
        raise ValueError('Recompute and finish native edits before preparing shell input')
    original=Path(filename) if filename else None
    original_hash=sha(original) if original is not None and original.is_file() else None
    folder=Path(owner.export_root).resolve()/owner.document_id/('F'+uuid.uuid4().hex)
    folder.mkdir(parents=True,exist_ok=False)
    manifest_path=folder/'snapshot.json'
    try:
        doc.saveCopy(str(folder/'editable.FCStd'))
        mesh=editor._object(draft['mesh_id'])
        mesh.FemMesh.writeABAQUS(str(folder/'native_mesh.inp'),1,False,
            volVariant='standard',faceVariant='shell',edgeVariant='beam')
        nodes,elements=native_mesh(read_bytes(folder/'native_mesh.inp').decode('ascii'))
        _,native_nodes,native_elements=editor._mesh(draft)
        if set(nodes)!=set(native_nodes) or elements!=native_elements or any(
                not all(_serialized_coordinate_close(a,b) for a,b in zip(native_nodes[n],xyz))
                for n,xyz in nodes.items()):
            raise ValueError('Native writeABAQUS coordinates/connectivity differ from the live shell mesh')
        sections,pressure,material=_native_fragments(editor,draft,prepared)
        model={'schema_version':'1','kind':MESH_KIND,
               'units':{'position':'mm','stress':'MPa','force':'N'},
               'source_nodes':{str(n):xyz for n,xyz in nodes.items()},
               'source_elements':{str(e):c for e,c in elements.items()},
               'draft':draft,'applied':record['applied'],'fixed_nodes':fixed,
               'material_name':draft['material_id'], 'native_sections':sections,
               'native_pressure':pressure,'native_material':material,
               'direction_rule':'S8 native order or (1,4,3,2,8,7,6,5); positive pressure opposes positive normal',
               'output_contract':{'family':'S8','expanded':'C3D20','position_map':'native_12d',
                    'nodal_surface_recovery':'native_extrapolated_averaged',
                    'exact_surface_integration_stress':'UNAVAILABLE',
                    'internal_points':27,'coordinates':'global_mm',
                    'stress':'global_Cauchy_MPa','strain':'global_total_tensor'}}
        text,_=build(model)
        (folder/'shell.inp').write_bytes(text.encode('ascii'))
        save_json(folder/'mesh.json',model)
        if (editor._native_state(draft)!=before or doc.FileName!=filename or owner.generation!=generation
                or doc.isTouched() or original_hash and sha(original)!=original_hash):
            raise ValueError('Live native model changed during shell preparation; partial files retained')
        require_ready_model(doc, owner=owner)
        editable=saved.get('retained_project')
        if editable:
            shutil.copyfile(editable,folder/'editable.caepre')
        members=[{'relative':p.name,'bytes':p.stat().st_size,'sha256':sha(p)}
                 for p in sorted(folder.iterdir()) if p.is_file()]
        manifest={'schema_version':'1','kind':KIND,'id':folder.name,
                  'native_version':list(owner.App.Version()),'analysis_id':analysis_id,
                  'input_file':'shell.inp','files':members,'applied_sha256':digest(record['applied']),
                  'document':{'label':doc.Label,'original_sha256':original_hash},
                  'solver_execution':'NOT_PERFORMED','qualification':'NOT_ASSESSED'}
        if editable: manifest['editable_project']='editable.caepre'
        save_json(manifest_path,manifest)
        validate_snapshot(manifest_path)
    except Exception as exc:
        # Never publish an invalid snapshot as a completed input, never remove
        # earlier runs or the current attempt's native writer output.
        if manifest_path.exists(): manifest_path.rename(folder/'snapshot.failed.json')
        save_json(folder/'preparation_failure.json',{'type':type(exc).__name__,'message':str(exc)})
        raise
    return {'snapshot_relative':manifest_path.relative_to(owner.export_root).as_posix(),
            'label':doc.Label+' / 셸 해석','backend':'structure.calculix.shell',
            'input_prepared':True,'solver_execution':'NOT_PERFORMED',
            'applied_sha256':digest(record['applied'])}
