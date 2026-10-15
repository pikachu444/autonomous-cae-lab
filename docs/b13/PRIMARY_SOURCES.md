# B1.3 지원 문법·원결과 의미의 근거

## 이 인도의 제품 원본

사용자 직접 업로드 `source.zip`: 7,870,993 bytes,
SHA256 `2944156387a56ee2303e0190dfa13ec6610fed305cda169716d9dbf028c8f781`.
첨부 manifest 1,440개 항목의 bytes/SHA 및 1,428개 raw Git blob SHA1을 실제 원본과 대조했다.
제품 기준 f3a9f747ec930b35f0788505a447d9994b839459, upstream pin 3e48bf6138f495299f45b1af254bfb4aaff307b8.
7개의 FreeCAD reference/license 항목은 제품 Git 파일이 아니라 별도 공개 배포 참조이다.

`reference_FreeCAD_1.1.4/Fem/ObjectsFem.py`, `femmesh/meshtools.py`,
`femsolver/calculix/write_femelement_geometry.py`, `write_constraint_pressure.py`,
`write_femelement_material.py`, `writer.py`의 첨부 원문을 재사용했다. 라이선스 주석은 변경하지 않았다.
새 별도 native writer/solver 설치로 대체하지 않는다.

## CalculiX 2.22 공식 문서

공식 매뉴얼: https://www.dhondt.de/ccx_2.22.pdf

§5.14 및 *EL FILE, *EL PRINT, *NODE FILE, *NODE PRINT, *SECTION PRINT,
*SHELL SECTION, *BEAM SECTION, *NORMAL의 출력 의미를 구별한다.
SECTION FORCES와 OUTPUT=3D는 동시에 같은 결과로 취급하지 않는다.
FRD 응력/변형률은 내부 적분점에서 확장 절점으로 복원/평균된 값이고,
DAT S/E/COORD의 내부 관측과 별도다. RF를 모든 MPC/구속 반력의 완전한 합으로 보장하지 않는다.

본 작성 환경의 웹 PDF screenshot 호출은 InternalError로 실패했다. PDF 그림을 시각적으로 검수했다는 주장은 하지 않는다. 아래 실제 공식 소스 본문을 추가로 읽어 타입·연결·적분점 규칙을 확인했다.

## 실제 읽은 공식 solver 소스

고정 참조: https://github.com/Dhondtguido/CalculiX/tree/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54

| 파일/읽은 구간 | blob SHA1 | 적용 근거 |
|---|---|---|
| src/gen3delem.f 1–540 | 41aef58ecbf8c6f5a371598fd5bb5cc3fd5243b2 | `.12d` original/expanded topology 기록, B32R→C3D20RB의 위치와 char8 유지 |
| src/gen3dfrom1d.f 1–310 | 원문 조회, 본 인도에 원 solver 코드 복제하지 않음 | RECT corner/midside/원 빔 절점의 정확한 연결 위치. 실제 ID는 `.12d`에서 읽음 |
| src/beamsections.f 75–455 | fee5a81105f7615dfa081f42ee699cdc360e71a9 | RECT이면 char8=R. 따라서 `.12d`의 `B32R   R` 및 `C3D20RBR` |
| src/e_c3d.f 260–785 | 98bd912129b8fe021cd9d90142cbbe3f3cb69abd | RECT/CIRC의 20RB는 mint3d=50, gauss3d13 |
| src/printout.f 100–385 | 원문 조회 | DAT 원 header 및 응력/변형률 성분 순서 |
| src/printoutint.f 1–275 | 3becef2a0b98774fdb27da5217671cfd9749ceb7 | DAT 출력도 50점, COORD 계산 경로의 소스 위험 |
| src/gauss.f 1–125, 222–370 | 748c93f41d3166d6d48dc1d4415897693bc1bad3 | gauss3d13의 50개 실제 순서. 일반 8점이나 표준 5점 Gauss 좌표를 대신 쓰지 않음 |

50점의 처음 8점은 x가 빠르게 변하는 ±0.577350269189626와 단면 ±0.5773502692 조합이다. 이후 각 x=-g,+g에서 단면의 ±0.9258200998, ±0.5773502692, 0 조합 중 이미 포함한 4개를 제외한 21개씩이 이어진다. `beam_gauss.py`는 이 번호를 식별/검증하기 위한 순서를 제공한다. 이것으로 native COORD를 생성하거나 실제 원 관측을 대체하지 않는다.

## COORD 경로: 확인한 것과 확인하지 못한 것

읽은 `printoutint.f`는 `coords(3,27)`을 선언하면서 RECT 20RB의 mint3d를 50으로 정한다. COORD/local 출력 계산 분기에는 `lakon(nelel)(4:8).eq.'20RB'` 비교 및 char8 B/C 판정이 있고, RECT의 R과 맞지 않는다. 따라서 읽은 소스만으로 정상 50점 COORD 출력이 보장된다고 결론낼 수 없다. 현재 설치 Windows 2.22 바이너리에 어떤 수정이 들어 있는지, 실제 실행이 실패/손상하는지는 **미확인**이다. 바이너리 crash나 성공을 관측한 것처럼 쓰지 않는다.

제품 writer는 사용자가 선택한 3D run에서 S/E/COORD를 명시 요청한다. reader는 50점 전체 coverage, 실제 `.12d` topology, FRD corner/midside, DAT 원 COORD, printed-coordinate precision을 함께 검증한다. 불일치/불완전 출력은 거절하고 원파일/실패 로그를 보존한다. 검사에 쓰는 계산 좌표는 오직 거절을 위한 대조값이며 결과로 출력하지 않는다. solver 소스 패치·교체·허용치 완화로 이 문제를 숨기지 않았다.

## 후처리에서 명시한 유도량

단면 유도 회전은 최소제곱 `u_i ≈ t + θ×(x_i-centroid)`의 미소 회전 계수다. native generalized DOF 추출이 아니다. 완전한 관측과 rank=6을 요구하고 잔차를 보존한다.

stress traction은 실제 확장 S8 단면 face의 native 복원 tensor에 S8 보간과 3×3 Gauss 실제 Jacobian 적분을 적용한 값이다. 응력 적분과 이산 구속 반력은 같다는 보장이 없다. 부호는 실제 끝의 외향 법선이고 기준점 이동은 `M(r1)=M(r0)-(r1-r0)×F`다. 이 식과 일정/선형 응력의 평형·중복/누락·부호 반례는 순수 수학 검사이며 실제 solver benchmark로 세지 않는다.
