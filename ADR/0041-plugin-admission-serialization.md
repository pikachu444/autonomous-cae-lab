# 0041 — Serialize native-plugin admission, keep execution independent

Status: Accepted, 2026-10-06. Requirements R01–R03, R19–R21, R43, R48, R52.

The clean774 fixture search produced9 CAD/9 CalculiX results, but18 summary
queries submitted in one research step included9 PROJECT_FILESYSTEM_READ_FAILED
refusals. Their identity/session checks passed. Some concurrent final source
checks took5.7–8.4s while loopback filesystem reads retain a5s deadline.
Native event-loop contention is a concrete candidate; the historical refusal
does not isolate timeout versus HTTP/parse failure. Preserve all9 raw failures.

Each loaded CAE native plugin now queues its complete pre-operation admission:
metadata, source capture, metadata refresh, final bytes, current guard/model/
arguments and receipt. Waiting calls acquire no cached approval: every call
starts its existing checks afresh. A refusal reaches its original caller and
releases the queue. The queue ends before tool execution. This does not lock
Core, the repository, HTTP jobs, the MCP resident or a native solver, and cannot
create a parent-waits-for-MCP store lock. No timeout, source/grant requirement,
canonical research profile, solver threshold or release rule is relaxed.

Serializing only individual GETs leaves another admission's synchronous final
check able to block the server. Increasing the metadata timeout merely hides
contention. Reusing one call's approval risks stale grants/source/stopping.
These alternatives were rejected. Latency for a large batch remains a separate
usability issue; this change does not establish active cancellation/reconnect.

Source controls: mixed18 admissions, rejection recovery and queued grant/source/
stopping drift; full guard344PASS/14SKIP and Lab557PASS. Independent read found
0P1/P2 in the four changed guard/table files. Actual clean-source retained18
summary reading is the next gate; no solver needs replay for that gate.

The paired UI correction preserves the original answer and safely tokenizes
escaped pipes/matched code spans, so the same9 results form a7-column table.
Actual saved-answer GUI and best candidate's13226-node field are inspected;
source-only tests are separate from native/provider qualification. Every
analysis still retains6PASS/7UNKNOWN, invalid stress and NOT_RELEASED.
