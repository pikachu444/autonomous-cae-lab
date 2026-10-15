# 같은 Plan owner를 편집하는 변수 위젯

`apps.research.plan_variables_widget.NumericalPlanVariablesWidget(parent=...)`는
독립 Numerical 창의 표를 옮기지 않고 새 Qt 위젯을 만든다. Data Pro가 작성한
`PlanOwnerAdapter`와 `embed_plan_variables` 계약을 소비한다. Material의 선택 Plan
표시·검토 대화상자·관련 저장과 공통 transport 통합은 각각 해당 담당 영역이다.
이 위젯만으로 Material embed와 관련 저장 전체를 완료한 것은 아니다.

```python
widget = embed_plan_variables(NumericalPlanVariablesWidget,
    parent=material_panel, adapter=adapter, document=reviewed_document)
widget.patchPreviewRequested.connect(review_explicit_owner_preview)
```

공개 메서드는 `bind_owner(adapter, document)`, `has_unapplied_buffer()`,
`buffer_snapshot()`, `show_patch_result(outcome)`, `detach_owner()`다. 공개 Signal은
`patchPreviewRequested(preview)`, `dirtyChanged(bool)`, `ownerActivated(document_id)`다.
`buffer_snapshot()`은 해당 위젯 안의 편집기만 확정하고 전체 Plan draft의 복사본을
돌려준다. 어댑터나 위젯이 새 문서 owner를 만들지 않는다.

호스트는 `document_snapshot()`으로 현재 연결된 정확한 문서 receipt의 복사본을 읽는다.
이 accessor는 네트워크 재조회나 셀 확정을 하지 않으며 미확정 buffer의 원래 identity를
관련 저장/닫기 복구와 연결하는 데 사용한다. 분리 상태에서는 `None`을 돌려준다.

호스트는 `set_variable_labels({id: 표시명})`으로 실제 선택 모델의 물리 명칭을 표시한다.
이름의 원 ID·버퍼·단위는 유지하며 알 수 없는 변수를 다른 물리량으로 추정하지 않는다.

변수 이름·단위와 Request Plan의 탐색 여부는 읽기 전용이다. 현재 지원하는
시작값·하한·상한·탐색 여부·선형/로그 변환은 기존 typed worksheet delegate와
PlanTable 붙여넣기를 사용한다. 아직 지원하지 않는 이산/종속 변수 엔진의 구현을
이 표로 대신하지 않는다. 선언된 readonly/dependent 행은 편집하지 않는다.

변경 검토는 어댑터의 preview만 호출한다. 호스트가 결과를 검토한 뒤 명시 execute와
저장을 수행한다. APPLIED 결과라도 owner·검토 입력·현재 identity·현재 셀 버퍼가
모두 일치할 때만 편집 완료로 바꾼다. 늦은 응답, UNKNOWN, 다른 owner, 변경된 저장
개정이나 편집 중인 셀은 기존 편집을 덮지 않는다. 미적용 편집이 있으면 다른 Plan
연결로 바꾸지 않는다. 분리와 위젯 종료는 shared owner를 닫거나 계산을 취소하지 않는다.

표에 포커스가 있을 때 Ctrl+Z/Y는 먼저 해당 위젯의 미적용 변경을 취소/재실행한다.
같은 창의 Material 실행 취소로 전달하지 않는다. 편집기 안의 Ctrl+Z와 Enter/Esc는
기존 Qt 편집 동작을 유지한다. 적용 후의 실행 취소는 기존 owner 명령을 사용한다.
응답이 유실되면 같은 command ID의 결과만 다시 확인하며 새 실행 취소를 만들지 않는다.
owner Redo는 어댑터의 대칭 `redo` transport가 연결된 경우에만 활성화한다.

검사에서는 두 owner의 포커스·키보드·미확정 편집·늦은 응답과 입력 보존을 확인했다.
실제 초기 Pro adapter/preview/execute와 기존 Numerical owner를 붙여 적용·Undo 및
job 증가 없음을 별도로 확인했다. Material 안의 최종 배치와 공통 HTTP transport는
통합 후 해당 담당의 검사로 확인해야 한다. Windows 세션의 clipboard 왕복 한계 때문에
블록 paste 의미 검사는 offscreen Qt 결과이며 native clipboard 성공으로 세지 않는다.
