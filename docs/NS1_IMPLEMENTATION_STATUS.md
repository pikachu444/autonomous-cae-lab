# NS1 구현 제출 상태

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

Astra 독립 검토는 아직 수행되지 않았다. 작성자의 자체 점검을 독립 검토라고 하지 않는다.
stdout의 반복별 잔차 곡선 읽기와 새 범용 수렴 허용오차 편집기는 잔여다.
STATIC,STABILIZE 및 범용 Newton line search는 이번 2.22 경로에서 지원하지 않는다.
원 stdout, 지원하는 기존 두 행 제어, STA 반복/거절/관측 cutback은 보존한다.

한글 사용법: [NS1_USER_MODEL_KO.md](NS1_USER_MODEL_KO.md).
