"""Retained input curves hydrate without loading unrelated result arrays."""
from caelab.evaluation import save_evaluation,read_result


def test_exact_setup_selection_keeps_unrelated_arrays_packed(tmp_path):
    points=[[0.,0.],[1.,.005]]
    save_evaluation({'execution_status':'SUCCEEDED','responses':{},
        'executed_setup':{'program':{'curves':[{'points':points}]}},
        'diagnostics':{'unrelated_field':list(range(2000))}},tmp_path/'result')
    packed=read_result(tmp_path/'result',selection={'responses':[]})
    assert 'data_ref' in packed['executed_setup']['program']['curves'][0]['points']
    actual=read_result(tmp_path/'result',selection={'responses':[],'include_executed_setup':True})
    assert actual['executed_setup']['program']['curves'][0]['points']==points
    assert actual['diagnostics']['unrelated_field']==packed['diagnostics']['unrelated_field']
    assert 'data_ref' in actual['diagnostics']['unrelated_field']
