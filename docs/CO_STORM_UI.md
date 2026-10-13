# Expert conversation and Study reading

This is the first **product Qt screen correction** for CO-STORM-UI-CORRECTION-01.
It reuses the existing discussion/Study owners, jobs, sources, Numerical Plan
transfer and original-discussion result return. It does not replace them with
a prototype session or a web wrapper.

## What opens

**Expert:** the left column contains New / My conversations and the topic tree.
The center contains the actual saved participants' utterances, full body text,
Reply and source buttons. The selected utterance and its topic are linked.
The input stays below the transcript. Sources, proposals, actual participant
definitions and transmission settings open only when requested. UUIDs and
raw turn JSON remain in Technical details, not in the transcript.

- Select a topic to reach its saved utterances; select an utterance to highlight
  its topic. Reply selects that exact turn and focuses the input.
- **Send** records a user intervention without inference. **Start discussion /
  Send and discuss** requests the existing bounded registered-role round.
  **Pause** prevents dispatch of the next response; it does not cancel an
  already running response. **Continue** uses the existing resume/advance path.
- **Participants** opens the actual role selection and Role details. **Connection**
  opens the existing local setup. No provider is called by opening either.
- Select a source button to read the archived source. Selected local source
  revisions still use KnowledgeStore. Literature citations open their exact
  archived locator; an absent archive cannot silently fetch a replacement.
  Abstract-only content stays labelled abstract-only.
- Saved runtime result citations read their recorded response channels through
  the existing result service. An empty channel marker reads calculation status,
  not all responses. Runtime markers do not preserve the original row/time
  slice: this view must not claim that they do. The preview reads at most the
  existing reader's requested 256 rows.
- **Plans** opens the selected actual PLANNED proposal using the existing
  editable Numerical Plan transfer. Selecting a card/source never adopts or
  executes a proposal.

Inline answer text such as “[1]” is retained as authored. It is not automatically
turned into a source link because the existing runtime does not validate a
sentence-to-source-number map. The separate numbered source buttons address
the actual verified source list. No citations or utterances are fabricated.

**Study:** the main Evidence tab reads the selected saved Expert utterance or
calculated result. Series have a curve and Values table with units; scalar values
remain scalar. Invalid/masked samples leave gaps and retain their raw table
values. Failed candidates remain failed, with their reason, rather than zeroes.
The adjacent Judgment / notes tab retains the user's hypothesis/support/conflict/
decision controls. Technical draft remains available for unsupported authored
draft fields, without taking over ordinary reading.

- Reopening a supported saved Study selects its first evidence row.
- Selecting another evidence row clears the old content immediately. A delayed
  response cannot replace the new selection.
- Exact five-field result references and exact saved turn references still go
  through research_reference. A response selector requests a bounded view.
  With a legacy reference containing no channel, the first available ordinary
  response is visibly selected for preview; **Keep this response selection**
  is required to store it. Reading alone does not alter evidence or judgment.
- Native fields that require a location stay with their original result viewer;
  no guessed node, projection or scalar reduction is introduced here.
- Open original tool, Discuss, Next research, Apply, Save and Undo/Redo continue
  to use the existing owner/navigation contracts.
- An AVAILABLE reference now replaces the initial “not resolved” message.
  It does not change UNKNOWN research judgment or NOT_RELEASED.

## Source and implementation decisions

The official ACL Anthology paper was read, including §3 and the rendered UI on
PDF page 23 (Figure 12 in that published PDF). This is the conversation UI supplied
as Figure 15 in the arXiv v2 reference. The arXiv HTML/image fetch was unavailable
in the author environment; it is not recorded as an independently opened image.

- Paper: https://aclanthology.org/2024.emnlp-main.554/
- PDF: https://aclanthology.org/2024.emnlp-main.554.pdf
- Official source: https://github.com/stanford-oval/storm
  at fb951af7744dab086e34962e9bc6fe878e145f83,
  collaborative_storm/engine.py and modules/co_storm_agents.py.
- Existing product directions: PRODUCT_PLAN and PRODUCT_UI_MCP_PLAN §6.6.

The implementation follows the source's transcript/topic/input relationship in
native Qt. It does not copy its evaluation questionnaire, red study annotations,
hosted service or Streamlit stack. Existing QLabel/QTextBrowser/list widgets
keep selectable readable text and one transcript scrollbar; no new controller,
schema, document store or dependency is introduced.

One bounded shared HTTP change admits **archived-only literature.read** on the
existing assistance route. It requires an archive ID; remote fresh literature
retrieval still requires the existing managed job. Existing result reading and
knowledge-source access are reused. This does not grant model transmission
permission or operator configuration authority.

## Deliberately unfinished original-protocol work

This checkpoint is usable screen/source work, **not full Co-STORM completion or
user GUI acceptance**. The current topic tree is manually authored and the
runtime dispatches sequential registered roles. The following original-protocol
gaps remain in the same product scope:

1. Moderator choosing the next topic/role from unused retrieved material.
2. Source-grounded automatic mind-map insertion and reorganization.
3. User intervention changing the next context of an already frozen active
   round. Today it is a retained user turn; it does not rewrite that round.
4. Conversation/map → cited article operation, view and export.

No inactive Article tab or invented generated map is presented as working.
These are subsequent runtime/product tasks, not removed requirements. The
assembly research checkpoint remains separately preserved at 373000b; no
assembly product completion is claimed.

## Open and check the changed screens

Use the project's existing ResearchUI runtime and service, with actual saved
document IDs from that store:

    python -m apps.research.desktop --service http://127.0.0.1:PORT expert --document-id X...
    python -m apps.research.desktop --service http://127.0.0.1:PORT study --document-id S...

For a bounded changed-path check:

    python -m pytest tests/test_costorm_reading.py tests/test_costorm_ui.py -q

The tests use real document owners plus clearly labelled transport/response
test doubles. They check readable turns and reply/topic linkage, unchanged poll,
exact local citation selection, content/units/masks, stale asynchronous content
and preserved research judgment. They make no provider or solver call.

**Author execution: NOT_RUN.** The remote executor is disconnected. No new Qt
render, screenshot, native OS input, inference or user acceptance is claimed.
Root Codex performs Windows compilation/Qt rendering with the existing saved
four-turn/one-calculation material, reports the actual scope, and integrates.
Source publication precedes that execution so it can proceed immediately.
