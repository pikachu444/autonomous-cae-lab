"""PUBLIC SYNTHETIC fixture. Scripted receipt/PNG, NOT a native capture or solver result."""
import hashlib
import json
from pathlib import Path
import struct
import zlib
from copy import deepcopy

from caelab.post_observation import file_pin
from caelab.report_image import FORMAT, make_origin, source_records, retained_analyses
from caelab.storage import canonical_hash
from caelab.report_image_axis import saved_axis_context


def png_bytes(width=4, height=3, pixel=(60, 90, 120)):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    scanlines = b''.join(b'\0' + bytes(pixel) * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(scanlines)) + chunk(b'IEND', b''))


def fixture(root, *, command_id='Ccapture', pixel=(60, 90, 120)):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    original = root / '원 자료.vtu'; original.write_text('<PUBLIC_SYNTHETIC_INPUT/>')
    result = root / 'saved' / '결과.vtu'; result.parent.mkdir()
    result.write_text('<PUBLIC_SYNTHETIC_RESULT_NOT_NATIVE/>')
    state = result.parent / 'analysis.pvsm'; state.write_text('<PUBLIC_SYNTHETIC_STATE/>')
    metadata = {'arrays': [{'name': 'stress', 'association': 'POINTS', 'units': 'MPa'}],
                'time': {'unit': 's', 'semantics': 'physical_time'}}
    source = {'entry_path': str(original), 'source_pins': [file_pin(original)],
              'native_metadata': metadata, 'native_metadata_sha256': canonical_hash(metadata),
              'input_id': 'Ipublic', 'label': '공개 합성 계약 fixture'}
    source['source_revision'] = canonical_hash({'format': '.vtu', 'files': [
        {'relative': original.name, 'sha256': source['source_pins'][0]['sha256'],
         'bytes': source['source_pins'][0]['bytes']}]})
    graph = {'nodes': [{'label': 'filter', 'type': 'Clip', 'properties': {'Value': 0.0}}],
             'output_label': 'filter'}
    graph['sha256'] = canonical_hash(graph)
    record = {'id': 'Rresult', 'recipe': {'source_ref': 'Sinput', 'filter': 'Clip'},
        'graph': graph, 'bindings': {'Sinput': {'revision': source['source_revision'],
          'metadata': source['native_metadata_sha256']}},
        'view_name': 'RenderView1', 'result_file': str(result), 'result_files': [file_pin(result)],
        'result_sha256': file_pin(result)['sha256'], 'source_name': 'saved-filter',
        'summary': {'execution_status': 'UNKNOWN', 'declarations': deepcopy(metadata)}}
    obj = {'id': 'Fresult', 'kind': 'filter', 'history': [record], 'position': 0,
           'label': '공개 합성 자료 (실제 native 아님)'}
    project = {'document_id': 'Dpost', 'project_root': str(root), 'workspace_file': state.name,
        'workspace_sha256': file_pin(state)['sha256'], 'sources': {'Sinput': source},
        'analysis': {'objects': {'Fresult': obj}}}
    manifest = result.parent / 'project.json'
    manifest.write_text(json.dumps(project, ensure_ascii=False), encoding='utf-8')
    origin, _, _, _ = make_origin(file_pin(manifest), 'Dpost', 'Snative', 123,
                                  'Fresult', 'Rresult')
    export = root / 'exports' / (command_id + '.png'); export.parent.mkdir()
    export.write_bytes(png_bytes(pixel=pixel))
    scene = {'view_type': 'RenderView', 'view_name': 'RenderView1',
        'camera': {'CameraPosition': [1., 2., 3.]}, 'view': {'ViewTime': .25},
        'representation': {'Representation': 'Surface', 'MapScalars': 1,
                           'InterpolateScalarsBeforeMapping': 1, 'Opacity': 1.0}, 'lookup_table': {}, 'legend': [],
        'field': {'name': 'stress', 'association': 'POINTS', 'components': 1,
                  'component': {'mode': 'SCALAR', 'index': None, 'name': None},
                  'unit': 'MPa', 'unit_status': 'DECLARED'},
        'clock': {'value': .25, 'view_time': .25, 'animation_time': .25,
                  'status': 'DATA_TIME', 'unit': 's', 'semantics': 'physical_time'},
        'graph': graph, 'warp': [], 'generations': {'content': 4, 'view': 3},
        'axis_context': saved_axis_context(project, obj, record),
        'block_coloring': {'profile': 'ParaView-SM-single-field-blocks/1', 'version': [6, 2, 0],
            'status': 'SINGLE_GLOBAL_FIELD', 'policy': 'ALL_CONFIGURED_SELECTORS_EQUIVALENT',
            'properties': {name: [] for name in ('BlockColorArrayNames', 'BlockColors',
                'BlockMapScalars', 'BlockInterpolateScalarsBeforeMappings', 'BlockOpacities', 'BlockUseSeparateColorMaps')},
            'global_lut_id': 'lut', 'block_lut_ids': []}}
    snapshot = {'format': FORMAT, 'capture_status': 'SUCCEEDED', 'origin': origin,
        'scene': scene, 'recipe': deepcopy(record['recipe']), 'sources': source_records(project, obj, record),
        'lineage': retained_analyses(project, obj, record),
        'result_files': record['result_files'], 'result_status': {'execution_status': 'UNKNOWN',
            'qualification': 'UNKNOWN', 'checks': [], 'failure_reason': None},
        'data_match': {'status': 'EXACT', 'sha256': 'a'*64},
        'captured_utc': '2026-10-15T00:00:00Z', 'engineering_release': 'NOT_RELEASED',
        'png': file_pin(export), 'pixel_size': [4, 3]}
    receipt = {'file': str(export), 'sha256': file_pin(export)['sha256'],
               'revision': 'Rresult', 'analysis_saved': False, 'report_snapshot': snapshot}
    command = {'command_id': command_id, 'document_id': 'Dpost', 'session_id': 'Snative',
        'operation': 'post.export', 'arguments': {'object_ref': 'Fresult', 'format': 'png', 'report_snapshot': True},
        'state': 'SUCCEEDED', 'outcome': {'state': 'SUCCEEDED', 'result': {
            'command_id': command_id, 'document_id': 'Dpost', 'session_id': 'Snative',
            'status': 'COMPLETED', 'result': receipt}}}
    return {'command': command, 'snapshot': snapshot, 'receipt': receipt, 'project': project,
            'manifest': manifest, 'object': obj, 'record': record, 'png': export,
            'source': original, 'result': result, 'state': state}


def refresh_snapshot(f):
    """Re-pin a deliberately changed public fixture. Never use in negative tamper tests."""
    f['manifest'].write_text(json.dumps(f['project'], ensure_ascii=False), encoding='utf-8')
    origin, project, obj, record = make_origin(file_pin(f['manifest']), 'Dpost', 'Snative', 123,
                                               'Fresult', 'Rresult')
    snapshot = f['snapshot']
    snapshot.update(origin=origin, recipe=deepcopy(record['recipe']),
                    lineage=retained_analyses(project, obj, record),
                    sources=source_records(project, obj, record), result_files=deepcopy(record['result_files']))
    snapshot['scene']['axis_context'] = saved_axis_context(project, obj, record)
    return snapshot
