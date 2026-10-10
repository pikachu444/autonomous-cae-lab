import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type PointerEvent,
} from "react";
import {
  Box,
  Boxes,
  File,
  FolderOpen,
  Save,
  Undo2,
  Redo2,
  Printer,
  Scissors,
  Copy,
  MousePointer2,
  Rotate3D,
  Move,
  ZoomIn,
  ZoomOut,
  Maximize,
  Eye,
  EyeOff,
  Focus,
  Grid3X3,
  Cuboid,
  Layers,
  CircleDot,
  Plus,
  Minus,
  Settings2,
  Hammer,
  Play,
  ChartNoAxesCombined,
  Crosshair,
  Thermometer,
  Magnet,
  ArrowDownToLine,
  Network,
  X,
  Check,
  ChevronDown,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import { Scene } from "./Scene";
import { components, resultNodes, resultInfo } from "./model";
import "./Abaqus.css";

const modules = [
  "Part",
  "Property",
  "Assembly",
  "Step",
  "Interaction",
  "Load",
  "Mesh",
  "Job",
  "Visualization",
] as const;
type Module = (typeof modules)[number];
type Dataset = "assembly" | "result";
type Representation = "shaded" | "edges" | "wireframe" | "transparent";
type Field = "none" | "magnitude" | "ux" | "uy" | "uz";
type Camera = "fit" | "iso" | "front" | "top" | "right" | "zoomIn" | "zoomOut";
type Material = {
  name: string;
  elastic: number;
  poisson: number;
  density: number;
};
type BC = {
  name: string;
  region: string[];
  ux: string;
  uy: string;
  uz: string;
};
type Draft = {
  materials: Material[];
  bcs: BC[];
  mesh: { size: number; technique: string; element: string };
  steps: string[];
  interactions: string[];
  jobs: string[];
};
type Probe = {
  id: number;
  x: number;
  y: number;
  z: number;
  ux: number;
  uy: number;
  uz: number;
  magnitude: number;
};
type Dialog =
  | "material"
  | "bc"
  | "mesh"
  | "step"
  | "interaction"
  | "job"
  | "info"
  | "new"
  | "xy"
  | null;
const emptyDraft: Draft = {
  materials: [],
  bcs: [],
  mesh: { size: 2, technique: "Free", element: "C3D4" },
  steps: [],
  interactions: [],
  jobs: [],
};
const storageKey = "cae-abaqus-reference-study-v1";
function validDraft(value: unknown): value is Draft {
  if (!value || typeof value !== "object") return false;
  const d = value as Draft;
  return (
    Array.isArray(d.materials) &&
    d.materials.every(
      (m) =>
        typeof m.name === "string" &&
        Number.isFinite(m.elastic) &&
        m.elastic > 0 &&
        Number.isFinite(m.poisson) &&
        m.poisson > -1 &&
        m.poisson < 0.5 &&
        Number.isFinite(m.density) &&
        m.density > 0,
    ) &&
    Array.isArray(d.bcs) &&
    d.bcs.every(
      (b) =>
        typeof b.name === "string" &&
        Array.isArray(b.region) &&
        b.region.every((id) => typeof id === "string") &&
        [b.ux, b.uy, b.uz].every(
          (v) =>
            typeof v === "string" && (v === "" || Number.isFinite(Number(v))),
        ),
    ) &&
    !!d.mesh &&
    Number.isFinite(d.mesh.size) &&
    d.mesh.size > 0 &&
    typeof d.mesh.technique === "string" &&
    typeof d.mesh.element === "string" &&
    [d.steps, d.interactions, d.jobs].every(
      (a) => Array.isArray(a) && a.every((v) => typeof v === "string"),
    )
  );
}
function initialDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(storageKey) || "null");
    if (validDraft(d)) return d;
  } catch {}
  return emptyDraft;
}
function Tool({
  icon: Icon,
  title,
  onClick,
  color = "#376ca5",
  active,
  disabled,
}: {
  icon: LucideIcon;
  title: string;
  onClick: () => void;
  color?: string;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      className={`abq-tool ${active ? "active" : ""}`}
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
    >
      <Icon size={18} strokeWidth={1.65} color={color} />
    </button>
  );
}
function Group({ children }: { children: ReactNode }) {
  return <span className="abq-tool-group">{children}</span>;
}
function Branch({
  title,
  count,
  open,
  toggle,
  children,
}: {
  title: string;
  count?: number;
  open: boolean;
  toggle: () => void;
  children?: ReactNode;
}) {
  return (
    <div className="abq-branch">
      <button className="abq-tree-line" onClick={toggle}>
        {open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        <FolderOpen size={13} color="#978944" />
        <span>
          {title}
          {count !== undefined ? ` (${count})` : ""}
        </span>
      </button>
      {open && <div className="abq-tree-children">{children}</div>}
    </div>
  );
}

export default function Abaqus() {
  const [draft, setDraft] = useState<Draft>(initialDraft);
  const [undo, setUndo] = useState<Draft[]>([]);
  const [redo, setRedo] = useState<Draft[]>([]);
  const [module, setModule] = useState<Module>("Assembly");
  const [dataset, setDataset] = useState<Dataset>("assembly");
  const [selected, setSelected] = useState<string[]>([]);
  const [hidden, setHidden] = useState<string[]>([]);
  const [representation, setRepresentation] = useState<Representation>("edges");
  const [camera, setCamera] = useState<{ name: Camera; tick: number }>({
    name: "iso",
    tick: 1,
  });
  const [explode, setExplode] = useState(0);
  const [clip, setClip] = useState({
    enabled: false,
    axis: "z" as "x" | "y" | "z",
    position: 0.5,
  });
  const [field, setField] = useState<Field>("none");
  const [deformation, setDeformation] = useState(0);
  const [showLoads, setShowLoads] = useState(false);
  const [probeMode, setProbeMode] = useState(false);
  const [probe, setProbe] = useState<Probe | null>(null);
  const [nodeId, setNodeId] = useState("");
  const [xyPage, setXyPage] = useState(0);
  const [activeStep, setActiveStep] = useState("Initial");
  const [treeTab, setTreeTab] = useState("Model");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    model: true,
    parts: false,
    assembly: true,
    instances: true,
    analysis: true,
    jobs: true,
  });
  const [menu, setMenu] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [dialogText, setDialogText] = useState("");
  const [form, setForm] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState("");
  const [consoleTab, setConsoleTab] = useState("Messages");
  const [messages, setMessages] = useState([
    "Local assembly geometry loaded. Browser interface study — CAD kernel and Abaqus solver are not connected.",
  ]);
  const [prompt, setPrompt] = useState(
    "Select an instance in the viewport or Model Tree.",
  );
  const [sidebarWidth, setSidebarWidth] = useState(228);
  const [consoleHeight, setConsoleHeight] = useState(106);
  const [context, setContext] = useState<{
    x: number;
    y: number;
    id: string;
  } | null>(null);
  const openFile = useRef<HTMLInputElement>(null);
  const app = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(draft));
    } catch {
      setPrompt(
        "Browser storage unavailable. Save the study JSON to preserve definitions.",
      );
    }
  }, [draft]);
  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenu(null);
        setContext(null);
        setDialog(null);
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);
  const log = (text: string) =>
    setMessages((prev) => [...prev.slice(-79), text]);
  function commit(next: Draft, text: string) {
    setUndo((prev) => [...prev, draft]);
    setRedo([]);
    setDraft(next);
    log(text);
  }
  function changeModule(value: Module) {
    setModule(value);
    setMenu(null);
    if (value === "Visualization") {
      setDataset("result");
      setTreeTab("Results");
      setField("magnitude");
      setSelected([]);
      setPrompt(
        "Retained displacement output: choose U component or query an exact node.",
      );
    } else {
      setDataset("assembly");
      setTreeTab("Model");
      setSelected([]);
      setPrompt(`${value} module: select an object, then choose a tool.`);
    }
    setCamera((p) => ({ name: "fit", tick: p.tick + 1 }));
  }
  function command(name: Camera) {
    setCamera((p) => ({ name, tick: p.tick + 1 }));
  }
  function select(id: string, additive = false) {
    if (!id) {
      setSelected([]);
      setPrompt("Selection cleared.");
      return;
    }
    setSelected((prev) =>
      additive
        ? prev.includes(id)
          ? prev.filter((x) => x !== id)
          : [...prev, id]
        : [id],
    );
    setPrompt(`Selected: ${components.find((c) => c.id === id)?.name || id}.`);
  }
  function unavailable(name: string) {
    setMenu(null);
    setDialogText(
      `${name} requires the Abaqus native kernel or solver connection. This browser study can store definitions and display retained geometry/results, but it cannot perform this operation. No geometry, mesh or solver result has been generated.`,
    );
    setDialog("info");
  }
  function openDialog(type: Exclude<Dialog, null>, existing?: Material | BC) {
    setMenu(null);
    setDialog(type);
    setFormError("");
    setForm(
      type === "material"
        ? existing
          ? Object.fromEntries(
              Object.entries(existing).map(([k, v]) => [k, String(v)]),
            )
          : {
              name: `Material-${draft.materials.length + 1}`,
              elastic: "",
              poisson: "",
              density: "",
            }
        : type === "bc"
          ? existing
            ? {
                name: existing.name,
                ux: (existing as BC).ux,
                uy: (existing as BC).uy,
                uz: (existing as BC).uz,
                region: (existing as BC).region.join(","),
              }
            : {
                name: `BC-${draft.bcs.length + 1}`,
                ux: "0",
                uy: "0",
                uz: "0",
                region: selected.join(","),
              }
          : type === "mesh"
            ? {
                size: String(draft.mesh.size),
                technique: draft.mesh.technique,
                element: draft.mesh.element,
              }
            : {
                name: `${type === "step" ? "Step" : type === "job" ? "Job" : "Interaction"}-${(type === "step" ? draft.steps : type === "job" ? draft.jobs : draft.interactions).length + 1}`,
              },
    );
    if (existing) setForm((prev) => ({ ...prev, originalName: existing.name }));
  }
  function applyDefinition() {
    const name = form.name?.trim();
    if (dialog !== "mesh" && !name) {
      setFormError("Enter a name.");
      return;
    }
    if (dialog === "material") {
      if (
        name !== form.originalName &&
        draft.materials.some((m) => m.name === name)
      ) {
        setFormError("A material with this name already exists.");
        return;
      }
      const elastic = Number(form.elastic),
        poisson = Number(form.poisson),
        density = Number(form.density);
      if (
        !form.elastic ||
        !form.poisson ||
        !form.density ||
        !Number.isFinite(elastic) ||
        elastic <= 0 ||
        !Number.isFinite(poisson) ||
        poisson <= -1 ||
        poisson >= 0.5 ||
        !Number.isFinite(density) ||
        density <= 0
      ) {
        setFormError(
          "Elastic modulus and density must be positive; −1 < Poisson ratio < 0.5. Specify consistent units.",
        );
        return;
      }
      commit(
        {
          ...draft,
          materials: [
            ...draft.materials.filter((m) => m.name !== form.originalName),
            { name, elastic, poisson, density },
          ],
        },
        `Material definition '${name}' stored (not evaluated).`,
      );
      setExpanded((p) => ({ ...p, materials: true }));
    } else if (dialog === "bc") {
      if (
        name !== form.originalName &&
        draft.bcs.some((b) => b.name === name)
      ) {
        setFormError("A boundary condition with this name already exists.");
        return;
      }
      const region = form.region.split(",").filter(Boolean);
      if (!region.length) {
        setFormError(
          "Select at least one assembly instance before defining a boundary condition.",
        );
        return;
      }
      if (
        ![form.ux, form.uy, form.uz].every(
          (v) => v === "" || Number.isFinite(Number(v)),
        )
      ) {
        setFormError(
          "Displacement values must be numeric, or blank for unconstrained.",
        );
        return;
      }
      commit(
        {
          ...draft,
          bcs: [
            ...draft.bcs.filter((b) => b.name !== form.originalName),
            { name, region, ux: form.ux, uy: form.uy, uz: form.uz },
          ],
        },
        `BC definition '${name}' stored for ${region.length} instance(s). No solve performed.`,
      );
      setExpanded((p) => ({ ...p, bcs: true }));
    } else if (dialog === "mesh") {
      const size = Number(form.size);
      if (!Number.isFinite(size) || size <= 0) {
        setFormError("Approximate global size must be positive.");
        return;
      }
      commit(
        {
          ...draft,
          mesh: { size, technique: form.technique, element: form.element },
        },
        `Seed definition stored: size ${size}. Existing tessellation remains unchanged; native mesh generation is unavailable.`,
      );
      setRepresentation("wireframe");
    } else {
      const key =
        dialog === "step"
          ? "steps"
          : dialog === "job"
            ? "jobs"
            : "interactions";
      if (draft[key].includes(name)) {
        setFormError("This name already exists.");
        return;
      }
      commit(
        { ...draft, [key]: [...draft[key], name] },
        `${dialog} draft '${name}' stored. No native operation submitted.`,
      );
      setExpanded((p) => ({ ...p, [key]: true }));
    }
    setDialog(null);
  }
  function hide(ids = selected) {
    if (!ids.length) {
      setPrompt("Select an instance to hide.");
      return;
    }
    setHidden((prev) => [...new Set([...prev, ...ids])]);
    setContext(null);
  }
  function isolate(ids = selected) {
    if (!ids.length) {
      setPrompt("Select an instance to isolate.");
      return;
    }
    setHidden(
      (dataset === "result"
        ? ["result-support"]
        : components.map((c) => c.id)
      ).filter((id) => !ids.includes(id)),
    );
    setContext(null);
  }
  function save() {
    const json = JSON.stringify(
      {
        format: "abaqus-browser-study",
        version: 1,
        draft,
        view: {
          module,
          dataset,
          hidden,
          representation,
          explode,
          clip,
          field,
          deformation,
          showLoads,
        },
      },
      null,
      2,
    );
    const url = URL.createObjectURL(
      new Blob([json], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "RollerFixture-browser-study.json";
    link.click();
    URL.revokeObjectURL(url);
    setMenu(null);
    log("Browser study saved as JSON. This is not an Abaqus .cae database.");
  }
  async function reopen(file?: File) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text());
      if (
        data.format !== "abaqus-browser-study" ||
        data.version !== 1 ||
        !validDraft(data.draft)
      )
        throw new Error("Unsupported or invalid browser-study file.");
      const view = data.view;
      if (
        !view ||
        !modules.includes(view.module) ||
        !["assembly", "result"].includes(view.dataset) ||
        !Array.isArray(view.hidden) ||
        !view.hidden.every((x: unknown) => typeof x === "string") ||
        !["shaded", "edges", "wireframe", "transparent"].includes(
          view.representation,
        ) ||
        !["none", "magnitude", "ux", "uy", "uz"].includes(view.field) ||
        !Number.isFinite(view.explode) ||
        view.explode < 0 ||
        view.explode > 1 ||
        !Number.isFinite(view.deformation) ||
        view.deformation < 0 ||
        !view.clip ||
        typeof view.clip.enabled !== "boolean" ||
        !["x", "y", "z"].includes(view.clip.axis) ||
        !Number.isFinite(view.clip.position) ||
        view.clip.position < 0 ||
        view.clip.position > 1 ||
        typeof view.showLoads !== "boolean"
      )
        throw new Error("Invalid view settings. Current study was preserved.");
      commit(data.draft, `Opened browser study: ${file.name}`);
      setModule(view.module);
      setDataset(view.dataset);
      setTreeTab(view.dataset === "result" ? "Results" : "Model");
      setHidden(view.hidden);
      setRepresentation(view.representation);
      setExplode(view.explode);
      setClip(view.clip);
      setField(view.field);
      setDeformation(view.deformation);
      setShowLoads(view.showLoads);
      setSelected([]);
      command("fit");
    } catch (e) {
      setDialogText(
        e instanceof Error ? e.message : "Unable to open this file.",
      );
      setDialog("info");
    }
  }
  function query(id: number) {
    const index = resultNodes.findIndex((n) => n.id === id),
      node = resultNodes[index];
    if (!node) {
      setPrompt(`Node ${id} is not present in the retained result mesh.`);
      return;
    }
    setProbe(node);
    setNodeId(String(id));
    setXyPage(Math.floor(index / 60));
    setConsoleTab("Query");
    setDataset("result");
    setModule("Visualization");
    setTreeTab("Results");
  }
  function resize(e: PointerEvent, direction: "tree" | "console") {
    e.preventDefault();
    const initial = direction === "tree" ? sidebarWidth : consoleHeight,
      start = direction === "tree" ? e.clientX : e.clientY;
    const move = (event: globalThis.PointerEvent) =>
      direction === "tree"
        ? setSidebarWidth(
            Math.max(175, Math.min(420, initial + event.clientX - start)),
          )
        : setConsoleHeight(
            Math.max(
              70,
              Math.min(
                (app.current?.clientHeight || 900) * 0.45,
                initial + start - event.clientY,
              ),
            ),
          );
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop, { once: true });
  }
  const toggle = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  const objectRow = (id: string, name: string, kind = "instance") => (
    <button
      key={id}
      className={`abq-tree-line abq-object ${selected.includes(id) ? "selected" : ""} ${hidden.includes(id) ? "hidden" : ""}`}
      onClick={(e) => select(id, e.ctrlKey || e.metaKey)}
      onContextMenu={(e) => {
        e.preventDefault();
        select(id);
        setContext({ x: e.clientX, y: e.clientY, id });
      }}
    >
      <Cuboid size={13} color={kind === "result" ? "#ac724b" : "#527aaf"} />
      <span>{name}</span>
      <span
        className="abq-eye"
        role="button"
        tabIndex={0}
        aria-label={`${hidden.includes(id) ? "Show" : "Hide"} ${name}`}
        onClick={(e) => {
          e.stopPropagation();
          hidden.includes(id)
            ? setHidden((prev) => prev.filter((x) => x !== id))
            : hide([id]);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.stopPropagation();
            hidden.includes(id)
              ? setHidden((prev) => prev.filter((x) => x !== id))
              : hide([id]);
          }
        }}
      >
        {hidden.includes(id) ? <EyeOff size={11} /> : <Eye size={11} />}
      </span>
    </button>
  );
  const menuItems: Record<
    string,
    { label: string; action: () => void; key?: string }[]
  > = {
    File: [
      { label: "New Browser Study…", action: () => openDialog("new") },
      {
        label: "Open Browser Study…",
        action: () => {
          setMenu(null);
          openFile.current?.click();
        },
        key: "JSON",
      },
      { label: "Save Browser Study", action: save, key: "JSON" },
      {
        label: "Import → Part…",
        action: () => unavailable("Import native CAD / Abaqus database"),
      },
      {
        label: "Print…",
        action: () => {
          setMenu(null);
          window.print();
        },
      },
    ],
    Model: [
      {
        label: "Edit Attributes…",
        action: () => {
          setDialogText(
            "Model-1 · Local clip assembly. Geometry is retained project data. Draft definitions use the units you specify; this view does not validate a physical model.",
          );
          setDialog("info");
        },
      },
      { label: "Create Material…", action: () => openDialog("material") },
      { label: "Create Step…", action: () => openDialog("step") },
    ],
    Viewport: [
      { label: "Fit View", action: () => command("fit") },
      { label: "Isometric View", action: () => command("iso") },
      { label: "Front View", action: () => command("front") },
      { label: "Top View", action: () => command("top") },
      { label: "Right View", action: () => command("right") },
      { label: "Restore All Display Groups", action: () => setHidden([]) },
    ],
    View: [
      { label: "Shaded", action: () => setRepresentation("shaded") },
      { label: "Shaded with Edges", action: () => setRepresentation("edges") },
      { label: "Wireframe", action: () => setRepresentation("wireframe") },
      { label: "Translucency", action: () => setRepresentation("transparent") },
      {
        label: "Section Cut",
        action: () => setClip((p) => ({ ...p, enabled: !p.enabled })),
      },
    ],
    Tools: [
      {
        label: "Query → Probe Values",
        action: () => {
          changeModule("Visualization");
          setProbeMode(true);
          setConsoleTab("Query");
        },
      },
      { label: "XY Data → Retained U by Node", action: () => openDialog("xy") },
      {
        label: "Set → Create…",
        action: () => unavailable("Create native geometry set"),
      },
    ],
    Plug_ins: [
      {
        label: "Plug-in Manager…",
        action: () => unavailable("Load Abaqus Python plug-ins"),
      },
    ],
    Help: [
      {
        label: "About This Browser Study",
        action: () => {
          setDialogText(
            "Abaqus/CAE 2026 interface reference study. Local project geometry and retained displacement data are displayed. This is not the licensed SIMULIA application; native CAD, meshing and solver execution are not connected.",
          );
          setDialog("info");
        },
      },
    ],
  };
  const moduleActions: Record<
    Module,
    { label: string; icon: LucideIcon; action: () => void; color: string }[]
  > = {
    Part: [
      {
        label: "Create Part",
        icon: Plus,
        action: () => unavailable("Create / edit native Part"),
        color: "#598149",
      },
      {
        label: "Edit Sketch",
        icon: Scissors,
        action: () => unavailable("Edit Sketch"),
        color: "#b4873b",
      },
      {
        label: "Partition",
        icon: Grid3X3,
        action: () => unavailable("Partition geometry"),
        color: "#9060a0",
      },
    ],
    Property: [
      {
        label: "Create Material",
        icon: Thermometer,
        action: () => openDialog("material"),
        color: "#ad554b",
      },
      {
        label: "Assign Section",
        icon: Layers,
        action: () => unavailable("Assign native section"),
        color: "#977d36",
      },
    ],
    Assembly: [
      {
        label: "Instance",
        icon: Boxes,
        action: () => unavailable("Create native instance"),
        color: "#ad8d43",
      },
      {
        label: "Exploded Display",
        icon: Move,
        action: () => setExplode((v) => (v ? 0 : 0.55)),
        color: "#598449",
      },
      {
        label: "Translate Instance",
        icon: ArrowDownToLine,
        action: () => unavailable("Translate native instance"),
        color: "#4d7cb6",
      },
    ],
    Step: [
      {
        label: "Create Step",
        icon: Plus,
        action: () => openDialog("step"),
        color: "#638b54",
      },
      {
        label: "Field Output Request",
        icon: File,
        action: () => unavailable("Edit solver output request"),
        color: "#aa8643",
      },
    ],
    Interaction: [
      {
        label: "Create Interaction",
        icon: Magnet,
        action: () => openDialog("interaction"),
        color: "#4e81b8",
      },
      {
        label: "Contact Property",
        icon: Settings2,
        action: () => unavailable("Native contact property"),
        color: "#a8863b",
      },
    ],
    Load: [
      {
        label: "Create Load",
        icon: ArrowDownToLine,
        action: () => unavailable("Native load definition"),
        color: "#b45c4c",
      },
      {
        label: "Create Boundary Condition",
        icon: Magnet,
        action: () => openDialog("bc"),
        color: "#557da7",
      },
      {
        label: "Show Retained Load Nodes",
        icon: Eye,
        action: () => {
          changeModule("Visualization");
          setShowLoads((v) => !v);
          setPrompt(
            "Load arrows mark the retained 200 N case; local BC definitions do not change this result.",
          );
        },
        color: "#7a9753",
      },
    ],
    Mesh: [
      {
        label: "Seed Part",
        icon: CircleDot,
        action: () => openDialog("mesh"),
        color: "#b6903d",
      },
      {
        label: "Mesh Controls",
        icon: Grid3X3,
        action: () => openDialog("mesh"),
        color: "#5591a1",
      },
      {
        label: "Mesh Part",
        icon: Network,
        action: () => unavailable("Generate native finite-element mesh"),
        color: "#98689f",
      },
    ],
    Job: [
      {
        label: "Create Job",
        icon: File,
        action: () => openDialog("job"),
        color: "#56835c",
      },
      {
        label: "Submit Job",
        icon: Play,
        action: () => unavailable("Submit Abaqus job"),
        color: "#af564b",
      },
      {
        label: "Job Monitor",
        icon: ChartNoAxesCombined,
        action: () => {
          setDialogText(
            `${draft.jobs.length} locally defined job draft(s). No jobs have been submitted; Abaqus solver connection is absent.`,
          );
          setDialog("info");
        },
        color: "#5983a5",
      },
    ],
    Visualization: [
      {
        label: "Plot Undeformed Shape",
        icon: Box,
        action: () => {
          setDeformation(0);
          setField("none");
        },
        color: "#9c8650",
      },
      {
        label: "Plot Deformed Shape",
        icon: Cuboid,
        action: () => setDeformation((v) => (v ? 0 : 1)),
        color: "#59986d",
      },
      {
        label: "Plot Contours on Deformed Shape",
        icon: Layers,
        action: () => {
          setField("magnitude");
          setDeformation(1);
        },
        color: "#b4585a",
      },
      {
        label: "Probe Values",
        icon: Crosshair,
        action: () => {
          setProbeMode((v) => !v);
          setConsoleTab("Query");
        },
        color: "#718da8",
      },
      {
        label: "XY Data Manager",
        icon: ChartNoAxesCombined,
        action: () => openDialog("xy"),
        color: "#497cac",
      },
    ],
  };
  const toolAction = moduleActions[module];
  const moduleMenu = module === "Visualization" ? "Result" : module;
  const actualMenuNames = [
    "File",
    "Model",
    "Viewport",
    "View",
    moduleMenu,
    "Tools",
    "Plug_ins",
    "Help",
  ];
  const renderInput = (label: string, key: string, type = "text") => (
    <label className="abq-form-row">
      <span>{label}</span>
      <input
        type={type}
        step="any"
        value={form[key] || ""}
        onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))}
      />
    </label>
  );
  const selectedComponent = components.find((c) => c.id === selected[0]);
  const activeIds =
    dataset === "result" ? ["result-support"] : components.map((c) => c.id);
  const visibleCount = activeIds.filter((id) => !hidden.includes(id)).length;
  const minNode = Math.min(...resultNodes.map((n) => n.id)),
    maxNode = Math.max(...resultNodes.map((n) => n.id));
  return (
    <div
      className="abq-app"
      ref={app}
      onClick={() => {
        if (menu) setMenu(null);
        if (context) setContext(null);
      }}
    >
      <div className="abq-titlebar">
        <Box size={12} color="#586fa4" />
        <span>
          Abaqus/CAE 2026 — Model Database: RollerFixture [Viewport: 1]
        </span>
        <span className="abq-window-buttons">—　□　×</span>
      </div>
      <div className="abq-menubar" onClick={(e) => e.stopPropagation()}>
        {actualMenuNames.map((name) => (
          <div className="abq-menu" key={name}>
            <button
              className={menu === name ? "open" : ""}
              onClick={() => setMenu(menu === name ? null : name)}
            >
              {name.replace("_", "-")}
            </button>
            {menu === name && (
              <div className="abq-menu-popup">
                {(
                  menuItems[name] ||
                  toolAction.map((a) => ({
                    label: a.label + "…",
                    action: a.action,
                  }))
                ).map((item) => (
                  <button
                    key={item.label}
                    onClick={() => {
                      setMenu(null);
                      item.action();
                    }}
                  >
                    <span>{item.label}</span>
                    {"key" in item && <small>{item.key}</small>}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="abq-toolbar-row">
        <Group>
          <Tool
            icon={File}
            title="New browser study"
            color="#629455"
            onClick={() => openDialog("new")}
          />
          <Tool
            icon={FolderOpen}
            title="Open browser study JSON"
            color="#a89440"
            onClick={() => openFile.current?.click()}
          />
          <Tool icon={Save} title="Save browser study JSON" onClick={save} />
          <Tool
            icon={Printer}
            title="Print viewport"
            color="#555d76"
            onClick={() => window.print()}
          />
        </Group>
        <Group>
          <Tool
            icon={Undo2}
            title="Undo definition"
            color="#aa864c"
            disabled={!undo.length}
            onClick={() => {
              setRedo((p) => [...p, draft]);
              setDraft(undo[undo.length - 1]);
              setUndo((p) => p.slice(0, -1));
              log("Definition edit undone.");
            }}
          />
          <Tool
            icon={Redo2}
            title="Redo definition"
            color="#aa864c"
            disabled={!redo.length}
            onClick={() => {
              setUndo((p) => [...p, draft]);
              setDraft(redo[redo.length - 1]);
              setRedo((p) => p.slice(0, -1));
              log("Definition edit redone.");
            }}
          />
        </Group>
        <Group>
          <Tool
            icon={MousePointer2}
            title="Select instance"
            color="#54585c"
            active={!probeMode}
            onClick={() => setProbeMode(false)}
          />
          <Tool
            icon={Crosshair}
            title="Query retained result node"
            color="#8d5353"
            active={probeMode}
            onClick={() => {
              changeModule("Visualization");
              setProbeMode(true);
              setConsoleTab("Query");
            }}
          />
          <select
            aria-label="Selection filter"
            value={probeMode ? "Nodes (retained result)" : "Part instances"}
            onChange={(e) => {
              if (e.target.value === "Nodes (retained result)") {
                changeModule("Visualization");
                setProbeMode(true);
                setConsoleTab("Query");
              } else {
                setProbeMode(false);
                changeModule("Assembly");
              }
            }}
          >
            <option>Part instances</option>
            <option>Nodes (retained result)</option>
          </select>
        </Group>
        <Group>
          <Tool
            icon={Maximize}
            title="Fit view"
            onClick={() => command("fit")}
          />
          <Tool
            icon={Rotate3D}
            title="Isometric view"
            color="#879344"
            onClick={() => command("iso")}
          />
          <Tool
            icon={ZoomIn}
            title="Zoom in"
            onClick={() => command("zoomIn")}
          />
          <Tool
            icon={ZoomOut}
            title="Zoom out"
            onClick={() => command("zoomOut")}
          />
        </Group>
        <Group>
          <Tool
            icon={Box}
            title="Front view"
            onClick={() => command("front")}
          />
          <Tool
            icon={Grid3X3}
            title="Top view"
            onClick={() => command("top")}
          />
          <Tool
            icon={Cuboid}
            title="Right view"
            onClick={() => command("right")}
          />
        </Group>
      </div>
      <div className="abq-toolbar-row">
        <Group>
          <Tool
            icon={Box}
            title="Shaded"
            color="#a99155"
            active={representation === "shaded"}
            onClick={() => setRepresentation("shaded")}
          />
          <Tool
            icon={Cuboid}
            title="Shaded with edges"
            color="#aaa065"
            active={representation === "edges"}
            onClick={() => setRepresentation("edges")}
          />
          <Tool
            icon={Grid3X3}
            title="Wireframe"
            color="#4e8b87"
            active={representation === "wireframe"}
            onClick={() => setRepresentation("wireframe")}
          />
          <Tool
            icon={Layers}
            title="Translucency"
            color="#8a77a0"
            active={representation === "transparent"}
            onClick={() => setRepresentation("transparent")}
          />
        </Group>
        <Group>
          <Tool
            icon={EyeOff}
            title="Hide selected"
            color="#808454"
            onClick={() => hide()}
          />
          <Tool
            icon={Focus}
            title="Isolate selected"
            color="#5c969b"
            onClick={() => isolate()}
          />
          <Tool
            icon={Eye}
            title="Restore all instances"
            color="#778f45"
            onClick={() => setHidden([])}
          />
          <Tool
            icon={Scissors}
            title="Section cut"
            color="#a96c4b"
            active={clip.enabled}
            onClick={() => setClip((p) => ({ ...p, enabled: !p.enabled }))}
          />
        </Group>
        <Group>
          <Tool
            icon={Move}
            title="Exploded assembly display"
            color="#597d98"
            active={explode > 0}
            onClick={() => setExplode((v) => (v ? 0 : 0.55))}
          />
          <label>
            Explode{" "}
            <input
              aria-label="Exploded display"
              type="range"
              min="0"
              max="1"
              step=".05"
              value={explode}
              onChange={(e) => setExplode(Number(e.target.value))}
            />
          </label>
        </Group>
        <Group>
          <label>
            Section{" "}
            <select
              aria-label="Section axis"
              value={clip.axis}
              onChange={(e) =>
                setClip((p) => ({
                  ...p,
                  axis: e.target.value as "x" | "y" | "z",
                }))
              }
            >
              <option>x</option>
              <option>y</option>
              <option>z</option>
            </select>
            <input
              aria-label="Section cut position"
              type="range"
              min="0"
              max="1"
              step=".01"
              value={clip.position}
              onChange={(e) =>
                setClip((p) => ({
                  ...p,
                  position: Number(e.target.value),
                  enabled: true,
                }))
              }
            />
          </label>
        </Group>
      </div>
      <div
        className="abq-contextbar"
        style={{ paddingLeft: sidebarWidth + 61 }}
      >
        <label>
          Module:{" "}
          <select
            value={module}
            onChange={(e) => changeModule(e.target.value as Module)}
          >
            {modules.map((m) => (
              <option key={m}>{m}</option>
            ))}
          </select>
        </label>
        <label>
          Model:{" "}
          <select aria-label="Model">
            <option>Model-1</option>
          </select>
        </label>
        {module === "Part" || module === "Mesh" || module === "Property" ? (
          <label>
            Part:{" "}
            <select
              aria-label="Part"
              value={selectedComponent?.id || ""}
              onChange={(e) => select(e.target.value)}
            >
              <option value="">All parts</option>
              {components.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        ) : module === "Visualization" ? (
          <>
            <label>
              Primary variable:{" "}
              <select
                aria-label="Result field"
                value={field}
                onChange={(e) => setField(e.target.value as Field)}
              >
                <option value="none">None</option>
                <option value="magnitude">U, Magnitude</option>
                <option value="ux">U, U1</option>
                <option value="uy">U, U2</option>
                <option value="uz">U, U3</option>
              </select>
            </label>
            <label>
              Deformation scale:{" "}
              <input
                aria-label="Deformation scale"
                type="number"
                min="0"
                max="10000"
                step=".5"
                value={deformation}
                onChange={(e) =>
                  setDeformation(
                    Math.max(0, Math.min(10000, Number(e.target.value))),
                  )
                }
              />
            </label>
          </>
        ) : (
          <label>
            Step:{" "}
            <select
              aria-label="Step"
              value={draft.steps.includes(activeStep) ? activeStep : "Initial"}
              onChange={(e) => {
                setActiveStep(e.target.value);
                setPrompt(`Active step: ${e.target.value} (draft definition).`);
              }}
            >
              <option>Initial</option>
              {draft.steps.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      <div className="abq-main">
        <aside className="abq-tree" style={{ width: sidebarWidth }}>
          <div className="abq-tree-tabs">
            {["Model", "Results"].map((t) => (
              <button
                key={t}
                className={treeTab === t ? "active" : ""}
                onClick={() => setTreeTab(t)}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="abq-tree-source">
            <select aria-label="Tree source">
              <option>
                {treeTab === "Model" ? "Model Database" : "Output Databases"}
              </option>
            </select>
            <Tool
              icon={Eye}
              title="Restore all display groups"
              onClick={() => setHidden([])}
            />
          </div>
          <div className="abq-tree-scroll">
            {treeTab === "Model" ? (
              <>
                <Branch
                  title="Models"
                  count={1}
                  open={expanded.model}
                  toggle={() => toggle("model")}
                >
                  <div className="abq-tree-line">
                    <Box size={12} color="#738ba5" />
                    <b>Model-1</b>
                  </div>
                  <Branch
                    title="Parts"
                    count={components.length}
                    open={expanded.parts}
                    toggle={() => toggle("parts")}
                  >
                    {components.map((c) => objectRow(c.id, c.name, "part"))}
                  </Branch>
                  <Branch
                    title="Materials"
                    count={draft.materials.length}
                    open={expanded.materials}
                    toggle={() => toggle("materials")}
                  >
                    {draft.materials.map((m) => (
                      <button
                        key={m.name}
                        className="abq-tree-line"
                        onClick={() => openDialog("material", m)}
                      >
                        <Thermometer size={12} color="#b16e60" />
                        {m.name}
                      </button>
                    ))}
                    <button
                      className="abq-tree-create"
                      onClick={() => openDialog("material")}
                    >
                      Create…
                    </button>
                  </Branch>
                  <Branch
                    title="Sections"
                    count={0}
                    open={expanded.sections}
                    toggle={() => toggle("sections")}
                  >
                    <button
                      className="abq-tree-create"
                      onClick={() => unavailable("Create native section")}
                    >
                      Create…
                    </button>
                  </Branch>
                  <Branch
                    title="Assembly"
                    open={expanded.assembly}
                    toggle={() => toggle("assembly")}
                  >
                    <Branch
                      title="Instances"
                      count={components.length}
                      open={expanded.instances}
                      toggle={() => toggle("instances")}
                    >
                      {components.map((c) => objectRow(c.id, `${c.name}-1`))}
                    </Branch>
                    <button
                      className="abq-tree-line"
                      onClick={() => unavailable("Native assembly constraints")}
                    >
                      <Magnet size={12} />
                      Constraints
                    </button>
                  </Branch>
                  <Branch
                    title="Steps"
                    count={1 + draft.steps.length}
                    open={expanded.steps}
                    toggle={() => toggle("steps")}
                  >
                    <div className="abq-tree-line">Initial</div>
                    {draft.steps.map((s) => (
                      <button
                        key={s}
                        className="abq-tree-line"
                        onClick={() =>
                          setPrompt(
                            `Step draft: ${s}; no time integration submitted.`,
                          )
                        }
                      >
                        <Layers size={12} />
                        {s}
                      </button>
                    ))}
                    <button
                      className="abq-tree-create"
                      onClick={() => openDialog("step")}
                    >
                      Create…
                    </button>
                  </Branch>
                  {[
                    "Field Output Requests",
                    "History Output Requests",
                    "Time Points",
                  ].map((s) => (
                    <button
                      className="abq-tree-line"
                      key={s}
                      onClick={() => unavailable(s)}
                    >
                      <ChevronRight size={11} />
                      <File size={12} color="#7489a1" />
                      {s}
                    </button>
                  ))}
                  <Branch
                    title="Interactions"
                    count={draft.interactions.length}
                    open={expanded.interactions}
                    toggle={() => toggle("interactions")}
                  >
                    {draft.interactions.map((s) => (
                      <div key={s} className="abq-tree-line">
                        <Magnet size={12} />
                        {s}
                      </div>
                    ))}
                    <button
                      className="abq-tree-create"
                      onClick={() => openDialog("interaction")}
                    >
                      Create…
                    </button>
                  </Branch>
                  <button
                    className="abq-tree-line"
                    onClick={() => unavailable("Native load manager")}
                  >
                    <ArrowDownToLine size={12} color="#be7359" />
                    Loads (0)
                  </button>
                  <Branch
                    title="BCs"
                    count={draft.bcs.length}
                    open={expanded.bcs}
                    toggle={() => toggle("bcs")}
                  >
                    {draft.bcs.map((b) => (
                      <button
                        key={b.name}
                        className="abq-tree-line"
                        onClick={() => openDialog("bc", b)}
                      >
                        <Magnet size={12} color="#6e97b4" />
                        {b.name}
                      </button>
                    ))}
                    <button
                      className="abq-tree-create"
                      onClick={() => openDialog("bc")}
                    >
                      Create…
                    </button>
                  </Branch>
                  <button
                    className="abq-tree-line"
                    onClick={() => openDialog("mesh")}
                  >
                    <Network size={12} color="#86974d" />
                    Mesh · seed {draft.mesh.size}
                  </button>
                </Branch>
                <Branch
                  title="Analysis"
                  open={expanded.analysis}
                  toggle={() => toggle("analysis")}
                >
                  <Branch
                    title="Jobs"
                    count={draft.jobs.length}
                    open={expanded.jobs}
                    toggle={() => toggle("jobs")}
                  >
                    {draft.jobs.map((j) => (
                      <button
                        key={j}
                        className="abq-tree-line"
                        onClick={() => unavailable(`Submit job '${j}'`)}
                      >
                        <File size={12} color="#849643" />
                        {j} (Draft)
                      </button>
                    ))}
                    <button
                      className="abq-tree-create"
                      onClick={() => openDialog("job")}
                    >
                      Create…
                    </button>
                  </Branch>
                </Branch>
              </>
            ) : (
              <Branch title="Retained output" open={true} toggle={() => {}}>
                {objectRow("result-support", "support — retained U", "result")}
                <div className="abq-result-summary">
                  Nodes: {resultInfo.nodes.toLocaleString()}
                  <br />
                  Elements: {resultInfo.elements.toLocaleString()}
                  <br />
                  Field: U [{resultInfo.unit}]<br />
                  <span title={resultInfo.source}>{resultInfo.source}</span>
                </div>
                <button
                  className="abq-tree-create"
                  onClick={() => changeModule("Visualization")}
                >
                  Display output
                </button>
              </Branch>
            )}
          </div>
        </aside>
        <div
          className="abq-splitter"
          role="separator"
          aria-label="Resize Model Tree"
          onPointerDown={(e) => resize(e, "tree")}
        />
        <div className="abq-workspace">
          <div className="abq-view-row">
            <div className="abq-toolbox">
              <div className="abq-toolbox-grid">
                {toolAction.map((a) => (
                  <Tool
                    key={a.label}
                    icon={a.icon}
                    title={a.label}
                    color={a.color}
                    onClick={a.action}
                  />
                ))}
                <Tool
                  icon={MousePointer2}
                  title="Select"
                  color="#586271"
                  onClick={() => setProbeMode(false)}
                />
                <Tool
                  icon={EyeOff}
                  title="Hide selected"
                  color="#809155"
                  onClick={() => hide()}
                />
                <Tool
                  icon={Focus}
                  title="Isolate selected"
                  color="#688d8a"
                  onClick={() => isolate()}
                />
                <Tool
                  icon={Eye}
                  title="Restore display group"
                  color="#8a9657"
                  onClick={() => setHidden([])}
                />
                <Tool
                  icon={Scissors}
                  title="Section cut"
                  color="#ad7762"
                  onClick={() =>
                    setClip((p) => ({ ...p, enabled: !p.enabled }))
                  }
                />
                <Tool
                  icon={Rotate3D}
                  title="Isometric view"
                  color="#698fb7"
                  onClick={() => command("iso")}
                />
                <Tool
                  icon={Maximize}
                  title="Fit view"
                  color="#6990b4"
                  onClick={() => command("fit")}
                />
                <Tool
                  icon={Grid3X3}
                  title="Existing tessellation"
                  color="#9081b2"
                  onClick={() => setRepresentation("wireframe")}
                />
                <Tool
                  icon={Crosshair}
                  title="Query node"
                  color="#a56363"
                  onClick={() => {
                    changeModule("Visualization");
                    setProbeMode(true);
                    setConsoleTab("Query");
                  }}
                />
              </div>
            </div>
            <div className="abq-viewport">
              <Scene
                theme="abaqus"
                dataset={dataset}
                representation={representation}
                selected={selected}
                hidden={hidden}
                onSelect={select}
                onProbe={(node) => {
                  setProbe(node);
                  setNodeId(String(node.id));
                  setConsoleTab("Query");
                }}
                command={camera}
                explode={explode}
                clip={clip}
                field={dataset === "result" ? field : "none"}
                deformation={dataset === "result" ? deformation : 0}
                showLoads={showLoads}
                probeMode={probeMode}
                probeId={probe?.id}
              />
              <div
                className={`abq-viewport-caption ${dataset === "result" ? "result" : ""}`}
              >
                Viewport: 1<br />
                {dataset === "assembly"
                  ? "Assembly: Model-1"
                  : `Deformation scale: ${deformation}`}
              </div>
            </div>
          </div>
          <div className="abq-prompt">
            <MousePointer2 size={13} />
            <span>{prompt}</span>
            <button
              onClick={() => {
                setSelected([]);
                setProbeMode(false);
                setPrompt("Selection cleared.");
              }}
            >
              Cancel
            </button>
            <button
              onClick={() =>
                setPrompt(
                  selected.length
                    ? `${selected.length} object(s) selected.`
                    : "Select an object in the viewport or tree.",
                )
              }
            >
              Done
            </button>
            <strong>SIMULIA</strong>
          </div>
        </div>
      </div>
      <div
        className="abq-console-splitter"
        role="separator"
        aria-label="Resize message area"
        onPointerDown={(e) => resize(e, "console")}
      />
      <div className="abq-console" style={{ height: consoleHeight }}>
        <div className="abq-console-tabs">
          {["Messages", "Query", "Definitions"].map((t) => (
            <button
              className={consoleTab === t ? "active" : ""}
              key={t}
              onClick={() => setConsoleTab(t)}
            >
              {t}
            </button>
          ))}
          <button className="abq-console-clear" onClick={() => setMessages([])}>
            Clear messages
          </button>
        </div>
        <div className="abq-console-content">
          {consoleTab === "Messages" ? (
            <pre>{messages.join("\n")}</pre>
          ) : consoleTab === "Query" ? (
            <>
              <div className="abq-query-row">
                <label>
                  Node ID:{" "}
                  <input
                    aria-label="Exact node ID"
                    type="number"
                    value={nodeId}
                    onChange={(e) => setNodeId(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") query(Number(nodeId));
                    }}
                  />
                </label>
                <button onClick={() => query(Number(nodeId))}>Probe</button>
                <button
                  className={probeMode ? "active" : ""}
                  onClick={() => {
                    changeModule("Visualization");
                    setProbeMode((v) => !v);
                  }}
                >
                  Pick node in viewport
                </button>
                <span>Retained support mesh · {resultInfo.unit}</span>
              </div>
              {probe && (
                <table className="abq-query-table">
                  <thead>
                    <tr>
                      {[
                        "Node",
                        "X",
                        "Y",
                        "Z",
                        "U1",
                        "U2",
                        "U3",
                        "U Magnitude",
                      ].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      {[
                        probe.id,
                        probe.x,
                        probe.y,
                        probe.z,
                        probe.ux,
                        probe.uy,
                        probe.uz,
                        probe.magnitude,
                      ].map((v, i) => (
                        <td key={i}>{i ? v.toPrecision(7) : v}</td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              )}
            </>
          ) : (
            <table className="abq-query-table">
              <thead>
                <tr>
                  <th>Definition</th>
                  <th>Value</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {draft.materials.map((m) => (
                  <tr key={m.name} onClick={() => openDialog("material", m)}>
                    <td>{m.name}</td>
                    <td>
                      E={m.elastic}; ν={m.poisson}; ρ={m.density}
                    </td>
                    <td>Draft</td>
                  </tr>
                ))}
                {draft.bcs.map((b) => (
                  <tr key={b.name} onClick={() => openDialog("bc", b)}>
                    <td>{b.name}</td>
                    <td>
                      U1={b.ux || "free"}; U2={b.uy || "free"}; U3=
                      {b.uz || "free"}
                    </td>
                    <td>{b.region.length} regions</td>
                  </tr>
                ))}
                <tr onClick={() => openDialog("mesh")}>
                  <td>Global seeds</td>
                  <td>
                    {draft.mesh.size} · {draft.mesh.technique} ·{" "}
                    {draft.mesh.element}
                  </td>
                  <td>Unmeshed draft</td>
                </tr>
              </tbody>
            </table>
          )}
        </div>
      </div>
      <div className="abq-statusbar">
        <span>
          {dataset === "assembly"
            ? `${visibleCount}/${components.length} instances displayed`
            : "Retained displacement data — no new solver run"}
        </span>
        <span>Abaqus 2026 browser interface study · local data</span>
      </div>
      <input
        ref={openFile}
        type="file"
        accept=".json,application/json"
        hidden
        onChange={(e) => {
          void reopen(e.target.files?.[0]);
          e.currentTarget.value = "";
        }}
      />
      {context && (
        <div
          className="abq-context-popup"
          style={{ left: context.x, top: context.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button onClick={() => hide([context.id])}>Hide</button>
          <button onClick={() => isolate([context.id])}>Isolate</button>
          <button
            onClick={() => {
              setHidden([]);
              setContext(null);
            }}
          >
            Show All
          </button>
          <button
            onClick={() => {
              setContext(null);
              command("fit");
            }}
          >
            Fit View
          </button>
        </div>
      )}
      {dialog && (
        <div className="abq-modal-shade" onClick={(e) => e.stopPropagation()}>
          <div
            className={`abq-dialog ${dialog === "xy" ? "wide" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-label={
              dialog === "info" ? "Command information" : `Edit ${dialog}`
            }
          >
            <div className="abq-dialog-title">
              {dialog === "material"
                ? "Edit Material"
                : dialog === "bc"
                  ? "Edit Boundary Condition"
                  : dialog === "mesh"
                    ? "Global Seeds / Mesh Controls"
                    : dialog === "new"
                      ? "New Browser Study"
                      : dialog === "xy"
                        ? "XY Data — Retained U Magnitude"
                        : dialog === "info"
                          ? "Abaqus Browser Study"
                          : `Create ${dialog[0].toUpperCase() + dialog.slice(1)}`}
              <button onClick={() => setDialog(null)} aria-label="Close dialog">
                <X size={13} />
              </button>
            </div>
            <div className="abq-dialog-body">
              {dialog === "info" ? (
                <p>{dialogText}</p>
              ) : dialog === "new" ? (
                <p>
                  Clear draft definitions and restore the displayed assembly?
                  Source geometry and retained results are preserved. This
                  action can be undone.
                </p>
              ) : dialog === "xy" ? (
                <>
                  <p>
                    Actual retained U magnitude by node ID. Plot: approximately
                    90 sampled nodes. Table: all retained nodes in pages of 60.
                    Click a point or row to query the same node.
                  </p>
                  <svg
                    className="abq-xy-plot"
                    viewBox="0 0 600 180"
                    role="img"
                    aria-label="Retained displacement by node"
                  >
                    <line x1="38" y1="150" x2="585" y2="150" stroke="#8999aa" />
                    <line x1="38" y1="15" x2="38" y2="150" stroke="#8999aa" />
                    <g fill="#465765" fontSize="9" fontFamily="Arial">
                      <text x="43" y="11">
                        U magnitude [mm]
                      </text>
                      {[0, 0.5, 1].map((fraction) => (
                        <g key={fraction}>
                          <line
                            x1="35"
                            x2="38"
                            y1={150 - fraction * 130}
                            y2={150 - fraction * 130}
                            stroke="#8999aa"
                          />
                          <text
                            x="32"
                            y={153 - fraction * 130}
                            textAnchor="end"
                          >
                            {(resultInfo.maxMagnitude * fraction).toExponential(
                              1,
                            )}
                          </text>
                        </g>
                      ))}
                      <text x="40" y="164">
                        {minNode}
                      </text>
                      <text x="575" y="164" textAnchor="end">
                        {maxNode}
                      </text>
                      <text x="305" y="172" textAnchor="middle">
                        Original node ID
                      </text>
                    </g>
                    {resultNodes
                      .filter(
                        (_n, i) =>
                          i %
                            Math.max(1, Math.floor(resultNodes.length / 90)) ===
                          0,
                      )
                      .map((n, i, a) => (
                        <circle
                          key={n.id}
                          cx={
                            40 +
                            ((n.id - minNode) * 535) /
                              Math.max(1, maxNode - minNode)
                          }
                          cy={
                            150 -
                            (n.magnitude * 130) / (resultInfo.maxMagnitude || 1)
                          }
                          r={probe?.id === n.id ? 4 : 2.5}
                          fill={probe?.id === n.id ? "#c4483e" : "#397dad"}
                          tabIndex={0}
                          role="button"
                          aria-label={`Probe node ${n.id}`}
                          onClick={() => query(n.id)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") query(n.id);
                          }}
                        />
                      ))}
                    {probe && (
                      <circle
                        cx={
                          40 +
                          ((probe.id - minNode) * 535) /
                            Math.max(1, maxNode - minNode)
                        }
                        cy={
                          150 -
                          (probe.magnitude * 130) /
                            (resultInfo.maxMagnitude || 1)
                        }
                        r={5}
                        fill="#c4483e"
                        stroke="#fff"
                        strokeWidth={1.5}
                        aria-label={`Selected node ${probe.id}`}
                      />
                    )}
                  </svg>
                  <div className="abq-xy-page">
                    <button
                      disabled={xyPage === 0}
                      onClick={() => setXyPage((p) => p - 1)}
                    >
                      Previous
                    </button>
                    <span>
                      Nodes {xyPage * 60 + 1}–
                      {Math.min(resultNodes.length, xyPage * 60 + 60)} /{" "}
                      {resultNodes.length}
                    </span>
                    <button
                      disabled={(xyPage + 1) * 60 >= resultNodes.length}
                      onClick={() => setXyPage((p) => p + 1)}
                    >
                      Next
                    </button>
                    <span>
                      {probe
                        ? `Selected node: ${probe.id}`
                        : "No node selected"}
                    </span>
                  </div>
                  <div className="abq-xy-table">
                    <table className="abq-query-table">
                      <thead>
                        <tr>
                          <th>Node</th>
                          <th>U1</th>
                          <th>U2</th>
                          <th>U3</th>
                          <th>Magnitude [{resultInfo.unit}]</th>
                        </tr>
                      </thead>
                      <tbody>
                        {resultNodes
                          .slice(xyPage * 60, xyPage * 60 + 60)
                          .map((n) => (
                            <tr
                              key={n.id}
                              className={probe?.id === n.id ? "selected" : ""}
                              onClick={() => query(n.id)}
                              tabIndex={0}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") query(n.id);
                              }}
                            >
                              <td>{n.id}</td>
                              <td>{n.ux.toPrecision(6)}</td>
                              <td>{n.uy.toPrecision(6)}</td>
                              <td>{n.uz.toPrecision(6)}</td>
                              <td>{n.magnitude.toPrecision(6)}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <>
                  {dialog !== "mesh" && renderInput("Name:", "name")}
                  {dialog === "material" && (
                    <>
                      <div className="abq-dialog-tabs">
                        <span className="active">Mechanical</span>
                        <span>General</span>
                        <span>Thermal</span>
                      </div>
                      <fieldset>
                        <legend>Elastic → Isotropic</legend>
                        {renderInput("Young’s modulus:", "elastic", "number")}
                        {renderInput("Poisson’s ratio:", "poisson", "number")}
                      </fieldset>
                      <fieldset>
                        <legend>Density</legend>
                        {renderInput("Mass density:", "density", "number")}
                      </fieldset>
                      <p className="abq-form-note">
                        Enter values in a consistent unit system. These are
                        editable draft definitions; no material identification
                        has run.
                      </p>
                    </>
                  )}
                  {dialog === "bc" && (
                    <>
                      <label className="abq-form-row">
                        <span>Type:</span>
                        <select>
                          <option>Displacement / Rotation</option>
                        </select>
                      </label>
                      <label className="abq-form-row">
                        <span>Region:</span>
                        <select
                          value={form.region || ""}
                          onChange={(e) =>
                            setForm((p) => ({ ...p, region: e.target.value }))
                          }
                        >
                          <option value="">Select region</option>
                          {selected.length > 1 && (
                            <option value={selected.join(",")}>
                              {selected.length} selected instances
                            </option>
                          )}
                          {components.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                          {form.region.includes(",") && (
                            <option value={form.region}>
                              Saved region group
                            </option>
                          )}
                        </select>
                      </label>
                      <fieldset>
                        <legend>Displacement</legend>
                        {renderInput("U1:", "ux", "number")}
                        {renderInput("U2:", "uy", "number")}
                        {renderInput("U3:", "uz", "number")}
                      </fieldset>
                      <p className="abq-form-note">
                        Blank component = unconstrained. Stored for the selected
                        instance(s); no response is computed.
                      </p>
                    </>
                  )}
                  {dialog === "mesh" && (
                    <>
                      <fieldset>
                        <legend>Global seeds</legend>
                        {renderInput(
                          "Approximate global size:",
                          "size",
                          "number",
                        )}
                      </fieldset>
                      <label className="abq-form-row">
                        <span>Technique:</span>
                        <select
                          value={form.technique}
                          onChange={(e) =>
                            setForm((p) => ({
                              ...p,
                              technique: e.target.value,
                            }))
                          }
                        >
                          <option>Free</option>
                          <option>Structured</option>
                          <option>Sweep</option>
                        </select>
                      </label>
                      <label className="abq-form-row">
                        <span>Element type:</span>
                        <select
                          value={form.element}
                          onChange={(e) =>
                            setForm((p) => ({ ...p, element: e.target.value }))
                          }
                        >
                          <option>C3D4</option>
                          <option>C3D10</option>
                          <option>C3D8R</option>
                        </select>
                      </label>
                      <p className="abq-form-note">
                        Stores meshing intent. Display uses existing
                        tessellation; changing seeds does not generate a new
                        finite-element mesh.
                      </p>
                    </>
                  )}
                  {dialog === "step" && (
                    <>
                      <label className="abq-form-row">
                        <span>Procedure:</span>
                        <select>
                          <option>Static, General (draft)</option>
                        </select>
                      </label>
                      <p className="abq-form-note">
                        Draft step name only. Native procedure settings and time
                        integration are not connected.
                      </p>
                    </>
                  )}
                  {dialog === "interaction" && (
                    <>
                      <label className="abq-form-row">
                        <span>Type:</span>
                        <select>
                          <option>Surface-to-surface contact (draft)</option>
                        </select>
                      </label>
                      <p className="abq-form-note">
                        A named draft. Native surface pairing and contact
                        evaluation are not connected.
                      </p>
                    </>
                  )}
                  {dialog === "job" && (
                    <>
                      <label className="abq-form-row">
                        <span>Model:</span>
                        <select>
                          <option>Model-1</option>
                        </select>
                      </label>
                      <label className="abq-form-row">
                        <span>Analysis:</span>
                        <select>
                          <option>Abaqus/Standard (draft)</option>
                        </select>
                      </label>
                      <p className="abq-form-note">
                        Creates a job draft. Submit explains the missing solver
                        connection; no completed job will be fabricated.
                      </p>
                    </>
                  )}
                  {formError && (
                    <div className="abq-form-error" role="alert">
                      {formError}
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="abq-dialog-buttons">
              {dialog === "info" || dialog === "xy" ? (
                <button onClick={() => setDialog(null)}>Close</button>
              ) : (
                <>
                  <button onClick={() => setDialog(null)}>Cancel</button>
                  <button
                    className="primary"
                    onClick={() =>
                      dialog === "new"
                        ? (commit(emptyDraft, "Draft definitions cleared."),
                          setHidden([]),
                          setSelected([]),
                          setDataset("assembly"),
                          setModule("Assembly"),
                          setTreeTab("Model"),
                          setExplode(0),
                          setClip((p) => ({ ...p, enabled: false })),
                          setDialog(null),
                          command("fit"))
                        : applyDefinition()
                    }
                  >
                    OK
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
