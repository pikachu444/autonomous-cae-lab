"""Installed FreeCAD direction objects for explicit straight-beam FE regions."""
from copy import deepcopy
from caelab.beam_model import BeamInputError, number, AXIS_TOL
from caelab.beam_output import element_axes


def geometry_axes(owner, model):
    from femmesh import meshtools
    def native(tangent, angle):
        v = meshtools.get_beam_main_axis_m(owner.App.Vector(*tangent), angle)
        return [float(v.x), float(v.y), float(v.z)]
    axes = element_axes(model['draft'], model['axes']['tangent'],
                        {r['id'] for r in model['elements']}, native_axis=native)
    if axes is not None:
        model['element_axes'] = {str(e): value for e,value in axes.items()}


def project(owner, record):
    from .beam_native import get_object, native_type, _quantity
    import ObjectsFem
    draft = record['draft']; analysis = get_object(owner, draft['analysis_id'], 'analysis_id')
    source = get_object(owner, draft['edge']['object'], 'edge')
    for index, row in enumerate(draft.get('axis_regions', [])):
        if row['rotation_id']:
            obj = get_object(owner, row['rotation_id'], f'axis_regions.{index}')
            if obj not in analysis.Group or native_type(obj) != 'Fem::ElementRotation1D':
                raise BeamInputError(f'axis_regions.{index}', '현재 해석의 native 단면 방향 객체를 선택하세요.')
        else:
            obj = ObjectsFem.makeElementRotation1D(owner.doc, name='BeamRegionRotation')
            obj.Label = row['label']+' 단면 방향'; analysis.addObject(obj)
            row['rotation_id'] = obj.Name
        if 'CAEElementIds' not in obj.PropertiesList:
            obj.addProperty('App::PropertyIntegerList', 'CAEElementIds', 'CAE Lab 빔 영역')
        obj.CAEElementIds = sorted(row['elements'])
        obj.Rotation = f"{number(row['rotation_deg']):.16g} deg"
        obj.References = [(source, [draft['edge']['subelement']])]
        if abs(_quantity(obj,'Rotation','deg')-number(row['rotation_deg'])) > AXIS_TOL:
            raise BeamInputError(f'axis_regions.{index}.rotation_deg', 'native 방향 객체가 요청 각도를 받지 않았습니다.')
    # Protect the last applied native object set while a newer raw draft is saved.
    record['native_axis_assignments'] = deepcopy(draft.get('axis_regions', []))


def stamp(owner, record, *, values_only=False):
    from .beam_native import get_object, _quantity
    result = []
    for row in record.get('native_axis_assignments', []):
        obj = get_object(owner, row['rotation_id'], 'axis_regions')
        out = {'id': obj.Name, 'rotation_deg': _quantity(obj, 'Rotation', 'deg'),
               'elements': list(getattr(obj, 'CAEElementIds', []))}
        if not values_only:
            out['references'] = [(o.Name if o is not None else None, [ns] if isinstance(ns,str) else list(ns))
                                 for o,ns in obj.References]
        result.append(out)
    return result


def import_values(owner, draft):
    from .beam_native import get_object, _quantity
    for index,row in enumerate(draft.get('axis_regions', [])):
        obj = get_object(owner, row['rotation_id'], f'axis_regions.{index}')
        refs = [(o.Name, [ns] if isinstance(ns,str) else list(ns)) for o,ns in obj.References]
        if refs != [(draft['edge']['object'], [draft['edge']['subelement']])]:
            raise BeamInputError(f'axis_regions.{index}', 'native 단면 방향의 모서리 참조가 바뀌었습니다. 명시적으로 복구하세요.')
        row['rotation_deg'] = str(_quantity(obj, 'Rotation', 'deg'))
        row['elements'] = list(getattr(obj, 'CAEElementIds', []))
    return draft


def geometry_with_reference(owner, record, *, rebind=False):
    """Map saved FE-region IDs by the existing exact mesh correspondence only.

    The returned model uses current native IDs; this read never rewrites the
    stored draft, property object, old reference mesh or old result. A subsequent
    explicit Apply publishes the mapped selection with its current reference.
    """
    from .beam_native import geometry
    from .beam_mesh_binding import require_same_binding
    d=record['draft']
    if 'axis_regions' not in d:
        model,binding=geometry(owner,d)
        return model,binding,None
    bare=deepcopy(d);bare.pop('axis_regions')
    model,binding=geometry(owner,bare)
    if 'binding' in record and not rebind:
        correspondence=require_same_binding(record,model,binding)
    else:
        correspondence={'kind':'EXPLICIT_CURRENT_SELECTION',
                        'elements':{r['id']:r['id'] for r in model['elements']},
                        'nodes':{r['id']:r['id'] for r in model['nodes']}}
    mapped=deepcopy(d)
    for i,row in enumerate(mapped['axis_regions']):
        try:row['elements']=[correspondence['elements'][e] for e in row['elements']]
        except KeyError as exc:
            raise BeamInputError(f'axis_regions.{i}.elements','저장 참조 메시의 요소가 아닙니다. 실제 대응을 확인하고 명시적으로 다시 지정하세요.') from exc
    model['draft']=mapped;geometry_axes(owner,model)
    return model,binding,correspondence
