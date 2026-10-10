import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Panel,
  Handle,
  Position,
  MarkerType,
  applyNodeChanges,
  applyEdgeChanges,
  useNodesInitialized,
  useReactFlow,
  useUpdateNodeInternals,
  type Node,
  type Edge,
  type NodeProps,
  type Connection,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  MessageSquare,
  Send,
  Reply,
  X,
  FileText,
  Link2,
  ExternalLink,
  GitBranch,
  RefreshCw,
  Plus,
  Check,
  ChevronRight,
  Maximize2,
} from "lucide-react";
import {
  Workspace,
  Toolbar,
  Button,
  Badge,
  Field,
  Properties,
  Notice,
  useStored,
} from "./common";
import "./ExpertWorkbench.css";

type Evidence = {
  title: string;
  origin: string;
  excerpt: string;
  finding: string;
  opposing?: string;
};
type Message = {
  id: string;
  author: string;
  time: string;
  body: string;
  evidence?: Evidence;
  reply?: string;
  plan?: boolean;
};
const ev = (
  title: string,
  excerpt: string,
  finding: string,
  opposing?: string,
): Evidence => ({
  title,
  origin: "합성 자료 · 상호작용 검토용 원문",
  excerpt,
  finding,
  opposing,
});
const topics = [
  {
    id: "material",
    title: "재료 파라미터 식별",
    sub: "단축 인장 · 민감도 · 검증",
    messages: [
      {
        id: "mat-1",
        author: "연구자",
        time: "09:12",
        body: "세 속도의 인장 곡선으로 항복 응력과 경화 계수를 식별하려고 합니다. 현재 데이터의 어떤 부분을 먼저 점검해야 하나요?",
      },
      {
        id: "mat-2",
        author: "재료 전문가 · 예시",
        time: "09:13",
        body: "먼저 탄성 구간과 소성 구간의 가중치를 분리하세요. 장비 컴플라이언스가 초기 기울기에 섞일 수 있으므로 탄성계수를 곧바로 자유 변수로 두는 것은 보류할 근거가 있습니다.",
        evidence: ev(
          "시험 메모 / 인장 시험 03",
          "변위는 크로스헤드에서 측정하였다. 신율계 기록은 0.012 변형률 이후 사용할 수 없다. 초기 하중 구간에서 치구 미끄럼이 관찰되었다.",
          "초기 기울기를 재료 특성으로 단정할 수 없습니다.",
          "시험 02의 신율계 기울기는 문헌 탄성계수와 일치합니다. 모든 곡선에 같은 보정을 적용할 근거는 부족합니다.",
        ),
      },
      {
        id: "mat-3",
        author: "수치 전문가 · 예시",
        time: "09:15",
        body: "현재 24점 DOE에서는 항복 응력이 초기 소성 구간에, 경화 계수가 후반 구간에 주로 영향을 줍니다. 후보 평가와 민감도는 수치 도구가 수행한 결과를 읽는 흐름으로 구성합니다.",
        evidence: ev(
          "민감도 표 / screening.csv",
          "구간별 정규화 민감도: sigma_y 0.72 / 0.18, K 0.19 / 0.66. 24개 후보 중 3개는 후반 구간 출력이 없다.",
          "출력이 없는 3개 후보는 미평가로 유지합니다.",
          "변수 범위를 넓히면 순위가 바뀔 수 있으므로 전역 민감도로 확장해 해석해서는 안 됩니다.",
        ),
      },
      {
        id: "mat-4",
        author: "연구자",
        time: "09:17",
        body: "후반부 잔차가 큰 후보를 버리기 전에 측정 구간 정렬도 확인하고 싶습니다.",
        reply: "mat-3",
      },
      {
        id: "mat-5",
        author: "재료 전문가 · 예시",
        time: "09:18",
        body: "범위를 유지하고 12개 후보를 추가하며 시험 02를 검증 전용으로 남기는 계획 변경을 제안합니다. 적용은 연구 계획만 변경합니다. 실행 제출은 Runner에서 별도로 진행합니다.",
        plan: true,
        evidence: ev(
          "연구 계획 / 식별 계획 r1",
          "총 후보 24개. 시험 01, 02, 03을 모두 식별에 사용한다. 예산 상한 30분. 검증용 시험 미지정.",
          "시험 02를 보류하면 검증 데이터가 생기지만 식별 데이터는 줄어듭니다.",
          "시험 02가 유일하게 신율계를 사용한 데이터라면 오히려 식별에 포함하는 쪽이 안정적일 수 있습니다.",
        ),
      },
    ],
  },
  {
    id: "defect",
    title: "파손 원인과 반대 근거",
    sub: "접촉 · 경계조건 · 경쟁 가설",
    messages: [
      {
        id: "def-1",
        author: "연구자",
        time: "10:03",
        body: "칩 가장자리의 파손이 재료 취성 때문인지 접촉 조건 때문인지 구분하고 싶습니다.",
      },
      {
        id: "def-2",
        author: "파손 전문가 · 예시",
        time: "10:04",
        body: "접촉 압력 최대점과 최초 파손 위치가 다릅니다. 접촉 압력만으로 원인을 설명하기는 어렵습니다. 최초 파손 시간 직전의 주응력과 경계 반력을 함께 확인할 것을 제안합니다.",
        evidence: ev(
          "관찰 기록 / impact-observation.txt",
          "최초 균열: 가장자리 A, 0.42 ms. 최대 접촉 압력 위치: 중앙 B, 0.31 ms. 두 시간은 영상 동기 기준이다.",
          "압력 최대값과 최초 균열은 위치·시간이 일치하지 않습니다.",
          "영상 시간 오차는 ±0.08 ms이며 관측되지 않은 내부 균열이 먼저 생겼을 가능성은 남습니다.",
        ),
      },
      {
        id: "def-3",
        author: "접촉 전문가 · 예시",
        time: "10:06",
        body: "마찰 계수에 따른 반력 변화가 큽니다. 다만 파손 위치가 고정되어 있으면 경계 구속이 지배적일 수 있습니다. 마찰과 구속을 각각 바꾸는 비교가 두 가설을 구분하는 데 유용합니다.",
        evidence: ev(
          "비교 결과 / friction-study.csv",
          "mu=0.1: 반력 112 N, 최초 파손 A. mu=0.3: 반력 149 N, 최초 파손 A. 동일 메시와 구속을 사용하였다.",
          "반력 변화가 파손 위치 변화로 이어지지는 않았습니다.",
          "손상 모델의 요소 크기 의존성이 위치 변화를 가렸을 수 있습니다. 메시 수렴은 수행되지 않았습니다.",
        ),
      },
      {
        id: "def-4",
        author: "연구자",
        time: "10:08",
        body: "구속만 바꾸는 비교 계획을 먼저 기록하겠습니다. 아직 원인으로 승인하지는 않겠습니다.",
        reply: "def-3",
      },
      {
        id: "def-5",
        author: "검증 전문가 · 예시",
        time: "10:09",
        body: "현재 근거의 결론은 경쟁 가설 유지입니다. 균열 시간 오차, 메시 의존성과 구속 조건의 실제 측정이 아직 필요합니다.",
        evidence: ev(
          "가설 검토 / competing-hypotheses.md",
          "H1: 취성 지배. H2: 구속 유발 인장. H3: 접촉 비대칭. 현 관찰은 H2와 H3 모두에 부합한다.",
          "전문가 의견 일치는 원인의 증명이 아닙니다.",
          "구속을 바꾼 계산만으로 실제 조립 공차 효과를 검증할 수 없습니다.",
        ),
      },
    ],
  },
  {
    id: "pde",
    title: "CAD 없는 확산 연구",
    sub: "경계조건 · 오차 · 다음 실험",
    messages: [
      {
        id: "pde-1",
        author: "연구자",
        time: "11:21",
        body: "직사각형 영역의 확산 문제에서 시간 간격을 절반으로 줄이면 오차가 얼마나 달라지는지 비교하고 싶습니다.",
      },
      {
        id: "pde-2",
        author: "PDE 전문가 · 예시",
        time: "11:22",
        body: "해석해가 있는 조건을 먼저 고정하고 시간 오차와 공간 오차를 나누어 비교하세요. CAD 문서는 필요하지 않습니다.",
        evidence: ev(
          "모델 정의 / diffusion.json",
          "영역 [0,1]×[0,1], alpha=0.01 m²/s. 모든 경계에서 u=0. 초기장 sin(pi x)sin(pi y). 단위는 모델 정의에 보존한다.",
          "이 조건에서는 지수 감쇠하는 기준해로 L2 오차를 계산할 수 있습니다.",
          "외부 유입 경계나 비균질 계수를 추가하면 이 기준해를 그대로 사용할 수 없습니다.",
        ),
      },
      {
        id: "pde-3",
        author: "수치 전문가 · 예시",
        time: "11:24",
        body: "합성 비교 자료의 오차비는 1.8입니다. 공간 오차가 섞여 있으므로 시간 적분 차수를 확정할 근거는 부족합니다.",
        evidence: ev(
          "오차 비교 / convergence.csv",
          "h=1/40. dt=0.02: L2 0.0018. dt=0.01: L2 0.0010. 최종 시간 t=1.0. h 변화 비교는 미수행.",
          "같은 공간 격자의 시간 간격 비교만 가능합니다.",
          "두 점만으로 수렴 차수를 확정할 수 없고 기준해 평가 오차도 확인해야 합니다.",
        ),
      },
      {
        id: "pde-4",
        author: "연구자",
        time: "11:26",
        body: "공간 격자를 두 단계 추가하는 후속 연구를 메모합니다. 대화 전송만으로 계산을 시작하지 않도록 해주세요.",
        reply: "pde-3",
      },
    ],
  },
] as { id: string; title: string; sub: string; messages: Message[] }[];
type TopicState = {
  draft: string;
  reply?: string;
  selected: string;
  scroll: number;
  messages: Message[];
};
type Job = {
  id: string;
  title: string;
  state: "진행 중" | "취소됨";
  detail: string;
};

export function Expert() {
  const [active, setActive] = useStored("expert-topic", "material");
  const [state, setState] = useStored<Record<string, TopicState>>(
    "expert-discussions",
    Object.fromEntries(
      topics.map((t) => [
        t.id,
        {
          draft: "",
          selected: t.messages[1].id,
          scroll: 0,
          messages: t.messages,
        },
      ]),
    ),
  );
  const [jobs, setJobs] = useStored<Job[]>("expert-jobs", [
    {
      id: "E-014",
      title: "시험 메모 근거 대조",
      state: "진행 중",
      detail: "자료 3건 · 합성 대기 작업",
    },
    {
      id: "E-015",
      title: "경쟁 가설 정리",
      state: "진행 중",
      detail: "논점 2 · 합성 대기 작업",
    },
  ]);
  const [plan, setPlan] = useStored("expert-plan", {
    candidates: 24,
    budget: 30,
    validation: "없음",
    status: "proposed",
  });
  const scrollRef = useRef<HTMLDivElement>(null);
  const current = state[active] || state.material;
  const selected = current.messages.find((m) => m.id === current.selected);
  const replying = current.messages.find((m) => m.id === current.reply);
  const update = (patch: Partial<TopicState>) =>
    setState((prev) => ({ ...prev, [active]: { ...prev[active], ...patch } }));
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = current.scroll;
  }, [active]);
  function send() {
    if (!current.draft.trim()) return;
    const message: Message = {
      id: `${active}-user-${Date.now()}`,
      author: "연구자",
      time: new Date().toLocaleTimeString("ko-KR", {
        hour: "2-digit",
        minute: "2-digit",
      }),
      body: current.draft.trim(),
      reply: current.reply,
    };
    update({
      messages: [...current.messages, message],
      draft: "",
      reply: undefined,
      selected: message.id,
    });
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth",
      });
    });
  }
  const discussion = (
    <div className="ex-discussion">
      <div className="ex-discussion-head spread">
        <div>
          <strong>{topics.find((t) => t.id === active)?.title}</strong>
          <div className="muted">
            {current.messages.length}개 발언 · 발언 선택과 답글 대상은
            독립적입니다
          </div>
        </div>
        <Badge tone="neutral">합성 대화</Badge>
      </div>
      <div
        ref={scrollRef}
        className="ex-messages"
        onScroll={(e) => update({ scroll: e.currentTarget.scrollTop })}
      >
        {current.messages.map((m) => (
          <article
            key={m.id}
            className={`ex-message ${current.selected === m.id ? "is-selected" : ""}`}
            tabIndex={0}
            onClick={() => update({ selected: m.id })}
            onKeyDown={(e) => {
              if (
                e.target === e.currentTarget &&
                (e.key === "Enter" || e.key === " ")
              ) {
                e.preventDefault();
                update({ selected: m.id });
              }
            }}
            aria-label={`${m.author} 발언 선택`}
          >
            <div className="spread">
              <strong>{m.author}</strong>
              <span className="muted mono">
                {m.time} · {m.id}
              </span>
            </div>
            {m.reply && (
              <div className="ex-quoted">
                <Reply size={12} />
                {current.messages
                  .find((x) => x.id === m.reply)
                  ?.body.slice(0, 70) || m.reply}
              </div>
            )}
            <p>{m.body}</p>
            <div className="spread">
              <span className="ex-source-label">
                {m.evidence ? (
                  <>
                    <FileText size={13} />
                    {m.evidence.title}
                  </>
                ) : (
                  "원문 근거가 없는 발언"
                )}
              </span>
              <Button
                icon={Reply}
                onClick={(e) => {
                  e.stopPropagation();
                  update({ reply: m.id });
                }}
              >
                답글
              </Button>
            </div>
            {m.plan && (
              <div className="ex-plan" onClick={(e) => e.stopPropagation()}>
                <strong>연구 계획 변경안</strong>
                <table>
                  <thead>
                    <tr>
                      <th>항목</th>
                      <th>현재 r1</th>
                      <th>제안 r2</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>후보 수</td>
                      <td>24</td>
                      <td>36 (+12)</td>
                    </tr>
                    <tr>
                      <td>예산 상한</td>
                      <td>30분</td>
                      <td>45분 (+15)</td>
                    </tr>
                    <tr>
                      <td>식별 / 검증</td>
                      <td>시험 01·02·03 / 없음</td>
                      <td>시험 01·03 / 시험 02</td>
                    </tr>
                  </tbody>
                </table>
                {plan.status === "proposed" ? (
                  <div className="row">
                    <Button
                      primary
                      icon={Check}
                      onClick={() =>
                        setPlan({
                          candidates: 36,
                          budget: 45,
                          validation: "시험 02",
                          status: "applied",
                        })
                      }
                    >
                      변경 적용
                    </Button>
                    <Button
                      onClick={() => setPlan({ ...plan, status: "discarded" })}
                    >
                      제안 버리기
                    </Button>
                  </div>
                ) : (
                  <Notice tone={plan.status === "applied" ? "good" : "neutral"}>
                    {plan.status === "applied"
                      ? "r2 계획 적용됨 · 계산은 제출되지 않았습니다"
                      : "제안 폐기됨 · r1 유지"}
                  </Notice>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
      <div className="ex-composer">
        <div className="spread ex-reply-status">
          <span>
            {replying ? (
              <>
                <Reply size={13} /> 답글 대상: {replying.author} · {replying.id}
              </>
            ) : (
              "새 발언 작성"
            )}
          </span>
          {replying && (
            <Button icon={X} onClick={() => update({ reply: undefined })}>
              대상 해제
            </Button>
          )}
        </div>
        {replying && (
          <div className="ex-reply-preview">{replying.body.slice(0, 120)}</div>
        )}
        <textarea
          aria-label="대화 초안"
          value={current.draft}
          onChange={(e) => update({ draft: e.target.value })}
          placeholder="논점, 해석 또는 다음 연구 질문을 기록하세요…"
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === "Enter") send();
          }}
        />
        <div className="spread">
          <span className="muted">
            초안 자동 저장 · Ctrl+Enter 전송 · 계산 실행 없음
          </span>
          <Button
            primary
            icon={Send}
            disabled={!current.draft.trim()}
            onClick={send}
          >
            대화 전송
          </Button>
        </div>
      </div>
    </div>
  );
  const rail = (
    <div className="panel-stack panel-scroll">
      <div className="section-title">연구 논점</div>
      {topics.map((t) => (
        <button
          key={t.id}
          className={`ex-topic ${active === t.id ? "is-selected" : ""}`}
          onClick={() => setActive(t.id)}
        >
          <MessageSquare size={16} />
          <span>
            <strong>{t.title}</strong>
            <small>{t.sub}</small>
            {state[t.id].draft && (
              <small className="ex-draft-marker">저장된 초안 있음</small>
            )}
          </span>
          <ChevronRight size={14} />
        </button>
      ))}
      <div className="section-title">관련 작업</div>
      {jobs.map((j) => (
        <div className="ex-job" key={j.id}>
          <div className="spread">
            <strong>{j.id}</strong>
            <Badge tone={j.state === "진행 중" ? "info" : "neutral"}>
              {j.state}
            </Badge>
          </div>
          <p>{j.title}</p>
          <div className="muted">{j.detail}</div>
          <Button
            danger
            icon={X}
            disabled={j.state !== "진행 중"}
            onClick={() =>
              setJobs((prev) =>
                prev.map((x) =>
                  x.id === j.id ? { ...x, state: "취소됨" } : x,
                ),
              )
            }
          >
            {j.id} 취소
          </Button>
        </div>
      ))}
      <div className="section-title">현재 연구 계획</div>
      <Properties
        rows={[
          ["후보 수", plan.candidates],
          ["예산 상한", `${plan.budget}분`],
          ["검증 자료", plan.validation],
        ]}
      />
    </div>
  );
  const evidence = (
    <div className="panel-stack panel-scroll">
      <div className="section-title">선택 발언의 근거</div>
      <Properties
        rows={[
          ["발언 ID", selected?.id || "—"],
          ["작성자", selected?.author || "—"],
          ["답글 대상", replying?.id || "없음"],
        ]}
      />
      {selected?.evidence ? (
        <>
          <h3 className="ex-evidence-title">{selected.evidence.title}</h3>
          <Badge tone="warn">합성 원문</Badge>
          <div className="muted">{selected.evidence.origin}</div>
          <div className="section-title">원문 발췌</div>
          <blockquote className="ex-excerpt">
            {selected.evidence.excerpt}
          </blockquote>
          <div className="section-title">이 발언이 해석한 내용</div>
          <p>{selected.evidence.finding}</p>
          {selected.evidence.opposing && (
            <>
              <div className="section-title">반대 근거 / 미해결 사항</div>
              <Notice tone="warn">{selected.evidence.opposing}</Notice>
            </>
          )}
          <Button
            icon={Reply}
            onClick={() => selected && update({ reply: selected.id })}
          >
            이 발언에 답글
          </Button>
        </>
      ) : (
        <Notice tone="neutral">
          선택한 발언에는 첨부된 원문이 없습니다. 다른 발언을 선택하면 해당
          원문과 반대 근거가 표시됩니다.
        </Notice>
      )}
      <div className="ex-evidence-foot">
        예시 전문가 발언은 미리 작성된 내용입니다. 실제 LLM, 검색 또는 계산은
        수행되지 않습니다.
      </div>
    </div>
  );
  return (
    <>
      <Toolbar>
        <MessageSquare size={16} />
        <strong>Expert</strong>
        <span className="muted">근거를 비교하고 다음 연구를 기록</span>
        <Badge tone="warn">오프라인 예시</Badge>
      </Toolbar>
      <Workspace
        id="expert"
        panels={{
          topics: { title: "논점 · 관련 작업", content: rail },
          discussion: { title: "연구 대화", content: discussion },
          evidence: { title: "원문 · 반대 근거", content: evidence },
        }}
        setup={(api) => {
          api.addPanel({
            id: "discussion",
            component: "content",
            title: "연구 대화",
          });
          api.addPanel({
            id: "topics",
            component: "content",
            title: "논점 · 관련 작업",
            position: { referencePanel: "discussion", direction: "left" },
            initialWidth: 265,
          });
          api.addPanel({
            id: "evidence",
            component: "content",
            title: "원문 · 반대 근거",
            position: { referencePanel: "discussion", direction: "right" },
            initialWidth: 335,
          });
        }}
      />
    </>
  );
}

type Port = {
  id: string;
  label: string;
  kind: string;
  schema: number;
  side: "in" | "out";
};
type DocData = {
  title: string;
  app: string;
  subtitle: string;
  revision: number;
  ports: Port[];
  [key: string]: unknown;
};
type GraphNode = Node<DocData>;
type GraphEdge = Edge<{
  revision: number;
  pending?: number;
  failedOnce?: boolean;
}>;
type Selection =
  | { type: "node"; id: string }
  | { type: "edge"; id: string }
  | { type: "port"; id: string; port: string }
  | null;
const port = (
  id: string,
  label: string,
  kind: string,
  side: "in" | "out",
  schema = 1,
): Port => ({ id, label, kind, side, schema });
const initialNodes: GraphNode[] = [
  {
    id: "material",
    type: "document",
    position: { x: 60, y: 70 },
    data: {
      title: "인장 재료 모델",
      app: "pre",
      subtitle: "plasticity.json · 편집 문서",
      revision: 1,
      ports: [port("material", "재료 정의", "material", "out")],
    },
  },
  {
    id: "analysis",
    type: "document",
    position: { x: 390, y: 70 },
    data: {
      title: "단축 인장 해석",
      app: "runner",
      subtitle: "tension-study · 실행 구성",
      revision: 1,
      ports: [
        port("material-in", "재료 입력", "material", "in"),
        port("field-out", "응답 결과", "field", "out"),
      ],
    },
  },
  {
    id: "response",
    type: "document",
    position: { x: 730, y: 60 },
    data: {
      title: "응력–변형률 비교",
      app: "post",
      subtitle: "response.csv · 비교 문서",
      revision: 1,
      ports: [
        port("field-in", "필드 / 곡선", "field", "in"),
        port("response-out", "응답 지표", "response", "out"),
      ],
    },
  },
  {
    id: "optimization",
    type: "document",
    position: { x: 730, y: 330 },
    data: {
      title: "파라미터 식별",
      app: "optimization",
      subtitle: "identification · 연구 계획",
      revision: 1,
      ports: [
        port("response-in", "응답 지표", "response", "in"),
        port("material-v2", "재료 입력 r2", "material", "in", 2),
      ],
    },
  },
  {
    id: "expert",
    type: "document",
    position: { x: 390, y: 330 },
    data: {
      title: "재료 식별 논점",
      app: "expert",
      subtitle: "근거·후속 연구 · 자문 문서",
      revision: 1,
      ports: [port("response-in", "응답 참조", "response", "in")],
    },
  },
];
const initialEdges: GraphEdge[] = [
  {
    id: "link-material",
    source: "material",
    target: "analysis",
    sourceHandle: "material",
    targetHandle: "material-in",
    data: { revision: 1 },
    label: "재료 · 문서 r1",
    type: "smoothstep",
  },
  {
    id: "link-results",
    source: "analysis",
    target: "response",
    sourceHandle: "field-out",
    targetHandle: "field-in",
    data: { revision: 1 },
    label: "응답 · 문서 r1",
    type: "smoothstep",
  },
  {
    id: "link-objective",
    source: "response",
    target: "optimization",
    sourceHandle: "response-out",
    targetHandle: "response-in",
    data: { revision: 1 },
    label: "지표 · 문서 r1",
    type: "smoothstep",
  },
];
const PortContext = createContext<{
  select: (id: string, port: string) => void;
  selection: Selection;
}>({ select: () => {}, selection: null });
function DocumentNode({ id, data, selected }: NodeProps<GraphNode>) {
  const ports = useContext(PortContext);
  const updateInternals = useUpdateNodeInternals();
  useEffect(() => {
    updateInternals(id);
  }, [id, selected, updateInternals]);
  return (
    <div className={`wb-node ${selected ? "is-selected" : ""}`}>
      <div className="wb-node-head">
        <FileText size={16} />
        <strong>{data.title}</strong>
        <span className="mono">r{data.revision}</span>
      </div>
      <div className="wb-node-sub">{data.subtitle}</div>
      <div className="wb-ports">
        {data.ports.map((p) => (
          <div className={`wb-port ${p.side}`} key={p.id}>
            <Handle
              id={p.id}
              type={p.side === "out" ? "source" : "target"}
              position={p.side === "out" ? Position.Right : Position.Left}
            />
            <button
              className={`nodrag ${ports.selection?.type === "port" && ports.selection.id === id && ports.selection.port === p.id ? "is-selected" : ""}`}
              onClick={(e) => {
                e.stopPropagation();
                ports.select(id, p.id);
              }}
              aria-label={`${data.title} ${p.label} 포트 선택`}
            >
              <span>{p.label}</span>
              <small>
                {p.kind} / schema r{p.schema}
              </small>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
const nodeTypes = { document: DocumentNode };
function GraphViewport({
  container,
}: {
  container: RefObject<HTMLDivElement | null>;
}) {
  const ready = useNodesInitialized();
  const { fitView } = useReactFlow<GraphNode, GraphEdge>();
  const fit = () => fitView({ padding: 0.16, minZoom: 0.15, maxZoom: 1 });
  useEffect(() => {
    if (!ready || !container.current) return;
    let frame = 0;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => {
          void fitView({ padding: 0.16, minZoom: 0.15, maxZoom: 1 });
        });
      });
    };
    const observer = new ResizeObserver(schedule);
    observer.observe(container.current);
    schedule();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [ready, fitView, container]);
  return (
    <Panel position="top-right">
      <Button
        className="wb-fit-button"
        icon={Maximize2}
        onClick={() => void fit()}
      >
        전체 문서 맞춤
      </Button>
    </Panel>
  );
}
function connectionIssue(
  c: Connection,
  nodes: GraphNode[],
  edges: GraphEdge[],
) {
  const a = nodes
    .find((n) => n.id === c.source)
    ?.data.ports.find((p) => p.id === c.sourceHandle);
  const b = nodes
    .find((n) => n.id === c.target)
    ?.data.ports.find((p) => p.id === c.targetHandle);
  if (!a || !b) return "출력 포트와 입력 포트를 선택하세요.";
  if (c.source === c.target)
    return "같은 문서의 포트끼리는 연결할 수 없습니다.";
  if (a.side !== "out" || b.side !== "in")
    return "출력 → 입력 순서로 연결하세요.";
  if (a.kind !== b.kind)
    return `자료 형식 불일치: ${a.kind} → ${b.kind}. 변환 문서가 필요합니다.`;
  if (a.schema !== b.schema)
    return `스키마 리비전 불일치: r${a.schema} → r${b.schema}. 호환되는 포트를 선택하세요.`;
  if (
    edges.some(
      (e) => e.target === c.target && e.targetHandle === c.targetHandle,
    )
  )
    return "이 입력 포트에는 이미 연결이 있습니다. 기존 연결을 선택해 변경하세요.";
  return "";
}
export function Workbench() {
  const [nodes, setNodes] = useStored<GraphNode[]>(
    "workbench-nodes",
    initialNodes,
  );
  const [edges, setEdges] = useStored<GraphEdge[]>(
    "workbench-edges",
    initialEdges,
  );
  const [selection, setSelection] = useStored<Selection>(
    "workbench-selection",
    { type: "node", id: "analysis" },
  );
  const [source, setSource] = useState("analysis|field-out");
  const [target, setTarget] = useState("expert|response-in");
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const graphRef = useRef<HTMLDivElement>(null);
  const [notice, setNotice] = useState(
    "문서, 포트와 연결을 각각 선택할 수 있습니다. 앱 열기는 별도 명령입니다.",
  );
  const selectedNode =
    selection && selection.type !== "edge"
      ? nodes.find((n) => n.id === selection.id)
      : undefined;
  const selectedPort =
    selection?.type === "port"
      ? selectedNode?.data.ports.find((p) => p.id === selection.port)
      : undefined;
  const selectedEdge =
    selection?.type === "edge"
      ? edges.find((e) => e.id === selection.id)
      : undefined;
  const edgeSource = nodes.find((n) => n.id === selectedEdge?.source);
  const outputs = nodes.flatMap((n) =>
    n.data.ports
      .filter((p) => p.side === "out")
      .map((p) => ({
        value: `${n.id}|${p.id}`,
        label: `${n.data.title} / ${p.label} (${p.kind} r${p.schema})`,
      })),
  );
  const inputs = nodes.flatMap((n) =>
    n.data.ports
      .filter((p) => p.side === "in")
      .map((p) => ({
        value: `${n.id}|${p.id}`,
        label: `${n.data.title} / ${p.label} (${p.kind} r${p.schema})`,
      })),
  );
  function connect(c: Connection) {
    const issue = connectionIssue(c, nodes, edges);
    if (issue) {
      setNotice(issue);
      setConnectionError(issue);
      return;
    }
    const id = `link-${Date.now()}`;
    const rev = nodes.find((n) => n.id === c.source)!.data.revision;
    setEdges((prev) => [
      ...prev,
      {
        ...c,
        id,
        data: { revision: rev },
        type: "smoothstep",
        label: `문서 r${rev}`,
      },
    ]);
    setSelection({ type: "edge", id });
    setConnecting(false);
    setConnectionError("");
    setNotice(`연결 저장됨 · 원본 문서 r${rev} 고정 참조`);
  }
  function updateConnection(retry = false) {
    if (!selectedEdge || !edgeSource) return;
    const rev = selectedEdge.data?.pending ?? edgeSource.data.revision;
    if (!retry && !selectedEdge.data?.failedOnce) {
      setEdges((prev) =>
        prev.map((e) =>
          e.id === selectedEdge.id
            ? { ...e, data: { ...e.data!, pending: rev, failedOnce: true } }
            : e,
        ),
      );
      setNotice(
        `저장 실패 시뮬레이션 · 원본 문서 r${rev}는 유지됩니다. 연결 갱신만 재시도하세요.`,
      );
    } else {
      setEdges((prev) =>
        prev.map((e) =>
          e.id === selectedEdge.id
            ? {
                ...e,
                data: { revision: rev, failedOnce: true },
                label: `문서 r${rev}`,
              }
            : e,
        ),
      );
      setNotice(
        `연결 참조 갱신 완료 · 문서 r${rev}. 원본 문서는 다시 생성하지 않았습니다.`,
      );
    }
  }
  const graph = (
    <PortContext.Provider
      value={{
        select: (id, port) => setSelection({ type: "port", id, port }),
        selection,
      }}
    >
      <div className="wb-graph" ref={graphRef}>
        <ReactFlow<GraphNode, GraphEdge>
          nodes={nodes.map((n) => ({
            ...n,
            selected: selection?.type === "node" && selection.id === n.id,
          }))}
          edges={edges.map((e) => ({
            ...e,
            selected: selection?.type === "edge" && selection.id === e.id,
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: e.data?.pending ? "#b87515" : "#6b7d8f",
            },
            style: {
              stroke: e.data?.pending ? "#b87515" : "#6b7d8f",
              strokeWidth:
                selection?.type === "edge" && selection.id === e.id ? 3 : 1.8,
            },
            animated: !!e.data?.pending,
          }))}
          nodeTypes={nodeTypes}
          onNodesChange={(changes) =>
            setNodes((prev) =>
              applyNodeChanges(
                changes.filter((c) => c.type !== "select"),
                prev,
              ),
            )
          }
          onEdgesChange={(changes) =>
            setEdges((prev) =>
              applyEdgeChanges(
                changes.filter((c) => c.type !== "select"),
                prev,
              ),
            )
          }
          onNodeClick={(_e, n) => setSelection({ type: "node", id: n.id })}
          onEdgeClick={(_e, e) => setSelection({ type: "edge", id: e.id })}
          onPaneClick={() => setSelection(null)}
          onConnect={connect}
          onConnectEnd={(_e, state) => {
            if (
              !state.isValid &&
              state.fromNode &&
              state.toNode &&
              state.fromHandle &&
              state.toHandle
            )
              setNotice(
                connectionIssue(
                  {
                    source: state.fromNode.id,
                    target: state.toNode.id,
                    sourceHandle: state.fromHandle.id ?? null,
                    targetHandle: state.toHandle.id ?? null,
                  },
                  nodes,
                  edges,
                ),
              );
          }}
          isValidConnection={(c) =>
            !connectionIssue(c as Connection, nodes, edges)
          }
          minZoom={0.15}
          maxZoom={1.6}
          deleteKeyCode={null}
          nodesConnectable
          edgesFocusable
          nodesFocusable
        >
          <Background gap={20} color="#d8dee5" />
          <Controls showInteractive={false} />
          <GraphViewport container={graphRef} />
        </ReactFlow>
        <div className="wb-graph-legend">
          <span className="wb-legend-line" />
          저장 참조 · 문서 리비전 고정
          <span className="wb-legend-line pending" />
          연결 갱신 대기
        </div>
      </div>
    </PortContext.Provider>
  );
  function startConnection() {
    if (selectedNode && selectedPort) {
      if (selectedPort.side === "out")
        setSource(`${selectedNode.id}|${selectedPort.id}`);
      else setTarget(`${selectedNode.id}|${selectedPort.id}`);
    }
    setConnectionError("");
    setConnecting(true);
  }
  const inspector = (
    <div className="wb-inspector">
      <div className="wb-inspector-head section-title">
        {connecting
          ? "키보드 연결 작성"
          : selection?.type === "node"
            ? "문서 속성"
            : selection?.type === "port"
              ? "포트 속성"
              : selection?.type === "edge"
                ? "연결 속성"
                : "선택 없음"}
      </div>
      <div className="wb-inspector-body panel-scroll">
        {connecting ? (
          <>
            <Notice tone="neutral">
              출력과 입력을 선택하세요. 형식과 스키마를 검사한 뒤 연결을
              저장합니다.
            </Notice>
            <Field label="출력 포트">
              <select
                value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  setConnectionError("");
                }}
              >
                {outputs.map((x) => (
                  <option value={x.value} key={x.value}>
                    {x.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="입력 포트">
              <select
                value={target}
                onChange={(e) => {
                  setTarget(e.target.value);
                  setConnectionError("");
                }}
              >
                {inputs.map((x) => (
                  <option value={x.value} key={x.value}>
                    {x.label}
                  </option>
                ))}
              </select>
            </Field>
            {connectionError && <Notice tone="bad">{connectionError}</Notice>}
            <div className="muted">
              재료 → 응답은 형식 불일치, 재료 → 재료 입력 r2는 스키마 불일치로
              거부됩니다. 실패해도 선택한 포트는 유지됩니다.
            </div>
          </>
        ) : (
          <>
            {selectedNode && (
              <>
                <h3>{selectedNode.data.title}</h3>
                <Properties
                  rows={[
                    ["선택 종류", selectedPort ? "포트" : "문서"],
                    ["문서 ID", selectedNode.id],
                    ["현재 문서", `r${selectedNode.data.revision}`],
                    ["대상 앱", selectedNode.data.app],
                  ]}
                />
                {selectedPort ? (
                  <>
                    <Properties
                      rows={[
                        ["포트", selectedPort.label],
                        ["방향", selectedPort.side === "in" ? "입력" : "출력"],
                        ["자료 형식", selectedPort.kind],
                        ["스키마", `r${selectedPort.schema}`],
                      ]}
                    />
                    <Notice tone="neutral">
                      포트 선택은 연결 대상을 검사합니다. 문서를 열려면 아래 앱
                      열기 명령을 사용하세요.
                    </Notice>
                  </>
                ) : (
                  <Notice tone="neutral">
                    새 리비전 생성은 합성 편집 저장을 재현합니다. 저장된 연결은
                    이전 문서 리비전을 계속 참조합니다.
                  </Notice>
                )}
              </>
            )}
            {selectedEdge && (
              <>
                <h3>
                  {nodes.find((n) => n.id === selectedEdge.source)?.data.title}{" "}
                  →{" "}
                  {nodes.find((n) => n.id === selectedEdge.target)?.data.title}
                </h3>
                <Properties
                  rows={[
                    ["연결 ID", selectedEdge.id],
                    ["출력 포트", selectedEdge.sourceHandle],
                    ["입력 포트", selectedEdge.targetHandle],
                    [
                      "저장된 원본 참조",
                      `문서 r${selectedEdge.data?.revision}`,
                    ],
                    ["현재 원본 문서", `문서 r${edgeSource?.data.revision}`],
                    [
                      "대기 갱신",
                      selectedEdge.data?.pending
                        ? `r${selectedEdge.data.pending}`
                        : "없음",
                    ],
                  ]}
                />
                {selectedEdge.data?.pending && (
                  <Notice tone="warn">
                    연결 저장 실패. 원본 문서는 보존됐으며 연결 갱신만 대기
                    중입니다. 아래 재시도 명령을 사용하세요.
                  </Notice>
                )}
              </>
            )}
            {!selection && (
              <Notice tone="neutral">
                그래프에서 문서·포트·연결을 선택하거나 문서 목록을 사용하세요.
              </Notice>
            )}
          </>
        )}
      </div>
      <div className="wb-inspector-commands">
        {connecting ? (
          <>
            <Button
              primary
              icon={Link2}
              onClick={() => {
                const [s, sh] = source.split("|");
                const [t, th] = target.split("|");
                connect({
                  source: s,
                  sourceHandle: sh,
                  target: t,
                  targetHandle: th,
                });
              }}
            >
              연결 검사 및 저장
            </Button>
            <Button
              icon={X}
              onClick={() => {
                setConnecting(false);
                setConnectionError("");
              }}
            >
              연결 작성 취소
            </Button>
          </>
        ) : (
          <>
            {selectedNode && (
              <>
                <Button
                  icon={ExternalLink}
                  primary
                  onClick={() => {
                    window.location.hash = selectedNode.data.app;
                  }}
                >
                  앱 열기 · {selectedNode.data.app}
                </Button>
                {!selectedPort && (
                  <Button
                    icon={Plus}
                    onClick={() => {
                      setNodes((prev) =>
                        prev.map((n) =>
                          n.id === selectedNode.id
                            ? {
                                ...n,
                                data: {
                                  ...n.data,
                                  revision: n.data.revision + 1,
                                },
                              }
                            : n,
                        ),
                      );
                      setNotice(
                        "새 문서 리비전 생성됨 · 저장된 연결은 이전 리비전을 계속 참조합니다.",
                      );
                    }}
                  >
                    새 문서 리비전 생성
                  </Button>
                )}
              </>
            )}
            {selectedEdge && (
              <>
                {selectedEdge.data?.pending ? (
                  <Button
                    primary
                    icon={RefreshCw}
                    onClick={() => updateConnection(true)}
                  >
                    연결 저장 재시도
                  </Button>
                ) : (
                  <Button
                    icon={GitBranch}
                    disabled={
                      selectedEdge.data?.revision === edgeSource?.data.revision
                    }
                    onClick={() => updateConnection()}
                  >
                    현재 원본 리비전으로 참조 갱신
                  </Button>
                )}
                <Button
                  danger
                  icon={X}
                  onClick={() => {
                    setEdges((prev) =>
                      prev.filter((e) => e.id !== selectedEdge.id),
                    );
                    setSelection(null);
                    setNotice("연결 제거됨 · 원본 문서는 유지됩니다.");
                  }}
                >
                  연결 제거
                </Button>
              </>
            )}
            <Button icon={Link2} onClick={startConnection}>
              키보드로 연결 작성
            </Button>
          </>
        )}
      </div>
    </div>
  );
  const documents = (
    <div className="panel-stack panel-scroll">
      <div className="section-title">문서</div>
      {nodes.map((n) => (
        <div key={n.id} className="wb-document-list">
          <button
            className={`wb-list-row ${selection?.type === "node" && selection.id === n.id ? "is-selected" : ""}`}
            onClick={() => setSelection({ type: "node", id: n.id })}
          >
            <FileText size={14} />
            <span>{n.data.title}</span>
            <Badge>r{n.data.revision}</Badge>
          </button>
          {n.data.ports.map((p) => (
            <button
              className={`wb-list-port ${selection?.type === "port" && selection.id === n.id && selection.port === p.id ? "is-selected" : ""}`}
              key={p.id}
              onClick={() =>
                setSelection({ type: "port", id: n.id, port: p.id })
              }
            >
              {p.side === "in" ? "←" : "→"} {p.label}
            </button>
          ))}
        </div>
      ))}
      <div className="section-title">저장된 연결</div>
      {edges.map((e) => (
        <button
          key={e.id}
          className={`wb-list-row ${selection?.type === "edge" && selection.id === e.id ? "is-selected" : ""}`}
          onClick={() => setSelection({ type: "edge", id: e.id })}
        >
          <Link2 size={14} />
          <span>
            {nodes.find((n) => n.id === e.source)?.data.title}
            <small>→ {nodes.find((n) => n.id === e.target)?.data.title}</small>
          </span>
          <Badge tone={e.data?.pending ? "warn" : "neutral"}>
            r{e.data?.revision}
          </Badge>
        </button>
      ))}
      <Notice tone="neutral">
        노드 이동과 문서 참조는 로컬에 저장됩니다. 실제 파일이나 계산을 변경하지
        않습니다.
      </Notice>
    </div>
  );
  return (
    <>
      <Toolbar>
        <GitBranch size={16} />
        <strong>Workbench</strong>
        <span className="muted">문서 간 연결 · 고정 리비전 참조</span>
        <Badge tone="warn">합성 문서</Badge>
      </Toolbar>
      <div className="wb-status" role="status">
        {notice}
      </div>
      <Workspace
        id="workbench"
        panels={{
          graph: { title: "연구 문서 그래프", content: graph },
          documents: { title: "문서 · 연결 목록", content: documents },
          inspector: { title: "선택 속성 · 연결", content: inspector },
        }}
        setup={(api) => {
          api.addPanel({
            id: "graph",
            component: "content",
            title: "연구 문서 그래프",
          });
          api.addPanel({
            id: "documents",
            component: "content",
            title: "문서 · 연결 목록",
            position: { referencePanel: "graph", direction: "left" },
            initialWidth: 240,
          });
          api.addPanel({
            id: "inspector",
            component: "content",
            title: "선택 속성 · 연결",
            position: { referencePanel: "graph", direction: "right" },
            initialWidth: 340,
          });
        }}
      />
    </>
  );
}
