# 공개 합성 진동계 연구 자료
소프트웨어 연결 검증용 공개 합성 모델이며 실제 회사 부품이나 물성 승인이 아니다.
등록 backend external.oscillator는 외부 SciPy solve_ivp DOP853 프로세스로 m*x''+c*x'+k*x=0을 풀어 response.csv를 쓴다. settings.conditions={mass_kg:1,initial_displacement_m:0.01,duration_s:1}; 초기 속도0.
DOE 변수 stiffness [N/m]40..140, damping [N s/m]0.8..5, 초기값80,2. force [N]와 displacement [m]는 time [s] series다. 목적은 force/abs_max. LHS8개로 시작하고 numerical.analyze로 실제 영향도를 계산한다. 현재 범위는 설계영역이며 불확실성 확률분포가 아니다. 사용자 편집 전에 실행하지 않는다.
연구 질문: 질량 변경 이후 전달력 증가 원인을 어떻게 구별할까? 강성과 감쇠 영향 비교, 별도 질량 조건 및 독립 이력 확인이 필요하다. 합성 동일법칙 동정은 물성 승인이 아니다. 문헌은 감쇠 진동계 식별 가능성과 실험 설계의 근거를 찾고 실제 읽은 범위만 인용한다.