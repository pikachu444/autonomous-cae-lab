"""Trusted Domain symmetry ports preserve frozen assignment boundaries."""
from copy import deepcopy

import pytest

from caelab.model_parameters import _validated_inputs, _locations, expected_settings, expected_declaration


def descriptor():
    return {'id':'symmetric_coupling','label':'Symmetric coupling','unit':'1','value':0.2,
            'lower':-1.0,'upper':1.0,'settings_path':['R',0,1],
            'settings_mirrors':[['R',1,0]],'declaration_paths':[['operator','R',0,1],['operator','R',1,0]]}


def test_both_settings_and_declared_coefficients_change_same_symmetric_value():
    settings={'R':[[1.0,0.2],[0.2,2.0]],'untouched':{'value':4}};model={'operator':{'R':deepcopy(settings['R'])}}
    original=deepcopy(settings);d=_validated_inputs([descriptor()]);_locations(d,settings,model)
    bound=expected_settings(settings,d,{'symmetric_coupling':-0.3})
    declared=expected_declaration(model,d,{'symmetric_coupling':-0.3})
    assert bound['R']==declared['operator']['R']==[[1.0,-0.3],[-0.3,2.0]]
    assert bound['untouched']==original['untouched'] and settings==original


@pytest.mark.parametrize('mirrors',[[],{},[['R',0,1]],[['R',0]],[[True]],[['R',1,0],['R',1,0]]])
def test_empty_wrong_typed_or_overlapping_trusted_ports_refuse(mirrors):
    d=descriptor();d['settings_mirrors']=mirrors
    with pytest.raises(ValueError):_validated_inputs([d])


def test_mirror_value_cannot_hide_nonsymmetric_baseline_or_change_another_input():
    d=descriptor();settings={'R':[[1.0,0.2],[0.4,2.0]]};model={'operator':{'R':[[1.0,0.2],[0.2,2.0]]}}
    with pytest.raises(ValueError):_locations(_validated_inputs([d]),settings,model)
    other=descriptor();other['id']='other';other.pop('settings_mirrors');other['settings_path']=['R',1,0];other['declaration_paths']=[['different']]
    with pytest.raises(ValueError):_validated_inputs([d,other])


def test_wrong_side_effect_cannot_be_represented_as_a_trusted_mirror():
    from plugins.pde_coupled.reference import selected_settings,describe_inputs,bind_inputs
    from caelab.model_parameters import expected_settings
    settings=selected_settings();settings['problem']['weak_form']['reaction']=[[1.0,0.0],[0.0,1.0]];d=describe_inputs(settings)
    for coupling in (-0.2,0.2):
        assigned={'reaction_01':coupling}
        bound=bind_inputs(settings,assigned)
        assert bound==expected_settings(settings,d,assigned)
        assert bound['problem']['weak_form']['reaction'][0][1]==bound['problem']['weak_form']['reaction'][1][0]==coupling
