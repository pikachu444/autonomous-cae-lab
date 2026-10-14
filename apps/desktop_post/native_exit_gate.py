"""One fail-closed owner gate for Win32 and the native Qt close filter.

This module owns no document, file format, solver, timer, or save service.  It
uses Controls._state/_save and retains a short-lived, exact close permission.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Literal

DecisionName = Literal["allow", "block", "unknown"]


@dataclass(frozen=True)
class CloseDecision:
    decision: DecisionName
    reason: str
    stamp: tuple[Any, ...] | None = None
    saved: bool = False


class UnknownState(RuntimeError):
    pass


def _report(controls: Any, event: str, message: str, error: BaseException | None = None) -> None:
    # Neither a broken logger nor a broken error dialog may authorize a close.
    try:
        controls._log(event, **({"error": str(error)} if error is not None else {}))
    except BaseException:
        pass
    try:
        controls.platform.error(controls.main, message)
    except BaseException:
        pass


def _busy(controls: Any) -> bool:
    result = controls.busy()
    if type(result) is not bool:
        raise UnknownState("native work state is not a boolean")
    return result


def capture(controls: Any) -> tuple[bool, tuple[Any, ...]]:
    """Read on the GUI owner thread. Missing/unknown native state is not clean."""
    owner = controls.owner
    owner.assert_thread()
    if getattr(owner, "closed", False) or controls.closed:
        raise UnknownState("the owner or controls are closed")
    dirty, stamp = controls._state()  # Existing authoritative refresh/pending check.
    descriptor = owner.descriptor()
    if not isinstance(descriptor, dict) or type(descriptor.get("dirty")) is not bool:
        raise UnknownState("document dirty state is UNKNOWN")
    snapshot = owner.snapshot
    if not isinstance(snapshot, dict):
        raise UnknownState("native snapshot is not a mapping")
    if "fresh" in snapshot and snapshot["fresh"] is not True:
        raise UnknownState("native snapshot is not fresh")
    if not isinstance(owner.session_id, str) or not owner.session_id:
        raise UnknownState("missing owner session")
    if snapshot.get("session_id", owner.session_id) != owner.session_id:
        raise UnknownState("snapshot belongs to a different session")
    if hasattr(owner, "document_id"):
        if snapshot.get("document_id", owner.document_id) != owner.document_id:
            raise UnknownState("snapshot belongs to a different document")
        if descriptor.get("id", owner.document_id) != owner.document_id:
            raise UnknownState("descriptor belongs to a different document")
    # A native registration requires the full production Owner contract. The
    # small legacy Win32 Controls adapter also supports its existing fake owners.
    if getattr(controls, "require_save_receipt", False):
        for key in ("generation", "view_generation"):
            if type(snapshot.get(key)) is not int or snapshot[key] < 0:
                raise UnknownState("missing native revision: " + key)
            if snapshot[key] != getattr(owner, key, None):
                raise UnknownState("inconsistent native revision: " + key)
        if snapshot.get("fresh") is not True:
            raise UnknownState("missing native freshness")
    extra_reader = getattr(controls, "close_fingerprint", None)
    extra = extra_reader() if extra_reader is not None else None
    receipt = tuple(getattr(owner, name, None) for name in
                    ("saved_revision", "saved_generation", "saved_view_generation"))
    # Canonical JSON rejects NaN and opaque values rather than silently accepting
    # an object repr as an engineering-state equality test.
    extra_stamp = json.dumps(extra, sort_keys=True, separators=(",", ":"), allow_nan=False)
    native_pending = False
    if isinstance(extra, dict) and "native_draft" in extra:
        native_pending = extra["native_draft"]["unapplied"]
        if type(native_pending) is not bool:
            raise UnknownState("native widget draft state is unknown")
    return bool(dirty) or native_pending, (owner.session_id, stamp, receipt, extra_stamp)


def _saved_receipt(controls: Any) -> None:
    if not getattr(controls, "require_save_receipt", False):
        return
    owner = controls.owner
    revision = getattr(owner, "saved_revision", None)
    if not isinstance(revision, str) or not revision:
        raise UnknownState("save did not publish a committed revision")
    for saved, current in (("saved_generation", "generation"),
                           ("saved_view_generation", "view_generation")):
        if type(getattr(owner, saved, None)) is not int:
            raise UnknownState("save did not publish " + saved)
        if getattr(owner, saved) != getattr(owner, current):
            raise UnknownState("the saved revision is no longer current")


def decide(controls: Any) -> CloseDecision:
    """Modal choice, save, and verification. Only literal allow is permission."""
    if controls.closed:
        return CloseDecision("unknown", "owner_closed")
    if controls.in_action:
        return CloseDecision("block", "reentrant")
    controls.in_action = True
    try:
        controls.owner.assert_thread()
        if _busy(controls):
            _report(controls, "native_close_busy", "현재 작업이 끝난 뒤 창을 닫으세요.")
            return CloseDecision("block", "busy")
        dirty, stamp = capture(controls)
        if not dirty:
            return CloseDecision("allow", "clean", stamp)
        choice = controls.platform.ask_close(controls.main)
        if choice == "cancel":
            return CloseDecision("block", "cancel")
        if choice not in ("save", "discard"):
            return CloseDecision("unknown", "unknown_choice")
        if _busy(controls):
            _report(controls, "native_close_busy", "현재 작업이 끝난 뒤 창을 닫으세요.")
            return CloseDecision("block", "busy_after_dialog")
        if capture(controls)[1] != stamp:
            _report(controls, "native_close_changed",
                    "닫기 선택 중 내용이 바뀌었습니다. 현재 창을 유지합니다. 다시 확인하세요.")
            return CloseDecision("block", "changed_during_dialog")
        if choice == "discard":
            return CloseDecision("allow", "discard", stamp)
        pending_reader = getattr(controls, "close_pending_inputs", None)
        if pending_reader is not None:
            pending = pending_reader()
            if type(pending) is not bool:
                raise UnknownState("native unapplied input state is unknown")
            if pending:
                _report(controls, "native_close_unapplied_inputs",
                        "적용하지 않은 입력이 있습니다. Properties에서 입력을 완료하고 적용 또는 되돌리기를 선택하세요.")
                return CloseDecision("block", "native_unapplied_inputs")
        if not controls._save():  # Existing Owner.save_project; never SaveState/SaveData.
            return CloseDecision("block", "save_failed")
        dirty, saved_stamp = capture(controls)
        if dirty or _busy(controls):
            _report(controls, "native_close_changed_after_save",
                    "저장 후 새 변경 또는 진행 중인 작업이 있습니다. 현재 창을 유지합니다.")
            return CloseDecision("block", "changed_after_save")
        _saved_receipt(controls)
        return CloseDecision("allow", "saved", saved_stamp, saved=True)
    except BaseException as error:
        _report(controls, "native_close_failed",
                "현재 상태를 확인하지 못했습니다. 창을 유지합니다.", error)
        return CloseDecision("unknown", "state_or_callback_failed")
    finally:
        controls.in_action = False


def validate(controls: Any, permission: CloseDecision | None) -> CloseDecision:
    """Recheck after the stock close handler. Never show a second save prompt."""
    if permission is None or permission.decision != "allow" or permission.stamp is None:
        return CloseDecision("unknown", "no_close_permission")
    try:
        controls.owner.assert_thread()
        if _busy(controls):
            return CloseDecision("block", "busy_before_close")
        if capture(controls)[1] != permission.stamp:
            _report(controls, "native_close_permission_expired",
                    "종료 처리 중 내용이 바뀌었습니다. 현재 창을 유지합니다. 다시 확인하세요.")
            return CloseDecision("block", "permission_expired")
        if permission.saved:
            _saved_receipt(controls)
        return permission
    except BaseException as error:
        _report(controls, "native_close_validation_failed",
                "종료 전 상태를 확인하지 못했습니다. 현재 창을 유지합니다.", error)
        return CloseDecision("unknown", "validation_failed")


def unchecked_fingerprint(native: Any) -> list[dict[str, Any]]:
    """Fingerprint actual unchecked values, not only pending property names.

    Reads the existing sources/views/representations/LUTs. It creates no proxies,
    applies no Properties and never executes an UpdatePipeline or a solver.
    """
    proxies: dict[str, Any] = {}
    candidates = (list(native.GetSources().values()) + list(native.GetViews()) +
                  list(native.GetRepresentations().values()))
    for proxy in list(candidates):
        lookup = getattr(proxy, "LookupTable", None)
        if lookup is not None:
            candidates.append(lookup)
    for proxy in candidates:
        identifier = proxy.SMProxy.GetGlobalIDAsString()
        if not isinstance(identifier, str) or not identifier:
            raise UnknownState("native proxy has no stable ID")
        proxies[identifier] = proxy
    result = []
    for identifier, proxy in sorted(proxies.items()):
        fields = {}
        for name in sorted(proxy.ListProperties()):
            prop = proxy.GetProperty(name).SMProperty
            if prop.GetInformationOnly():
                continue
            data: dict[str, Any] = {}
            if hasattr(prop, "GetNumberOfUncheckedElements"):
                data["values"] = [prop.GetUncheckedElement(i)
                                  for i in range(prop.GetNumberOfUncheckedElements())]
            if hasattr(prop, "GetNumberOfUncheckedProxies"):
                refs = []
                for i in range(prop.GetNumberOfUncheckedProxies()):
                    ref = prop.GetUncheckedProxy(i)
                    refs.append(None if ref is None else ref.GetGlobalIDAsString())
                data["proxies"] = refs
            if hasattr(prop, "GetMTime"):
                data["mtime"] = int(prop.GetMTime())
            if data:
                fields[name] = data
        result.append({"id": identifier, "fields": fields})
    return result
