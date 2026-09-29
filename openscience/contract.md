# OpenScience ↔ CAE-Lab contract v1

OpenScience owns the research request and interpretation. The CAE-Lab process owns execution and evidence. A request names a `study_id`, `experiment_id`, generic `model` reference and **registered research IDs** in `values`; it never passes FreeCAD property syntax or a solver deck. The current adapter supports `fixture.cadquery` and trusted registered model `roller_support` or another source model in the pinned fixture plugin.

1. `study.create(id, name, research_question, hypothesis, objective)` → persisted study.
   `study.inspect(id)` resumes a prior study.
2. `parameters.discover(backend, model)` → candidate native metadata for human registration; OpenScience should display user-facing labels. Discovery is read-only.
3. `parameters.register(study_id, backend, model, native_path, parameter_id, display_name, lower, upper, mode, kind)` → mapping plus geometry-effect probe. Native path appears only at the registration boundary, not in subsequent experiments.
   `parameters.list(study_id)` returns the versioned mapping.
   `parameters.refresh(study_id, backend, model)` rechecks existing mappings after a native CAD source revision and writes new registry history.
4. `experiment.run(study_id, experiment_id, backend, model, values, hypothesis_id?, settings?)` → persisted result. Duplicate IDs are refused, and `FAIL` prevents later work.
5. `experiment.inspect(experiment_id)` → full schema including artifact hashes. `experiment.summary(experiment_id)` → concise outcome, metric values, failed and unknown validation types and result reference. `experiment.compare(ids)` → summaries.

The Python API is `caelab.Lab`. The CLI maps the same operations to `python -m caelab`. JSON schemas under `schemas/` define the common envelopes. `openscience/mcp_server.py` is a thin local stdio transport using the official MCP Python SDK; it does not implement engineering logic. The server store is selected by `CAELAB_STORE`, not an argument that a model can point at an arbitrary filesystem path. The `openscience.json.example` shows project configuration; its absolute paths and OpenScience identity need confirmation in a real installation.

`status=COMPLETED_REVIEW_REQUIRED` says the CAD transaction ran and its checks are recorded. `decision=NOT_RELEASED` is retained while any machine/strength/physical/durability requirements are unknown. `status=REJECTED` can be an intended invalid-design observation, not a process crash. `FAILED_EXECUTION` marks a backend error. The OpenScience agent must follow the result's evidence IDs rather than interpreting a tool exit code as engineering approval.

No live OpenScience call was performed in the current environment. The product identified from official sources is provisionally [Synthetic Sciences OpenScience](https://github.com/synthetic-sciences/openscience). It supports local stdio MCP project connectors, but the CLI is not installed here. Live acceptance requires connecting this MCP server, reading a tool trace and verifying both valid and invalid runs in the CAE-Lab store.
