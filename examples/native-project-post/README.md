# Post native project checks

`native_roundtrip.py` creates small public synthetic VTU/PVD data through the installed native readers. It covers the existing Post saved pipeline, retained A0 → B0/B1 history, current A1 cursor, exact time/array selection, explicit raw-state adoption, and the existing portable copy/head transaction. `partial_history.py` preserves an unavailable history without altering its original record or inventing a reader.

Run native phases only through `scripts/native_check.py` with an invocation-owned Job Object. Use a fresh short root such as `C:/np-post-demo` to avoid Windows native path limits. Existing user ParaView processes are not touched.

```powershell
python scripts/native_check.py --timeout 120 --output-dir _workspace/post-demo-create -- $pvpython examples/native-project-post/native_roundtrip.py create --root C:/np-post-demo
python scripts/native_check.py --timeout 180 --output-dir _workspace/post-demo-copy -- $python examples/native-project-post/native_roundtrip.py transaction --root C:/np-post-demo --pvpython $pvpython
```

`$python` and `$pvpython` must be absolute paths to the current local Python and installed ParaView executables. The transaction makes two cold native opens, temporarily renames only its own example folders, and restores those names in `finally`. No solver/provider is used. Explicit example Apply edits are counted separately from opening saved results; cold-open readbacks audit product Apply, Python process creation and Python network connections.

`first-save` exercises the saved import's new-target Save, same live document identity and publication-reply loss with one actual native Save. `partial_history.py run --root <fresh-root> --pvpython <absolute-pvpython>` performs its setup and both partial cold opens. `gui_open.py` exercises the standard GUI startup with an N0 private launch config; its native render does not prove OS mouse/keyboard interaction.

`repair_shared.py` creates one selected source shared by a primary reader, two auxiliary FileName slots and an existing retained reader. It verifies rollback after a controlled post-change verification failure, then actual same-content repair, unchanged history cores and native Save/head. `partial_history.py typed-save` exercises the actual typed native Save with controlled current-window consent callbacks: absent GUI and cancellation both perform zero Save calls; confirmation performs one. Controlled consent is separate from OS GUI clicking.

`saved-example/portable-project.json` is a complete synthetic saved-project copy produced by the actual first-save check. Its pure verification is READY with no execution. Copy the whole `saved-example` folder before opening it for editing. Historical paths in frozen originals are evidence strings; the current local installation and verified member map determine opening.
