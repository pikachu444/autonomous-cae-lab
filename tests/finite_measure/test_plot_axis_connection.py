"""Measured plot connection over public finite Data processing, no material run."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from caelab.adapters.file_table import read_table
from caelab.data_processing import preview_recipe
from caelab.finite_measure_input import mapping,recipe as processing_recipe
from caelab.finite_measure_protocol import recipe
from caelab.material_test import deformation_plot_axis
from caelab.storage import canonical_hash


@pytest.fixture
def finite_case():
    folder=Path(__file__).resolve().parents[2]/'examples/finite-measure'
    config=json.loads((folder/'train-config.json').read_text(encoding='utf-8'))
    columns=mapping(config);raw=read_table(folder/'train.csv',columns)
    source=dict(document_id='Tfinite',job_id='Jfinite',input_revision='Ifinite',input_sha256=canonical_hash(columns))
    processed=preview_recipe(raw,source,processing_recipe(config))
    assert processed['execution_status']=='SUCCEEDED'
    settings=dict(model='neo_hooke',parameters={'mu':.8,'lmbda':5.},stress_unit='MPa',time_unit='s')
    return processed,settings,recipe('finite_lambda','x',lateral='free')


def test_finite_measured_plot_validates_real_settings_and_keeps_unloading_order(finite_case):
    processed,settings,kinematics=finite_case;before=deepcopy((processed,settings,kinematics))
    axis=deformation_plot_axis(processed['responses']['finite_sigma'],processed,kinematics,settings=settings)
    assert axis=={'name':'측정 신장비','unit':'1','values':[1.,1.1,1.2,1.14,1.24,1.18]}
    assert (processed,settings,kinematics)==before


@pytest.mark.parametrize('invalid',[None,{'model':'linear_elastic'},{'time_unit':'ms'}])
def test_finite_measured_plot_does_not_fabricate_model_or_time_settings(finite_case,invalid):
    processed,settings,kinematics=finite_case
    actual=None if invalid is None else {**settings,**invalid}
    with pytest.raises(ValueError):
        deformation_plot_axis(processed['responses']['finite_sigma'],processed,kinematics,settings=actual)


def test_legacy_three_argument_plot_still_joins_exact_rows():
    driver=dict(kind='series',unit='1',measure='engineering_strain',component='xx',frame='material_cartesian',
        location='material_point',reduction='none',source_rows=[4,5,6],
        axes=[dict(name='time',unit='s',values=[0,1,2])],value=[0.,.2,.1])
    imported={'execution_status':'SUCCEEDED','responses':{'driver':driver}}
    observed=dict(axes=[dict(name='time',unit='s',values=[0,2])],source_rows=[4,6],value=[0.,20.])
    kinematics=dict(channel='driver',kind='engineering_strain',lateral_22=1,lateral_33=1)
    assert deformation_plot_axis(observed,imported,kinematics)=={'name':'측정 변형률','unit':'1','values':[0.,.1]}
