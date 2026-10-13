# Focused user checks

Use public tiny Markdown/CSV and an existing PDF extraction fixture. No private
company documents or credentials. No model call is required to check source work.

1. New Expert → enter question and roles → import local file → preview actual
   extracted content → attach. Existing composer text remains. Canceling a source
   selection does not change the composer; explicitly imported library items remain.
2. Add an existing library source, remove one, Apply/Undo/Redo, Save and reopen.
   The same content, question, selected roles and exact result attachments remain.
3. Update/revoke a source outside the discussion. The old saved selection either
   resolves its permitted exact revision or offers an explicit repair; Request
   round cannot silently switch content. Unrelated sources are excluded.
4. Missing file, unsupported type, empty/scanned PDF and failed import show an
   actionable error. The question and already selected sources stay editable.
5. With provider unavailable, save and add a user intervention; no fabricated AI
   turn or paid fallback. A controlled test response can check round freezing and
   citations but must be labelled as a test double.
6. If a currently authorized free inference path is independently confirmed,
   perform one bounded round and inspect actual cited source content and proposal
   navigation. Otherwise record live inference as not run, retain the requirement,
   and continue other product work.

## Backend checkpoint — 2026-10-13

Actual Pro authored `7090d1c`, integrated as `c409665`. Codex ran
`python -m pytest tests/test_expert_sources.py -q` in the owned Windows runtime:
4 passed in 5.42s. Existing archive/BM25/JobManager paths were exercised; model
generators and OpenScience host were explicit doubles, with no live inference.
The tests cover exact source revisions, exclusion of unselected content from
retrieval/history/delegation, explicit transmission scope, import, saved draft
reopen and blocked legacy-round recovery. Astra/xhigh independently reviewed the
eight changed files and found no actionable source defect; it ran no UI or tests.

This partially addresses AC-EX02/03 and the source boundary behind AC-EX04.
Native chooser/content preview/attach arrived in Pro `5037e46` (main `1170af4`).
The new `tests/test_expert_sources_ui.py` checks passed 4/4 in 6.57s over actual
Qt/local HTTP/archive, with only file-dialog path choice replaced. One additional
legacy-harvest test passed in 1.75s. A shutdown worker exception occurred after
the Qt assertions and was sent to Pro. Root also imported public
Markdown/text PDF/CSV and rendered the actual chooser and saved discussion with
three sources, an editable question and no configured provider. It exposed a
reopen title-prefetch race; Astra found periodic refresh clearing selection.
Pro's correction `5d6b970` (main `e1903e6`) addresses worker delivery after close,
title-prefetch retry, exact selection preservation during polling and preview
ownership across discussion changes. The revised four Qt checks passed in 6.50s,
with active polling, historical-citation reading after deselection, owner switch
and late-worker cleanup; the shutdown exception did not recur. Root checked the
actual three-file render after deferred title reads settled: all source names
and the selected original text were visible. Source:
`runs/product-development/20261013/expert-preview-886155b1/receipt.json`.

The bounded local-source feature is implemented. Astra identified the two UI
findings on the earlier source; Codex checked the corrections by source and
execution, without claiming a second Astra pass. Complete OS/DPI usability and
actual authorized inference remain unverified. Neither this checkpoint
nor a scripted response establishes whole Expert/Co-STORM completion or
engineering approval.
