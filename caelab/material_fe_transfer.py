"""Saved Material -> exact native FEM assignment using the existing owners.

This is a value/command adapter, not a store, owner or solver coordinator. Preview
is pure; source guards are produced only by Workbench from its Material owner.
Native Apply rechecks source guards and target in its existing transaction.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
from .storage import canonical_hash, check_id, load_json, save_json
from .evaluation import file_hash
from plugins.material_point import law_native as law
from . import law_native_fe as fe
from .adapters.law_native_runtime import source_identity

OPERATIONS = ('pre.fem.law_read', 'pre.fem.law_preview', 'pre.fem.law_save',
              'pre.fem.law_apply', 'pre.fem.law_freeze')
READ_ONLY = {'pre.fem.law_read', 'pre.fem.law_preview', 'pre.fem.law_freeze'}
SCHEMA = 'saved-material-native-assignment/1'
PROPERTY = 'CAELabLawNative'


def retain_inputs(saved, folder):
    """An asset of the existing immutable Material revision, never a new store."""
    if saved.get('draft', {}).get('backend') != law.POINT:
        return
    save_json(Path(folder) / 'law-native-source.json', source_identity(text=True))


def _check_source_text(identity):
    if not isinstance(identity, dict) or identity.get('interface') != 'law-native/1':
        raise ValueError('Unsupported law source interface identity')
    for name, row in identity.get('files', {}).items():
        if not isinstance(row.get('text'), str):
            raise ValueError('Retained law source text missing: ' + name)
        if hashlib.sha256(row['text'].encode('utf-8')).hexdigest() != row.get('sha256'):
            raise ValueError('Retained law source hash mismatch: ' + name)
    if not identity.get('files'):
        raise ValueError('Empty law source identity is not an interface')


def source_snapshot(owner, reference):
    """Read exact owner revision, including provenance; no submit/build/evaluate."""
    if not isinstance(reference, dict) or set(reference) != {'document_id', 'saved_revision', 'input_sha256'}:
        raise ValueError('Select exact saved Material document/revision/input_sha256')
    identifier, revision = check_id(reference['document_id']), check_id(reference['saved_revision'])
    if not identifier.startswith('M'):
        raise ValueError('The source must be a saved Material document')
    with owner._lock(identifier):
        saved = owner._verify_revision(identifier, revision)
        if saved.get('id') != identifier or saved.get('saved_revision') != revision:
            raise ValueError('Source identity differs from its retained revision')
        if canonical_hash(saved['draft']) != reference['input_sha256']:
            raise ValueError('Source input hash mismatch')
        folder = owner._folder(identifier)
        revision_folder = folder / 'revisions' / revision
        retained = revision_folder / 'law-native-source.json'
        # Older original laws remain original; mapping carries an explicit new
        # fixed interface source, rather than pretending that it was built then.
        identity = load_json(retained) if retained.is_file() else source_identity(text=True)
        _check_source_text(identity)
        current = source_identity()
        for name, row in current['files'].items():
            if identity['files'].get(name, {}).get('sha256') != row['sha256']:
                raise ValueError('Saved law source differs from current interface; explicitly review a new revision')
        guards = []
        for p in (folder/'document.json', folder/'working.json', revision_folder/'revision.json'):
            if not p.is_file() or p.is_symlink():
                raise ValueError('Current source durability is unavailable')
            guards.append({'path':str(p.resolve()), 'sha256':file_hash(p)})
        source = {'reference':deepcopy(reference), 'input_revision':saved['input_revision'],
            'original_draft':deepcopy(saved['draft']), 'law_source':identity,
            'mapping_origin':'RETAINED_EXACT_SOURCE' if retained.is_file() else 'EXPLICIT_NEW_FIXED_INTERFACE_FOR_LEGACY_LAW',
            'saved_provenance':{k:deepcopy(v) for k,v in saved.items()
                if k not in ('_undo','_redo','draft') and ('source' in k or 'adopt' in k or 'calibr' in k or k in ('runs','comparisons'))},
            'source_guard':guards, 'build':{'kind':'FIXED_PYTHON_INTERFACE', 'execution':'NOT_REQUIRED',
                'arbitrary_source_approval':'NOT_GRANTED; original exact-source MFront authority unchanged'}}
        source['snapshot_sha256'] = canonical_hash(source)
        return source


def verify_source(source, *, live=False, current_code=False):
    if not isinstance(source, dict) or 'snapshot_sha256' not in source:
        raise ValueError('Missing saved Material source snapshot')
    value = deepcopy(source); expected = value.pop('snapshot_sha256')
    if canonical_hash(value) != expected:
        raise ValueError('Material source snapshot hash mismatch')
    if canonical_hash(source['original_draft']) != source['reference']['input_sha256']:
        raise ValueError('Frozen source coefficients/input identity mismatch')
    _check_source_text(source['law_source'])
    if live:
        guards = source.get('source_guard')
        if not isinstance(guards, list) or len(guards) != 3:
            raise ValueError('Only an owner-resolved source can be applied')
        for guard in guards:
            p=Path(guard['path'])
            if p.is_symlink() or not p.is_file() or file_hash(p) != guard['sha256']:
                raise ValueError('SOURCE_CONFLICT: source revision/working input changed after review')
    if current_code:
        current = source_identity()['files']
        if set(current) != set(source['law_source']['files']) or any(
            v['sha256'] != source['law_source']['files'][k]['sha256'] for k,v in current.items()):
            raise ValueError('INTERFACE_SOURCE_CONFLICT: review exact installed law source again')
    return deepcopy(source)


def map_to_mpa(draft):
    """Explicit identity/units transform; never replace energy/state/time model."""
    s = law.from_saved_legacy(draft)
    scale = law.STRESS_TO_MPA[s['stress_unit']]
    mapping = []
    for name, value in s['parameters'].items():
        unit=law.parameter_unit(s['model'],name,s['stress_unit'])
        factor=1. if unit in ('1','s') else scale
        s['parameters'][name]=value*factor
        mapping.append({'coefficient':name,'source_value':value,'source_unit':unit,
                        'factor':factor,'target_value':value*factor,
                        'target_unit':unit if unit in ('1','s') else 'MPa','origin':'SAVED_MATERIAL_COEFFICIENT'})
    if s['model']=='single_branch_maxwell':
        for name in ('dissipated_energy','work'):
            s['initial_state'][name] *= scale
    if 'boundary_control' in s:
        for name, values in s['boundary_control']['stress_components'].items():
            s['boundary_control']['stress_components'][name]=[v*scale for v in values]
        s['boundary_control']['solver']['atol'] *= scale
    s['stress_unit']='MPa'
    law.validate_settings(s)
    return s, mapping


def make_review(source, target, options):
    """Pure preview. Invalid literal inputs stay present in a blocked review."""
    verify_source(source)
    review={'schema':SCHEMA,'source':deepcopy(source),'target':deepcopy(target),
        'options':deepcopy(options),'status':'BLOCKED','errors':[], 'interface':None,
        'mapping':[], 'executed':False,'compiler_executed':False,'solver_executed':False,
        'qualification':{'physical_calibration':'UNKNOWN','strength':'UNKNOWN',
                         'failure':'UNKNOWN','engineering_release':'UNKNOWN'}}
    try:
        if not isinstance(options,dict) or set(options)!={'solver','boundary','purpose'}:
            raise ValueError('Review explicit solver, boundary and purpose')
        if options['purpose'] != 'CONSTITUTIVE_SPECIMEN':
            raise ValueError('Missing strength/failure parameters: only constitutive specimen is admitted; engineering/failure run blocked')
        s,mapping=map_to_mpa(source['original_draft'])
        settings={'law':s,'mesh':deepcopy(target['mesh']),
                  'solver':deepcopy(options['solver']),'boundary':deepcopy(options['boundary']),
                  'compare_point':True}
        fe.validate_settings(settings)
        if target.get('admission_errors'):
            raise ValueError('; '.join(target['admission_errors']))
        review.update(status='READY_FOR_EXPLICIT_APPLY',mapping=mapping,
            interface={'backend':law.FE,'kind':'FELUPE_CONSTITUTIVE_CALLBACK',
                'not_a_calculix_card':True,'declaration':law.declaration(s),
                'settings':settings,'required_values':[
                    {'name':'mesh','origin':'CURRENT_NATIVE_FEM','unit':'mm'},
                    {'name':'boundary','origin':'EXPLICIT_SPECIMEN_OVERRIDE','value':deepcopy(options['boundary'])},
                    {'name':'initial_state','origin':'SAVED_MATERIAL','value':deepcopy(s['initial_state'])},
                    {'name':'time','origin':'SAVED_MATERIAL','unit':'s','value':s['time']}],
                'card_preview':json.dumps({'backend':law.FE,'solver':options['solver'],
                    'law':s,'mesh_identity':target['mesh_sha256']},ensure_ascii=False,indent=2)})
    except (ValueError,TypeError,KeyError,OverflowError) as error:
        review['errors'].append(str(error))
    review['review_sha256']=canonical_hash(review)
    return review


def verify_review(review, target, *, live_source=True):
    row=deepcopy(review);digest=row.pop('review_sha256',None)
    if digest != canonical_hash(row) or row.get('schema')!=SCHEMA:
        raise ValueError('Review receipt is corrupted')
    if row['status']!='READY_FOR_EXPLICIT_APPLY':
        raise ValueError('Review is blocked; do not apply an old valid interface')
    if canonical_hash(row['target'])!=canonical_hash(target):
        raise ValueError('TARGET_CONFLICT: exact analysis/region/assignment/mesh/step changed')
    verify_source(row['source'],live=live_source,current_code=True)
    fresh=make_review(row['source'],target,row['options'])
    if fresh['review_sha256']!=digest:
        raise ValueError('Mapping differs from the reviewed source/interface')
    return row


def cold_assignment(record):
    """Retained read independent of current source paths/compiler/runtime/owners."""
    if not isinstance(record,dict) or 'assignment_sha256' not in record:
        raise ValueError('Missing retained assignment receipt')
    r=deepcopy(record);digest=r.pop('assignment_sha256')
    if canonical_hash(r)!=digest:
        raise ValueError('Retained assignment hash mismatch')
    verify_source(r['review']['source'])
    review=deepcopy(r['review']);rd=review.pop('review_sha256')
    if canonical_hash(review)!=rd:
        raise ValueError('Retained review hash mismatch')
    return deepcopy(record)


def guard_other_export(owner, analysis_id):
    rows=owner.read_metadata().get('law_native_assignments',[])
    if any(row.get('analysis_id')==analysis_id for row in rows):
        raise ValueError('LAW_NATIVE_INTERFACE_REQUIRED: use explicit law_freeze/FELUPE run; CalculiX cannot silently use the old elastic card')
    analysis=owner._object(analysis_id)
    if any(getattr(obj,PROPERTY,'') for obj in getattr(analysis,'Group',())):
        raise ValueError('LAW_NATIVE_ASSIGNMENT_PRESENT: retained metadata is missing; repair before any export')


def enrich_command(wb, identifier, operation, arguments, session_id, generation, command_id):
    """Workbench-only source resolution and exact lost-ack recovery."""
    if not isinstance(arguments,dict) or any(k.startswith('_') for k in arguments):
        raise ValueError('Private source/receipt injection is not allowed')
    if command_id:
        try:previous=wb.native_commands.status(command_id)
        except KeyError:previous=None
        if previous is not None:
            if ((previous['document_id'],previous['operation'],previous['session_id'],previous['expected_generation'])
                    != (identifier,operation,session_id,generation)
                    or previous['arguments'].get('_public_arguments')!=arguments):
                raise ValueError('command_id conflicts with an earlier law transfer')
            return previous,None
    args=deepcopy(arguments)
    args['_public_arguments']=deepcopy(arguments)
    if operation=='pre.fem.law_preview':
        args['_source_snapshot']=source_snapshot(wb.material_documents,args.pop('source'))
    elif operation=='pre.fem.law_apply':
        if 'review_command_id' not in args:
            raise ValueError('Apply requires an actual completed preview command ID')
        previous=wb.native_commands.status(args.pop('review_command_id'))
        if (previous['state']!='SUCCEEDED' or previous['operation']!='pre.fem.law_preview'
                or previous['document_id']!=identifier or previous['session_id']!=session_id):
            raise ValueError('Select this native owner session\'s completed preview')
        result=previous.get('outcome',{}).get('result',{}).get('result')
        # Native command result contains the owner response payload under result.
        if not isinstance(result,dict):raise ValueError('Preview command has no retained owner result')
        args['_review']=deepcopy(result.get('review',result.get('payload',{}).get('review')))
        if not isinstance(args['_review'],dict):raise ValueError('Completed preview did not contain a law review')
        verify_source(args['_review']['source'],live=True,current_code=True)
    return None,args
