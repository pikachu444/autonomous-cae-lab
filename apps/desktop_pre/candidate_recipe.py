"""Capture a saved Analysis recipe; no mesher, solver or optimizer runs here."""
from copy import deepcopy
from pathlib import Path

from caelab.storage import canonical_hash, save_json
from .fem_edit import _native_type
from .research_inputs import value_at, validate_limits
from .candidate_correspondence import capture


def prepare_recipe(owner, args):
    if set(args) != {'analysis_id', 'solver_id', 'variable_ids', 'responses'}:
        raise ValueError('Choose Analysis, solver, registered variables and explicit responses')
    owner.before_design_action('prepare Numerical Plan')
    analysis, solver = owner._object(args['analysis_id']), owner._object(args['solver_id'])
    if _native_type(analysis) != 'Fem::FemAnalysis' or solver not in analysis.Group or _native_type(solver) != 'Fem::SolverCcxTools':
        raise ValueError('Choose this Analysis and its CalculiX solver')
    identifiers = args['variable_ids']
    if not isinstance(identifiers, list) or not 1 <= len(identifiers) <= 32 or len(set(identifiers)) != len(identifiers):
        raise ValueError('Choose 1..32 distinct registered variables')
    state = owner.research.descriptor(analysis.Name)
    variables = []
    for name in identifiers:
        row = next((r for r in state['registered'] if r['id'] == name), None)
        if row is None or row['diagnostic']:
            raise ValueError((row or {}).get('diagnostic') or 'Registered variable is missing')
        row = deepcopy(row)
        row.pop('diagnostic', None)
        row['value'] = value_at(owner, row['target'], row['unit'])
        validate_limits(row, row['lower'], row['upper'], row['value'])
        variables.append(row)
    contacts = [row for row in owner.fem.contact._data()['contacts']
                if row['analysis_id'] == analysis.Name and not getattr(owner._object(row['object_id']), 'Suppressed', False)]
    route = 'contact' if contacts else 'single_solid'
    meshes = [obj for obj in analysis.Group if hasattr(obj, 'FemMesh') and not getattr(obj, 'Suppressed', False)]
    if not meshes or any(_native_type(obj) != 'Fem::FemMeshGmsh' for obj in meshes):
        raise ValueError('Create active body Gmsh meshes and select their settings before a native study')
    recipe = {'version': 1, 'analysis_id': analysis.Name, 'solver_id': solver.Name,
              'route': route, 'variables': variables, 'responses': deepcopy(args['responses']),
              'meshes': [{'object_id': obj.Name, 'body_id': obj.Shape.Name,
                          'settings': owner.fem._mesh_settings(obj)} for obj in meshes],
              'correspondence': capture(owner),
              'pairs': [{'id': row['object_id'], 'label': row['draft']['label']} for row in contacts],
              'qualification': 'UNKNOWN'}
    from .assembly_candidates import capture as capture_assembly
    assembly = capture_assembly(owner, analysis, variables)
    if assembly:
        if route != 'contact':
            raise ValueError('Two-occurrence execution currently uses the supported contact Analysis; '
                             'define its physical pair and FEM conditions before preparing this recipe')
        recipe['assembly'] = assembly
    from caelab.adapters.cad_analysis import validate_recipe
    validate_recipe(recipe)
    data = owner.read_metadata()
    data['candidate_recipe'] = recipe
    owner._transaction('Prepare Analysis research', lambda: owner.write_metadata(data))
    saved = owner.project.save()
    if saved.get('unavailable_dependencies'):
        raise ValueError('Saved draft has missing dependencies; repair them before creating an executable recipe')
    project = Path(saved['retained_project'])
    # The manifest and editable dependency graph are already in one immutable archive.
    from caelab.native_cad import inspect_project, sha
    manifest = inspect_project(project)
    if canonical_hash(manifest['metadata']['candidate_recipe']) != canonical_hash(recipe):
        raise ValueError('Saved recipe differs from the selected native input')
    result = {'project_relative': project.relative_to(owner.export_root).as_posix(),
              'project_sha256': sha(project), 'recipe': recipe, 'revision': saved['revision'],
              'label': owner.doc.Label, 'solver_execution': 'NOT_PERFORMED'}
    save_json(project.parent / 'research-recipe.json', result)
    return result
