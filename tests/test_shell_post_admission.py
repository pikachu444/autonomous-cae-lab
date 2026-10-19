"""Real shell producer and Post admission, with an explicit native-reader double."""
from copy import deepcopy
from xml.etree import ElementTree as ET
from types import SimpleNamespace

import pytest

from test_desktop_post_external import native, Array, Source
from test_shell_support import model, raw_sources
from caelab.adapters.shell_fem import collect
from caelab.shell_inspection import load


@pytest.fixture
def produced(tmp_path):
    data=model()
    mesh,_,_=raw_sources(tmp_path/'job'/'solver',data)
    artifact=collect(tmp_path/'job',data,mesh,execution_status='SUCCEEDED')['post_artifact']
    entry=tmp_path/'job'/artifact['relative']
    source=Source('XMLUnstructuredGridReader',str(entry))

    class WrittenArray(Array):
        def __init__(self,element):
            super().__init__(int(element.get('NumberOfComponents','1')))
            self.element=element
        def GetComponentName(self,index):
            return self.element.get('ComponentName'+str(index),'')

    tree=ET.parse(entry)
    for section in ('PointData','CellData','FieldData'):
        setattr(source,section,{a.get('Name'):WrittenArray(a)
                               for a in tree.findall('.//'+section+'/DataArray')})
    return entry,source,artifact['native_metadata']


def test_shell_producer_admits_meanings_and_all_raw_sources(native,produced):
    _,_,external=native
    entry,source,metadata=produced
    assert external.validate_declared_metadata(source,metadata)==metadata
    expected=load(entry,metadata['shell_inspection'])['paths']
    assert set(external.source_files(entry,metadata))=={entry,*expected}
    assert any(path.name=='shell.12d' for path in expected)
    assert any(path.name=='shell.dat' for path in expected)


@pytest.mark.parametrize('damage',['unit','recovery','location','extra'])
def test_shell_meaning_changes_are_rejected(native,produced,damage):
    _,_,external=native
    _,source,original=produced
    metadata=deepcopy(original)
    row=next(r for r in metadata['arrays'] if r['name']=='S_surface_recovered')
    if damage=='unit':row['units']='Pa'
    elif damage=='recovery':row['recovery']='exact_surface_integration_point'
    elif damage=='location':row['location']='internal_integration_point'
    else:metadata['unknown']=True
    with pytest.raises(ValueError):
        external.validate_declared_metadata(source,metadata)


def test_changed_raw_shell_source_blocks_post_reopen(native,produced):
    _,_,external=native
    entry,_,metadata=produced
    raw=entry.parent/'source'/'shell.12d'
    raw.write_bytes(raw.read_bytes()+b'changed')
    with pytest.raises(ValueError):
        external.source_files(entry,metadata)


@pytest.mark.parametrize('component',[None,'XX'])
def test_shell_legend_uses_units_and_preserves_native_component_when_unspecified(native,produced,monkeypatch,component):
    _,_,external=native
    _,source,metadata=produced
    view=external.p.CreateView('RenderView')
    bar=SimpleNamespace(Title='',ComponentTitle='Previous selection')
    updates=[]
    def update_component(transfer,display):
        updates.append(transfer)
        bar.ComponentTitle='Native selection' if component is None else component
    monkeypatch.setattr(external,'_source_metadata',lambda _:metadata)
    monkeypatch.setattr(external.p,'GetColorTransferFunction',lambda name:name,raising=False)
    monkeypatch.setattr(external.p,'GetScalarBar',lambda table,view:bar,raising=False)
    monkeypatch.setattr(external.p,'UpdateScalarBarsComponentTitle',update_component,raising=False)
    external.select_array(source,'POINTS','S_surface_recovered',component=component,view=view)
    assert bar.Title=='Surface stress (recovered) [MPa]'
    assert updates==['S_surface_recovered']
    assert bar.ComponentTitle==('Native selection' if component is None else 'XX')
