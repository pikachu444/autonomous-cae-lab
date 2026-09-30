"""Compatible PDE operation over the shared declared-model experiment runner."""

from .declared_model import run_declared_model


def run_pde(lab, *, study_id: str, experiment_id: str, backend: str,
            settings: dict, hypothesis_id: str | None) -> dict:
    adapter = lab.pde_adapters.get(backend)
    # A shared describe_model method may already exist on a legacy adapter.
    # Only an explicit PDE opt-in may change its historical revision identity.
    description = (getattr(adapter, "pde_model_declaration", False) is True and
                   callable(getattr(adapter, "describe_model", None)))
    return run_declared_model(lab, study_id=study_id, experiment_id=experiment_id,
                              backend=backend, settings=settings, hypothesis_id=hypothesis_id,
                              adapters=lab.pde_adapters, namespace="pde", output_directory="pde",
                              description=description)
