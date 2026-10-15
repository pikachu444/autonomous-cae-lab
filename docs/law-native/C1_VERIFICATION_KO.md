# LAW-C1 검사 범위와 원 실패 보존

## 입력 확인

원 correction 문서, 150563B frozen-simulation.json, 434930B 공식 FELUPE wheel과 첫 LAW ZIP/원 source ZIP을 실제 열고 확인했다. 원 source ZIP 4175702B, 지정 SHA256 ee331d10e9fc4c4daf7d5095e2eee3a42d4b795eb2192d07c79f7f37563c4d4f 및 ZIP CRC가 맞았다. 첫 LAW ZIP SHA256 51827aa3076e82190d52dc7838a70fa1f1fd964bc74946d0b533f69986e7b432도 맞았다. 첨부 원문/원 frozen bytes는 변경하지 않는다.

## 세 종류의 증거를 구분

**사용자가 보고한 원 Windows 실패.** Job Jbb0d8ff23fa642779dfb615ae00300fa, Simulation V54701bb407d9424a9b9392393a44def4. `simulation.run/FAILED`, `ValueError: Use an uploaded input reference, not a server path`, FE NOT_RUN/result_refs=[]다. 원 Job 파일 bytes와 원 specimen.FCStd는 첨부되지 않았다. correction 문서의 기록을 보존하며 해당 파일을 직접 검사했다고 주장하지 않는다. `This job has no retained result`는 바깥쪽 후속 읽기 오류이지 최초 원인이 아니다.

**교정 전 Linux 재현.** 첫 LAW 반환을 원 source에 적용한 baseline에서 같은 frozen JSON을 기존 Simulation owner로 실행했다. 새 Linux Job J45de7da9c72247ef890fa2db653d672e가 같은 경로 거절로 solver 전에 FAILED, 결과 참조 0개였다. 이 새로운 재현 실패를 원 Windows Job 또는 새 성공으로 바꾸지 않았다. `evidence/baseline-failure/`와 그 process receipt에 보존했다.

**교정 후 Linux 실제 실행.** 제공 wheel을 --no-index --no-deps로 실제 설치한 뒤 exact 원 frozen 파일로 기존 Simulation 경로를 실행했다. 실제 FELUPE 11.1.3/NumPy 2.3.5/SciPy 1.17.0/Python 3.13.5 환경이다. 별도 신규 solver/optimizer/store는 없다. 실제 실행 1회와 별도 Python cold 1회를 `evidence/c1-exact/`에 보존했다.

## 실제 DP FE/save/cold 결과

| 항목 | 실제 결과 |
|---|---|
| Simulation 문서 | V781868cbaab74314bb14374503ad7514 |
| 새 FE Job | J54c1b48b35f14cdc9b71a5c3588282a6 — SUCCEEDED |
| 저장 개정 | Ra1e6b39f0ded4367bc3f836e2f36d623 |
| 두 _settings 진입 | 모두 원 settings 그대로 통과; hash 068c46a55544a960ecdd36ed70ca16e24ff95d3fe23e2f664118398bec7cd33b |
| 공간 FE | 실제 8Hex8, 각 시점 64적분점, 4시점, 내부 자유도 3, global Newton 3회 |
| 최대 자유도 평형 잔차 | 8.101433657963767e-14 N; 원 기준 1e-8 N 유지 |
| 모든 적분점 최대 stress 차이 | 5.5622980307516024e-14 MPa; 원 각 시점 absolute+relative 기준 유지 |
| 모든 적분점 최대 F 차이 | 2.6020852139652106e-18; 원 기준 2e-9 유지 |
| 원 accepted state 격리 | PASS; 모든 적분점·증분의 초기 상태 hash 계승 확인 |
| 원 source guard I/O | 실행 부모/cold 경로의 tripwire 접근 기록 0; worker 코드 또한 live=False 경로 |
| 저장 결과와 새 프로세스 결과 hash | 996f5ea658ec6733ca32935a334e6f2975ad7d7df94fbdb1d1f99b9ce10ecdbf — 동일 |
| cold | 새 Python 프로세스, 새 Job 0, 계산/제출/하위프로세스 시도 0, FELUPE import 0 |
| 정리 | run/cold Workbench shutdown.joined=true; 각 소유 프로세스 CONFIRMED_REAPED |

`evidence/c1-exact/run/workspace`는 원 계산과 저장 개정의 실제 전체 asset/file set이다. 결과파일 hash와 owner 저장 구조를 유지하기 위해 사후 축약하지 않았다. 원 law/source 텍스트를 현재 helper 코드에 맞춰 재서명하지 않았다.

원 assignment = 469bf171043872392a200187a33abfac5e70e30efee80e8a3b9c0c5936a3717d

원 source = 3677ecc567333c5c28c454dd02934b80958cbdabe0005ea036021fd943f75096

원 review = 2616385f2d615db34f25664fa598ff40768ed5f4850ca2b6de4c7f657ca50c1e

위 값과 원 세 guard/저장 revision 관계/10개 수치 source는 모두 그대로다.

## 좁은 단위 검사와 실패 로그

C1 provenance/native identity 및 기존 retention_transfer만 실행했다. 최종 작업본 결과는 144 passed이며 실행/라우팅 대역 검사를 실제 FE로 표시하지 않는다. law/mesh/boundary/solver와 다른 backend의 path/실행 override, 공격자가 hash를 재계산한 receipt, 원 source code 변경/입력 불일치 거절을 포함한다. 두 독립 세션의 Proxy allocation address와 문서 runtime name 차이는 같게, 실제 물리/영구 ID 변화는 다르게 판정한다. live Apply의 session/generation/source CAS 차단도 유지한다.

개발 중 첫 mapping 재검증은 원 card_preview의 JSON key 순서 때문에 실패했다. 원 문자열/해시는 그대로 둔 채 비교용 사본의 JSON 의미를 확인하도록 교정했다. 문서 참조 검사를 강화한 뒤 첫 fixture 검사 2건은 deepcopy가 mock Document identity를 복제하여 실패했다. 실제 소스의 동일 문서 검사는 유지하고 mock 구성만 고쳤으며 다음 검사 144 passed였다. 첫 143-pass 기록, 2-failure/142-pass 기록, 수정 후 기록을 모두 보존한다.

별도 성공/실패/timeout 소유 종료 기록이 있다. timeout 검사는 sleep 30초 프로세스를 0.3초 제한으로 의도적으로 timeout시켰고 실제 -9 종료/CONFIRMED_REAPED를 기록했다. 원 실패/검사 실패를 삭제하지 않는다. 공개 source archive 추가 네트워크 조회의 DNS 실패도 보존하되, 오프라인 wheel 설치 실패로 혼동하지 않는다.

깨끗한 원 source→첫 LAW patch→C1 dedicated/root patch 적용, 전체 file bytes 대조, clean-tree 회귀 결과, 공개 current Workbench에 공통 patch 적용 결과는 패킷 `evidence/patch-verification.json`과 `evidence/c1-clean-unit/`를 확인한다. 이 검사는 실제 current root/Sol/Post/PDE/Portable WIP 전체를 받은 검사와 다르다.

## 미실행과 완료 경계

Windows = NOT_RUN. FreeCAD 1.1.4 실제 실행 = NOT_RUN. 원 specimen.FCStd 새 owner에서 native re-freeze = NOT_RUN. root/Sol 병렬 WIP 전체 통합 실행 = NOT_RUN. 이번에 실제 Qt 또는 3-law 전체 Windows 캠페인을 다시 실행하지 않았다.

전체 동일 native 입력 E2E 인수는 원 FCStd를 root의 실제 FreeCAD에서 다시 열어 C1 re-freeze→그 exact 입력 FE→save/cold를 수행한 뒤 판정해야 한다. 이를 위해 고정 macro/기존 owned-process supervisor 실행기를 제공한다. 이 환경에서 통과한 것은 **원 FreeCAD가 이미 생성한 exact frozen JSON→실제 Linux FE→저장→별도 Python cold**다. 별도의 FreeCAD native 성공과 합쳐 완료라고 하지 않는다. 물리 보정/강도/파손/공학 release는 여전히 UNKNOWN이다.
