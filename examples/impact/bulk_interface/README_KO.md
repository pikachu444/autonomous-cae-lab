# 공개 합성 벌크·계면 입력

모든 계수는 제품 연결/reader 회귀를 위한 **SYNTHETIC** 수치다. 물성 교정이나 공학 수용 예제로 사용하지 않는다. 제품의 `default_law()`에는 이 값들이 들어 있지 않다.

`example.settings()`는 기존 positive-thickness cohesive coupon에 벌크 LAW36 소성과 INIEVO 교정표를 명시한 작은 입력이다. 벌크 2개 요소와 계면 1개 요소, bulk와 interface의 분리 선택을 검증한다. 기본 예제에는 delayed TYPE24 재접촉이 없고, 실제 전체 반복 계면 이력을 재현했다고 주장하지 않는다. 해당 카드 연결/이중계상 위반 감지는 전용 interface tests의 합성 관측으로 검사한다.

`bulk_coupon.settings(nx, output_factor, cfl_scale)`은 1 mm³ 합성 벌크를 X 방향 1개 또는 2개 affine C3D8R로 나누고 아래면을 고정, 윗면에 초기 속도를 주는 prospective kinetic-release 입력이다. 같은 기존 Simulation과 native adapter를 사용한다. native 계산 전에는 실제 손상·삭제가 언제 생기는지 확정하지 않는다. 출력 간격 변경과 native /DT scale 변경은 다른 비교다.

설정 파일 생성만 필요한 경우, 저장소 루트에서 다음을 실행한다. 기존 파일은 덮지 않는다.

```text
python -m examples.impact.bulk_interface.example "synthetic-b-settings.json"
```

운영자의 기존 pinned Windows runtime으로 실제 계산을 명시 요청하는 명령은 다음과 같다. 이 인도에서는 NOT_RUN이다. runtime 선택/해시 검사는 기존 opencourant_runtime을 그대로 따른다. 설치·다운로드·업데이트 기능은 없다.

```text
python -m examples.impact.bulk_interface.run_local --workspace "C:\CAE\B-check\reference" --execute-synthetic --nx 1 --cfl-scale 0.9
python -m examples.impact.bulk_interface.run_local --workspace "C:\CAE\B-check\mesh" --execute-synthetic --nx 2 --cfl-scale 0.9
python -m examples.impact.bulk_interface.run_local --workspace "C:\CAE\B-check\time" --execute-synthetic --nx 1 --cfl-scale 0.45
python -m examples.impact.bulk_interface.run_local --workspace "C:\CAE\B-check\sampling" --execute-synthetic --nx 1 --cfl-scale 0.9 --output-factor 0.5
```

각 명령은 새 Simulation을 열고 저장한 뒤 기존 JobManager로 명시 실행한다. 종료와 결과/로그를 보존해 다시 저장한다. Ctrl+C나 예외도 finally의 기존 Workbench 종료 경로를 사용한다. 다른 사용자 프로그램을 종료하지 않는다. 실패 파일을 읽으려고 위 명령을 다시 실행하지 않는다. 같은 해석 문서에서 원 작업을 선택하고 **연구 → 보존 결과 다시 읽기…**를 사용한다. B의 추가 벌크·계면 선택을 이 읽기 경로에 연결하는 후속 작업은 사용법의 미완료 범위를 확인한다.

`NATIVE_ACCEPTANCE_PLAN.json`은 실행 전 고정한 작은 비교량/기준이다. 실제 run 결과가 기준을 만족하지 않으면 해당 조건을 실패/UNKNOWN으로 남기고 계수나 허용치를 몰래 바꾸지 않는다. 벌크 native 수용, 부분 손상 계면 loop, 삭제 후 recontact, native pair force/impulse, Windows Qt 작업을 각각 별도로 기록한다.

제품 API와 선택/오류·저장/재후처리 계약은 `docs/IMPACT_BULK_INTERFACE_KO.md`, 전체 잔여는 `docs/IMPACT_B_ORIGINAL_LEDGER.md`를 따른다.
