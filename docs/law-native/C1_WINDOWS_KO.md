# LAW-C1 실제 원 FCStd → 재고정 → FE → cold 인수 실행

이 패킷의 Linux 검사에서 exact frozen JSON의 실제 DP FE와 저장/새 Python 프로세스 cold 읽기는 수행했다. **Windows, FreeCAD 및 같은 FCStd의 실제 새 owner re-freeze는 NOT_RUN**이다. 원 specimen.FCStd와 원 Windows 실패 Job bytes는 이 대화에 첨부되지 않았다. 원파일을 새 synthetic specimen으로 바꾸지 않는다.

## 적용

이미 첫 LAW 인도가 통합된 작업트리에서 수행한다. 병렬 WIP를 보존하고 전용/core hunk만 정합한다. 새 helper/tests/tools는 dedicated.patch에 포함되어 있다. source 폴더와 patch를 중복 적용하지 않는다. reference-only의 전체 modified 파일은 리뷰 전용이지 현재 WIP에 복사하는 파일이 아니다.

```powershell
git apply --check C:\Delivery\LAW-C1\dedicated.patch
git apply C:\Delivery\LAW-C1\dedicated.patch
git apply --check C:\Delivery\LAW-C1\root-integration.patch
git apply C:\Delivery\LAW-C1\root-integration.patch
```

현재 WIP와 hunk가 충돌하면 충돌한 C1 의미만 정합한다. 오래된 공통 파일이나 LAW native 파일 전체로 교체하지 않는다. 공통 patch는 Workbench._settings 한 함수만 바꾼다. 기존 root native solver 타입 guard와 FEM assert_thread 순서는 그대로 남긴다.

## 기존 Python의 오프라인 FELUPE

원 사용자의 기존 NumPy/SciPy/Python을 사용한다. 별도 solver/env/store를 만들지 않는다. wheel SHA256은 아래와 같다. 이 파일은 제공된 pure wheel이며 새 네트워크/DNS 우회 다운로드를 하지 않았다.

```text
felupe-11.1.3-py3-none-any.whl
bytes: 434930
sha256: 0136a783abc010f89d12f33409aa9b7b9d0701a5998b045f7445adb380a58a19
```

이미 FELUPE 11.1.3이 설치된 root 환경은 재설치할 필요가 없다. 필요한 경우 실제 사용하는 Python 경로를 변수에 넣어 아래 명령을 실행한다. --no-deps이므로 NumPy/SciPy 부재는 설치 성공/실행 성공으로 대체되지 않는다. 기존 환경을 준비하지 못하면 해당 단계 NOT_RUN으로 남긴다.

```powershell
$Py = 'C:\YOUR_EXISTING_PYTHON\python.exe'
& $Py -m pip install --no-index --no-deps --disable-pip-version-check C:\Delivery\LAW-C1\offline\felupe-11.1.3-py3-none-any.whl
& $Py -c "import felupe,numpy,scipy; print(felupe.__version__,numpy.__version__,scipy.__version__)"
```

## 원 FCStd를 새 FreeCAD owner로 재열기하는 전체 인수

저장소 root에서 실행한다. FreeCAD.exe와 Python은 실제 설치 경로를 명시한다. output은 아직 없는 새 폴더여야 한다. 원 실패/원 입력/이전 결과 폴더를 출력으로 사용하지 않는다.

```powershell
$FreeCAD = 'C:\YOUR_EXISTING_FREECAD_1_1_4\bin\FreeCAD.exe'
$Original = 'C:\SourceCodes\autonomous-cae-lab\_workspace\delivery-data-material\law-native-freecad\apply-02'
& $Py tools\law_native\c1_acceptance.py `
  --frozen "$Original\frozen-simulation.json" `
  --fcstd "$Original\specimen.FCStd" `
  --freecad $FreeCAD `
  --output 'C:\CAE-C1-Evidence\original-fcstd-r01'
```

기본 FCStd SHA256은 `7af4c7ca8ddb1d183e150b7fd7c3170839b85d2613ab4a4a9df946dac8297d8b`다. 다르면 원파일을 잘못 선택한 것이므로 거절한다. 의도적으로 별도 원파일을 검증할 경우에만 --fcstd-sha256을 명시한다. 그것은 이 원 요청의 exact 원파일 인수와 구분해야 한다.

실행기는 고정 macro를 자기 소유의 새 FreeCAD 프로세스에서만 실행한다. 처음부터 열려 있는 문서가 있으면 거절한다. 원 FCStd를 열고 영구 owner.document_id 및 저장 assignment를 확인한 뒤, `native.read`뿐 아니라 `native.capture`와 `native.freeze`까지 호출한다. live Apply/원 source guard I/O를 tripwire로 금지하며, generation/metadata/원 FCStd bytes 변화가 없어야 한다. `native/captured-native-target.json`과 의미 차이 경로를 남긴다. 실패 시 새 Apply, 재서명, geometry/mesh 재생성으로 고치지 않는다.

재고정이 성공한 경우에만 그 `native/refrozen-simulation.json`의 simulation_draft가 원 입력과 정확히 같은지 확인하고, 기존 Workbench→SimulationDocuments→JobManager→FELUPE adapter로 새 DP Job을 한 번 실행한다. 8Hex8/64적분점/4시점/내부3자유도, 평형 및 every-IP point–FE 비교, accepted state 격리, 기존 tolerance를 검사하고 기존 owner로 저장한다. 다음 별도 Python 프로세스에서 기존 저장 결과를 읽는다. cold 단계는 제출/계산/하위프로세스/FELUPE import/원 source guard 접근을 금지하고 input/job/result/source identity를 확인한다.

각 프로세스는 기존 owned_check 및 execution_control/Windows Job 경로로 소유된다. 성공·실패·timeout 모두 finally에서 자기 프로세스/트리만 종료·reap한다. process-name 검색 종료나 외부 PID 종료는 없다. stage.json의 PASS와 process receipt의 cleanup, 최종 summary.json을 함께 확인한다. exit0만 FE/native 성공으로 보지 않는다.

## FreeCAD 없이 원 frozen 입력의 FE/cold만 검사

```powershell
& $Py tools\law_native\c1_acceptance.py `
  --frozen "$Original\frozen-simulation.json" `
  --output 'C:\CAE-C1-Evidence\exact-input-only-r01'
```

이 모드의 정상 최종 상태는 `PARTIAL_ACCEPTANCE_NATIVE_NOT_RUN`이다. FE/cold가 PASS여도 동일 FCStd 새 owner 재고정 인수는 완료가 아니다. 이번 Pro Linux 실행이 이 모드다.

## 좁은 회귀 검사

```powershell
& $Py tools\law_native\owned_check.py --output 'C:\CAE-C1-Evidence\unit-r01' --timeout 45 -- `
  $Py -m pytest -q tests\law_native\test_c1_provenance.py tests\law_native\test_c1_native_identity.py tests\law_native\test_retention_transfer.py
```

회귀 fixture는 native 모델/라우팅 경계의 단위 증거이며 실제 FreeCAD/FE로 표시하지 않는다. 이 요청은 새 Qt/native/solver 전체 캠페인이 아니다. 세 law의 기존 Windows 성공이나 별도 FreeCAD Apply/read 성공을 이번 동일입력 E2E로 합치지 않는다.
