from copy import deepcopy
from types import SimpleNamespace as NS

from apps.desktop_pre.native_context import model_snapshot


def test_context_reads_native_fields_and_extensions_without_an_owner():
    doc = NS(Name='Model', Label='User model', FileName='model.FCStd')
    material = NS(Name='Steel', Label='Steel material', TypeId='App::MaterialObjectPython',
                  PropertiesList=['Material'], Material={'YoungsModulus': '210 GPa'}, Document=doc)
    force = NS(Name='Force', Label='User load', TypeId='Fem::ConstraintForce',
               PropertiesList=['Force', 'References'], Force=NS(Value=12., Unit='N'),
               References=[(material, ['Face1'])], Document=doc)
    mesh = NS(Name='Mesh', Label='User mesh', TypeId='Fem::FemMeshObject', PropertiesList=['FemMesh'],
              FemMesh=NS(NodeCount=4, VolumeCount=1, Volumes=[7],
                         getElementNodes=lambda key: (1, 2, 3, 4)), Document=doc)
    doc.Objects = [material, force, mesh]
    doc.getObject = lambda name: None
    before = deepcopy(material.Material)
    result = model_snapshot(doc, [force])
    assert result['model_state'] == 'current_editing_model'
    assert result['materials'][0]['properties']['Material'] == before
    assert result['conditions'][0]['properties']['Force'] == {'value': 12., 'unit': 'N'}
    assert result['mesh'][0]['elements'] == {'volumes': [{'nodes_per_element': 4, 'count': 1}]}
    assert result['selection'] == [{'object': 'Force'}]
    assert 'mesh_quality' not in result
    assert material.Material == before
