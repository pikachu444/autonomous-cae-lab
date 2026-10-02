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
$script:OpenSciencePdeResearchTools = @('caelab_study_create', 'caelab_study_inspect',
    'caelab_pde_run', 'caelab_experiment_inspect', 'caelab_experiment_summary',
    'caelab_experiment_compare')

function New-OpenScienceResearchDefinition {
    param([ValidateSet('FixtureScalar', 'StructuralFamilies', 'PDEFields', IgnoreCase=$false)][string]$Profile = 'FixtureScalar')
    if ($Profile -ceq 'PDEFields') {
        return [ordered]@{
            schema = 3; kind = 'autonomous-cae-lab.openscience-research-definition'
            profile = 'pde-fields-v1'; agent = 'research'
            allowed_tools = @($script:OpenSciencePdeResearchTools)
            runtime_environment = [ordered]@{ MPLBACKEND = 'Agg'; OMP_NUM_THREADS = '2'
                QT_QPA_PLATFORM = 'offscreen'; CAELAB_FENICSX_PYTHON = '/usr/bin/python3' }
            budgets = [ordered]@{ steps = 24; mcp_timeout_seconds = 3600; command_timeout_seconds = 3600
                pde = @{ max_cell_count = 32; max_mesh_levels = 3; min_mesh_levels = 3; degree = 1
                    max_time_steps = 128; max_snapshot_node_values = 200000
                    max_imported_bytes = 98304; max_request_bytes = 131072 } }
            capabilities = @(
                [ordered]@{ backend = 'pde.fenicsx'; operations = @('pde_run')
                    inputs = 'Dimensionless scalar linear elliptic unit square, constant diffusion/reaction and whole-boundary Dirichlet value, safe expression/reference and three doubling P1 meshes.'
                    evidence = 'Immutable native XDMF/H5, actual residual, reference errors/rates and source/runtime identities. Legacy scalar has no native DOF JSON and is download-only in the field inspector.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
                [ordered]@{ backend = 'pde.fenicsx.rectangle'; operations = @('pde_run')
                    inputs = 'Declared dimensionless rectangle, constant scalar diffusion/reaction, named whole-side Dirichlet/outward Neumann expressions, reference and three doubling P1 meshes.'
                    evidence = 'Same-record scalar native nodes/triangles, named-side binding, XDMF/H5, symbolic errors/rates and actual residual.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
                [ordered]@{ backend = 'pde.fenicsx.transient'; operations = @('pde_run')
                    inputs = 'Dimensionless scalar unit-capacity backward Euler rectangle, initial/side/source/reference expressions and exactly one mesh or time refinement axis, with explicit step and retained node-value budgets.'
                    evidence = 'Complete N+1 native histories and current/previous state identities; initial interpolation is NOT_RUN, not a native solve.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
                [ordered]@{ backend = 'pde.fenicsx.coupled'; operations = @('pde_run')
                    inputs = 'Two scalar fields with regional SPD cross-diffusion/common PSD reaction, a conforming straight midpoint interface on a rectangle, regional expressions and directed named-side data.'
                    evidence = 'Blocked native u0/u1 fields, regional cells, interface adjacency/two traces, split sides, XDMF/H5, reference errors/rates and actual residual.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
                [ordered]@{ backend = 'pde.fenicsx.imported'; operations = @('pde_run')
                    inputs = 'Exactly three immutable bounded ASCII MSH2.2 original data/label/SHA levels, scalar P1, named physical Dirichlet/outward Neumann expressions and declared reference. Original data is frozen model context, never a path or optimization variable.'
                    evidence = 'Original/dense mesh hashes and native mapping/boundary files, scalar DOFs/XDMF/H5, measured-h reference rates and actual residual. Imported activation requires its separate independent native audit.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' }
            )
            limitations = @('This scope is not current native execution proof, physical model qualification or engineering release.',
                'Only the five listed bounded real64 serial P1 families are admitted; vector, nonlinear expansion, CFD, MPI/HPC and arbitrary research code are outside this scope.',
                'Research work budgets bound mesh/time/retention and parsed-hook JSON, not numerical accuracy. Original MCP wire byte size is not observable at the tool hook; whole HTTP body limits are separate.',
                'No generic job, variable registration or numerical optimizer tools are provided. Numerical engines own search candidates.',
                'A finite wrong reference or flux remains an actual numerical REJECTED result; scientific and unsafe-expression preflight belongs to Domain/adapters.',
                'Missing/partial field representations remain explicit or download-only; displayed retained failed fields do not become valid metrics.',
                'Strength, material, physical and durability qualification remain UNKNOWN; all results remain NOT_RELEASED.')
        }
    }
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
                    inputs = 'settings contains exactly case, load_case, load_factor and bounded mesh_cells. Domain supplies the frozen geometry/material/boundary/response definitions and references; adapters own native translation and execution. Benchmark identity, hash and case_definition are research context outside settings.'
                    runtime = 'Existing ccx2.21; shared checked HEXA20 catalogue and equivalent nodal loads.'
                    evidence = 'Complete native displacement/reaction/integration-point stress, FRD/raw tables and immutable Core records.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' },
                [ordered]@{ backend = 'structural.families.code_aster'; operations = @('model_analysis_run')
                    cases = @('ansys_vmd1_regular', 'lame_cylinder_plane_strain', 'scordelis_lo_solid')
                    inputs = 'settings contains exactly case, load_case, load_factor and bounded mesh_cells. Domain supplies the same frozen definitions/catalogue/loads and references; adapters own native translation and execution. Benchmark identity, hash and case_definition are research context outside settings.'
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
    } elseif ($Definition.schema -eq 3 -and $Definition.profile -ceq 'pde-fields-v1') {
        'PDEFields'
    } else { 'FixtureScalar' }
    Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $Definition) -ceq
        (Get-OpenScienceSourcePinSha256 (New-OpenScienceResearchDefinition -Profile $profile))) 'Research scope/runtime/budget differs from the supported definition.'
}

function Get-OpenScienceResearchPrompt($Definition) {
    Assert-OpenScienceResearchDefinition $Definition
    $scope = $Definition | ConvertTo-Json -Depth 12 -Compress
    if ($Definition.schema -eq 3 -and $Definition.profile -ceq 'pde-fields-v1') {
        return @"
You are the research control plane for Autonomous CAE Lab. Follow the human's supplied mathematical question through the declared PDE families below. Explain the plan, choose an admitted backend, execute new experiment IDs, inspect and compare actual receipts, and interpret their evidence. Use only the six listed tools and the selected provider/model. Capability metadata is not current execution or qualification proof.
For caelab_pde_run pass exactly study_id, experiment_id, backend and settings, with hypothesis_id only when supplied. Use the original settings shape of the selected family; benchmark identities, reference evidence, publication records and capability metadata are context, not additional tool arguments. Never silently delete, substitute or relax a requested condition, reference, threshold or response to get a PASS.
If required equation, geometry, boundary, initial, reference or refinement conditions are missing, ask a concrete question before execution. Identify unsupported families explicitly. Respect the declared mesh/time/retained-node/byte work budgets; they are resource limits, not solver accuracy or engineering verdicts. Time histories refine only one axis with the other fixed. Imported original bytes/hash/order are immutable data, not filesystem paths or search variables.
This PDEFields scope does not provide numerical optimization or job tools. Numerical engines generate search candidates; do not act as a substitute numerical optimizer. Append a new experiment for changed conditions and use the same returned study/experiment/model revision in inspection, summaries and comparisons.
Invalid inputs block native execution. Finite incorrect reference/flux may yield an actual retained REJECTED result. Preserve failed attempts, invalid values/reasons, independent UNKNOWN checks and NOT_RELEASED. Initial interpolation is not a native solve; successful execution/visualization is not strength, physics or release approval. Missing/partial native fields are unavailable or download-only, never fabricated.
Declared profile: $scope
"@
    }
    if ($Definition.schema -eq 2 -and $Definition.profile -ceq 'structural-families-v1') {
        return @"
You are the research control plane for Autonomous CAE Lab. Follow the human's research question through the declared Core capabilities below. Select the appropriate admitted backend, explain the plan, execute new experiment IDs, compare actual receipts, and interpret the numerical evidence. Use multiple admitted tools as needed; do not fabricate results or run another provider/model.
This StructuralFamilies profile admits only the six tools in allowed_tools. Variable registration and numerical optimization are not provided in this profile; do not request unlisted tools or act as a substitute numerical optimizer. Respect the declared capability and work budgets.
For caelab_model_analysis_run, pass study_id, experiment_id, backend and settings, with hypothesis_id only when supplied. The settings object must contain exactly four keys: case, load_case, load_factor, mesh_cells. Use the explicit settings supplied in the research context without adding fields. benchmark_definition_id, benchmark_definition_sha256, benchmark_definition, case_definition, references, tolerances and other research metadata describe the frozen problem and its evidence; they are not settings or additional tool arguments. Domain supplies the frozen scientific definitions and references; adapters own native translation and execution. Do not rewrite an invalid request by silently deleting or substituting conditions.
If required case, load, mesh or other engineering inputs are missing, ask a concrete question before solver execution. Identify unsupported requests explicitly and do not claim an available implementation or installation from metadata alone.
Inspection, summaries and comparisons must use the same study/model/experiment IDs returned by Core. Append new experiments for changed conditions. Invalid inputs suppress downstream solver execution. Preserve failed attempts, all UNKNOWN validation states, invalid metrics, reference failures, engineering assumptions and NOT_RELEASED. Solver exit success is not a strength or release verdict. Do not relax a reference, threshold or response to obtain PASS.
Declared profile: $scope
"@
    }
    @"
You are the research control plane for Autonomous CAE Lab. Follow the human's research question through the declared Core capabilities below. Select the appropriate backend, explain the plan, register research variables, execute new experiment IDs, compare actual receipts, and interpret the numerical evidence. Use multiple admitted tools as needed; do not fabricate results or run another provider/model.
If required material, load, boundary conditions, equation, objective or other engineering inputs are missing, ask a concrete question before solver execution. Identify unsupported requests explicitly and do not claim an available implementation or installation from metadata alone. Respect the declared capability and work budgets.
For adaptive search use optimization_plan and optimization_run: the existing numerical engine generates candidates. Do not choose successive numerical candidates yourself as a substitute optimizer. Preserve infeasible/failed points and report the actual termination and qualification limits.
Inspection, summaries and comparisons must use the same study/model/experiment/campaign IDs returned by Core. Append new experiments for changed conditions. Invalid CAD suppresses downstream solver execution. Preserve all UNKNOWN validation states, invalid metrics, reference failures, engineering assumptions and NOT_RELEASED. Solver exit success is not a strength or release verdict. Do not relax a reference, threshold or response to obtain PASS.
Declared profile: $scope
"@
}
