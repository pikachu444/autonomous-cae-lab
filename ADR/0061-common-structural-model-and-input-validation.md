# 0061 — 공통 구조 모델과 solver 변환기

결정: 사용자 [이슈 #10](https://github.com/pikachu444/autonomous-cae-lab/issues/10).

구조 해석은 FreeCAD FEM 객체와 Abaqus inp 어휘를 따르는 공통 모델 하나로 표현한다.
형상·메시·집합·재료·단면·단계·조건·접촉·초기조건·출력을 담고 solver를 선택한다.
CalculiX는 inp, OpenRadioss는 inp2rad, Code_Aster는 MED/.comm 변환기를 사용한다.
PDE, 재료점, 외부 계산기는 각자의 형식을 유지한다.

변환기는 요소·재료·접촉·단계 지원표와 입력 검사를 책임진다. 검증 사례가 없다는
이유로 실행을 막지 않는다. 필요한 입력·결과 처리를 함께 구현하며 결과의 검증 상태와
solver 오류·경고를 보존한다. 계산 성공은 공학적 승인이 아니다.

ADR0060의 공통 구조 모델 금지와 ARCHITECTURE의 벤치마크 선행 등록 조건을 대체한다.
1단계는 사용자 FreeCAD→CalculiX→ParaView→토론·수정·재실행·저장 흐름을 연결하며,
기능별 backend 통합과 공통 모델 내부 교체는 2단계다.
