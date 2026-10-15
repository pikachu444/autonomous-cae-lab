# Data 원 보정 자료와 미완성 셀을 새 사본에서 이어가기

이 증분은 실제 C3A02+C1 위의 Data 교정이다. C1 R1/R2를 다시 구현하거나 기존 Windows 25 PASS를 취소하지 않는다. Report/Study/Expert/PDE/Simulation/Evaluation 및 managed FCStd/Post C3B는 필수 별도 후속이다.

## 사용자 동선

기존 사본 검토에서 Data 저장본과 원 Data 보관 Q를 함께 명시 선택한다. `saved_only`를 선택해도 그 Q의 acknowledged 보정 자료와 미완성 raw는 그대로 이동한다. 원 store 없이 보관 원문/보정 CSV를 읽은 다음, 현재 편집 owner와 현재 buffer 덮어쓰기를 검토하고 **명시 재개**한다. 이때 raw `1e`를 수치로 적용하거나 import/solver를 호출하지 않는다.

현재 Data의 보정 자료를 검토하고 정상적인 owner 편집을 이어간다. 명시 저장 뒤 기존 보관(Keep)으로 **새 current Q**를 만든다. 기존 close gate로 닫고 새 프로세스에서 현재 session 변경을 명시 승인하여 새 Q를 복구한다. 다시 사본을 만들 때 원 archive와 새 current Q를 각각 명시 선택한다. 원 Q의 recover/discard 권한을 새 store로 옮기지 않는다.

GUI/포커스/UTF-8 수정 파일은 이 증분에 없다. 기존 GUI가 같은 preview/resume 및 raw packet을 소비한다. Windows/Qt/native 실행은 이번 환경에서 NOT_RUN이다.

## root 적용

정확한 작성 기준은 제공 공개 snapshot에 실제 C3A02·C1을 적용한 local tree `7d7b79ec49bf095480c5b76878314852bc3852ed`다. 최신 `7d8d852 + Law/B13 WIP` 전체 tree는 제공되지 않았으므로 그 기준 적용은 root가 최소 hunk를 대조한다. 첨부 Windows 재현이 체크한 7개 source SHA는 이 기준과 일치함을 확인했다.

이미 C1이 통합된 코드에 **이번 product.patch, 이번 integration.patch만** 순서대로 적용한다. 원 C3A/C1 patch를 다시 적용하지 않는다. 전용 source 전체 파일은 검토/참조용이며, 공통 Data/Material 파일 전체본을 덮어쓰지 않는다.

```sh
git apply --check product.patch
git apply product.patch
git apply --check integration.patch
git apply integration.patch
```

## 작은 검증과 공개 예제

제품 저장소 루트에서 기존 Python 환경으로 실행한다. 준비는 원 `create_case`의 실제 CSV 성공 import 1회·의도 FAILED import 1회다. cold 단계에는 새 job/evaluator/DAG/provider/FE가 없다. 네 명령은 각각 별도 foreground 프로세스다. 각 Workbench는 finally에서 종료한다. `prepare`는 새 폴더만 받으며 자기 source fixture를 지우지 않고 이름을 바꿔 보존한다.

```sh
python -m examples.portable_connection_data_c2_public prepare NEW_CASE
python -m examples.portable_connection_data_c2_public finish NEW_CASE/copy
python -m examples.portable_connection_data_c2_public recover-recopy NEW_CASE/copy --destination NEW_RECOPY
python -m examples.portable_connection_data_c2_public read-recopied NEW_RECOPY
python -m pytest -q tests/test_portable_data_q_c2.py
```

pytest는 하나의 module fixture를 재사용한다. 이미 준비한 사본이 있으면 `DATA_C2_PREPARED_COPY`에 지정하며 각 테스트는 자기 복제본에서만 작업한다. 15개 국소 case에는 서로 다른 프로세스의 전체 왕복, missing/tampered declared source/input.json, raw-only ID/path 거절, current 권한/token, Data 유실 응답/whole post-state, retained metadata 원 bytes, 미발행 쓰기 실패가 포함된다. metadata 국소 case의 추가 명시 upload는 자료 등록일 뿐 import/FE 실행이 아니다. 기존 25/26/59 전체를 실행할 필요가 없다.

`public-example-data-q-c2.zip`은 실제 saved_only+DataQ 사본이며 old operational Q를 새 raw-recovery로 설치하지 않은 출발 자료다. 기존 `extract_project`로 새 위치에 추출한 후 위 `finish` → `recover-recopy` → `read-recopied`를 사용할 수 있다. 받은 사본을 통째 복제/이동한 뒤 이전 위치의 current Keep 권한을 그대로 쓰지 말고, 원 archive로 읽고 현재 명시 재개/새 Keep를 수행한다.

실제 수행 결과와 미실행 플랫폼은 인도 ZIP의 `VERIFICATION_KO.md`와 원문 logs를 본다. 소스 제공, 예제 준비, archive 원문 읽기, 현재 편집 왕복, Windows 실제 화면 관측을 서로 구별한다.
