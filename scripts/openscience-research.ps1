# Research-purpose admission reuses Core operations and numerical engines.
# This descriptor is a declared scope, not evidence of an installed solver.
$script:OpenScienceResearchTools = @('caelab_study_create', 'caelab_study_inspect', 'caelab_parameters_discover',
    'caelab_parameters_register', 'caelab_parameters_list', 'caelab_experiment_run',
    'caelab_experiment_inspect', 'caelab_experiment_summary', 'caelab_experiment_compare',
    'caelab_analysis_run', 'caelab_optimization_plan', 'caelab_optimization_run',
    'caelab_optimization_inspect', 'caelab_pde_run')
$script:OpenScienceStructuralResearchTools = @('caelab_study_create', 'caelab_study_inspect',
    'caelab_model_analysis_run', 'caelab_experiment_inspect', 'caelab_experiment_summary',
    'caelab_experiment_compare')

function New-OpenScienceResearchDefinition {
    param([ValidateSet('FixtureScalar', 'StructuralFamilies', IgnoreCase=$false)][string]$Profile = 'FixtureScalar')
    if ($Profile -ceq 'StructuralFamilies') {
        return [ordered]@{
            schema = 2; kind = 'autonomous-cae-lab.openscience-research-definition'
            profile = 'structural-families-v1'; agent = 'research'
            benchmark_definition = @{ id = 'P2-family-v1-20261002'; path = 'benchmarks/specifications/structural-families-v1.json' }
            allowed_tools = @($script:OpenScienceStructuralResearchTools)
            runtime_environment = [ordered]@{ MPLBACKEND = 'Agg'; OMP_NUM_THREADS = '2'; QT_QPA_PLATFORM = 'offscreen'
                CAELAB_CODEASTER_IMAGE = '/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif'
                CAELAB_CODEASTER_IMAGE_SHA256 = 'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64'
                CAELAB_SINGULARITY_COMMAND = '/usr/bin/singularity' }
            budgets = [ordered]@{ steps = 24; mcp_timeout_seconds = 3600; command_timeout_seconds = 3600
                model_analysis = @{ max_mesh_levels = 3; max_axis_cells = 48; max_elements_per_level = 1024
                    max_nodes_per_level = 10000; max_load_factor = 2.0 } }
            capabilities = @(
                [ordered]@{ backend = 'structural.families.calculix'; operations = @('model_analysis_run')
                    cases = @('ansys_vmd1_regular', 'lame_cylinder_plane_strain', 'scordelis_lo_solid')
                    inputs = 'Named frozen geometry/material/boundary/response definition, explicit load_case, load_factor and bounded mesh_cells.'
                    runtime = 'Existing ccx2.21; shared checked HEXA20 catalogue and equivalent nodal loads.'
                    evidence = 'Complete native displacement/reaction/integration-point stress, FRD/raw tables and immutable Core records.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
                [ordered]@{ backend = 'structural.families.code_aster'; operations = @('model_analysis_run')
                    cases = @('ansys_vmd1_regular', 'lame_cylinder_plane_strain', 'scordelis_lo_solid')
                    inputs = 'Same frozen definitions/catalogue/loads; backend syntax remains adapter-owned.'
                    runtime = 'Existing exact17.4 SIF and SHA, Singularity containment; no runtime or model fallback.'
                    evidence = 'Complete native tables/MED, checked catalogue bijection, source/image/version identities and independent references.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' }
            )
            limitations = @('Declared capabilities are not current numerical proof or engineering release.',
                'Original NFX distorted meshes, unresolved torsion and independent shell rotations remain UNKNOWN.',
                'Cylinder uses printed E220GPa with an independent analytical reference; conflicting vendor displacements remain UNKNOWN.',
                'Scordelis-Lo solid inner-surface response and conventional reference are distinct from shell midsurface/shallow/deep theories.',
                'This profile admits comparisons and changed loads. Numerical campaigns remain in the separate sequential Phase3 work.',
                'Strength, materials, physical loads and durability remain UNKNOWN; all outcomes remain NOT_RELEASED.')
        }
    }
    [ordered]@{
        schema = 1; kind = 'autonomous-cae-lab.openscience-research-definition'
        agent = 'research'; allowed_tools = @($script:OpenScienceResearchTools)
        runtime_environment = [ordered]@{ MPLBACKEND = 'Agg'; OMP_NUM_THREADS = '2'
            QT_QPA_PLATFORM = 'offscreen'; CAELAB_FENICSX_PYTHON = '/usr/bin/python3' }
        budgets = [ordered]@{ steps = 24; mcp_timeout_seconds = 3600; command_timeout_seconds = 3600
            optimization = @{ max_generations = 1; population_size = 5 }
            analysis = @{ max_mesh_levels = 2 }
            pde = @{ max_cell_count = 32; max_mesh_levels = 3 } }
        capabilities = @(
            [ordered]@{ backend = 'fixture.cadquery'; operations = @('parameters_discover', 'parameters_register', 'experiment_run')
                model = 'roller_support'; inputs = 'Registered research variables and bounds; valid CAD gates export.'
                runtime = 'Existing WslPython with pinned fixture/CadQuery dependencies'
                evidence = 'Core source/Python/platform and fixture source fingerprints; immutable CAD artifacts'
                verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
            [ordered]@{ backend = 'fixture.calculix'; operations = @('analysis_run', 'optimization_plan', 'optimization_run', 'optimization_inspect')
                inputs = 'Verified parent CAD experiment; explicit assumed/measured material, load and mesh; objective/constraints/seed'
                runtime = 'Gmsh and ccx on the configured resident WSL PATH; existing SciPy numerical engine'
                evidence = 'Existing solver executable/version, parent STEP, raw fields, mesh/reaction checks and campaign journals'
                verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
            [ordered]@{ backend = 'pde.fenicsx'; operations = @('pde_run')
                inputs = 'Bounded scalar linear elliptic weak form on unit square, Dirichlet data, manufactured reference and declared mesh/error limits'
                runtime = 'Existing isolated /usr/bin/python3 FEniCSx worker; not the Lab venv'
                evidence = 'Existing worker source/version/interpreter, fields, reference errors/rates and residual checks'
                verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' }
        )
        limitations = @('Capability metadata does not establish installation, a numerical PASS or engineering approval.',
            'CFD/Navier-Stokes, arbitrary geometry/domain/equation families and PDE input-binding optimization are not admitted by this profile.',
            'One bounded numerical generation does not establish a converged/global optimum.',
            'Solver completion does not qualify strength, materials, physical loads or release.',
            'Other implemented adapters remain outside this bounded research profile until their phase acceptance.',
            'In-flight solver/campaign cancellation is not established by the historical CAD-only cancellation proof.')
    }
}

function Get-OpenSciencePurposeTools($Context) {
    if ($Context.Purpose -ceq 'Research') {
        if ($Context.ResearchDefinition) { return ,@($Context.ResearchDefinition.allowed_tools) }
        return ,@($script:OpenScienceResearchTools)
    }
    return ,@($script:OpenScienceBoundedTools)
}

function Assert-OpenScienceResearchDefinition($Definition) {
    $profile = if ($Definition.schema -eq 2 -and $Definition.profile -ceq 'structural-families-v1') {
        'StructuralFamilies'
    } else { 'FixtureScalar' }
    Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $Definition) -ceq
        (Get-OpenScienceSourcePinSha256 (New-OpenScienceResearchDefinition -Profile $profile))) 'Research scope/runtime/budget differs from the supported definition.'
}

function Get-OpenScienceResearchPrompt($Definition) {
    Assert-OpenScienceResearchDefinition $Definition
    $scope = $Definition | ConvertTo-Json -Depth 12 -Compress
    @"
You are the research control plane for Autonomous CAE Lab. Follow the human's research question through the declared Core capabilities below. Select the appropriate backend, explain the plan, register research variables, execute new experiment IDs, compare actual receipts, and interpret the numerical evidence. Use multiple admitted tools as needed; do not fabricate results or run another provider/model.
If required material, load, boundary conditions, equation, objective or other engineering inputs are missing, ask a concrete question before solver execution. Identify unsupported requests explicitly and do not claim an available implementation or installation from metadata alone. Respect the declared capability and work budgets.
For adaptive search use optimization_plan and optimization_run: the existing numerical engine generates candidates. Do not choose successive numerical candidates yourself as a substitute optimizer. Preserve infeasible/failed points and report the actual termination and qualification limits.
Inspection, summaries and comparisons must use the same study/model/experiment/campaign IDs returned by Core. Append new experiments for changed conditions. Invalid CAD suppresses downstream solver execution. Preserve all UNKNOWN validation states, invalid metrics, reference failures, engineering assumptions and NOT_RELEASED. Solver exit success is not a strength or release verdict. Do not relax a reference, threshold or response to obtain PASS.
Declared profile: $scope
"@
}
