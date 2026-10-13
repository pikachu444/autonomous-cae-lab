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
Native chooser/content preview/attach are still being authored by the same Pro.
AC-EX01 and the complete GUI workflow remain pending; neither this checkpoint
nor a scripted response establishes whole Expert/Co-STORM completion or
engineering approval.
