# SVK finite-strain material-point acceptance

Use HYPERELASTIC_PACKET.md / ADR0026. This is large rotation/small Green strain
SVK, not general rubber or constitutive FE/physical qualification.

| Gate | Actual evidence | Current verdict |
| --- | --- | --- |
| Pure Domain |156 distinct cold Python3.12 checks; exact port/main import recheck | PASS source only, not312 tests |
| Independent math |59 checks,29 Decimal80 invariant-energy states/full9P/81Hessian/6Cauchy and correlated tamper controls | PASS bounded source,0openP1/P2 |
| Installed readiness |3002B/d97 tests source exact; TFEL5/MGIS3/options/compiler policy readonly checks | PASS availability only |
| Native adapter/common registry |Private adapter implementation; Core/wire/old material/inverse retained | ACTIVE, not registered |
| Actual compile/state/tangent/energy |New clean-source store,11endpoints/594signed probes/all3h/sameDLL MTest | NOT_RUN |
| Research/human inspection |Separate explicit admission and same-record GUI | NOT_ADMITTED / NOT_RUN |
| Physical/general rubber/FE coupling |Independent measured/stability/coupling qualification | UNKNOWN, NOT_RELEASED |

Record: benchmarks/records/20261003-svk-domain-development.json. The cold raw
example is SYNTHETIC_NOT_NATIVE. Initial t0 buffers remain unprepared; absent
dissipation/MTest energy stays UNKNOWN. Actual native W must remain separate
from derived analytical W; source/version alone does not prove binary identity.
Preserve all-h signed columns/endpoints/complete independent probe states and
reliable nominal-only updates. Do not change the frozen scientific thresholds.
Local raw hashes/compact public records do not establish remote raw durability.
