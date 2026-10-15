# S1 Windows 공간 계산 확인

2026-10-15, 실제 Pro S1 전용 소스와 root 공통 연결을 현재 main에 통합한 뒤 별도로 확인했다. Pro 작성 환경의 미실행 기록은 [원 수용 결과](ACCEPTANCE_RESULTS.md)에 보존한다. 전체 B6·S2 완료나 공학적 승인 판정은 아니다.

기존 Windows runtime의 Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, PySide6 6.9.1을 사용했다. 공식 scikit-fem 12.0.2 pure Python wheel(178,478 bytes, SHA256 `34cd891f80072c0c1eb759a2371e82f0eeec91ff7c08acab96d27b6edbbe1b05`)의 CRC·공식 manifest·BSD-3-Clause를 대조하고 해당 패키지만 설치했다. runtime에 pip가 없어 이미 설치된 시스템 pip의 `--python <runtime executable>` 기능을 사용했다. 기존 패키지를 갱신하거나 새 solver·WSL·CAD·AI·유료 서비스를 설치하지 않았다.

`scripts/native_check.py`로 전용 네 모듈을 실행해 62개 통과, skip 0건을 확인했다. 계약·실패·취소·owner 시험의 명시 대역과 `test_s1_installed_spatial.py`의 실제 scikit-fem 조립·SciPy 계산을 구별한다. 두 공개 예제 모두 한글·공백 경로에 저장하고 별도 프로세스에서 solver import와 계산·mapping 호출을 금지한 채 원 retained 결과와 Post 입력을 다시 읽었다.

| 실제 공개 예제 | 관측 |
|---|---|
| Uniform | 공급 P1 9절점 → 수신 12절점. 열 sparse solve 1회·구조 1회. 온도 최대 오차 `5.684341886080802e-14 K`, 자유팽창 오차 `2.2768245622195593e-18 m`, 구조 상대 잔차 `3.9179525417677946e-16` |
| Affine | 공급 0초 9절점·2초 15절점 → 수신 1초 12절점. 두 실제 정상 해를 공간 보간하고 시간 가중치 0.5/0.5 적용. 독립식 `305+4*x-2*y K` 최대 오차 `5.684341886080802e-14 K`, 구조 상대 잔차 `4.452072369351257e-16` |

원 residual `1e-10`, 온도 재현 `1e-10 K`, 자유팽창 `1e-10 m` 기준을 유지했다. 비균일 예제는 균일 자유팽창 benchmark를 명시적으로 적용하지 않았다. worker는 reduced plane-stress Lamé 계수 `lambda=E*nu/(1-nu²)`, `mu=E/(2*(1+nu))`를 라이브러리 `linear_elasticity`에 넘긴다. 공식 12.0.2의 `plane_stress` 반환값을 E/nu로 다시 해석하지 않는다. 절대온도 경로에서 구조 Tref는 한 번만 차감하며 ΔT에서는 다시 빼지 않는다.

실제 `windows` Qt platform에서 Affine 저장 문서를 새 HTTP service로 읽고 Evaluation·온도 전달 설정·전달값 창을 보통/좁은 크기로 표시했다. 기존 appearance와 설치된 Malgun Gothic으로 한글·단위를 확인했다. 공급 9/15절점·수신 12절점 전환, 행 선택, 시각 `1e` 오류 뒤 `1` 수정, 계산 0회 읽기가 동작했다. 좌표·가중치의 개행 JSON과 수신 시계 dict를 사람이 읽는 표현으로 교정했다. Windows Qt 프로그램 입력·렌더 확인이며 사람의 OS 마우스 조작이나 native ParaView 실행과는 구별한다.

로컬 근거는 `runs/product-development/20261015/pde-s1-windows/`의 `contract-and-actual-01`, `visible-qt-process-01`, 최종 창 캡처 `qwindows-03`이다. 좁은 창의 실제 크기는 전달 680×640, 설정 560×540, Evaluation 950×640, PDE 1000×680이며 뒤의 두 창은 기존 최소 크기를 적용한다.

독립 검토가 발견한 재조회 때 공급 시점 선택 유실은 공통 창과 전용 view를 나눠 교정했다. 읽는 중에는 이전 자료를 지우고 선택만 유지하며 새 전달 선택은 수신 보기로 초기화한다. PySide6의 tuple `findData`가 복원하지 못하는 반례를 추가해 실제 itemData 비교로 고쳤다. 첫 실패(`gui-corrections-02`)를 보존하고 GUI 두 시험을 재실행해 `gui-corrections-03`에서 모두 통과했다. 확대된 창 확인 driver의 callback 대기 오류(`visible-qt-process-02`)도 원 로그로 보존한다. 소유 창과 service는 성공·실패 모두 finally에서 닫았고 각 완료 receipt의 Windows Job은 `job_empty`였다.

PDE 계산 방법 선택기의 내부 ID 표시는 `선형 약형식 (scikit-fem)` 같은 공학 이름으로 바꿨다. 정확한 ID는 itemData·진단에 남기며 Simulation은 기존 MODELS 이름을 유지한다. 방법 선택으로 settings를 자동 변환하지 않고 직접 입력한 미지원 ID·잘못된 타입의 저장 초안도 보존한다. 알려진 방법으로 돌아올 때 기존 settings를 유지한다. 이 반례를 더한 GUI 3건은 `method-captions-04`에서 통과했으며 큰 FE 시험은 반복하지 않았다. 실제 Windows 창의 PDE·Simulation 캡처는 `qwindows-captions-04`, 실행 receipt는 `method-captions-visible-04`이며 두 창을 닫고 계산 0회·`job_empty`를 확인했다.

후속 작은 문구 정리에서 전달 시계 원점 ID와 삼각형별 가중치는 툴팁에 보존하고 주 화면은 공급·수신 시각과 시간 가중치를 표시한다. 숫자 표시는 8유효숫자로 제한하며 원값·보존 자료·전체 값 툴팁은 그대로다. PDE의 함수 공간 계열·메시 수준·모델 영역 제목을 한글로 정리했다. 처음 지정한 전달/반복 tuple이 catalog 두 번째 항목일 때 정확히 선택하는 공통 교정 반례를 포함한 GUI 4건은 `copy-and-initial-selection-05`에서 통과했다. 최종 전달창 캡처는 `qwindows-copy-05/transfer-narrow.png`, 실제 Windows 실행은 `copy-visible-05`다. 큰 FE 계산을 반복하지 않았으며 전체 사용성 완료 주장은 아니다.

Post 경계도 별도로 확인했다. 실제 ParaView 6.2의 pvpython에서 공개된 통제 필드를
기존 writer→입력 등록→Workbench 조회→보존 PVD/VTU reader로 읽었다. P1/정상 온도와
DG0/물리 snapshot 응력의 기저·메시 식별·snapshot 의미, 원 값·단위를 보존한다.
잘못된 선언·배열 위치·원 시각 불일치를 거절하고 이전 형식도 유지한다. 최초 16개와
시간 단위 4개만 추가로 확인했으며 하나의 20개 실행으로 표시하지 않는다. s/ms/min/h의
숫자·단위는 그대로 보존하며 서로 다른 시계의 동등성이나 새 단위 환산을 주장하지 않는다.
메시 식별은 원 선언의 보존이지 native에서 메시를 독립 재계산한 증명이 아니다.
실행은 `_workspace/delivery-numerical-pde/pde-s1-post-metadata/`에 있고 두 Job을 종료했다.

이 Post 확인에는 새 FE 계산이나 ParaView GUI 조작이 없다. MCP SDK/stdio, 전체 legacy
회귀, 일반 비직사각형 geometry·vector/tensor·보존적 전달, 실제 과도 열해석, S2 공유 변수
MDO·adjoint는 이번 확인에 포함하지 않는다. 물리적 적합성과 engineering release는 UNKNOWN이다.
