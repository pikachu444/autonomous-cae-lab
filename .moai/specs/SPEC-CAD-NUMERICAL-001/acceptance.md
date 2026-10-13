# User completion and bounded development checks

## AC-N01 — start from a saved user model

Open and save a supported two-body CAD/FE model. Select a geometry dimension,
load/displacement, material property and applicable contact coefficient in the
native variable picker, with their different units and search bounds. Create a
Numerical Plan directly and reopen it without a CAD, AI or solver run merely
to edit the Plan. Inactive/expression-controlled values explain their state.

## AC-N02 — evaluate real distinct candidates

An explicit DOE/search creates independent candidate inputs. Each selected
variable actually reaches the candidate CAD or exported physical deck. A valid
geometry change regenerates the relevant body mesh and validated face mapping;
an ambiguous topology change retains a failed editable candidate. An invalid
binding, failed mesher, solver failure and cancellation stay distinguishable.
The base and old results remain unchanged. Do not rerun unchanged solver suites.

## AC-N03 — inspect responses and continue editing the chosen design

Compare retained candidate values and actual selected response components,
units and reductions. Open Post for the exact candidate. Explicitly open a
successful candidate as a new native design, edit/recompute/save it and reopen
it. Close or change the original design and verify that the old candidate still
opens independently; neither source nor candidate retention is overwritten.

## Development timing

During implementation, use changed-owner unit checks for typed binding,
retention-before-failure, correspondence refusal, process cancellation and
branch opening. One small native preparation/execution check is appropriate
once the new candidate route exists. Wider multi-model numerical comparisons
and engineering reference qualification follow feature completion; they are
not a prerequisite for writing the variable picker or candidate/adoption path.

Status: requirements and independent design review prepared; implementation
assigned to actual Pro as PRO-CAD-NUMERICAL-01. No product implementation or
acceptance completion is claimed by this packet.
