"""New optional source meanings use the existing exact-reader validator."""
from copy import deepcopy
import pytest
from test_desktop_post_external import native, Array, Source
from test_post_strain_measures import side


def metadata():
    value=side('euler_almansi')
    return {'coordinate_units':'mm','coordinate_frame':'current',
        'static':{'step':1,'increment':1,'load_parameter':1.},
        'arrays':[{'name':'strain','association':'POINTS','components':9,'units':'1','frame':'current',
            'quantity':'strain','measure':'euler_almansi','strain_role':'total',
            'reference_configuration':'undeformed specimen','strain_precision':deepcopy(value['strain_precision'])}]}


def reader():
    source=Source('XMLUnstructuredGridReader',[]);source.PointData={'strain':Array(9)};return source


def test_exact_reader_retains_optional_strain_meanings_and_bound(native):
    _,_,external=native;value=metadata();before=deepcopy(value)
    assert external.validate_declared_metadata(reader(),value)==before and value==before


@pytest.mark.parametrize('key',['strain_role','reference_configuration','strain_precision'])
def test_invalid_optional_source_declaration_is_not_admitted(native,key):
    _,_,external=native;value=metadata();value['arrays'][0][key]=7
    with pytest.raises(ValueError):external.validate_declared_metadata(reader(),value)
