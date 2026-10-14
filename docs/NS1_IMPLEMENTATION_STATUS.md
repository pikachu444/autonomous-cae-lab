# NS1 구현 제출 상태

## 2026-10-14 자료무결성 교정 제출

요청 **PRO-NS1-CORRECTION-20261014-01**. 기준 PR8 `2ff3f6b` (제품 `fa7dfe0`).
Codex가 전달한 Astra(xhigh)의 두 독립 검토 지적을 같은 PR 브랜치에서 교정했다.
이 절이 이번 교정 상태이며 아래 최초 제출의 실행 기록은 역사로 보존한다.
Codex의 main `4bad73f` 통합과 Sol의 Windows UI 교정은 이번 변경에 섞지 않았다.
CURRENT_STATE, material_panel/fem_panel/test_ns1_material_ui, motion/Data 파일은 변경하지 않았다.
새 workflow, solver, 실행 서비스 또는 추가 비용은 없다.

**적용 상태:** 등방 탄성을 명시 적용한 뒤 같은 기본 재료에 native 활성 J2를 추가하면
이전 억제 객체가 그대로 있어도 실행을 차단한다. 적용 법칙과 기본 재료별 활성 객체
집합을 함께 대조한다. 기존 applied_draft/applied_native만으로 첫 지원의 0개/1개
기대 집합을 결정하므로 저장 스키마 변경이나 묵시적 재적용은 없다. 읽기에서도
적용 상태를 false와 오류로 표시하며, 옛 원곡선을 새 객체에 귀속하지 않는다.
검사/거절은 원초안·단위·억제 객체·다른 기본 재료의 정상 상태를 수정하지 않는다.

**부분결과:** strict FRD reader가 EOF의 부분기록을 별도 오류로 식별한다.
retained_prefix는 이 경우 마지막 미완성 증분 전체를 제외한 사본을 한 번 재검사한다.
필드 중간·행 중간·필드 사이·종료 표식 중간 EOF를 다루며, 닫힌 필드의 누락 행,
중간 손상, 잘못된 숫자/라벨/절점, 잘못된 end marker는 EOF로 숨기지 않는다.
STA에서 수렴한 증분과 파생 사본의 마지막 완전 증분을 구별해 기록한다.
원 FRD/STA/입력/실패·취소 상태는 유지하며 S/E/PEEQ를 0이나 보간으로 채우지 않는다.
완전한 첫 증분도 없으면 부분결과를 만들지 않는다. 접촉/tie/다단계 검사는 유지한다.

### 이번에 실제 실행한 검사

수정 전 두 제보 재현 검사는 각각 실패했다. 교정 후 다음 서로 겹치지 않는
범위에서 **총 186 passed, 0 failed, 0 skipped**를 확인했다.

- 교정/경계 검사 78개: test_ns1_native_edit + test_ns1_partial_eof의 adapter 4개 제외.
  정상 J2/명시 탄성/옛 저장본, 추가·대체·억제·삭제·다른 기본 재료, collect/freeze 차단,
  EOF 위치별 단일/접촉/tie/다단계 정적·기존 탄성 동적 파서, 중간 손상 거절을 포함한다.
- adapter 실패/취소 4개: 원문 FRD/STA와 입력 보존, 완전 1증분만 Post에 연결,
  마지막 STA 수렴과 실제 보존 증분의 구별. 대표 1개는 solver 경로를 제거한
  별도 Python 프로세스에서 사본·저장 실패기록을 재열었다. 네 경로에서 이력을 확인한다.
- 기존 호환 104개: test_contact_steps, test_contact_tie, test_frozen_fem,
  test_contact_native_export, test_ns1_material_limits, test_ns1_native_collect,
  test_calculix_material. 기존 순서/중복/단계/좌표/tie 경고 보호를 유지한다.

Python 3.13.5 / pytest 9.0.2의 Linux 컨테이너 검사다. gfortran F20.0 검사는
실제 컴파일·실행했다. native 객체와 solver는 명시 대역, FRD/STA는 합성 입력이다.
전체 솔버 캠페인과 실제 FreeCAD/CalculiX/ParaView 또는 GUI는 실행하지 않았다.
컨테이너 일괄 실행 중 도구 제한 시간으로 끝나지 않은 시도는 통과로 세지 않았다.
최종 기록은 범위를 나눈 완료 XML 세 개이며, 판정·수치 허용치·20초 자식 프로세스
제한은 완화하지 않았다. 같은 새 프로세스 재열기 반복은 대표 한 건으로 줄였다.

Codex 전달 Windows 결과 **80 passed / 1 skipped / UI 2 failed**는 별도 기록이다.
Windows gfortran 미설치 skip과 480 요청 시 608 최소폭·e-5/e-05 표시 차이는 Sol 소유로
남겼다. 이전 원격 234 통과로 이 Windows UI 문제를 해소했다고 표시하지 않는다.
이번 교정의 Astra 재검토, Codex의 Windows native 확인·main 통합은 아직 이 작성자가
확인하지 않았다. 독립 최초 검토와 교정 후 재검토를 구분한다.


요청 PRO-NS1-RESUME-20261014-02 / 2026-10-14.
시작 코드: main 0508b6d, native upstream 3e48bf6138f495299f45b1af254bfb4aaff307b8.
첫 재료 모듈은 중복 적용하지 않았다. 기존 NS1 브랜치에 main을 merge한 9b6c83f,
20자/200점/변형률 의미 교정 a98928e 이후 사용자 모델 연결을 이어 구현했다.
작성 중 main의 2942e4d까지 추가 변경을 확인했으며 motion/Data 변경과 소유 파일이
겹치지 않는다. 49917e9에서 해당 main을 정상 merge했고 native pin을 검사했다.
연결 제품 코드는 9478723a496fea2284b2630b30079b7a2e6d3a3a에 게시했다.
GitHub 검사 run 38537661329에서 195개 통과 및 정상 push를 확인했다.

## 구현한 사용자 경로

| 경로 | 코드에서 연결한 동작 | 이번 원격 확인 |
|---|---|---|
| 재료 | 선택 기본 재료/적용 body, raw 표·단위·정의, native J2 객체, 저장/명시 적용, 오류 행 | 실제 Qt 및 native 객체 대역. Windows FreeCAD 미실행 |
| 단일 body | 실제 collector→요소 집합/재료/STATIC·NLGEOM→기존 CalculiX adapter | collector/프로세스 대역, deck 내용 검사 |
| 기존 두 body 접촉 | LINEAR/Coulomb 유지, 탄성/J2 혼합 body 할당, 별도 메시 ID 변환 유지 | collector/프로세스 대역, 기존 접촉 회귀 |
| 결과 | FRD PE scalar, S/E/PEEQ, STA 수렴 접두부, 거절/관측 cutback, NaN/valid mask | 명시 합성 FRD/STA, 원자료 보존 검사 |
| 실패/취소/새 시도 | 옛 실패 입력 불변, 별도 output, 원 계산 조건 열기 | 실제 adapter+프로세스 대역. 새 Python 프로세스 재열기 |
| Post 재열기 | 저장 입력/결과로 파생 Post 재구성, 계산 실행 없음 | solver 경로를 제거한 새 프로세스에서 통과. ParaView native 미실행 |

단일 body와 접촉 모델이 같은 기존 backend/JobManager 계약을 사용한다.
새 solver·고정 예제 전용 backend·웹 UI는 없다. 기존 Post 원자료 변경/CAD 변수 복구와
motion/Data 소유 파일은 수정하지 않는다. 공통 schema 호환은 사용법 끝부분에 적었다.

## 실제 로컬 검사

최종 관련 검사 **195 passed, 7.40 s**: `test_calculix_material`, `test_ns1_*`,
`test_contact`, `test_contact_execution`, `test_contact_native_export`,
`test_contact_steps`, `test_contact_steps_ui`, `test_contact_tie`, `test_frozen_fem`,
`test_pre_fem_edit`, `test_pre_fem_panel_ui`, `test_contact_inspection`.
이 숫자는 전체 저장소 검사나 실제 솔버 계산 수가 아니다.

PySide6 Essentials/shiboken6 6.9.1 실제 이벤트/렌더로 재료 창 480/1100×900,
Runner 740/1100×780을 확인했다. 한글, 단위, 셀 지수 표시, 키보드 붙여넣기/이동,
미완성 값과 201행 위치 이동, 지연된 명령 응답이 새 편집을 덮지 않는 동작을 검사했다.
gfortran으로 F20.0 첫 20자 읽기를 실제 컴파일·실행해 기존 100000배 오류와 교정을
검사했다. 전체 CalculiX를 실행한 검사가 아니다.
마지막 Runner 화면에서 축 글자/눈금이 좁은 창에서 겹치는 문제를 발견해
constrained layout, 글꼴 기준 표 너비 및 눈금 수 제한으로 수정했다.
실제 Qt 두 크기에서 축 라벨이 canvas 안에 있고 눈금이 겹치지 않는 검사 2개가 통과했다.

기존 첫 CI는 36개 재료 검사가 통과했다. 이후 Qt/공식 소스를 가져오는 임시 CI에서
잘못 지정한 FreeCAD `write_materials.py` URL의 404로 멈췄고 검사 실행은 건너뛰었다.
올바른 `write_femelement_material.py`를 공식 tag 1.1.4에서 읽었으며 임시 참조 다운로드는
최종 CI에서 제거했다. 소스 확보 실패와 제품 검사 실패를 혼동하지 않는다.
첫 연결 CI는 Ubuntu의 libEGL.so.1 누락으로 Qt 검사 수집 단계에서 실패했다.
libegl1/libopengl0 및 한글 글꼴을 명시 설치한 다음 195개 전부 통과했다.
일회성 게시 workflow와 소비한 patch는 제거하고 읽기 전용 focused CI만 남긴다.

## 아직 닫지 않은 수용 조건

Windows native FreeCAD 1.1.4에서 native PLASTIC writer 대조, 실제 C3D10 사용자
모델의 CalculiX 2.22 소성 계산, 기존 접촉 병행, 실제 취소 및 ParaView 재열기는
Codex 확인이 필요하다. 준비한 공개 입력과 따라 하기는 NS1_USER_MODEL_KO.md에 있다.
이 검사가 없으므로 단일/접촉 전체 native 실행 또는 AC-12·13 완료를 주장하지 않는다.

최초 제출 당시 Astra 독립 검토는 미실행이었다. 이후 Codex가 전달한 독립 검토와
이번 교정 상태는 위 자료무결성 교정 절을 따른다. 작성자 자체 검사는 독립 재검토가 아니다.
stdout의 반복별 잔차 곡선 읽기와 새 범용 수렴 허용오차 편집기는 잔여다.
STATIC,STABILIZE 및 범용 Newton line search는 이번 2.22 경로에서 지원하지 않는다.
원 stdout, 지원하는 기존 두 행 제어, STA 반복/거절/관측 cutback은 보존한다.

한글 사용법: [NS1_USER_MODEL_KO.md](NS1_USER_MODEL_KO.md).

## 병렬 main 변경 최종 병합

main 9a63fe92ea57f698a7e90f7c119fc4b067f8f3f0의 메시 품질 비교 변경을
기존 NS1 제품 연결에 정상 병합했다. 공통 bridge/명령 목록은 Git의 3-way
병합을 사용했고 CURRENT_STATE는 양쪽 추가 내용을 모두 보존했다.
NS1 기존 195개 및 추가 bridge/메시 품질 검사를 합쳐 **234 passed**.
이 확인도 Windows native 해석이나 Astra 독립 검토를 대체하지 않는다.

첫 확장 검사는 231 passed / 3 failed였다. 직접 재현한 원인은 기존 bridge
검사 대역의 Analysis.Group 누락과 기존 export_button 누락이었다. 실제
Analysis 구성과 UI에 맞춰 대역을 보완했고 실행 검증 제품 코드는 약화하지 않았다.
동결 중 재전송 방지/문서 식별자/긴 작업의 started receipt 검사도 모두 재통과했다.
