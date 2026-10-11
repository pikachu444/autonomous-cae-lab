import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Box,
  Layers,
  Play,
  ChartNoAxesCombined,
  MessagesSquare,
  Workflow,
  Component,
} from "lucide-react";
import { Pre, Post } from "./PrePost";
import { Runner, Optimization } from "./RunnerOptimization";
import { Expert, Workbench } from "./ExpertWorkbench";
import { StorageStatus } from "./common";
import "./style.css";

const apps = {
  pre: {
    name: "Pre",
    label: "전처리",
    doc: "Fixture assembly",
    ref: "PRE-041",
    icon: Box,
    component: Pre,
  },
  post: {
    name: "Post",
    label: "후처리",
    doc: "하중 조건 A / B 비교",
    ref: "POST-018",
    icon: Layers,
    component: Post,
  },
  runner: {
    name: "Runner",
    label: "실행기",
    doc: "연구 작업",
    ref: "로컬 실행 환경 · 시안",
    icon: Play,
    component: Runner,
  },
  optimization: {
    name: "Optimization",
    label: "최적화",
    doc: "클램프 설계 탐색",
    ref: "STUDY-032",
    icon: ChartNoAxesCombined,
    component: Optimization,
  },
  expert: {
    name: "Expert",
    label: "전문가",
    doc: "클램프 접촉부 파손 검토",
    ref: "DISCUSSION-014",
    icon: MessagesSquare,
    component: Expert,
  },
  workbench: {
    name: "Workbench",
    label: "문서 연결",
    doc: "클램프 강성 연구",
    ref: "WORKSPACE-009",
    icon: Workflow,
    component: Workbench,
  },
};
type AppId = keyof typeof apps;
function route(): AppId {
  const k = location.hash.replace("#", "") as AppId;
  return k in apps ? k : "optimization";
}
function App() {
  const [app, setApp] = useState<AppId>(route);
  useEffect(() => {
    const f = () => setApp(route());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const cfg = apps[app];
  const Screen = cfg.component;
  return (
    <div className="app-shell">
      <header className="app-bar">
        <div className="wordmark">
          <Component size={20} strokeWidth={1.7} /> CAE LAB
        </div>
        <nav className="app-tabs" aria-label="설계 시안 앱">
          {Object.entries(apps).map(([id, a]) => (
            <button
              key={id}
              className={app === id ? "active" : ""}
              aria-current={app === id ? "page" : undefined}
              onClick={() => (location.hash = id)}
            >
              <a.icon size={14} />
              {a.name}
            </button>
          ))}
        </nav>
        <span className="prototype-label">INTERACTION STUDY · 2026.10</span>
      </header>
      <div className="app-document">
        <h1>{cfg.doc}</h1>
        <span className="doc-ref">{cfg.ref}</span>
        <span className="spacer" />
        <span className="muted">{cfg.label} · 독립 앱 작업 배치</span>
      </div>
      <main className="app-body">
        <Screen key={app} />
      </main>
      <footer className="app-footer">
        <span>조작 가능한 설계 시안</span>
        <span>합성 데이터 · 계산 / CAD / LLM 미연결</span>
        <StorageStatus />
      </footer>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
