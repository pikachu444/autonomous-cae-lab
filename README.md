# Autonomous CAE Lab

A local engineering research workbench for material histories, parameter fitting,
numerical studies, existing solver results and optional expert assistance. Python
calculations do not require CAD, an AI account, OpenScience or MCP.

## Install and start

**Windows 10/11 x64, without WSL:** download and extract the repository ZIP,
then double-click `Start-CAE-Lab.cmd`. It installs a private Python environment
and opens the workbench. Internet is required; system Python, Git and admin
rights are not required for the base/numerical/material features. Keep the
extracted source folder. Native CAD/solvers and expert accounts are separate.
See the [Windows quick start and supported scope](docs/WINDOWS_QUICKSTART.md).

For manual installation on Linux or Windows, Python 3.12+ is required.
From a source checkout:

```bash
git submodule update --init --recursive
python -m venv .venv
# Linux/macOS; on Windows use .venv\Scripts\Activate.ps1
source .venv/bin/activate
python -m pip install -e '.[numerical,material]'
caelab doctor --backend material.felupe
caelab serve --store ./runs/my-research --port 8766
```

Open **http://127.0.0.1:8766/workbench**. Upload a table, declare its channels and
units, edit a material loading history, fit independent experimental curves or
run a DOE. The same page shows execution history, cancellation, actual response
curves, comparisons and downloadable HTML reports. Synthetic teaching inputs are
explicitly labeled. The original `/` interface remains available for existing
CAD records and workflows.

| Extra | Adds | Optional runtime/license consideration |
| --- | --- | --- |
| none | NumPy, direct API, retained-result reading, local service | No CAD/AI import on discovery |
| `numerical` | SciPy fitting, DOE, search, statistics, RBF surrogate | BSD; no solver or model account |
| `material` | FELUPE material-point laws and tangent responses | FELUPE GPL-3.0; review distribution obligations |
| `cad` | Existing CadQuery fixture integration | Native FreeCAD remains separately installed |
| `native-mechanics` | Gmsh Python dependency | CalculiX/other native solver runtimes installed separately |
| `sensitivity` | SALib matched Sobol sampling/analysis | Separate from ordinary DOE regression influence |
| `assist` | Haystack retrieval/agent integration and PDF text | Explicit model/runtime configuration; no fallback |
| `mcp` | Official MCP SDK transport | Connects to an existing service |
| `dev` | Pytest, browser testing and PDF test dependencies | Chromium separately installed |

A wheel can be built with `python -m pip wheel --no-deps .`. A separate clean
installation of the base wheel was tested without CAD, SciPy, FELUPE or MCP.
For preserved native backends use the source checkout and their documented
runtime settings; a Python extra does not install or qualify every native solver.
Existing native runtime instructions are in [local execution](docs/LOCAL_EXECUTION.md).

## Direct calculation and saved results

```python
from caelab import evaluate, prepare, run, read_result

settings = {
    "model": "linear_elastic", "parameters": {"E": 1500., "nu": .29},
    "stress_unit": "MPa", "time_unit": "s", "time": [0., 1.],
    "deformation_gradient": [
        [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
        [[1.002, 0., 0.], [0., 1., 0.], [0., 0., 1.]],
    ],
}
response = evaluate("material.felupe", settings)
with prepare("material.felupe", settings) as model:
    first = model.evaluate({"E": 1200.})
    second = model.evaluate({"E": 1800.})
run("material.felupe", settings, output="runs/material-result")
restored = read_result("runs/material-result", selection=["stress_xx"])
```

`evaluate`/`prepare` perform no mandatory recording. A trusted Python callable
`function(values, settings)` returning named responses can use the same numerical
APIs without registration. Each prepared resource is owned by one caller; process
workers prepare their own resources. `run` requires a new output directory.
`read_result` reads retained JSON/NumPy arrays without the originating solver or AI.
It supports response selection, component/location filters, row/time ranges and
selected/all hash verification. Units, component, location, reduction and axis
meaning stay attached to responses. Missing values are never substituted with zero.

CLI equivalents:

```bash
caelab backends
caelab evaluate --backend material.felupe --settings my-history.json
caelab run --backend material.felupe --settings my-history.json --output runs/result-01
caelab read runs/result-01 --response stress_xx
caelab fit --backend material.felupe --plan my-fit.json --output runs/fit-01
caelab submit --operation doe --arguments my-managed-doe.json --request-id study-01
caelab job J_REPLACE_WITH_RETURNED_ID
```

## Numerical research

`caelab.numerical` exposes `fit_model`, `run_doe`, `optimize`, `analyze_candidates`,
`run_uq`, `fit_surrogate`, `epsilon_optimize`, `sample_sensitivity`,
`analyze_sensitivity`, `compare_curves` and `detect_event`/`compare_events`.
Variables declare names, units, bounds, initial values and linear/log transforms.
Fit experiments separately declare loading settings, response, observations,
weight, residual scale, mask and `fit`/`holdout` role. Holdout histories never tune
coefficients. Series objectives require an explicit reduction such as `max` or
`final`; response labels alone do not perform a reduction.

```bash
python examples/workbench_numerical.py --output runs/numerical-example
```

This runnable example produces a real FELUPE multi-history fit and holdout plot,
SciPy search/DOE/statistics, uncertainty results, RBF confirmation, epsilon/Pareto
results, identified file exchange and measured timing/I/O. Its observations are
synthetic; fitting them is an integration check, not material qualification.
Measured results and limitations are in [the current progress record](docs/WORKBENCH_PROGRESS.md).

`execution={"mode": "process", "workers": 2, "threads": 1,
"max_evaluations": 100}` requests separate prepared workers and a hard total
model-evaluation cap. Fit finite differences and holdout consume that same cap.
A whole finite-difference group may stop with unused budget when it cannot fit.
Serial and explicitly supported batch evaluation are also available. Memory is a
reservation hint, not OS isolation. Small material calculations can be faster
without processes; measured timings make no general speedup claim.

Recorded native numerical studies use
`caelab.adapters.native_evaluation.NativeEvaluationFactory(backend, output)` and
the existing checked `describe_inputs`/`bind_inputs` boundary. The managed service
selects this explicit file path for parameterized native adapters. Adapters
without declared mutable inputs support their existing single-run API; they do
not silently become parameterized. Actual native runtime availability remains
backend-specific.

## Existing results and external solvers

`files.table` imports CSV, whitespace/fixed-width text (including Fortran D
exponents) and named one-dimensional arrays in NPZ. Declare `columns` with
`column`, `unit`, `component`, `location` and optional axis mapping. Scaling and
offset are explicit. Repeated/restarted axes need separately selected segments;
unknown native block formats need an operator-supplied extractor.

Three modes are distinct:

- Import and analyze already generated results, without running their solver.
- `export_batch`/`import_batch` exchange candidates and match actual returned
  candidate ID, case ID and parameter values. Missing candidates stay unevaluated.
- Register an operator-owned external command, optional extraction command,
  templates, numeric bounds and output mapping. Each real candidate gets an owned
  directory and cancellation-aware process. HTTP/MCP cannot supply executable
  paths or arbitrary commands. Workspace registrations stay workspace-local.

`caelab.adapters.external_files.register_external_backend` is available to trusted
Python callers. Managed registration uses `external_backends` in the operator
configuration passed to `caelab serve --workbench-config config.json`. Each entry
contains `variables`, `command` (argv list), `result` (path and mapping), optional
`templates` (`source`, `destination`), `extractor`, `threads` and `timeout`.
A template uses `$variable` placeholders; source inputs are preserved. LS-OPT is
not required or used. This is a generic connection, not a qualified commercial
solver card or a claimed company LS-DYNA execution.

## One managed workspace and optional experts

A workspace has one controller process. HTTP, CLI and MCP share job IDs,
idempotent request IDs, result references and cancellation. Restarted unfinished
jobs become `INTERRUPTED`; they are neither replayed nor adopted by recorded PID.
Cancellation remains requested until a safe checkpoint/owned process exit.
Unconfirmed cleanup retains the controller reservation. Direct synchronous Python
runs remain independent and use their own result paths.

For optional retrieval and experts:

```bash
python -m pip install -e '.[assist,mcp]'
caelab serve --store runs/research --workbench-config examples/workbench_config.json
```

The example config enables named expert roles with **no configured model**.
Documents can be uploaded, archived/versioned, indexed and searched using Haystack
BM25; source locators reopen original excerpts. Revoked documents are excluded
from subsequent contexts. PDF extraction is text-only: scanned text, equations,
tables and figures may remain unread. Literature search currently uses Crossref;
metadata discovery, actual public-text reading and knowledge import are separate.

To connect an approved OpenAI-compatible endpoint, set `runtime.provider`,
`model`, `api_base_url` and `credential_env` in an operator-local config. Keep the
credential itself in that environment variable. Explicit `transmission` policy
controls external questions, collections, result data and public literature.
The caller's selected documents/results and transmission scope must also permit
the transfer. No provider fallback, purchasing or automatic account login occurs.
Per-role `expert_models` can choose separately configured models without expanding
access. See `RuntimeConfig` in `caelab/assist/experts.py` for bounded call/tool/time
settings and `examples/workbench_experts.json` for roles.

Experts use the real Haystack tool loop to retrieve, interpret actual results,
consult an explicitly permitted second expert and propose editable numerical
plans. Authorized execution additionally requires backend, variable/range,
evaluation and resource scopes. Planning is not execution. A missing model
returns `NOT_CONFIGURED`. Live model/host verification was unavailable in this
cloud session; mocked generator tests are labeled accordingly.

For MCP set `CAELAB_SERVICE_URL=http://127.0.0.1:8766` and run
`python -m openscience.workbench_mcp`. Use the official SDK client configuration
in [workbench.json.example](openscience/workbench.json.example), or the generic
[OpenScience example](openscience/openscience.json.example). The transport does not
construct another controller. Old generated ResearchProfile launchers, copied
scenario guards and fixed model/tool-count restrictions were removed. The older
Study-oriented stdio entry remains an explicitly isolated compatibility API;
setting `CAELAB_SERVICE_URL` delegates that entry to the shared workbench too.

## Checks and development

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e '.[numerical,material,assist,sensitivity,mcp,dev]'
python -m pytest -q
node --test tests/*.js openscience/tests/native_git_state.test.mjs
python scripts/verify_mcp.py
python scripts/verify_workbench_ui.py --help
```

The browser script starts/stops its own service and tests material fit/holdout,
DOE, actual influence, CSV mapping and report download. Chromium must be installed
(or pass `--browser-executable`). Native CI jobs retain their scientific reference
checks; no local mock certifies a native solver or actual product-host connection.

Development starts with [CODEX_START.txt](CODEX_START.txt), [AGENTS.md](AGENTS.md),
[W1–W5 design](docs/WORKBENCH_REDESIGN.md), [use cases](docs/WORKBENCH_USE_CASES.md)
and [workflow](docs/CODEX_WORKFLOW.md). Historical execution records remain intact.
The single current implementation/progress record is
[WORKBENCH_PROGRESS.md](docs/WORKBENCH_PROGRESS.md).
