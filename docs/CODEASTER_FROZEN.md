# FreeCAD 사용자 모델을 기존 Code_Aster로 계산

`structure.codeaster.frozen`은 FreeCAD의 기존 정적 FEM 내보내기를 받아
Code_Aster17.4로 계산하는 전용 어댑터다. 기존 Code_Aster 사각 블록·SSNP121A
기준 예제와 그 고정 입력·허용값은 바꾸지 않는다. 새 메시 생성기나 해석 엔진을
추가하지 않는다.

현재 입력 변환·실행 요청·결과 연결 코드는 구현됐지만, 이 Windows 환경에는 등록된
Code_Aster 런타임이 없어 실제 Code_Aster 계산은 확인하지 않았다. 설치된 CalculiX의
일반 해석은 별도로 사용할 수 있다.

## 같은 모델로 이어지는 범위

FreeCAD에서 사용자의 단일 solid와 기존 C3D10 메시, 하나의 등방 선형 재료,
선택한 Fixed 면과 Force 면을 준비하고 `pre.freeze`로 보관한다. 기존
`freecad-fem-frozen`에는 원 좌표·native/입력 요소 순서, 선택면에서 실제로
분배된 절점 하중, 구속 DOF, 재료, 원 native deck, 편집 가능한 FCStd가 함께
저장된다. `frozen_fem.validate_snapshot`의 해시·전체 입력 대조·Jacobian·강체
모드 관문을 그대로 적용한다. 임의 형상과 곡면 중간절점은 이 관문을 통과한
원 좌표 그대로 전달하며 사각 블록으로 교체하지 않는다.

어댑터는 같은 mesh/material/Fixed/Force를 native ASTER `.mail`과
`MECA_STATIQUE` 입력으로 옮긴다. C3D10과 ASTER TETRA10의 여섯 edge 순서가
같으므로 추가 순열을 적용하지 않는다. 원 ID와 native 번호 사이의 대응을
보존하고, 실제 import 뒤 전 좌표·요소 연결 순서·Fixed 선택을 확인한 후
계산한다. 접촉, 소성, 기하 비선형, shell/beam, 동적 단계와 여러 solid는
이 경로에서 실행하지 않으며 해당 조건을 원 snapshot 관문에서 거절한다.
다른 어댑터의 기존 지원 조합은 유지된다.

## 입력과 실행 위치

공유 서비스의 실행 입력은 다음 형태다. 클라이언트가 서버의 임의 파일 경로를
지정하지 않고 기존 등록 snapshot ID를 사용한다.

```python
client.submit('run', {
    'backend': 'structure.codeaster.frozen',
    'settings': {'data_id': registered_snapshot_id},
})
```

완료된 `pre.freeze` 명령이 있으면
`client.native_submit(export_command_id, solver='codeaster')`로 같은 snapshot을
등록·제출한다. 같은 명령/솔버 재시도는 같은 작업을 돌려주며, 기본 CalculiX
작업과 Code_Aster 작업은 별도 ID를 갖는다. 접촉·동적 단계 등의 다른 내보내기에
Code_Aster를 지정하면 지원 범위를 설명하고 제출을 거절한다.

직접 Python에서는 `FrozenFemCodeAsterAdapter().run({'snapshot_path': absolute_manifest},
output=new_directory)`를 사용한다. 출력 폴더는 비어 있어야 한다.
runtime을 찾기 전에 원 snapshot과 native 실행 파일을 보관하므로, runtime이
없어도 `solver/model.export`, `model.comm`, `mesh.mail`, `mesh.json`,
`input.json`과 `frozen_input/editable.FCStd`를 확인할 수 있다.

기존 Linux Singularity/SIF 환경을 재사용한다. 기존 `CAELAB_CODEASTER_IMAGE`,
정확한 `CAELAB_CODEASTER_IMAGE_SHA256`와 기존 실행 경로가 필요하다.
기존 runtime preflight는 Singularity·Gmsh·prlimit을 확인하지만 이 어댑터는
Gmsh를 실행하거나 재메시하지 않는다. 설치·WSL 생성·호스트 등록·계정 설정은
수행하지 않는다. Windows UI가 연결된 실제 서비스의 실행 환경을 사용하며,
등록되지 않은 원격 호스트나 다른 runtime으로 자동 전환하지 않는다.

## 결과를 읽고 다시 열기

모든 절점의 native `DEPL`과 `REAC_NODA`, 모든 요소의 5개 `SIEF_ELGA` 점을
원 테이블·MED와 함께 보존한다. 누락·중복·다른 order·다른 물리 위치는 읽기
실패이며 0으로 보충하지 않는다. 적분점 좌표는 곡면 TET10의 실제 좌표
사상과 대조한다.

- `post/displacement.vtu`: 기존 VTU writer를 사용한 실제 변위(mm), 반력(N),
  원 절점/요소 ID 및 입력 Fixed/Loaded 분류.
- `post/stress_points.vtu`: 실제 native 적분점 위치(mm)의 응력(MPa) 점 자료.
  절점 응력으로 외삽하거나 평균하지 않는다. 원 요소·점·subpoint를 보존한다.
- `post/native_fields.json`, `solver/*.table.json`, `solver/results.med`:
  원 물리량·대응과 native 원출력.

주 `post_artifact`와 `additional_post_artifacts`는 기존 registrar가 해시를
검증해 Post 입력으로 등록할 수 있는 상대경로·바이트 수·해시·단위/좌표계
metadata를 가진다. 저장 결과 읽기는 솔버를 다시 실행하지 않는다.
정적 `INST`는 저장된 load parameter이며 초 단위 물리 시간으로 표시하지 않는다.
실행 성공은 메시 정확도·재료 적합성·실물 검증·공학적 승인을 뜻하지 않는다.

계산 목록에서 작업을 선택하고 **후처리에서 열기**를 누른다. 저장된 공간 결과가
하나면 바로 열고, 여러 개면 **변위와 반력 (mm, N)** 또는 **적분점 응력 (MPa)**처럼
물리량과 단위로 구분해 선택한다. 취소하면 결과를 열거나 계산을 다시 실행하지 않는다.
이 선택 창의 조작과 지연 응답 처리는 Qt에서 확인했으며 실제 Code_Aster 결과의
전체 사용자 흐름을 검증한 것은 아니다.

## 이번 확인과 한계

전용 입력/결과 검사13개는 원 입력 보존, 비정렬 native 번호 대응, 곡면 중간절점,
누락/중복/잘못된 위치 거절, runtime 부재 시 입력 보관, 변위/반력 VTU와 적분점
분리를 확인한다. 검사 결과의 native 테이블과 FreeCAD 객체는 명시적 대역이다.
추가 Workbench/JobManager 통합검사3개와 기존 DesktopLinks 계약검사3개는
정상 제출·재시도·저장 결과 읽기와 첫째/둘째 Post 등록 실패를 확인했다.
둘째 등록이 실패해도 실제 계산 원출력과 첫 등록은 남지만 작업은 실패이며,
전체 Post 준비 완료로 표시하지 않는다.
실제 Windows Code_Aster 실행, 곡면/구멍 있는 실제 FCStd의 새 solver 실행과
그 결과의 native ParaView UI 확인은 **NOT_RUN**이다. 현재 환경에서 설정된
Singularity/SIF를 찾지 못했으며 다른 runtime을 설치하지 않았다.
위 명시적 대역 출력을 설치된 ParaView6.2의 실제 VTU reader와 기존
`validate_declared_metadata`로 읽어 두 파일의 단위·좌표계·정적 상태와
배열 선언이 수용됨을 확인했다. 이 reader 확인은 Code_Aster 수치 실행이
아니다. `scripts/native_check.py`로 실행한 소유 프로세스는 종료 후 정리됐다.

native ASTER 파일의 80자 줄 제한과 이어지는 레코드는
[공식 구조](https://codeaster.gitlab.io/doc/docaster/manuals/man_u/u3/u3.01.00/Structure_du_fichier_de_maillage.html)와
[공식 형식](https://codeaster.gitlab.io/doc/docaster/manuals/man_u/u3/u3.01.00/Liste_des_formats_de_description.html)을
따른다. 고정 런타임과 native 테이블의 원 처리는 기존 `codeaster_worker.py` 및
`codeaster_elasticity.py`의 책임을 재사용한다.

CAD 담당이 실제 FreeCAD/Gmsh로 만든 외반경8mm·보어반경2.5mm·높이14mm clamp의
단일 solid snapshot(3,415절점/1,886 C3D10)도 입력 생성에 사용했다.
전체 좌표·요소 순서·948 Fixed DOF·재료·원분배하중과 편집 파일을 보존했고
생성 `.mail`의 최대 줄 길이는49자였다. 이 확인에서 원 native 입력의 합력은
설정100N과 달리 −Z99.7336210423518N임을 발견했다. 두 솔버 입력의 숫자를
임의로 맞추지 않았으며 원자료와 차이를 보존해 CAD 담당에게 전달했다.
실제 Code_Aster import/해석이나 그 계산 결과의 검증을 뜻하지 않는다.
원 입력 대응의 로컬 근거는
`_workspace/codeaster-frozen/actual-curved-clamp-input-report.json`이다.
