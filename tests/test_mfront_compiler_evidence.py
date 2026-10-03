"""Shared compiler log admission; renamed records are TEST ONLY parser inputs."""

import pytest

from caelab.adapters import mfront_hyperelastic_worker as worker
from test_mfront_hyperelastic import actual_compiler_case


def test_default_shared_classifier_preserves_exact_svk_records():
    text, compiler, flags = actual_compiler_case()
    assert worker.compiler_command_evidence(text, compiler, flags) == worker.compiler_command_evidence(
        text, compiler, flags, behaviour=worker.BEHAVIOUR)


def test_second_trusted_identifier_keeps_two_sources_five_stages_and_exact_link():
    """Renaming text evaluates the parser only, never MFront or a new law."""
    text, compiler, flags = actual_compiler_case()
    name = "SingleBranchMaxwell"
    renamed = text.replace(worker.BEHAVIOUR, name)
    records = worker.compiler_command_evidence(renamed, compiler, flags, behaviour=name)
    assert [row["stage"] for row in records] == ["DEPENDENCY", "DEPENDENCY", "COMPILE", "COMPILE", "LINK"]
    assert {row["source"] for row in records if row["stage"] == "COMPILE"} == {
        name + ".cxx", name + "-generic.cxx"}
    assert records[-1]["objects"] == [name + "-generic.o", name + ".o"]
    assert all(row["tokens"][0] == compiler for row in records)
    assert all("-O2" in row["tokens"] and "-fno-fast-math" in row["tokens"]
               for row in records[:-1])
    with pytest.raises(ValueError):
        worker.compiler_command_evidence(renamed, compiler, flags)
    with pytest.raises(ValueError):
        worker.compiler_command_evidence(text, compiler, flags, behaviour=name)


@pytest.mark.parametrize("name", (None, True, 5, "", "../SingleBranchMaxwell", "/foreign", "A;B", "A B", "A\nB", "한글", "A.mfront"))
def test_shared_classifier_refuses_foreign_or_malformed_source_identifier(name):
    text, compiler, flags = actual_compiler_case()
    with pytest.raises(ValueError, match="ASCII source identifier"):
        worker.compiler_command_evidence(text, compiler, flags, behaviour=name)


@pytest.mark.parametrize("kind", ("extra_compile", "wrong_object", "hidden_fast_math", "wrong_library"))
def test_second_identifier_does_not_relax_existing_exact_command_policy(kind):
    text, compiler, flags = actual_compiler_case()
    name = "SingleBranchMaxwell"
    text = text.replace(worker.BEHAVIOUR, name)
    if kind == "extra_compile":
        text += compiler + " " + " ".join(flags) + " foreign.cxx -o foreign.o -c\n"
    elif kind == "wrong_object":
        text = text.replace(name + "-generic.o", "foreign.o")
    elif kind == "hidden_fast_math":
        text = text.replace(" -M -Wall", " -M \\\n -ffast-math -Wall", 1)
    else:
        text = text.replace("-lTFELMath", "-lForeignMath")
    with pytest.raises(ValueError):
        worker.compiler_command_evidence(text, compiler, flags, behaviour=name)
