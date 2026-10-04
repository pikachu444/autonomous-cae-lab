# ADR 0033: Hand Lab questions to the existing official research control plane

Date: 2026-10-04. Status: accepted boundary; source, actual user flow and cancellation are separate acceptance gates.

## Problem

The Lab research form saved a Core study but did not submit its question to
OpenScience. Actual connected research existed through the owned launcher,
while an ordinary user could not reach that execution from this screen.
This gap does not invalidate the earlier bounded research evidence.

## Decision

Add a transport-level `research_run` job and read-only connection status to
the existing Lab service. The same single-writer, writable-store, request-token,
origin and cooperative-cancellation gates apply. This is not a new Core tool.
The bridge invokes the fixed official launcher through a trusted PowerShell
facade and passes the complete question through its existing UTF8 stdin path.
No command, filesystem path, provider, model, tool list or descriptor can be
supplied by a browser request.

The server owner configures one existing, verified Research runtime. Its
approved `openai-codex/gpt-5.6-sol`, canonical research descriptor, managed
project, source and writable store must match. Drift, a dead runtime or an
unavailable connector refuses new inference. Starting or replacing a runtime,
logging in, broadening a descriptor and switching models are separate actions.
In WSL, only trusted mounted-drive paths are mapped for the fixed Windows
executable. Credentials remain in their existing external profile.

A trusted optional cancellation callback extends the existing launcher. User
cancellation is recorded separately from timeout and preserves its exact
session abort, confirmed idle, owned CLI termination and retained raw output.
The existing source-identity resource also reports the actual resident writer
state without creating a store. Session idle and CLI exit alone cannot prove
that an underlying synchronous native tool has finished. The bridge additionally
requires this same-store resident to confirm idle before releasing its job gate.
It waits for existing tools to finish; forced in-flight solver cancellation is
not claimed by this observer. Unproved cleanup keeps admission closed. Existing callers retain their default
behavior. A trusted forced-stdin option also covers short user questions.

The research screen leads with a question and shows the connected model,
supported scope, actual response, tool status and links to the same stored
experiments. Metadata-only study creation remains available as a secondary
action. Follow-up questions reuse only a verified owned session; changed
conditions append experiments. Numerical engines continue to generate search
candidates. Returned prose, CLI completion, numerical verdict and engineering
approval remain distinct.

## Alternatives and requirement impact

Duplicating an LLM client in Lab would bypass the existing verified control
plane. Using the fixed acceptance drivers as request handlers would replace
the user's question with a test sequence. A link or clipboard alone would not
establish delivery, same-store execution or observed cancellation.

R02/R03/R05 retain control-plane, Core, Domain and adapter ownership.
R11/R13/R20/R21/R25/R33/R34/R43/R48/R51/R52 require exact questions, sessions,
source/store identity, real execution, independent review and preserved evidence.
The `FixtureScalar` descriptor still admits only its existing support/scalar
models; the original fixture assembly has no admitted public mechanics route.
Other descriptors and prior solver gates are unchanged. Whole52, wider research
planning, Phase6/7, physical qualifications and release remain open.

## Verification

Source gates exercise UTF8/argument preservation, ownership/store/source/model
drift, foreign sessions, single-writer/read-only refusal, partial responses,
confirmed and unconfirmed cancellation, and truthful browser controls.
After a reviewed committed source, a new shared store and owned runtime must
receive a real browser question, produce actual Core experiments and a readable
answer, then accept a changed-condition follow-up and observed busy cancellation.
The actual record must distinguish successful, failed and unverified parts.
UNKNOWN and NOT_RELEASED remain unchanged; no numerical criterion is relaxed.
