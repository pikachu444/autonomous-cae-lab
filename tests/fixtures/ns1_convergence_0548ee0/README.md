# Supplied native convergence fixture (not a new run)

These five files are byte-for-byte copies of `reference_native_run` in the supplied
`source-0548ee0.zip`, baseline 0548ee06ec9c8b86064e6111925a972d3f2e4f67.
The task provider identified them as Codex's Windows FreeCAD 1.1.4 / CalculiX 2.22
run of the public block-j2.FCStd model. This implementation did not execute that
solver. There are ten converged increments and 25 CVG iteration rows.

`contact.inp`, `contact.cvg`, `contact.sta`, `ccx_contact.stdout.log`, and
`contact_execution.json` retain their original bytes, units, Windows paths and
provenance. The execution JSON refers to other artifacts **not included here**;
this is not a complete runnable attempt directory or an independently validated
physical benchmark. Tests copy only the required logs to fresh temporary folders.

Malformed/truncated, rejected, cancelled, and multi-step cases in tests are
explicitly synthetic and are not attributed to this actual run.
