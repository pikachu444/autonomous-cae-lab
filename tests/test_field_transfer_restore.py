"""PVSM-only recovery checks with existing native proxy doubles; no native run."""
import hashlib
import sys
from types import ModuleType
import xml.etree.ElementTree as ET

import pytest
from test_post_r3_repairs import post_modules, state_xml


@pytest.fixture(autouse=True)
def numpy_conversion_not_used(monkeypatch):
    support = ModuleType('paraview.numpy_support')
    support.vtk_to_numpy = lambda value: value
    monkeypatch.setitem(sys.modules, 'paraview.numpy_support', support)


def saved_case(tmp_path):
    original = state_xml(tmp_path / 'original.pvsm')
    tree = ET.parse(original); server = tree.getroot().find('ServerManagerState')
    # This visible representation, camera and layout must keep their exact IDs.
    rep = server.find("Proxy[@id='7']/Property[@name='Input']/Proxy")
    rep.set('value', '5')
    camera = ET.SubElement(server.find("Proxy[@id='8']"), 'Property', name='CameraPosition')
    ET.SubElement(camera, 'Element', index='0', value='3.25')
    tree.write(original, encoding='utf-8', xml_declaration=True)
    data = tmp_path / 'result.vtu'; data.write_bytes(b'controlled saved bytes')
    record = {'id': 'Vcomparison', 'summary': {'comparison_version': 2},
              'source_name': 'comparison', 'proxy_names': ['missing clip', 'comparison'],
              'result_file': str(data), 'result_files': [{'path': str(data), 'bytes': data.stat().st_size,
                  'sha256': hashlib.sha256(data.read_bytes()).hexdigest()}]}
    return original, data, {'analysis': {'objects': {'C': {'history': [record]}}}}


@pytest.mark.parametrize('missing_b', [False, True])
def test_pinned_field_replaces_executable_output_keeps_view_and_healthy_source(post_modules, tmp_path, missing_b):
    original, data, document = saved_case(tmp_path)
    before = original.read_bytes()
    output = tmp_path / 'copy' / 'read.pvsm'
    result = post_modules.source_repair.partial_state(original, document,
        [{'reader_name': 'B'}] if missing_b else [], output, retain_applied=True)
    assert result['retained_source_names'] == ['comparison']
    server = ET.parse(output).getroot().find('ServerManagerState')
    field = server.find("Proxy[@id='5']")
    assert field.get('type') == 'XMLUnstructuredGridReader'
    assert field.find("Property[@name='FileName']/Element").get('value') == str(data.resolve())
    assert field.find("Property[@name='Input']") is None
    assert server.find("Proxy[@id='4']") is None
    assert server.find("Proxy[@id='1']") is not None
    assert server.find("Proxy[@id='3']") is not None
    assert server.find("Proxy[@id='7']/Property[@name='Input']/Proxy").get('value') == '5'
    assert server.find("Proxy[@id='8']/Property[@name='CameraPosition']/Element").get('value') == '3.25'
    assert server.find("Proxy[@id='9']") is not None
    assert original.read_bytes() == before


def test_changed_retained_bytes_cannot_replace_graph(post_modules, tmp_path):
    original, data, document = saved_case(tmp_path)
    data.write_bytes(b'changed')
    output = tmp_path / 'not-published.pvsm'
    with pytest.raises(ValueError, match='missing or changed'):
        post_modules.source_repair.partial_state(original, document, [], output, retain_applied=True)
    assert not output.exists()
