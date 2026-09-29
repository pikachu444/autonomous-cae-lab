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


class CapabilityUnavailable(RuntimeError):
    """A backend has no executable adapter in this installation."""
