# 첫 지원과 차단 — Input A

모든 “지원”은 코드의 입력 admission/연결 구현 범위를 뜻한다. 원 Pro 작성 환경의 Windows native 검증은 NOT_RUN이었다. Sol 통합에서 명시 Itetra4=1000/CFL0.5의 작은 native 탄성 병진 사례를 실제 확인했다(USAGE_KO의 Windows 국소 확인). 전체 A/GUI/계층 INP 수용은 별도 미완료다. Runtime은 기존 latest-20261011/source cb760c206e346eff12161a2268b134ef9d48a4ef의 binary/CFG identity를 변경 없이 사용한다. converter_source_commit=NOT_PROVEN_BY_RELEASE를 유지한다.

## 입력·문법·물리

| 대상 | 첫 지원 field/option/reference | 실행 전/후 관문과 잔여 |
|---|---|---|
| 원 입력 | ASCII 총 6 MiB, root 아래 포함 파일, CRLF/LF 원 bytes, file/line/occurrence, original-range hunk | root escape/cycle/link/junction/case shadow/reserved filename, 변조, 겹치는 hunk, stale 화면 차단. 원본과 명시 수정본 분리 |
| 계층 | meshed `PART,NAME`; 단일 `ASSEMBLY,NAME`; dependent `INSTANCE,NAME,PART`; include 반복/중첩 | instance마다 같은 local ID와 이름을 분리. 순수 회전도 첫 행 `0,0,0`; global 축 두 점 + degree 각도; 이동 뒤 오른손 회전 |
| 계층 mesh/law | C3D4 + isotropic ELASTIC, DENSITY, SOLID SECTION의 ELSET/MATERIAL | section/재료 누락·중복, 원 연결·material mapping 검증. C3D8/10 계층, plastic 계층, connector, independent instance 등 차단 |
| 계층 대상 | NODE/NSET, ELEMENT/ELSET, NSET/ELSET GENERATE 및 assembly INSTANCE option·qualified 참조; TYPE=ELEMENT SURFACE | exact ordered face와 명시 선행 집합 참조. inheritance override·모호한 얼굴·unknown option 차단. 좌표 근접 matching 없음 |
| 계층 조건 | model-level 고정 병진 BOUNDARY; 기존 설정의 운동·TYPE24 접촉·중력·시간 | CLOAD/DLOAD/STEP/원 INITIAL CONDITIONS 등 첫 미지원 영향 카드는 위치와 함께 차단. 조건을 버리고 계산하지 않음 |
| 기존 flat INP | 기존 C3D4/C3D8/C3D8R/C3D10/COH3D8 경로 유지 | 기존 plastic/LAW117 범위 유지. 이 전체 경로의 native 재인수는 이번에 수행하지 않음 |
| Native 묶음 | root의 같은 basename `_0000.rad` + `_0001.rad`; 열1 `#include relative-name` | pinned include reader/config 근거. INP `*INCLUDE`와 구별. starter와 engine은 별도 graph. export tree는 source bytes와 대조 |
| Native BEGIN | `#RADIOSS STARTER`, BEGIN 이름, 2025/Irun=0, INPUT/WORK 모두 Mg/mm/s | 사용자 단위 명시도 필수. kg/mm/ms 등 다른 단위의 자동 변환/재표기 없음 |
| Native mesh | NODE의 10+20×3 field, TETRA4 10×5 field, PART(prop/mat/subset0), MAT/ELAST | missing/duplicate ID, ordered native↔C3D4 permutation, part/material 연결 대조. 미사용 영향 PART/MAT/PROP도 차단 |
| PROP/SOLID | 기존 레시피: 첫 8 정수 `[24,-1,0,-1,2,0,3,-1]`; C3D4는 명시 Ismstr=2 또는 표준 Itetra4=1000도 구별해 보존, 이어 `.1`; 다음 `[1.1,.05,0,0,0]`, `[0,.01,100,100,.01]`, 마지막 `[0,0,1]` | 모든 지정 field 및 추가 trailing field 검사. 다른 property 옵션을 이름만 허용하지 않음. Starter actual review의 Itetra4=3/Ismstr=10·12는 Engine 전에 차단. 원 자동 설정은 읽기 보존과 실제 실행 가능을 구별 |
| Native 집합/면 | GRNOD NODE/PART/SURF/GRBRIC/GRNOD, GRBRIC/BRIC, SURF/SEG | 정수·중복·순환·결손 및 유일한 방향 있는 원 요소면 대조 |
| Native BCS/운동 | global 병진 고정 BCS, INIVEL/TRA(VX/VY/VZ, group, skew0, Tstart0, sensor0) | 회전 BCS/local skew/ROT/AXIS 미지원. 겹치는 속도 target 및 구속 충돌 차단. `/RBODY`는 차단 |
| Native 접촉/중력 | TYPE24의 기존 고정 field 레시피·명시 마찰계수; constant FUNCT (0,1),(1,1); global GRAV | main/secondary exact surface 검증, 다른 접촉/시간함수/숨은 field 차단. pair별 force를 합성하지 않음 |
| Native Engine | RUN basename/1, DT 또는 DT/NODA/CST/0, ANIM/DT 시작0, VECT DISP/VEL/ACC/CONT, BRICK TENS/STRESS·DAMA, ELEM/DAMG, TH/TITLE, TFILE/4, STOP `0 0 0 1 1`, PRINT/-100/50, PARITH/OFF | positive time/interval, 0<CFL≤1, 명시 mass scaling target, 최대 1024 frame. 중복/누락·알 수 없는 Engine field/옵션 차단 |
| 초기 자세 | 기존 INP motion에 proper 3×3 R, MODEL_GLOBAL frame, MODEL_GLOBAL/INITIAL_BODY vector frame | 직교·det+1·finite 검증. 전체 요소를 포함한 대상의 좌표와 V/ω 변환. 반사/전단/부분 위치변환 차단 |
| 높이 의미 | velocity: 측정 V; release_height: 좌표를 중력 반대 방향으로 옮기고 해당 낙하를 계산; impact_height: 생략한 비행 구간을 √(2gh) 속도로 반영 | measured V와 같은 높이 구간의 중복 입력 차단. release의 비영 병진 초기 V도 차단. 중력/축/필수 값 임의 보충 없음 |
| 질량/관성 | homogeneous C3D4의 체적 적분·질량·COM·대칭 전체 관성·parallel-axis·변환 전후·주관성·초기 KE/momentum | 입력 유도값. 반복 고유값의 유일하지 않은 주축은 None/상태로 표시. solver 강체 관성/actual RBODY 비교는 UNKNOWN/NOT_RUN, 미구현 |

## 결과·실행·소유

| 항목 | 구현된 동작 | 하지 않는 주장 |
|---|---|---|
| 실행 | 기존 owned Starter/Engine, exact binary/CFG, 원 log/raw prefix, warning/units/end 관문 | native 없이 성공, reference 예제를 사용자 모델 수용으로 대체하지 않음 |
| 실제 field reader | 기존 ANIM→VTK와 TH→CSV, 실제 time, NODE_ID/ELEMENT_ID, vector component/frame/unit, active mask, Post PVD/VTU | 가까운 좌표 대응, 없는 값/단위, unknown array를 지원 채널로 등록하지 않음 |
| field 종류 | 실제 배열이 존재할 때 변위 mm/속도 mm/s/가속도 mm/s²/전체 접촉 절점력 N/응력 MPa | pair-specific force, 모든 solver 증분/peak, 접촉쌍 impulse, 강체 회전 DOF 측정 합성 없음 |
| 이력 단위 | 기존 전역 에너지 응답 J(원 N·mm ×.001), 질량 kg(원 Mg ×1000), 운동량 kg·m/s(원 Mg·mm/s와 수치 같음) | 원 TH/CSV를 바꾸거나 단위만 바꾸지 않음. raw 채널 23 NO NAME은 물리 이름을 붙이지 않음 |
| exact 선택 | frame별 pin과 payload 검증; source instance/local/effective mapping; selected/all 검증 구별 | `metadata_only=True`를 VERIFIED로 반환하지 않음. source target ID 재사용은 명시 재선택/대응 수락 전 차단 |
| 상태 | solver 종료, 전체 작업 실패, 후처리 실패, cancel/cleanup 미확인을 별도 사실로 보존 | 실패 값을 공학 성공으로 바꾸지 않음 |
| 재읽기 | 같은 Simulation의 원 job → 별도 READBACK_ONLY Job; 기본 VTK/CSV solver0, 명시 ANIM/TH 재변환만 pinned converter. 명시 재읽기에 한해 이력과 프레임을 독립 회수 | 새 owner/store 또는 새 해석 실행 아님; 원 실행 status/원 input/record는 불변. 일부만 읽으면 새 읽기 작업은 FAILED이며 읽힌 응답·Post와 누락 범위를 함께 보존. 정상 계산의 엄격 완료 관문은 유지 |
| 부분 이력 | TH/TITLES 부재에도 보존 CSV의 완결·유한·비음수 증가 시각 prefix를 읽음. 첫 잘못된 행에서 중단하고 원 행 번호와 이후 미확인을 명시 | 끝의 불완전 행, 틀린 열 수/값·시각, 중간 손상을 건너뛰지 않음. 줄 끝이 없는 마지막 행도 잘린 숫자일 수 있어 미확인. TH 대조가 없으면 native 이력 대응은 UNKNOWN, 값·시각 보충/보간/끝시각 추정 없음 |
| 부분 프레임 | 원 슬롯·pin·시각·ID를 유지하며 검증된 VTK는 개별 선택. raw ANIM 순번(A001→슬롯0)의 빈 번호도 보존하며 구간 선택의 원 슬롯 번호는 유지. 손상/누락 슬롯은 읽기 오류로 남기고 시계열 segments를 분리. 기존 Post writer는 검증된 실제 표본만 출력 | 재변환하지 않은 프레임은 native artifact pin과 기존 frame pin을 모두 대조하며, pin 불일치 payload를 승인하지 않음. 손상 프레임을 시간 연속값으로 연결하거나 누락 뒤 접촉 impulse 적분을 재시작하지 않음. Post 표본 사이의 연속 해석/보간 수용 주장은 없음 |
| 저장 | 기존 document.update/save/undo/redo, revision 입력/결과 사본, 새 owner의 선택 읽기 | GUI 적용/Windows OS UX/실제 ParaView 렌더가 검사됐다는 주장 없음 |

Unknown 카드의 영향 표는 보수적인 재검토 범위다. 해석하지 못한 카드가 정확히 어느 물리량을 얼마나 바꾸는지 계산했다고 표시하지 않는다. 초안 저장과 Run 준비 판정은 서로 다르다.

2026-10-16의 부분 재읽기 확인은 solver를 다시 실행하지 않은 reader 검사다. 기존 Windows native04의 별도 사본에서 TH/TITLES 부재·CSV 마지막 행 잘림·VTK 한 프레임 손상을 함께 적용해 정상 프레임 12개와 완결 이력 119행, 분리된 두 구간을 읽고 저장한 뒤 새 프로세스에서 다시 선택했다. 원 native04 파일의 해시는 변하지 않았다. 이 검사는 새 해석의 물리 수용이나 전체 GUI·ParaView 사용자 흐름 완료를 뜻하지 않는다.
