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
    param([ValidateSet('FixtureScalar', 'FixtureRefinement', 'StructuralFamilies', 'PDEFields', 'MaterialPoints', 'ViscoelasticPoints', 'ContactPatches', IgnoreCase=$false)][string]$Profile = 'FixtureScalar')
    if ($Profile -ceq 'FixtureRefinement') {
        # Explicit new scope: never change the historical schema1 fingerprint.
        $definition = New-OpenScienceResearchDefinition -Profile FixtureScalar
        $definition.schema = 7
        $definition.profile = 'fixture-refinement-v1'
        $definition.budgets.analysis.max_mesh_levels = 3
        $definition.capabilities[0].inputs = 'Discover native paths/current values/bounds first. Register only requested research variables; registration bounds must contain the current CAD value and stay within discovered native bounds, including fixed variables. A fixed variable must keep its discovered current_value. A requested different value needs free registration and an explicit experiment value. Unregistered CAD dimensions retain their current defaults.'
        $definition.capabilities[1].inputs = 'analysis_run requires exactly parent_experiment_id, experiment_id, backend=fixture.calculix and settings with exactly load/material/mesh. load: force_per_support_N and source. material: model, provenance, qualification; orthotropic E_1_MPa/E_2_MPa/E_3_MPa/nu_12/nu_13/nu_23/G_12_MPa/G_13_MPa/G_23_MPa/axes, or isotropic elastic_modulus_MPa/poisson_ratio. mesh: max_sizes_mm, two or three positive strictly descending sizes in mm. optimization_plan uses this same analysis_settings and deterministic numerical engine.'
        $definition.capabilities[1].boundary_model = 'One verified roller_support solid, roller diameter8.3mm and depth>=24mm: bottom fixed in X/Y/Z; total negative-Z saddle force distributed by clipped tessellated surface area over the central24mm. This idealization is fixed by the existing adapter, not caller-supplied bolt/contact conditions. Orthotropic axes are global CAD X/Y/Z; axes text declares provenance and does not rotate the constitutive tensor.'
        $definition.capabilities[1].numerical_verdict = 'Existing final-two-mesh displacement relative change<=5% and signed all-axis reaction balance<=1% remain unchanged. Peak stress is an invalid diagnostic, not strength evidence. Three meshes alone do not establish asymptotic convergence.'
        $definition.limitations += @('This opt-in profile admits one additional analysis mesh level; the historical FixtureScalar default remains two. Tool/backend/model/security/cleanup and native execution policies are unchanged.',
            'Arbitrary support boundaries, material rotations, bolt/contact mechanics and original assembly mechanics are not admitted. Missing physical material/load data stay explicitly assumed and UNKNOWN; all results remain NOT_RELEASED.')
        return $definition
    }
    if ($Profile -ceq 'ContactPatches') {
        return [ordered]@{
            schema = 6; kind = 'autonomous-cae-lab.openscience-research-definition'
            profile = 'contact-patches-v1'; agent = 'research'
            allowed_tools = @($script:OpenScienceStructuralResearchTools)
            runtime_environment = [ordered]@{ MPLBACKEND = 'Agg'; OMP_NUM_THREADS = '1'; QT_QPA_PLATFORM = 'offscreen'
                CAELAB_CODEASTER_IMAGE = '/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif'
                CAELAB_CODEASTER_IMAGE_SHA256 = 'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64'
                CAELAB_SINGULARITY_COMMAND = '/usr/bin/singularity' }
            budgets = [ordered]@{ steps = 24; mcp_timeout_seconds = 3600; command_timeout_seconds = 3600
                contact_patch = @{ max_nodes = 1154; max_solid_cells = 1060; max_boundary_segments = 184
                    max_stress_locations = 4240; max_slave_pressure_nodes = 25; max_request_bytes = 16384 } }
            capabilities = @(
                [ordered]@{ backend = 'structural.code_aster.contact_patch'; operations = @('model_analysis_run')
                    cases = @('ssnp121a_frictionless_patch')
                    inputs = 'Exact case/material/top_displacement_m/limits with optional mesh_variant=uniform_quad4_2x; omitted selector preserves original. Domain owns finite scientific admission and unchanged six1%/reaction1%/balance1e-6 verdicts. No arbitrary code, paths, counts or levels.'
                    runtime = 'Existing exact Code_Aster17.4 SIF and SHA with OMP1 and Singularity containment; no runtime or model fallback.'
                    evidence = 'Code_Aster SSNP121A: original313 nodes/265 QUAD4/92 SEG2 or uniform2 1154/1060/184 with original313 name/coordinate prefix. Native pressure13/25 nodes, stress1060/4240 locations, complete U/RF and hash-bound JSON/MED fields.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' }
            )
            limitations = @('Declared research scope is not current connected Research execution proof, physical qualification or engineering release.',
                'This is native Code_Aster SSNP121A, not NAFEMS CGS1 or MIDAS replication. Failed CalculiX pilot7PASS/6FAIL remains failed and outside this production scope.',
                'One uniform subdivision establishes sensitivity, not asymptotic convergence. Measured stress XY and native integration weight W remain separate; native contact gap and measured geometric stress Z are unavailable. Projected gap is diagnostic.',
                'Budgets bound parsed-hook JSON and retained resource counts, not original MCP wire bytes or engineering accuracy. Native wall defaultNone and positive CPU86400 remain separate execution policies.',
                'Only the six listed tools are admitted. OpenScience chooses questions, hypotheses, conditions and interpretation; deterministic numerical engines own search candidates.',
                'Inspect actual returned IDs/revisions, signed pressure versus positive magnitude, sample metrics versus whole-field diagnostics, checks and raw artifact references. Full native fields require same-record hash-bound JSON/MED, not summary arrays.',
                'Generic Lab Results offers metrics and raw downloads, with no contact preset or contact full-field viewer. The PDE field viewer excludes contact; conversation/result identity and human full-field visual inspection are separate gates.',
                'All ten blocking engineering UNKNOWNs remain. Preserve failed results and invalid metrics; no automatic model/backend fallback, retry, reference response substitution or release claim. All outcomes remain NOT_RELEASED.')
        }
    }
    if ($Profile -ceq 'ViscoelasticPoints') {
        return [ordered]@{
            schema = 5; kind = 'autonomous-cae-lab.openscience-research-definition'
            profile = 'viscoelastic-points-v1'; agent = 'research'
            allowed_tools = @($script:OpenScienceStructuralResearchTools)
            runtime_environment = [ordered]@{ MPLBACKEND = 'Agg'; OMP_NUM_THREADS = '2'; QT_QPA_PLATFORM = 'offscreen'
                CAELAB_MFRONT_IMAGE = '/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif'
                CAELAB_MFRONT_IMAGE_SHA256 = 'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64'
                CAELAB_SINGULARITY_COMMAND = '/usr/bin/singularity' }
            budgets = [ordered]@{ steps = 24; mcp_timeout_seconds = 3600; command_timeout_seconds = 3600
                material_point = @{ min_history_entries = 2; max_history_entries = 17
                    max_signed_probe_states = 576; max_request_bytes = 65536 } }
            capabilities = @(
                [ordered]@{ backend = 'material.mfront.viscoelastic'; operations = @('model_analysis_run')
                    cases = @('single_branch_maxwell')
                    inputs = 'Exact case/material/temperature_k/history/limits; physical six-component tensor strain xx,yy,zz,xy,xz,yz and 2..17 ordered entries. Domain owns initial-state, representability and fixed stress/tangent/energy verdicts.'
                    runtime = 'Existing exact17.4 SIF and SHA, TFEL5/MGIS3/MTest and Singularity containment; no runtime or model fallback.'
                    evidence = 'Immutable Core metrics/checks and hash-bound actual stress, BranchStress, tangent and native stored/dissipated energy histories, all signed probes and same-library MTest.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' }
            )
            limitations = @('Declared scope is not current native execution proof, physical qualification or engineering release.',
                'Synthetic infinitesimal isotropic single-branch Maxwell material point; measured materials, finite-strain viscoelasticity, multiple branches and spatial finite-element coupling remain unqualified.',
                'Work budgets bound parsed-hook JSON and signed-probe counts, not original MCP wire bytes or scientific accuracy. Native wall defaultNone and positive CPU86400 are separate execution policies.',
                'Only the six listed tools are admitted; variable registration, jobs and numerical optimizer tools are not provided. Numerical engines own search candidates.',
                'Interpret actual returned IDs, revisions, metrics and UNKNOWNs. Complete measured histories require same-record hash-bound artifacts; summary error metrics cannot substitute for response histories.',
                'Shared-time refinement checks composition of the identical piecewise-linear path, not temporal convergence order; increment tangents depend on dt.',
                'Material, physical, strength, durability, binary/source equivalence and deployment requirements remain UNKNOWN; all outcomes remain NOT_RELEASED.')
        }
    }
    if ($Profile -ceq 'MaterialPoints') {
        return [ordered]@{
            schema = 4; kind = 'autonomous-cae-lab.openscience-research-definition'
            profile = 'material-points-v1'; agent = 'research'
            allowed_tools = @($script:OpenScienceStructuralResearchTools)
            runtime_environment = [ordered]@{ MPLBACKEND = 'Agg'; OMP_NUM_THREADS = '2'; QT_QPA_PLATFORM = 'offscreen'
                CAELAB_CODEASTER_IMAGE = '/home/pikachu444/.local/share/autonomous-cae-lab/code_aster_17.4.0-oci.sif'
                CAELAB_CODEASTER_IMAGE_SHA256 = 'f4d9a7bfdd9c20ebba1fde3a710ead56b2041d16efc22425ecc84c4866e08e64'
                CAELAB_SINGULARITY_COMMAND = '/usr/bin/singularity' }
            budgets = [ordered]@{ steps = 24; mcp_timeout_seconds = 3600; command_timeout_seconds = 3600
                material_point = @{ min_history_entries = 3; max_history_entries = 12
                    max_signed_probe_states = 594; max_request_bytes = 65536 } }
            capabilities = @(
                [ordered]@{ backend = 'material.mfront.hyperelastic'; operations = @('model_analysis_run')
                    cases = @('saint_venant_kirchhoff')
                    inputs = 'Exact case/material/temperature_k/history/limits; physical nine-component F with 3..12 ordered entries. Domain owns finite-strain/probe scientific admission and fixed reference limits.'
                    runtime = 'Existing exact17.4 SIF and SHA, TFEL5/MGIS3/MTest and Singularity containment; no runtime or model fallback.'
                    evidence = 'Immutable Core metrics/checks and hash-bound actual native F/P/A/W histories, all signed probes and same-library MTest. Summaries do not expose full measured histories.'
                    verification = 'IMPLEMENTED_NOT_CURRENT_EXECUTION_PROOF' }
            )
            limitations = @('Declared scope is not current native execution proof, physical qualification or engineering release.',
                'Unmodified SVK covers large proper rotations with small Green strain, not general rubber, large-stretch stability or finite-element constitutive coupling.',
                'Work budgets bound parsed-hook JSON and signed-probe counts, not original MCP wire bytes or scientific accuracy. Native wall defaultNone and positive CPU86400 are separate execution policies.',
                'Only the six listed tools are admitted; variable registration, jobs and numerical optimizer tools are not provided. Numerical engines own search candidates.',
                'Interpret actual returned IDs, revisions, metrics and UNKNOWNs. Full measured F/P/A/W histories require same-record hash-bound artifacts and are not invented from summaries.',
                'Material, physical, strength, durability, binary/source equivalence and deployment requirements remain UNKNOWN; all outcomes remain NOT_RELEASED.')
        }
    }
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
    $profile = if ($Definition.schema -eq 7 -and $Definition.profile -ceq 'fixture-refinement-v1') {
        'FixtureRefinement'
    } elseif ($Definition.schema -eq 2 -and $Definition.profile -ceq 'structural-families-v1') {
        'StructuralFamilies'
    } elseif ($Definition.schema -eq 6 -and $Definition.profile -ceq 'contact-patches-v1') {
        'ContactPatches'
    } elseif ($Definition.schema -eq 5 -and $Definition.profile -ceq 'viscoelastic-points-v1') {
        'ViscoelasticPoints'
    } elseif ($Definition.schema -eq 4 -and $Definition.profile -ceq 'material-points-v1') {
        'MaterialPoints'
    } elseif ($Definition.schema -eq 3 -and $Definition.profile -ceq 'pde-fields-v1') {
        'PDEFields'
    } else { 'FixtureScalar' }
    Assert-OpenScienceCondition ((Get-OpenScienceSourcePinSha256 $Definition) -ceq
        (Get-OpenScienceSourcePinSha256 (New-OpenScienceResearchDefinition -Profile $profile))) 'Research scope/runtime/budget differs from the supported definition.'
}

function Get-OpenScienceResearchPrompt($Definition) {
    Assert-OpenScienceResearchDefinition $Definition
    $scope = $Definition | ConvertTo-Json -Depth 12 -Compress
    if ($Definition.schema -eq 7 -and $Definition.profile -ceq 'fixture-refinement-v1') {
        return @"
You are the research control plane for Autonomous CAE Lab. Follow the supplied question with the existing fourteen tools and selected provider/model. Explain the plan in ordinary language, create NEW experiment IDs, inspect the actual returned results, compare measured responses, and answer the question with values, units, checks, assumptions and same-record references. No invented results or model/backend fallback. Metadata is not current execution or release proof.
For fixture.cadquery/roller_support discover native paths, current values and bounds before registration. Bounds must contain the current CAD value and lie within discovered bounds even for a fixed parameter; lower=upper is not a valid registration shortcut. A mode=fixed variable must keep its discovered current_value. To request a different value, register it as free and supply that explicit value for each experiment. Register only requested variables; other CAD dimensions retain their current defaults. Preserve existing CAD revisions and reuse their returned experiment IDs for analysis and changed loads.
For caelab_analysis_run pass exactly parent_experiment_id, experiment_id, backend=fixture.calculix and settings. The parent is the verified CAD experiment ID; Core inherits its study and hypothesis. Settings has exactly load, material, mesh. load has exactly force_per_support_N (positive magnitude in N, applied in negative Z) and source (assumed or measured provenance). mesh has exactly max_sizes_mm: a two or three item positive strictly descending array in mm, preserving the requested sizes. Do not use mesh.element_size_mm, units, analysis_type, material_axes, boundary_conditions, loads, checks, limits or limitations as settings keys.
Material has model, provenance and qualification. For model=orthotropic use E_1_MPa, E_2_MPa, E_3_MPa, nu_12, nu_13, nu_23, G_12_MPa, G_13_MPa, G_23_MPa and a nonempty axes declaration. For model=isotropic use elastic_modulus_MPa and poisson_ratio. The existing adapter uses the global CAD X/Y/Z axes; axes is provenance text, not a rotation API. Preserve supplied constants and clearly mark hypothetical properties; do not silently supply measured material data.
The admitted boundary idealization is bottom fixed in X/Y/Z, with total negative-Z saddle force distributed by clipped tessellated surface area over the central24mm of one verified support (roller diameter8.3mm, depth>=24mm). Explain this fixed idealization before execution. Do not invent bolt-hole clamps, contact or rotation controls. If the question requests incompatible boundaries or axes, state the limitation and ask for the missing decision; do not replace the requested physics silently. Already explicit compatible assumptions do not require asking again.
The unchanged adapter checks final-two-mesh displacement change<=5% and signed all-axis reaction balance<=1%. Peak stress remains an invalid diagnostic; three meshes alone do not prove asymptotic convergence. Finite scientific-invalid inputs belong to Domain preflight and retained rejection evidence; never normalize them, relax thresholds, substitute reference responses or retry an unchanged failure. Report tool errors distinctly from successful corrected calls.
For numerical search use optimization_plan/optimization_run with the same declared analysis_settings: the existing deterministic numerical engine generates candidates. Preserve infeasible/failed points and actual termination. Do not act as a substitute numerical optimizer. Inspect and compare only actual returned study/model/experiment/campaign IDs. Changed conditions append new experiments. Preserve all UNKNOWNs, invalid metric values/reasons, old artifacts and NOT_RELEASED. CLI completion and solver success are not engineering approval.
Declared profile: $scope
"@
    }
    if ($Definition.schema -eq 6 -and $Definition.profile -ceq 'contact-patches-v1') {
        return @"
You are the research control plane for Autonomous CAE Lab. Follow the supplied Code_Aster SSNP121A contact question through only these six tools and the selected provider/model. Choose hypotheses and conditions, execute NEW experiment IDs, inspect the same returned IDs/revisions, compare actual signed responses and interpret checks, counterexamples and UNKNOWNs. No automatic model/backend fallback, retry or invented results.
For caelab_model_analysis_run pass exactly study_id, experiment_id, backend and settings, with hypothesis_id only when supplied. Backend is structural.code_aster.contact_patch and case is ssnp121a_frictionless_patch. Settings contains exactly case, material, top_displacement_m and limits, with mesh_variant only when uniform_quad4_2x is explicitly requested. Omission retains original mesh and declaration. Material contains youngs_modulus_pa and poisson_ratio; limits remain reference_relative=.01 and force_balance_relative=1e-6. Do not inject IDs/hashes, arbitrary code/paths/levels, fill or normalize conditions, substitute reference responses, or relax numerical limits. Missing required conditions need a concrete question before execution. Finite scientific-invalid settings belong to Domain preflight and retained REJECTED/NOT_RUN evidence; never bypass it.
The original313/265/92 mesh and one fixed uniform2 1154/1060/184 mesh share original313 names/coordinates and physical conditions. Pressure has13/25 slave nodes and stress1060/4240 locations; full U/RF and stress arrays are in actual hash-bound native JSON/MED artifacts, not generic tool summaries. Distinguish signed contact traction from positive pressure magnitude, actual A/B/N14 samples from whole-field diagnostics, measured stress XY from native integration weight W. Native gap and geometric stress Z are unavailable; projected gaps remain derived diagnostics. One subdivision is sensitivity, not asymptotic convergence. This is not NAFEMS CGS1/MIDAS replication; failed CalculiX pilot7PASS/6FAIL remains failed and outside this scope.
Report only real returned study/experiment/model revisions, valid and invalid metric values/reasons, actual validation checks, all ten blocking engineering UNKNOWNs and raw artifact references. Generic Lab Results has common metrics/raw downloads, no contact preset or full-field viewer; the PDE viewer excludes contact. Conversation/result identity and human full-field inspection are separate gates. Numerical engines own search candidates; no numerical optimizer or job tools are admitted here. Preserve every failed experiment and NOT_RELEASED. Solver completion, comparison or visualization is not engineering release.
Declared profile: $scope
"@
    }
    if ($Definition.schema -eq 5 -and $Definition.profile -ceq 'viscoelastic-points-v1') {
        return @"
You are the research control plane for Autonomous CAE Lab. Plan from the supplied viscoelastic question, use only this explicit six-tool scope and the selected provider/model, execute NEW experiment IDs, inspect and summarize the same returned IDs/revisions, compare actual results and interpret numerical evidence and UNKNOWN checks. No alternate model/provider, fallback or invented results.
For caelab_model_analysis_run pass exactly study_id, experiment_id, backend and settings, with hypothesis_id only when supplied. Use backend material.mfront.viscoelastic and case single_branch_maxwell. Settings contains exactly case, material, temperature_k, history and limits. Material contains equilibrium_bulk_modulus_mpa, equilibrium_shear_modulus_mpa, branch_bulk_modulus_mpa, branch_shear_modulus_mpa and relaxation_time_s. Each history entry contains time_s and six physical tensor strain components xx,yy,zz,xy,xz,yz; these are not engineering shear or deformation gradients. Keep every supplied condition, fixed limit and all three finite-difference steps unchanged. Missing inputs require a concrete question before execution; never delete or substitute conditions or relax a limit to obtain PASS.
Respect the declared 2..17 history entries, 576 signed probes and parsed JSON resource budget. Domain/adapters own zero initial state, representability, independent reference equations, native syntax and numerical verdicts. Scientific-invalid inputs must remain retained preflight rejections with no native execution. The synthetic infinitesimal single-branch law is not measured material, finite-strain viscoelasticity or spatial FE qualification. Shared-time subdivision checks composition of the identical piecewise-linear path, not temporal convergence order; increment tangents depend on dt.
Core metrics may contain complete retained histories. Interpret response values only from actual valid returned histories or same-record hash-bound artifacts, never from error metrics or analytical predictions alone. Stress, relaxing BranchStress and actual native stored/dissipated energies are distinct; do not replace missing energy with half stress times strain after unloading.
Registration, job and numerical optimizer tools are not available here. Numerical engines own candidate search. Preserve failed experiments, invalid metric values/reasons, assumptions, independent UNKNOWNs and NOT_RELEASED. Solver completion and comparison are not material, strength, physical, durability or release qualification.
Declared profile: $scope
"@
    }
    if ($Definition.schema -eq 4 -and $Definition.profile -ceq 'material-points-v1') {
        return @"
You are the research control plane for Autonomous CAE Lab. Plan from the supplied material-point question, use only this explicit six-tool scope and the selected provider/model, execute NEW experiment IDs, inspect and summarize the same returned IDs/revisions, compare actual results and interpret the numerical evidence and UNKNOWN checks. No alternate model/provider, fallback or invented results.
For caelab_model_analysis_run pass exactly study_id, experiment_id, backend and settings, with hypothesis_id only when supplied. Use backend material.mfront.hyperelastic and case saint_venant_kirchhoff. Settings contains exactly case, material, temperature_k, history and limits. Keep the supplied physical nine-component F order xx,yy,zz,xy,yx,xz,zx,yz,zy and every fixed limit/all three finite-difference steps unchanged. Missing inputs require a concrete question before execution; never delete or substitute conditions or relax a limit to obtain PASS.
Respect the declared 3..12 history entries, 594 signed probes and parsed JSON resource budget. Domain/adapters own determinant, Green-strain, initial-state and probe admission, reference equations, native syntax and numerical verdicts. Scientifically invalid input must remain a retained preflight rejection with no native execution. Initial t0 is unprepared; measured native history begins at the actual identity endpoint.
This bounded SVK law covers large proper rotations with small Green strain, not general rubber, large-stretch stability or finite-element material coupling. Generic Core summaries provide metrics/checks, not full measured F/P/A/W histories. Interpret a full history only from supplied same-record hash-bound artifacts; never pretend a summary measured an unavailable component or energy.
Registration, job and numerical optimizer tools are not available here. Numerical engines own candidate search. Preserve failed experiments, invalid metric values/reasons, engineering assumptions, independent UNKNOWNs and NOT_RELEASED. Solver completion and a comparison are not material, strength, physical, durability or release qualification.
Declared profile: $scope
"@
    }
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
