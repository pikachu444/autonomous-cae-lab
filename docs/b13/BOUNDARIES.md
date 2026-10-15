# B1.3 작성·검사·수용 경계

요청 `PRO-B13-SHELL-BEAM-20261015-03-DIRECT`. 작성자는 이 요청의 응답 작성 모델이다. 다른 대화의 미회수 코드나 다른 모델 작성물을 회수한 것으로 표시하지 않았다. 이 파일은 완료 승인서가 아니다.

아래 검사 표는 실제 Pro 작성 환경의 인도 근거다. 이후 Codex의 Windows 전용 통합·Qt 확인과
native 저장 재읽기의 binding 차단은 [사용 흐름](WORKFLOW_KO.md#수용-상태)에 구분해 기록한다.
그 후속 확인도 B1.3 전체 완료나 공학적 승인으로 바꾸지 않는다.

## 작성한 것과 닫지 않은 것

| 원 요구 | 이번 코드 | 수용 경계 |
|---|---|---|
| 영역별 셸 두께/offset/법선/축 | raw 영역 draft, 정확 coverage, native 속성/참조 비교·불러오기, 기존 Apply/writer/preview, Qt 편집 연결 | Linux 도메인/대역/원 Python writer 함수 검사. 실제 곡면 native 계산·화면은 미실행. |
| 실제 셸 상하면/내부 IP | 기존 `.12d`/FRD/DAT reader 확장, 영역/기저/원행 위치, 새 내부 CELLS, cold 검증·조회 | 합성 곡면 원자료로 연결 검사. 합성 파일은 native 수치 결과가 아니다. |
| 빔 요소별 축 | 직선 B32R RECT의 분할 방향, 설치 meshtools oracle, 기존 번호 대응·writer | 곡선 빔 미지원. 비축정렬 gate 유지. 실제 분할 축 native 계산 미실행. |
| 별도 빔 응력 출력 | 명시적인 OUTPUT3D run, 실제 확장 topology·원 S/E/IP50, 같은 mechanical 입력 비교, 기존 adapter/inspection/Post | **ccx2.22 native COORD 검증은 미완료.** 잘못된 좌표를 추정치로 대체하지 않는 관문이 있다. |
| native 회전 | unavailable 유지 | **원 DOF 회전 요구 미완료.** 유도 강체-fit은 별도 구현이며 대체 완료가 아니다. |
| 지지부 응답 | 원 확장 RF 합 및 orbital moment, 복원 stress traction 적분, 기준점 이동·중복/누락 방지 | **완전한 MPC/이산 구속 반력 미완료.** 구현된 두 관측/유도량을 그 반력으로 간주하지 않는다. |
| 사용자 편집·저장·새 owner | 기존 transactions/save/snapshots/동결 모델/기존 owner 재사용, raw 포함 Qt helper | 실제 Qt 상호작용·Windows FCStd 저장/재열기 수용 미실행. 기존 보존 Windows fixture는 읽기 회귀로만 재사용. |

E3–E6, C1–C6, 전체 B2, 일반 CAD 전체, FN-12/14/15 부모 행은 닫지 않는다. 신규 native 입증 전 `engineering_valid`를 true로 바꾸지 않는다.

## 소유 경계와 최소 통합

전용 셸/빔 도메인·reader·writer·inspection·전용 새 Qt helper와 tests/docs/examples는 product.patch에 들어간다. 다음 네 기존 파일만 integration.patch로 분리한다.

1. `apps/desktop_pre/beam_panel.py`: 전용 출력 widget 설치, 기존 read_draft/load_result/reset에 연결. 기존 delegate/receipt/Escape 알고리즘 전체 교체 금지.
2. `apps/desktop_pre/shell_panel.py`: optional regions를 DraftBuffer에 유지, 영역 편집/명시 native 불러오기/저장 원결과 조회 입구. 기존 한 영역 UI와 저장 경로 유지.
3. `apps/desktop_pre/beam_result_window.py`: 검증된 raw_stress 저장 결과를 전용 worksheet로 보내는 분기.
4. `apps/desktop_post/external.py`: 기존 beam metadata 전체 재검증을 먼저 통과한 새 3D 빔 선언에만 source_blocks/source_array/원 field/기저 출처와 명시 recovery/shear 값을 허용. 일반 임의 메타데이터 검증을 완화하지 않음.

Core/schema/registry/bridge/connection/project/save/Runner 공통 구현, Numerical/Expert/DynamicR2/Portable/Material/M1/M4 및 Post 종료 lifecycle은 변경하지 않는다. 현재 main b2e359d 및 이후 변경에 대한 자동 적용/병합 성공은 주장하지 않는다. root는 인도 기준의 제한 hunk를 최신 파일에 통합한다. 전체 old source tree를 덮는 방식은 금지한다.

## 검사 수준

- 순수 Python: draft/영역/axis/조건/물리량 정의, 기계 입력 equality, source pins, corruption, cold reopen.
- 기존 native API를 본뜬 대역: Owner/문서/native 속성/mesh binding. 실제 FreeCAD 객체는 아니다.
- 첨부 FreeCAD 배포의 실제 Python writer 함수: 대역 units/model 속성을 주고 실제 함수 본문을 실행해 production `_native_fragments`와 검사한다. FreeCAD 프로세스 실행이 아니다.
- 실제 설치된 VTK XML reader: 생성 VTU의 HEX20 및 50점 CELLS 분리를 읽었다. ParaView 프로그램 수용이 아니다.
- 합성 `.12d`/FRD/DAT: 포맷, sparse ID, raw 수치/위치/성분/시간 대응과 거절 경계용. 계산해/solver 수치 검증이 아니다.
- PySide6가 없으므로 새 Qt 모듈 검사는 skip이다. 기존 `test_shell_panel.py`는 환경 부재를 skip 처리하지 않아 실패/오류로 남는다.

기존 Post 대역은 `HideUnusedScalarBars`가 없어 셸 범례 두 건과 공통 선택 두 건이 실패한다. 수정 전 기준에서도 같은 네 실패를 재현했다. 대역/원 테스트를 수정하거나 실패를 삭제하지 않았다. 원 로그는 인도 `evidence/`에 보존한다.

## 50점 교정 이력

초기 작성에서는 B32R를 일반 C3D20R의 8점으로 취급한 잘못된 합성 검사 설정이 있었다. 공식 2.22 `e_c3d.f`/`printoutint.f`/`gauss.f`를 읽고 **50점과 실제 번호 순서**로 코드·fixture를 교정했다. 초기 성공 로그는 그 잘못된 전제 아래의 실행 기록일 뿐이며 현재 reader의 증거나 native 수용으로 사용할 수 없다. 후속 50점 검사 로그가 이 부분을 대체한다. 기존 물리 기준/허용값을 실패 뒤 낮추지 않았다.

그 교정 과정에서 2.22 COORD 소스 위험도 확인했다. 이 위험은 실행 결과가 아니라 정적 소스 관측이다. 상세 파일과 위치는 PRIMARY_SOURCES.md에 있다. 설치 바이너리의 성공을 가정하지 않고 실제 DAT 위치 검증을 추가했다.
