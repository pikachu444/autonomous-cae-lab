"""Bind an exact retained history selection to the existing Study source."""
from copy import deepcopy

from .impact_responses import select_history
from .research_operations import RESULT_REF_KEYS, validate_result_reference
from .storage import canonical_hash

SCHEMA='caelab.impact-history-selection/1'


def capsule(packet):
    return {'schema':SCHEMA,'selection':deepcopy(packet['selection']),
            'selection_sha256':packet['selection_sha256']}


def replay(source, result, selection):
    """Recompute from the immutable owner, rejecting stale masks and meaning."""
    source=validate_result_reference({key:source[key] for key in RESULT_REF_KEYS})
    if (not isinstance(selection,dict) or set(selection)!={'schema','selection','selection_sha256'}
            or selection['schema']!=SCHEMA or not isinstance(selection['selection'],dict)):
        raise ValueError('정확한 충격 이력 선택을 다시 확인하세요.')
    if canonical_hash(result)!=source['result_sha256']:
        raise ValueError('선택한 원 결과의 내용이 바뀌었습니다.')
    fresh=select_history({'source':source,'result':result},selection['selection']['request'])
    if capsule(fresh)!=selection:
        raise ValueError('선택한 시각·원행·마스크·물리 의미가 바뀌었습니다. 다시 선택하세요.')
    return fresh


def selected_result(source, result, selection):
    packet=replay(source,result,selection)
    actual=deepcopy(result)
    actual['responses']={packet['source']['response']:packet['response']}
    actual.setdefault('diagnostics',{})['history_selection']=deepcopy(selection)
    return actual


def snapshot(workbench, identifier, job_id):
    """Read a saved owner and its pinned initial mass, without a native reader."""
    import json
    from pathlib import PurePosixPath
    from .dynamic_result_store import admit_pin
    from .impact_native_io import read_bytes
    from .research_operations import result_reference
    from .storage import check_id
    identifier,job_id=check_id(identifier),check_id(job_id)
    owner=workbench._document_owner(identifier)
    if owner is not workbench.simulation_documents:
        raise ValueError('보존된 충격 해석 결과를 선택하세요.')
    with owner._lock(identifier):
        document=owner.read(identifier)
        result=workbench.document_result(identifier,job_id)
        source=result_reference(document,job_id,result)
        value={'source':source,'result':result}
        run=next(row for row in document['runs'] if row['job_id']==job_id)
        pin=result.get('retained_native',{}).get('input_artifacts',{}).get('initial_mass_properties.json')
        if pin is not None:
            directory=result.get('native_result',{}).get('directory')
            if (not isinstance(directory,str) or PurePosixPath(directory)!=PurePosixPath('calculation')
                    or pin.get('relative')!='initial_mass_properties.json'):
                raise ValueError('보존된 초기 질량의 원 입력 위치가 다릅니다.')
            folder=owner._folder(identifier)/'revisions'/check_id(run['retained_result']['revision'])/'results'/job_id/'calculation'
            path=admit_pin(folder,pin)
            value.update(initial_mass_properties=json.loads(read_bytes(path,expected=pin,maximum=1024*1024)),
                         initial_mass_source=deepcopy(pin))
        return value
