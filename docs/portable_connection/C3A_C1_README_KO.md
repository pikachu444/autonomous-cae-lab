# C3A02 C1 교정 적용과 재현

기준은 실제 보존된 C3A02 ZIP의 product.patch+integration.patch를 첨부 원 source에 적용한 exact tree `f01477ba8a1cee8796b272f49d7c3e47ed226e0b`다. 이것은 공개 Git commit 번호가 아니라 첨부 source/overlay/C3A02를 대조한 local tree hash다. 현행 main `4e2cf2c`와 병렬 WIP의 전체 원본은 이번 첨부에 없으므로 그 트리에서의 적용/Windows 관측을 주장하지 않는다.

## 적용

이미 C3A02가 통합된 기준에서 C1 `product.patch`와 `integration.patch`를 각각 `git apply --check` 후 적용한다. integration.patch는 공통 두 파일의 최소 hunk이다. 공유 파일 전체본을 덮어쓰지 않는다. Sol이 수정하는 GUI 파일은 이 patch에 없다. 이번 ZIP은 증분이며 전체 저장소/이전 인도의 대체본이 아니다.

## 사용자 작업

이동 사본에서 시작할 저장본(예: Material R1, 두 Plan R1)과 보관 Q를 각각 명시한다. Q만 참조하는 과거 Material R2도 필요하면 같은 Material owner를 선택 목록에 포함해야 한다. 현재 working으로 Q를 대신하지 않는다. 원문 보기에서 당시 saved/ack/raw 및 부분 저장 receipt를 각각 읽는다.

이어가기는 현재 owner/session/CAS/buffer 검토 후 별도 명시 조작이다. 당시 acknowledged 입력만 기존 UPDATE로 반영하고 미완성 text는 buffer로 전달한다. 수정·저장·새 Keep는 현재 owner 명령이다. 원본의 recovery/discard 권한이 생기지 않는다. 닫고 새 process에서 새 current Keep를 명시 복구한 뒤 기존 사본 만들기로 재복사한다.

응답 유실은 같은 preview/command/current buffer로 재시도한다. 그 뒤 다른 창에서 run·비교·편집이 추가됐다면 오래된 응답으로 화면을 덮지 않고 거절한다. 기존 buffer와 원 Q는 남는다.

## 작은 Linux 회귀

```sh
python -B -m pytest -q tests/test_portable_recovery_c3a_c1.py
python -B -m pytest -q tests/test_portable_recovery_c3a.py
python -B -m pytest -q tests/test_portable_recovery_c3a_http.py
python -B -m examples.portable_connection_c3a_c1_public --output /absolute/NEW_FOLDER
```

공개 예제는 **자신이 새로 만든 합성 원본과 첫 사본만** 삭제한다. 실제 owner의 부분 저장은 Material SAVED / 첫 Plan FAILED(명시 주입) / 둘째 Plan BLOCKED로 만든다. 과거 Material R2 폴더도 이 합성 원본에서만 제거하여 Q.assets만 남는 경우를 검사한다. 원 store 없는 별도 cold에서 두 Plan 재개·명시 edit/save/Keep·재복사, 별도 current Keep 재열기를 수행한다. 각 Workbench와 child는 finally에서 종료한다.

테스트의 evaluate 반례는 실제 material.evaluate owner command에 bounded failed submission 대역을 연결한다. run append 동작은 실제 owner 코드이고 solver/evaluator 실행은 없다. 직접 필드 변경 tests는 숨은 history/unknown-field 내구성 반례임을 이름과 주석으로 구분한다. 원 작은 table import fixture 실행과 cold의 실행 0을 혼동하지 않는다.

실제 실행 결과·중간 실패·RED·최종 clean-apply 결과는 ZIP의 `VERIFICATION_KO.md`와 logs/에 있다. Windows/실제 Qt 화면/native는 NOT_RUN이다. C3B는 이번 완료 범위가 아니다.
