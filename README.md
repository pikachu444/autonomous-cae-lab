# Autonomous CAE Lab

A local-first engineering research workbench: use existing numerical tools,
material models, solvers and data analysis through a common working environment.
CAD-based design is one use case, not the definition of the product. Optional
expert assistance combines project knowledge, literature and engineering tools.

## Current development direction

Read [the workbench redesign and implementation plan](docs/WORKBENCH_REDESIGN.md).
It separates verified implementation from target behavior and identifies the
next coherent improvement bundle. [AGENTS.md](AGENTS.md) is the development entry
point; cumulative historical records are no longer mandatory startup reading.

Python/API and CLI are the primary computation interfaces. OpenScience and MCP
are optional integrations in the target architecture. Existing code already has
CAD-free model/PDE interfaces and SciPy-based search, but portable installation,
extension, runtime admission and performance still need work. This documentation
change does not claim that those improvements have been implemented.

## Existing code and usage

- `caelab/`: Python API, CLI, experiments, numerical drivers and backend adapters.
- `plugins/`: domain-specific models/checks and the reused fixture implementation.
- `apps/lab/`: local human interface and existing job coordination.
- `openscience/`: current MCP and OpenScience integration; not the intended owner
  of the numerical core.
- `tests/`, `scripts/`, `benchmarks/`: existing checks and recorded examples.

Existing environment instructions remain in [local execution](docs/LOCAL_EXECUTION.md)
and [OpenScience use](docs/OPENSCIENCE_USE.md). They describe specific historical
installations; confirm applicable paths, dependencies and current code before use.
The CAD demo is not the complete product. No universal clean-install or current
native-solver qualification is asserted here.

Older status histories, architecture decisions and execution records remain
available for targeted reference. They must not override the current owner-approved
direction or be mistaken for measurements from the latest checkout.

Do not commit credentials, company models, private reports or experimental data.
