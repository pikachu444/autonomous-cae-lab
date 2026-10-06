"""Select a recorded field response; native interpretation remains in adapters."""

from .response_history import _read_native


def selected_response(lab, result, proposal, selection):
    from .adapters.structural_response_fields import select_field_response

    # The enclosing comparison verifies result/proposal/thread and all retained
    # artifacts before and after this read. Never accept a caller's physical value.
    raw, artifact = _read_native(lab, result, selection["artifact"])
    if artifact["sha256"] != selection["sha256"]:
        raise ValueError("Selected field hash does not match the recorded artifact")
    return select_field_response(result, proposal, raw, artifact, selection)
