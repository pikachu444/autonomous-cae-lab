# 보존 변위의 구조 경계 전달

TR-U는 보존된 CalculiX 절점 변위 `U`를 다른 C3D10 메시의 지정 변위 경계로
전달한다. 선택한 **외부 기준면 TRI6** 위의 목표 경계만 지원한다. 내부 절단면,
최근접점 투영, 외삽, HEX 요소, 힘의 보존 전달은 이 경로의 지원 범위가 아니다.
원래 메시의 CCX 절점 순서와 절점 ID를 사용하며, 이미 적용된 native-to-deck
순열을 다시 적용하지 않는다.

입력은 원본 결과와 기준 메시의 SHA256, 저장 원본 참조, 전체 3성분 변위,
좌표계와 길이 단위, 정적 step/increment/load parameter다. 현재 작은 native
연결은 `load_parameter=1`인 정적 결과를 사용한다. 이는 물리적 시간 1초를
뜻하지 않는다. VTU는 기존 CCX writer의 단일 ASCII piece, `NativeNodeId`와
`U_mm` 배열을 읽는다. 화면에서 변형된 형상을 기준 좌표로 사용하지 않는다.

원래 외부 면과 목표 외부 면을 선택한 다음 좌표 변환, 거리/자연좌표/가중치
허용값과 반복 한도를 명시한다. 위치와 변위의 길이 변환은 각각 한 번,
변위 회전은 `u_target = s R u_source`로 한 번 수행한다. 위치의 평행이동은
변위에 더하지 않는다. 음수일 수 있는 이차 형상함수 가중치는 그대로 사용한다.

미리보기에는 목표 절점별 원본 면, 자연좌표, 원 가중치, 매핑 변위와 유효 mask가
남는다. 모서리/꼭짓점의 여러 면이 만나는 경우 실제 공통 corner 또는 quadratic
edge topology와 가중치의 수치적 일치를 함께 확인한다. 같은 변위 값만으로 서로
다른 겹친 면을 합치지 않는다. 필수 목표 절점 또는 원본 3성분 지지가 하나라도
없으면 전체 경계 적용을 차단하고 실패 미리보기를 보존한다. 실패의 일부 경계를
솔버에 적용하지 않는다.

`caelab.structural_field_ports.read_ccx_vtu` 또는 `read_ccx_displacement`로 원본을
읽고, `caelab.structural_field_transfer.prepare_transfer`로 순수 미리보기를
생성한다. 이 함수는 native 프로그램이나 솔버를 실행하지 않는다. 실제 수신은
기존 native 입력 검증, contact condition/step writer와
JobManager를 통해 수행한다. 원본 열 초기장이나 원래 지지조건을 새 수신 모델에
자동 복사하지 않는다. 기존 목표 조건과의 DOF 충돌도 기존 writer의 검증 대상이다.

현재 첫 native 경로는 기존 Pre의 고정 입력을 등록한 `frozen_contact`와 Runner의
`structure.calculix.contact`를 사용한다. `receiver_from_capture`는 실제 native
capture의 기준 좌표/순서/선택 외부 면을 추출하고, `bind_transfer_model`은 미리보기의
수신 해시와 전체 필수 DOF를 다시 확인한다. 이 첫 profile에서 교체할 수 있는 것은
새 독립 모델의 `TransferBoundary` 0 변위 기준 조건 하나와 기본 정적 단계뿐이다.
다른 지지/하중/편집 단계가 있으면 자동으로 지우지 않고 거절한다. 매핑된 절점별
지정 변위와 곡선은 기존 compiler가 생성하며 원 0 경계와 원 단계는 provenance에 남는다.
`structural_transfer_snapshot.freeze_transfer`가 기존 native 입력 형식으로 보존한다.
실행 요청의 settings에는 등록된 `data_id`만 전달한다.

이 파생 입력에 동봉된 FCStd는 **형상과 메시의 기준 CAD**다. 원래 0 경계 조건을
보존하며, 매핑된 지정 변위가 FreeCAD 조건으로 적용된 편집 모델이라고 표현하지 않는다.
계산에 실제 사용한 값은 파생 `mesh.json`의 `boundary_dofs`와 기존 writer가 쓴
`contact.inp`에 있다. 기준 CAD를 열어 다음 계산을 준비할 때에는 전달을 명시적으로
다시 구성해야 한다. 현재 Runner의 입력 문서 열기와 계산 단계의 조건 수정은
이 파생 입력에 대해 안내 후 차단한다. 기준 CAD의 조건을 바꿔 같은 전달 계산을
재실행하는 GUI는 아직 지원하지 않는다. 전달 authoring GUI 전체 완료를 뜻하지 않는다.

작은 연결 예제의 원본은 실제 `Dthermalfree` CCX 결과이고, 수신은 같은 10×1×1 mm
영역의 35절점/8 C3D10 메시다. 외곽 34절점의 XYZ만 지정하고 내부 절점 하나를
자유롭게 둔다. 원본의 자유 열팽창 응력 0을 기계적 수신 응력의 기준으로 쓰지
않는다. E=210000 MPa, ν=0.3인 새 기계적 수신의 기준은 `u=.0005 X`, 정상응력
262.5 MPa와 전단응력 0이다. 이 예제의 거리 `1e-10 mm`, 자연좌표 `1e-12`,
가중치 `1e-11`은 이 작은 직선 fixture의 명시 설정이며 일반 곡면/큰 좌표의
기본 허용값이나 공학 보증으로 확장하지 않는다.

원본 판정과 수신의 수치 대조는 별개다. 솔버 성공이나 위 작은 해의 일치가
재료/강도/구조 적합성의 승인을 뜻하지 않으며 공학 판정은 UNKNOWN으로 유지한다.

재현용 순수 선언 생성(새 출력 폴더 필요):

```powershell
python tests/check_structural_u_transfer_windows.py --prepare runs/structural-u-transfer-example
```

이 명령은 원본을 읽고 선언과 미리보기를 보존한다. native 수신 실행 완료를
뜻하지 않는다. 실제 native 인도에서는 같은 선언의 입력/결과와 소유 프로세스
정리 기록을 함께 확인한다.

2026-10-18의 실제 작은 연결에서는 source 재계산 없이 수신 CCX를 한 번 실행했다.
실행 `J5a04c25dc23643cf8df25191a7838cff`는 성공했고 내부 절점 35의 변위는
`[0.00125, 0.000125, 0.000125] mm`로 원 변위 기준을 통과했다. 기존 FRD 절점 응력은
정상 성분 `262.497 MPa`여서 원 응력 기준 `262.5 MPa`와
`rel=2e-6, abs=1e-6 MPa`의 대조는 **FAIL**이다. 이를 보정하거나 허용오차를 늘리지
않았다. `contact.dat`는 0 byte이며 해당 입력에는 적분점 응력 print 요청이 없어
적분점 응력 대조는 **UNKNOWN**이다. 공학 판정도 UNKNOWN이다.

보존 결과는 `runs/structural-u-transfer-20261018-05/receiver-result.json`에 있고,
별도 Python/HTTP와 실제 Runner의 cold 읽기는 `...-06/cold-result.json`에 남는다.
ParaView에서 같은 등록 결과의 변위 크기와 원 기준 형상을 읽고 프로젝트를 저장한
후 별도 프로세스에서 다시 열었다. 읽기 과정은 job 1→1, 새 submit/solver 0을
확인했다. 원 수치 실패와 원 input/result 파일은 그대로 보존한다.
