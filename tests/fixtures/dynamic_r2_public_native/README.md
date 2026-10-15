# 원 공개 native 읽기 fixture

이 디렉터리는 사용자가 제공한 public-native-sample 그대로다. FRD는 첫 3개 실제 프레임과 명시 derived 종결자, DAT는 해당 시각의 원 prefix, rout는 전체 실제 Windows 출력이다. 원 full400 FRD/DAT가 아니다. EVIDENCE_MANIFEST.original.json에는 업로드되지 않은 전체 원 raw의 hash/크기와 설치 binary hash가 구별되어 있다.

이 fixture와 tools/profile_dynamic_r2.py의 cyclic synthetic-size double을 실제 새 ccx 실행 또는 물리 수용으로 계산하지 않는다. 원 FRD/DAT/rout/입력/snapshot 파일은 수정하지 않는다.
