# ParaView Post 저장 프로젝트 이동과 복구

독립 Post에서 저장한 파이프라인, 원본 reader, 보존 분석 이력, 선택, 시간과 카메라를 파일 사본에 포함한다. Workbench 서비스 없이도 설치된 ParaView와 기존 문서 소유자의 저장 경로를 쓴다. 해석 솔버를 다시 실행하지 않는다.

## 일반 작업

1. 결과를 Post에서 열고 ParaView의 Pipeline Browser에서 대상을 선택한다. Properties의 미적용 변경은 Apply 또는 되돌리기로 정리한다.
2. Post의 프로젝트 저장 동작이나 `Ctrl+S`로 현재 파이프라인과 표시를 저장한다. 가져온 저장본의 첫 저장은 **새 작업 프로젝트로 저장**할지 확인한다. 현재 창의 편집은 같은 창에서 이어지고 원 저장본은 보존된다.
3. 연결 화면에서 저장본의 사본 만들기를 선택한다. 저장본과 필수 입력 파일을 포함한 사본 검사 결과를 확인하고 폴더를 고른다. 저장본을 별도 창에서 열기와 작업 사본 열기는 구분된다.
4. 사본을 다른 폴더나 컴퓨터로 옮긴 뒤 현재 컴퓨터에 설치된 ParaView로 연다. 사본에 적힌 실행 프로그램 경로는 실행 권한으로 쓰지 않는다.
5. 편집 후 저장하고 다시 사본을 만들 수 있다. 재복사한 사본의 현재 head와 원본 보존 자료는 별도로 검증된다.

가져온 저장본과 아직 현지 저장하지 않은 작업 사본은 **미저장** 상태로 열린다. 원 저장본의 보존 정보와 현재 창의 저장 완료 상태를 구분한다. 명시적인 native 저장을 마친 뒤에만 현재 창이 저장 완료 상태가 된다.

같은 작업 사본이 이미 열려 있으면 연결 화면은 검증된 현재 창을 활성화한다. 다른 저장본은 독립 문서 ID로 열린다. 이전 창의 미저장 편집을 덮어쓰지 않는다.

## 파일이 없거나 바뀐 경우

필수 파일이 없으면 완전한 열기로 표시하지 않는다. **일부 복구**를 명시적으로 선택하면 건전한 형제 데이터와 화면을 열고 누락된 branch를 안내한다. 바이트가 바뀐 파일은 누락과 구별하여 차단한다.

보존한 분석 파일도 없으면 그 분석의 원 recipe, graph, bindings, 결과 pin, draft, 선택 위치와 Undo/Redo 기록을 남긴다. 원값을 대신하는 reader나 계산 결과를 만들지 않는다. 저장 시 누락된 분석을 과거 기록으로 함께 보관할지 다시 확인한다. 존재하는 검증 파일과 원 snapshot proof만 함께 저장하며, 다시 옮겨 열어도 누락 상태가 유지된다. 과거 요약은 **과거 기록·원값 미확인**이며 검증된 수치 입력으로 사용할 수 없다.

동일 내용 위치 수리는 기존 등록 입력의 파일명 관계, bytes/hash, container occurrence, reader type과 선언 metadata를 대조한다. PVD frame이나 물리 선언이 바뀌면 새 입력 결과로 추가해야 한다. 위치 수리로 기존 실패나 UNKNOWN을 성공으로 바꾸지 않는다.

처음 등록할 때 원 파일이 없었어도 저장본에 정확한 파일 pin과 누락 위치가 선언돼 있으면, 같은 내용의 등록 입력으로 현재 창에서 복구한 뒤 저장하고 사본을 다시 만들 수 있다. 원 누락 기록과 과거 snapshot은 보존한다. 원 pin이 없는 파일이나 다른 이름 관계·내용을 임의로 추정하지 않는다.

한 source를 같이 읽는 보조 reader와 retained reader도 모든 FileName slot을 먼저 확인하고 한 번에 수리한다. 영향받는 과거 graph와 bindings를 함께 검증한 뒤 문서를 갱신한다. 도중 실패하면 reader, 문서와 basis 매핑을 모두 되돌린다. 서로 다른 source 여러 개를 한꺼번에 수리하는 범용 기능은 제공하지 않는다.

연결 화면에서 저장을 요청한 경우에도 누락 분석 보관 동의는 현재 ParaView 창에서 받는다. 창이 없으면 저장하지 않고 현재 창에서 확인하도록 안내한다. 취소한 예약은 실패로 확정하고 실제 저장을 실행하지 않는다.

## 지원 경계

실제 reader/property 조합은 `XMLUnstructuredGridReader/FileName`, `PVDReader/FileName`, `XMLTableReader/FileName`, `XMLPolyDataReader/FileName`만 허용한다. PVD는 순서, 반복 frame, time/group/part를 보존한다. 순수 dependency codec은 parallel VTK의 `Piece Source`와 composite hierarchy도 검사하지만, 실제 native capability가 확인되지 않은 reader는 완전 지원으로 승격하지 않는다.

reader의 모든 FileName slot, 원 source pin, 전체 history의 기존 retained reader와 명시 metadata를 수집한다. 무지원 reader, 실행 가능한 PVSM proxy, 누락 pin은 성공 처리하지 않는다. raw PVSM은 명시적인 상태 읽기와 현재 실제 reader 확인 후 새 관리 프로젝트로 저장하는 adapter 경로를 사용한다. 과거 history를 새로 만들지 않는다.

과거 분석은 해당 revision이 참조한 upstream을 검증한다. A0에서 만든 B의 이력이 있을 때 A의 현재 선택을 A1로 바꾸어도 B의 과거 입력은 A0로 남는다. 현재 입력이 달라졌다는 표시는 별도로 표시한다. 경로 이외의 filter 인자, reader type, output port와 물리 선언 변경은 계속 검출한다.

## 확인한 동작과 남은 확인

실제 ParaView 새 프로세스에서 원 경로 없는 작업 사본 열기, B 새 Apply/Undo/Redo, A cursor 이동 후 B의 고정 입력 보존, 실제 Save/head 등록, 기존 사본 작성 경로, 첫 사본 없는 두 번째 열기를 확인했다. 가져온 저장본의 첫 Save는 같은 live ID를 유지하면서 새 작업 대상에 저장했다. 저장 응답이 유실된 경우 다음 명시 확인에서 같은 완료 Save를 재확인했고 실제 Save는 한 번이었다.

누락 history는 실제 부분 열기→명시 보관 Save→재복사→첫 사본 없는 두 번째 부분 열기에서 원 기록과 pin을 보존하고 건전한 분석을 검증했다. 모든 native 검사는 호출별 Windows Job Object에서 실행하고 종료 후 `job_empty`를 확인했다.

교정 검사에서는 중간 source가 처음부터 누락된 상태에서 건강한 retained A0를 유지하고, 동일 내용 복구 후 새 B1을 저장했다. 같은 세션에서 A0의 reader 위치를 수리한 뒤 B1의 고정 입력을 검증하고 물리 인자 변경을 검출했다. 다시 저장·복사한 뒤 원 경로와 첫 등록 폴더 없이 cold open까지 확인했다. 저장 전 확정 거절과 동기 실패는 다음 명시 저장을 허용하지만, 완료 뒤 응답 유실이나 등록 실패는 같은 완료 명령을 재확인한다. 교정 원문은 `_workspace/delivery-native-project-post/correction-01/CORRECTION_KO.md`에 있다.

![실제 ParaView의 q field 렌더](post-native-render.png)

이미지는 실제 native render이다. Windows 세션 잠금으로 OS 화면 캡처가 검게 반환되어 메뉴 클릭, 한국어 글꼴, 좁은 창과 키보드 focus의 실제 화면 수용은 아직 확인하지 못했다. 기존 `paraview.exe` 창의 startup, GUI dispatch, 실제 owner와 render readback은 확인했다. 이 결과를 GUI 전체 수용이나 물리적 타당성 승인으로 보지 않는다. 예제 수치는 합성 자료이며 물리적 적합성은 UNKNOWN이다.

검사 원문과 현재 소스 manifest는 `_workspace/delivery-native-project-post/DELIVERY_KO.md`, 예제 driver는 `examples/native-project-post/`에 있다.
