"use strict";

// Presentation admission from the server's declared capability; Core rechecks evidence.
(function (root) {
  function supportsBackend(preset, backend) {
    const allowed = preset?.parent_backends;
    return preset?.operation === "analysis_run" && typeof backend === "string" &&
      Array.isArray(allowed) && allowed.length > 0 &&
      allowed.every((name) => typeof name === "string" && name.trim().length > 0) &&
      new Set(allowed).size === allowed.length && allowed.includes(backend);
  }
  function eligibleParent(preset, record) {
    return supportsBackend(preset, record?.backend) &&
      record.status === "COMPLETED_REVIEW_REQUIRED" && record.solver_status === "NOT_RUN" &&
      typeof record.cad_revision === "string" && record.cad_revision.length > 0;
  }
  const api = { supportsBackend, eligibleParent };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.cadControls = api;
})(typeof window !== "undefined" ? window : globalThis);
