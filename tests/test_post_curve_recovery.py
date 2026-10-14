"""Saved curve dependency recovery with native proxy doubles, no solver."""
from copy import deepcopy
import hashlib
import json
import xml.etree.ElementTree as ET

from test_post_r3_repairs import post_modules, state_xml

import sys
from types import ModuleType
import pytest


@pytest.fixture(autouse=True)
def native_numpy_conversion_double(monkeypatch):
    # This module checks PVSM names/bindings only. It performs no VTK conversion.
    support = ModuleType('paraview.numpy_support')
    support.vtk_to_numpy = lambda value:value
    monkeypatch.setitem(sys.modules, 'paraview.numpy_support', support)


def digest(record):
    value={k:record[k] for k in ('id','recipe','graph','bindings')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),
        ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()


def test_partial_restore_removes_only_pinned_missing_curve_branches(post_modules, tmp_path):
    source=state_xml(tmp_path/'original.pvsm')
    tree=ET.parse(source);server=tree.getroot().find('ServerManagerState')
    registrations=server.find("ProxyCollection[@name='sources']")
    for number,name in ((20,'direct curve'),(21,'old measurement curve'),(22,'healthy curve'),
                        (23,'previous retained reader')):
        ET.SubElement(server,'Proxy',id=str(number),group='sources',type='XMLTableReader')
        ET.SubElement(registrations,'Item',id=str(number),name=name)
    tree.write(source,encoding='utf-8',xml_declaration=True)
    old={'id':'Vold','recipe':{'source_ref':'Smissing'},'graph':{},
         'bindings':{'Smissing':{'revision':'missing-bytes'}}}
    new={'id':'Vnew','recipe':{'source_ref':'Sgood'},'graph':{},
         'bindings':{'Sgood':{'revision':'good-bytes'}}}
    def curve(identifier,name,ref,binding,dependency=None):
        return {'id':identifier,'source_name':name,'proxy_names':[name],
            'recipe':{'version':3,'a':{'source_ref':ref},'b':{'source_ref':'Sgood'}},
            'graph':{},'bindings':{ref:{'revision':binding},'Sgood':{'revision':'good-bytes'}},
            'dependencies':{ref:dependency} if dependency else {},
            'summary':{'comparison_version':3}}
    direct=curve('Vdirect','direct curve','Smissing','missing-bytes')
    past=curve('Vpast','old measurement curve','Mmeasured',digest(old),'Vold')
    healthy=curve('Vhealthy','healthy curve','Mmeasured',digest(new),'Vnew')
    direct['retained_source_name']='previous retained reader'
    document={'sources':{'Sgood':{'reader_name':'A'},'Smissing':{'reader_name':'B'}},
        'analysis':{'objects':{
            'Mmeasured':{'kind':'measurement','position':1,'history':[old,new]},
            'C':{'kind':'comparison','position':2,'history':[direct,past,healthy]}}}}
    before=source.read_bytes()
    output=tmp_path/'partial.pvsm'
    result=post_modules.source_repair.partial_state(source,document,
        [{'reader_name':'B','source_ref':'Smissing'}],output)
    assert {'direct curve','old measurement curve'} <= set(result['removed_source_names'])
    assert {'A','healthy clip','healthy curve','previous retained reader'} <= set(result['healthy_source_names'])
    assert source.read_bytes()==before
    # With the exact input back, semantic removal no longer chooses the current
    # measurement cursor or removes the prior result.
    assert not post_modules.source_repair._unavailable_curve_names(document,[])


def test_legacy_binding_resolves_exact_revision_without_current_cursor(post_modules):
    old={'id':'Vold','recipe':{'source_ref':'Smissing'},'graph':{},
         'bindings':{'Smissing':{'revision':'missing-bytes'}}}
    new={'id':'Vnew','recipe':{'source_ref':'Sgood'},'graph':{},
         'bindings':{'Sgood':{'revision':'good-bytes'}}}
    result={'id':'Vcurve','source_name':'curve','proxy_names':['curve'],
        'recipe':{'version':3},'graph':{},'summary':{'comparison_version':3},
        'bindings':{'M':{'revision':digest(old)}}}
    document={'sources':{'Smissing':{},'Sgood':{}},'analysis':{'objects':{
        'M':{'position':1,'history':[old,new]},'C':{'history':[result]}}}}
    assert post_modules.source_repair._unavailable_curve_names(document,
        [{'source_ref':'Smissing'}]) == {'curve'}
    result['bindings']['M']['revision']=digest(new)
    assert not post_modules.source_repair._unavailable_curve_names(document,
        [{'source_ref':'Smissing'}])
