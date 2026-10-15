# 재현 명령과 검사 분류

두 patch를 적용한 exact baseline 저장소에서 실행한다. 기존 설치된 Python 환경만 사용한다. pytest, numpy 등 baseline의 기존 테스트 의존 외에 새 의존을 추가하지 않았다.

```text
python -m pytest -q tests/test_portable_report_c3b.py tests/test_portable_report_c3b_transport.py tests/test_portable_report_c3b_gui_contract.py tests/test_report_image_core.py::test_capture_existing_store_save_reopen_and_external_removal tests/test_report_image_core.py::test_study_judgments_and_old_assets_survive_image_replacement_undo tests/test_report_image_core.py::test_corrupt_report_asset_read_flags_and_failed_save_keeps_manifest tests/test_report_image_core.py::test_damaged_unpublished_image_revision_cannot_use_degraded_read_to_commit tests/test_portable_recovery_c3a_c1.py::test_r1_saved_only_original_counterexample tests/test_portable_data_q_c2.py::test_resume_retains_acknowledged_calibration

python -m examples.portable_report_c3b_public --output "NEW_PUBLIC_EXAMPLE_DIRECTORY"
```

위 pytest가 최종 44 PASS의 정확한 묶음이다. tests/test_portable_report_c3b_gui_contract.py는 실제 ReportWindow 메서드 AST를 컴파일하여 대역 객체로 command/data/late reply 경계만 검사한다. 실제 Qt import/창 수용이 아니므로 Windows Qt PASS로 해석하지 않는다. HTTP는 실제 기존 loopback LabHTTPServer/Client와 subprocess CLI다. server.shutdown/server_close/thread.join/Workbench.shutdown을 finally에서 수행한다.

공개 예제는 parent 외 별도 process 두 개를 실행한다. 각 child timeout은 45초이며 subprocess.run의 timeout 종료/wait와 child Workbench finally shutdown을 사용한다. 원본이나 첫 사본 삭제는 생성 주체인 parent만 자신의 폴더에 수행하며 child가 종료된 뒤에 한다. timeout/stdout/stderr는 예제 출력 폴더에 기록한다.

## 로그 대응

01 baseline RED / 02 최초 정상 owner smoke / 03 archive-image smoke / 04 최초 2실패 포함 원 로그 / 05 해당 교정 / 06 당시 영향 회귀 / 07 당시 separate-process 예제 / 08 transport·GUI 경계 / 09 owner-history 보강 / 10 최종 국소 suite / 11 최종 separate-process 예제.

07은 그 당시 구현의 예제이고 최종 인도 증거는 11이다. 04의 실패를 10의 통과로 덮어쓰지 않았다. 제공하는 baseline-red probe는 검증 전용 허용 목록 변형으로 실패 원인을 드러낸 것으로 제품 코드가 아니다. final-source manifest의 SHA를 적용 결과와 대조한다.

## 원 Pro 인도본의 수동 통합 참고

현재 main에는 통합되어 있다. 아래는 원 인도물을 별도로 검토할 때의 기준과 명령이며 일반 설치 과정이 아니다.


공개 기준은 22da57c74a8239b1898c13d703fd3d7558f72118이다. source.zip 전체 공유 파일로 현재 WIP를 덮지 않는다. root는 전용 product.patch와 공유 3파일의 root-integration.patch를 각각 확인한다.

```text
git apply --check product.patch
git apply --check root-integration.patch
git apply product.patch
git apply root-integration.patch
```

두 patch는 한 구현 단위다. 하나만 적용해 Report를 지원한다고 판단하지 않는다. 공유 patch가 현행 WIP와 충돌하면 해당 hunk를 실제 현재 파일과 통합한다. 전용 source/에는 공유 파일 전체 대체본이 없다. 새 dependency 설치, 유료 API, provider 또는 solver 실행은 필요하지 않다.


## 기존 CLI·Python 사용


이미 실행 중인 제품 서비스를 쓰면 새 coordinator를 만들지 않는다. Report, 함께 선택할 원자료의 실제 ID는 기존 문서 목록에서 고른다.

```text
python -m caelab.portable_project inspect --service http://127.0.0.1:8766 --document B실제ID --document M실제ID
```

inspect/create의 엄격한 request 파일과 UTF-8 출력이 필요한 자동화는 기존 `caelab.portable_recovery_commands`의 inspect/create를 그대로 사용한다. 이 인도에서 실제 Client 결과와 이 CLI의 Report inspection, create, 같은-command 재확인을 대조했다. 원 서비스가 실행 중이지 않은 store에서는 기존 portable_project의 --workspace 옵션을 사용한다. 실행 중인 store에 두 owner process를 임의로 붙이지 않는다.

Python은 기존 `inspect_copy/create_copy/open_project`와 `document_command`를 사용한다. 공개 예제에 실제 호출과 finally shutdown이 있다. 수동 JSON/hash 편집은 사용자 동선이 아니며 내부 파일을 편집하면 검증이 거절될 수 있다.
