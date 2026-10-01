"""Backend boundary. Core sees only these observations, never CAD syntax."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class Candidate:
    native: dict[str, str]
    label: str
    unit: str
    value: float
    lower: float | None
    upper: float | None
    source_sha256: str


@dataclass(frozen=True)
class FileRevision:
    """Adapter-prepared bytes; Core owns publication and recovery, not native syntax."""

    target: Path
    prepared: Path
    before_sha256: str
    after_sha256: str


@dataclass
class Outcome:
    decision: str
    checks: list[dict[str, Any]]
    generated: bool = False
    metrics: dict[str, dict[str, Any]] = field(default_factory=dict)
    pending_validations: list[str] = field(default_factory=list)
    native_revision: str | None = None
    source_sha256: str | None = None
    raw_result: str | None = None


class CADAdapter(Protocol):
    backend: str
    version: str

    def document_id(self, model: str) -> str: ...

    def discover(self, model: str) -> list[Candidate]: ...

    def probe_effect(self, model: str, candidate: Candidate, lower: float, upper: float) -> dict[str, Any]: ...

    def regenerate(self, model: str, native_values: dict[str, float], output: Path) -> Outcome: ...


class AnalysisAdapter(Protocol):
    """Solver-specific implementation behind a common research operation."""

    backend: str
    version: str
    analysis_type: str
    default_metrics: list[str]

    def solve(self, parent_result: dict[str, Any], parent_root: Path,
              output: Path, settings: dict[str, Any]) -> dict[str, Any]: ...


class DOEAdapter(Protocol):
    """Deterministic numerical design generator; no CAD or solver calls."""

    engine: str
    version: str

    def sample(self, variables: list[dict], *, count: int, seed: int
               ) -> tuple[list[dict[str, float]], dict]: ...


class OptimizationAdapter(Protocol):
    """Numerical search; Core supplies checked objective/constraint feedback."""

    engine: str
    version: str

    def describe(self, variables: list[dict], *, seed: int, max_generations: int,
                 population_size: int, initial_values: dict | None,
                 constraint_count: int) -> dict: ...

    def run(self, variables: list[dict], evaluate: Any, *, seed: int,
            max_generations: int, population_size: int, initial_values: dict | None,
            constraint_count: int) -> dict: ...


class ModelAnalysisAdapter(Protocol):
    """Declared geometry, mathematics or material models need no CAD parent.

    An optional pure describe_model(settings) supplies solver-independent model,
    boundary/load and output metadata. Numerical syntax stays in the adapter.
    """

    backend: str
    version: str
    domain: str
    physics_domain: str
    analysis_type: str
    default_metrics: list[str]

    def solve(self, output: Path, settings: dict[str, Any]) -> dict[str, Any]: ...


class PDEAdapter(ModelAnalysisAdapter, Protocol):
    """Compatible specialized name for declared mathematical PDE operations.

    A pure describe_model hook affects PDE metadata/revisions only with the
    explicit adapter attribute pde_model_declaration = True. Legacy adapters
    keep settings-only revisions even when they expose the shared hook.
    """


class ParameterizedModelAdapter(ModelAnalysisAdapter, Protocol):
    """Optional pure, named scalar bindings for declared-model campaigns.

    Input descriptors contain id, label, unit, value, lower, upper and trusted
    settings_path/declaration_paths lists of typed keys to existing scalar
    leaves. Core independently applies these locations and freezes all other
    context. Users select names, never supply native paths or code. Source
    files and the nonempty runtime identity are frozen before evaluations.
    """

    input_source_files: tuple[Path, ...]

    def describe_model(self, settings: dict) -> dict: ...

    def describe_inputs(self, settings: dict) -> list[dict]: ...

    def bind_inputs(self, settings: dict, values: dict[str, float]) -> dict: ...

    def input_runtime_identity(self) -> dict: ...


class CapabilityUnavailable(RuntimeError):
    """A backend has no executable adapter in this installation."""
