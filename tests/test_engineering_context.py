"""Independent evidence reads do not register jobs or run model preparation."""
from copy import deepcopy

import pytest

from caelab.engineering_context import read_context


def test_independent_input_and_actual_solver_logs_are_read_without_static_family_gate(tmp_path):
    source = tmp_path / 'user.inp'
    source.write_text('*NODE\n1,0,0,0\n*ELEMENT,TYPE=USER99\n7,1\n*MATERIAL,NAME=Steel\n'
        '*ELASTIC\n210000,.3\n*PLASTIC\n300,0\n*STEP,NLGEOM\n*DYNAMIC\n.01,1\n'
        '*DLOAD\nBody,GRAV,9810,0,0,-1\n*BOUNDARY\nHeld,1,3\n*FRICTION\n.2\n*END STEP\n')
    (tmp_path / 'user.sta').write_text('actual increment not converged\n')
    (tmp_path / 'user.dat').write_text('actual contact force\n')
    context = read_context(object(), selection={'path': str(source), 'scope': {'step': 1}})
    assert context['model']['model_state'] == 'calculation_input'
    assert context['model']['mesh']['element_types'] == {'USER99': {'connectivity_records': 1}}
    assert context['model']['materials'][0]['options'] == {'NAME': 'Steel'}
    assert context['model']['loads'][0]['rows'] == ['Body,GRAV,9810,0,0,-1']
    assert context['model']['units'] is None and context['state'] is None
    assert {row['label'] for row in context['logs']} == {'user.sta', 'user.dat'}
    assert 'job_id' not in context


def test_live_model_and_post_selection_are_preserved_separately_from_disk(tmp_path):
    source = tmp_path / 'model.FCStd'; source.write_bytes(b'current saved document')
    snapshot = {'kind': 'freecad-model', 'materials': [{'name': 'Current material'}], 'mesh_quality': {'status': 'NOT_PROVIDED'}}
    selection = {'path': str(source), 'scope': {'objects': ['Pressure'], 'faces': ['Face4']},
        'model_snapshot': snapshot, 'result_metadata': {'arrays': [{'name': 'STRESS', 'units': None}], 'time': .5}}
    before = deepcopy(selection)
    context = read_context(object(), selection=selection)
    assert context['model']['model_state'] == 'current_editing_model'
    assert context['result']['time'] == .5 and context['source']['scope']['faces'] == ['Face4']
    assert selection == before and source.read_bytes() == b'current saved document'
    with pytest.raises(ValueError, match='job or independent'):
        read_context(object(), 'Jone', selection=selection)


def test_multiple_selected_files_retain_separate_source_identity(tmp_path):
    files = [tmp_path / name for name in ('one.log', 'two.log')]
    for file in files: file.write_text(file.name)
    context = read_context(object(), selection={'sources': [{'path': str(file)} for file in files]})
    assert [row['source']['path'] for row in context['sources']] == list(map(str, files))


def test_selected_companions_share_log_and_convergence_observations(tmp_path):
    source=tmp_path/'selected.inp'
    source.write_text('*NODE\n1,0,0,0\n*STEP\n*STATIC\n*END STEP\n')
    log=source.with_suffix('.cvg');log.write_bytes(b'actual convergence text\n')
    output=source.with_suffix('.dat');output.write_bytes(b'actual result log\n')
    selection={'sources':[{'path':str(path),'scope':{'selected_kind':path.suffix}}
                          for path in (source,log,output)]}
    context=read_context(object(),selection=selection)
    assert len(context['logs'])==2 and len(context['convergence'])==1
    assert context['convergence'][0]['path']==str(log)
    for selected,path in zip(context['sources'],(source,log,output)):
        assert selected['source']=={'path':str(path),'scope':{'selected_kind':path.suffix}}
        assert selected['log_paths']==[str(log),str(output)]
        assert selected['convergence_path']==str(log)
        assert 'logs' not in selected and 'convergence' not in selected
    assert context['sources'][0]['model']['model_state']=='calculation_input'
    assert {row['text'] for row in context['logs']}=={'actual convergence text\n','actual result log\n'}


def test_unsaved_native_model_can_be_read_without_a_file():
    context = read_context(object(), selection={'model_snapshot': {'materials': [{'name': 'Steel'}]},
                                              'scope': {'objects': ['Pressure']}})
    assert context['source']['path'] is None
    assert context['model']['model_state'] == 'current_editing_model'


def test_saved_freecad_reader_uses_configured_native_installation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from caelab import engineering_context
    source = tmp_path / 'model.FCStd'; source.write_bytes(b'saved native document')
    calls = []
    monkeypatch.setattr(engineering_context, '_freecad_summary',
        lambda path, **kwargs: calls.append((path, kwargs)) or {'kind': 'freecad-model'})
    workbench = SimpleNamespace(config={'desktop': {'freecad_executable': 'C:/installed/FreeCAD.exe'}})
    result = read_context(workbench, selection={'sources': [{'path': str(source)}]})
    assert calls == [(source, {'freecad_executable': 'C:/installed/FreeCAD.exe'})]
    assert result['sources'][0]['model']['model_state'] == 'saved_model'


def test_native_post_headers_preserve_arrays_and_raw_output_coordinate(tmp_path):
    frame = tmp_path / 'frame.vtu'
    frame.write_text('<VTKFile><UnstructuredGrid><Piece NumberOfPoints="2" NumberOfCells="1">'
        '<PointData><DataArray Name="S" NumberOfComponents="2" ComponentName0="SXX" ComponentName1="SYY" '
        'format="ascii">1 2 3 4</DataArray></PointData></Piece></UnstructuredGrid></VTKFile>')
    collection = tmp_path / 'result.pvd'
    collection.write_text('<VTKFile type="Collection"><Collection><DataSet timestep=".5" file="frame.vtu"/>'
                          '</Collection></VTKFile>')
    result = read_context(object(), selection={'path': str(collection)})['result']
    assert result['output_values'] == [.5] and result['time_semantics'] is None
    assert result['frames'][0]['pieces'][0]['arrays'][0]['component_names'] == ['SXX', 'SYY']
    assert result['frames'][0]['pieces'][0]['arrays'][0]['units'] is None
