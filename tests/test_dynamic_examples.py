"""Example construction/policy tests; no installed FreeCAD or real solver."""
from copy import deepcopy
import pytest
from test_dynamic_support import dynamic_model,snapshot
from examples.dynamic.verify_restart import prefix_snapshot,validate_policy,verify,OUTPUT_TOLERANCES,SAVED_TOLERANCES
from caelab.adapters.contact_fem import validate_snapshot


def policy():
    return {'absolute':{k:0. for k in OUTPUT_TOLERANCES},'relative':0.,'time':0.,
            'saved_arrays':{k:0. for k in SAVED_TOLERANCES},'saved_relative':0.,'saved_time':0.}


def test_prefix_uses_existing_snapshot_format_preserving_original(tmp_path):
    model=dynamic_model(two=True);source=snapshot(model,tmp_path/'source');original=source.read_bytes()
    new=prefix_snapshot(source,model['analysis_steps']['steps'][:1],tmp_path/'new')
    manifest,frozen,_,_=validate_snapshot(new)
    assert manifest['kind']=='freecad-contact-frozen'
    assert len(frozen['analysis_steps']['steps'])==1
    assert source.read_bytes()==original
    assert (new.parent/'editable.FCStd').read_bytes()==(source.parent/'editable.FCStd').read_bytes()


@pytest.mark.parametrize('key,value',[('relative',None),('time',float('nan')),('saved_time',True),('absolute',{}),('saved_arrays',{})])
def test_invalid_policy_blocks_before_any_attempt(tmp_path,key,value):
    model=dynamic_model(two=True);source=snapshot(model,tmp_path/'source')
    p=policy();p[key]=value
    with pytest.raises(ValueError):verify(source,tmp_path/'attempts',p)
    assert not (tmp_path/'attempts').exists()


def test_predeclared_zero_policy_is_valid_for_exact_protocol_testing():
    validate_policy(policy(),dynamic_model(two=True))
