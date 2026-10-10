import { useEffect, useRef, useState, type ReactNode } from "react";
import { AgGridReact } from "ag-grid-react";
import {
  AllCommunityModule,
  ModuleRegistry,
  themeQuartz,
} from "ag-grid-community";
import Plotly from "plotly.js-basic-dist-min";
import {
  Box,
  ChevronDown,
  ChevronRight,
  Eye,
  EyeOff,
  FolderOpen,
  Save,
  Undo2,
  Redo2,
  Search,
  X,
  Plus,
  Circle,
  ArrowUp,
  Maximize,
  Grid3X3,
  Move3D,
  Scissors,
  Target,
  Layers,
  Ruler,
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Check,
  Settings,
  FileText,
  Play,
  Crosshair,
  PanelLeftClose,
} from "lucide-react";
import { Scene } from "./Scene";
import {
  components,
  resultNodes,
  resultInfo,
  assemblyBounds,
  componentBounds,
  resultBounds,
} from "./model";
import "./HyperMesh.css";

ModuleRegistry.registerModules([AllCommunityModule]);
type NodeData = {
  id: number;
  x: number;
  y: number;
  z: number;
  ux: number;
  uy: number;
  uz: number;
  magnitude: number;
};
type Material = {
  id: string;
  name: string;
  E: number;
  nu: number;
  density: number;
  unit: string;
};
type Condition = {
  id: string;
  name: string;
  entities: string[];
  kind: string;
  direction: string;
  value: number;
  unit: string;
};
type Study = {
  format: "hypermesh-browser-study-1";
  name: string;
  dataset: "assembly" | "result";
  selected: string[];
  hidden: string[];
  names: Record<string, string>;
  assignments: Record<string, string>;
  materials: Material[];
  conditions: Condition[];
  representation: "shaded" | "edges" | "wireframe" | "transparent";
  explode: number;
  clip: { enabled: boolean; axis: "x" | "y" | "z"; position: number };
  field: "none" | "magnitude" | "ux" | "uy" | "uz";
  deformation: number;
  showLoads: boolean;
};
type Panel =
  | "properties"
  | "material"
  | "condition"
  | "measure"
  | "mesh"
  | "validate"
  | "solver"
  | "section"
  | "display";
type Command = { name: string; action: string; color?: string; shape?: number };
type Group = { title: string; commands: Command[] };
const key = "hypermesh-browser-study-1";
const fresh = (): Study => ({
  format: key,
  name: "CAE assembly",
  dataset: "assembly",
  selected: [],
  hidden: [],
  names: {},
  assignments: {},
  materials: [],
  conditions: [],
  representation: "edges",
  explode: 0,
  clip: { enabled: false, axis: "x", position: 0.5 },
  field: "none",
  deformation: 0,
  showLoads: false,
});
const stringMap = (value: unknown): value is Record<string, string> =>
  value !== null &&
  typeof value === "object" &&
  !Array.isArray(value) &&
  Object.values(value).every((item) => typeof item === "string");
const sourceIds = new Set([...components.map((c) => c.id), "result-support"]);
const entityIds = (value: unknown): value is string[] =>
  Array.isArray(value) &&
  value.every((id) => typeof id === "string" && sourceIds.has(id)) &&
  new Set(value).size === value.length;
const validMaterial = (m: any): m is Material =>
  m &&
  typeof m.id === "string" &&
  m.id.length > 0 &&
  typeof m.name === "string" &&
  m.name.trim().length > 0 &&
  typeof m.unit === "string" &&
  m.unit.trim().length > 0 &&
  Number.isFinite(m.E) &&
  m.E > 0 &&
  Number.isFinite(m.nu) &&
  m.nu > -1 &&
  m.nu < 0.5 &&
  Number.isFinite(m.density) &&
  m.density >= 0;
const validCondition = (c: any): c is Condition =>
  c &&
  typeof c.id === "string" &&
  c.id.length > 0 &&
  typeof c.name === "string" &&
  c.name.trim().length > 0 &&
  typeof c.unit === "string" &&
  c.unit.trim().length > 0 &&
  entityIds(c.entities) &&
  c.entities.length > 0 &&
  ["Displacement", "Force", "Constraint"].includes(c.kind) &&
  ["ux", "uy", "uz"].includes(c.direction) &&
  Number.isFinite(c.value);
const isStudy = (v: any): v is Study =>
  v?.format === key &&
  ["assembly", "result"].includes(v.dataset) &&
  typeof v.name === "string" &&
  entityIds(v.selected) &&
  entityIds(v.hidden) &&
  Array.isArray(v.materials) &&
  v.materials.every(validMaterial) &&
  new Set(v.materials.map((m: Material) => m.id)).size === v.materials.length &&
  Array.isArray(v.conditions) &&
  v.conditions.every(validCondition) &&
  new Set(v.conditions.map((c: Condition) => c.id)).size ===
    v.conditions.length &&
  stringMap(v.names) &&
  Object.keys(v.names).every((id) => sourceIds.has(id)) &&
  stringMap(v.assignments) &&
  Object.entries(v.assignments).every(
    ([id, material]) =>
      sourceIds.has(id) &&
      (material === "" || v.materials.some((m: Material) => m.id === material)),
  ) &&
  typeof v.showLoads === "boolean" &&
  ["shaded", "edges", "wireframe", "transparent"].includes(v.representation) &&
  ["none", "magnitude", "ux", "uy", "uz"].includes(v.field) &&
  Number.isFinite(v.explode) &&
  v.explode >= 0 &&
  v.explode <= 1 &&
  Number.isFinite(v.deformation) &&
  v.deformation >= 0 &&
  v.deformation <= 10000 &&
  v.clip &&
  typeof v.clip.enabled === "boolean" &&
  ["x", "y", "z"].includes(v.clip.axis) &&
  Number.isFinite(v.clip.position) &&
  v.clip.position >= 0 &&
  v.clip.position <= 1;
const load = () => {
  try {
    const parsed = JSON.parse(localStorage.getItem(key) || "null");
    return isStudy(parsed) ? parsed : fresh();
  } catch {
    return fresh();
  }
};
const tabs = [
  "Sketch",
  "Topology",
  "1D",
  "2D",
  "3D",
  "Assembly",
  "Connectors",
  "Morph",
  "Model",
  "Validate",
  "Analyze",
  "Skeleton",
  "Design Space",
  "Optimize",
  "Design Explorer",
  "Post",
  "Report",
  "Developer",
  "PhysicsAI",
  "Custom",
];
const command = (
  name: string,
  action: string,
  color = "#849080",
  shape = 0,
): Command => ({ name, action, color, shape });
const groups: Record<string, Group[]> = {
  Model: [
    {
      title: "Home",
      commands: [
        command("Files", "open", "#ae9f73"),
        command("Measure", "measure", "#879692", 2),
        command("Move", "move", "#c27d54", 3),
      ],
    },
    {
      title: "Organize",
      commands: [
        command("Organize", "properties", "#909079"),
        command("Libraries", "material", "#ae6f5a", 1),
        command("Renumber", "renumber", "#cc7560", 1),
        command("ID Manager", "ids", "#829292"),
      ],
    },
    {
      title: "AI/ML",
      commands: [
        command("Match", "unsupported", "#9e7767", 1),
        command("Classify", "unsupported", "#9e7669"),
      ],
    },
    {
      title: "Manage",
      commands: [
        command("Parts", "properties", "#86909d"),
        command("Subsystems", "properties", "#b46b58", 1),
        command("Mechanism", "unsupported", "#989b9b", 2),
      ],
    },
    {
      title: "Build",
      commands: [
        command("Reps", "display", "#a16b63", 1),
        command("Controls", "mesh", "#ac6857", 1),
        command("Scenario", "condition", "#9b9c9b", 3),
        command("Model Update", "open", "#a77d68", 1),
      ],
    },
    {
      title: "Compare",
      commands: [
        command("Verification", "validate", "#929b88"),
        command("Comparison", "result", "#b87e64", 1),
      ],
    },
  ],
  Sketch: [
    {
      title: "Create",
      commands: [
        command("Points", "sketch", "#b08059", 3),
        command("Lines", "sketch", "#b08059", 3),
        command("Circles", "sketch", "#b08059", 2),
      ],
    },
    {
      title: "Tools",
      commands: [
        command("Measure", "measure", "#8d9d88", 2),
        command("Constraints", "condition", "#ab6c64"),
      ],
    },
  ],
  Topology: [
    {
      title: "Geometry",
      commands: [
        command("Inspect", "properties", "#a09c84"),
        command("Cleanup", "topology", "#a3847b"),
        command("Edges", "edges", "#779196"),
        command("Surfaces", "shaded", "#939f81"),
      ],
    },
    {
      title: "Tools",
      commands: [
        command("Measure", "measure", "#8d9d88", 2),
        command("Section", "section", "#c58257", 3),
      ],
    },
  ],
  "1D": [
    {
      title: "Elements",
      commands: [
        command("Bars", "remesh", "#a17b5f", 3),
        command("Beams", "remesh", "#a17b5f", 3),
      ],
    },
    {
      title: "Review",
      commands: [
        command("Properties", "properties"),
        command("Quality", "validate", "#a29b70"),
      ],
    },
  ],
  "2D": [
    {
      title: "Mesh",
      commands: [
        command("Surface Mesh", "remesh", "#ae9a7b"),
        command("Automesh", "remesh", "#a57b60", 1),
        command("Map", "remesh", "#8b988e"),
      ],
    },
    {
      title: "Edit",
      commands: [
        command("Element Edit", "remesh", "#a27c65", 1),
        command("Quality", "validate", "#9fa576"),
        command("Edges", "edges", "#829492"),
      ],
    },
    {
      title: "Properties",
      commands: [
        command("Materials", "material", "#ab7360"),
        command("Thickness", "properties", "#849695"),
      ],
    },
  ],
  "3D": [
    {
      title: "Mesh",
      commands: [
        command("Tetra Mesh", "remesh", "#9b937a"),
        command("Hex Mesh", "remesh", "#849693"),
        command("Solid Map", "remesh", "#b2836c", 1),
      ],
    },
    {
      title: "Display",
      commands: [
        command("Wireframe", "wireframe", "#80999e"),
        command("Section", "section", "#c68560", 3),
      ],
    },
    {
      title: "Review",
      commands: [
        command("Quality", "validate", "#9c9d75"),
        command("Nodes", "query", "#8a9693", 3),
      ],
    },
  ],
  Assembly: [
    {
      title: "Assembly",
      commands: [
        command("Components", "properties", "#9b967d"),
        command("Explode", "explode", "#ad7e66", 1),
        command("Show All", "showall", "#8c9d81"),
        command("Isolate", "isolate", "#a0a484"),
      ],
    },
    {
      title: "Connections",
      commands: [
        command("Connections", "condition", "#b37d64", 3),
        command("Measure", "measure", "#8d9d88", 2),
      ],
    },
  ],
  Connectors: [
    {
      title: "Connectors",
      commands: [
        command("Create", "connector", "#a28679", 3),
        command("Realize", "connector", "#899c95"),
        command("Review", "condition", "#9d8f76"),
      ],
    },
  ],
  Morph: [
    {
      title: "Morph",
      commands: [
        command("Domains", "morph", "#a9a083"),
        command("Handles", "morph", "#bb8068", 3),
        command("Freehand", "morph", "#80908c"),
      ],
    },
  ],
  Validate: [
    {
      title: "Checks",
      commands: [
        command("Model Checker", "validate", "#8f9e7b"),
        command("Mesh Quality", "validate", "#a9946d"),
        command("Entity Review", "properties", "#89979a"),
      ],
    },
    {
      title: "Inspect",
      commands: [
        command("Measure", "measure", "#8d9d88", 2),
        command("Node Query", "query", "#93998b", 3),
      ],
    },
  ],
  Analyze: [
    {
      title: "Analysis",
      commands: [
        command("Materials", "material", "#a37160"),
        command("Load Collectors", "condition", "#bf765b", 3),
        command("Boundary", "condition", "#8a9796"),
      ],
    },
    {
      title: "Run",
      commands: [
        command("Solver", "solver", "#919a88"),
        command("Run", "solver", "#b88b72", 1),
      ],
    },
  ],
  "Design Explorer": [
    {
      title: "Study",
      commands: [
        command("Design Variables", "explorer", "#9c9b79"),
        command("Responses", "result", "#9a8578"),
        command("Evaluate", "solver", "#ae785f", 1),
      ],
    },
  ],
  Post: [
    {
      title: "Results",
      commands: [
        command("Load Results", "result", "#ad9b73"),
        command("Contour", "contour", "#947b9d", 1),
        command("Deformed", "deform", "#8d9d81"),
        command("Query", "query", "#92998d", 3),
      ],
    },
    {
      title: "Display",
      commands: [
        command("Section", "section", "#c48359", 3),
        command("Table / Plot", "table", "#9b9285"),
        command("Undeformed", "undeform", "#859497"),
      ],
    },
  ],
  Report: [
    {
      title: "Export",
      commands: [
        command("Save Study", "save", "#a08262"),
        command("Node Data", "exportnodes", "#85938f"),
      ],
    },
  ],
};
const defaultGroups: Group[] = [
  {
    title: "Tools",
    commands: [
      command("Entity Review", "properties"),
      command("Display", "display"),
      command("Model Checker", "validate", "#939d7e"),
      command("Not Connected", "unsupported", "#a88b7c"),
    ],
  },
];
function Glyph({
  name,
  color = "#9b9786",
  shape = 0,
}: {
  name: string;
  color?: string;
  shape?: number;
}) {
  const icons: Record<string, ReactNode> = {
    Files: (
      <>
        <path d="M10 4h19l5 6v23H10z" fill="#edece1" />
        <path d="M6 12h12l4 4h15l-4 19H4z" fill="#b9a66f" />
        <path d="M11 21h19M10 26h17" fill="none" />
      </>
    ),
    Measure: (
      <>
        <path d="m6 28 25-21 6 7-25 21z" fill="#d6c99f" />
        <path d="m12 25 3 4m2-8 3 4m2-8 3 4m2-8 3 4" fill="none" />
        <path d="M4 11h12M4 7v8M16 7v8" stroke="#ae5c4c" />
      </>
    ),
    Move: (
      <>
        <path d="M20 21V5m0 16 15 9M20 21 6 28" fill="none" strokeWidth="3" />
        <path d="m20 3-4 7h8zM38 32l-4-8-4 7zM3 30l9 1-4-7z" fill="#b56951" />
        <circle cx="20" cy="21" r="4" fill="#d7ceac" />
      </>
    ),
    Organize: (
      <>
        <path d="M20 12v8H7v7m13-7h14v7" fill="none" strokeWidth="2" />
        <rect x="13" y="3" width="15" height="10" fill="#c1b68d" />
        <rect x="2" y="27" width="12" height="10" fill="#9cb1aa" />
        <rect x="27" y="27" width="12" height="10" fill="#b47f6a" />
      </>
    ),
    Libraries: (
      <>
        <path d="M4 10 20 3l17 8M5 34h32" fill="none" strokeWidth="2" />
        <path d="M7 12v20h6V12z" fill="#ad7568" />
        <path d="M16 9v23h6V9z" fill="#a5a783" />
        <path d="m26 11 6-2 6 21-6 2z" fill="#899eac" />
      </>
    ),
    Renumber: (
      <>
        <rect x="3" y="5" width="22" height="17" rx="1" fill="#e0d8bd" />
        <rect x="16" y="20" width="23" height="16" rx="1" fill="#a2b6b1" />
        <path d="M7 24v9h5" fill="none" stroke="#b35d4b" strokeWidth="2" />
        <text x="8" y="18" stroke="none" fill="#5c625c" fontSize="11">
          12
        </text>
        <text x="20" y="32" stroke="none" fill="#354d54" fontSize="11">
          34
        </text>
      </>
    ),
    "ID Manager": (
      <>
        <rect x="5" y="5" width="31" height="31" fill="#e6e4d9" />
        <path d="M5 5h31v7H5z" fill="#8da0a4" />
        <text
          x="10"
          y="29"
          stroke="none"
          fill="#687c84"
          fontSize="16"
          fontWeight="bold"
        >
          ID
        </text>
      </>
    ),
    Match: (
      <>
        <path d="M3 9h13v8h7v14H3z" fill="#b87d6b" />
        <path d="M38 9H25v8h-7v14h20z" fill="#b3b497" />
        <path d="M10 35h23m-3-3 4 3-4 3" fill="none" stroke="#777f7a" />
      </>
    ),
    Classify: (
      <>
        <circle cx="10" cy="11" r="7" fill="#ba8d71" />
        <rect x="23" y="4" width="14" height="14" fill="#9caeae" />
        <path d="m11 23 8 14H3z" fill="#a1ad89" />
        <circle cx="30" cy="29" r="7" fill="#b9a684" />
        <path d="M20 2v36M2 21h38" stroke="#9ba6a5" strokeDasharray="2 2" />
      </>
    ),
    Parts: (
      <>
        <path d="m4 12 17-8 17 8-17 8z" fill="#ccd1c5" />
        <path d="M4 12v20l17 6V20z" fill="#899ba9" />
        <path d="m21 20 17-8v20l-17 6z" fill="#657782" />
        <path d="m16 17 8-4 7 4-7 4z" fill="#eff0e6" />
        <path d="M24 21v10l7-3V17" fill="#c5c6ba" />
      </>
    ),
    Subsystems: (
      <>
        <path d="M20 9v20M8 20h25" fill="none" strokeWidth="2" />
        <path
          d="m14 3 7-3 7 4-7 4zM14 3v8l7 4V8M21 8l7-4v8l-7 3"
          fill="#aab49c"
        />
        <rect x="2" y="24" width="13" height="12" fill="#b78272" />
        <rect x="27" y="24" width="13" height="12" fill="#8fa4ae" />
      </>
    ),
    Mechanism: (
      <>
        <path
          d="M8 31 17 10l17 15"
          fill="none"
          stroke="#b18966"
          strokeWidth="6"
        />
        <circle cx="8" cy="31" r="5" fill="#9babb1" />
        <circle cx="17" cy="10" r="5" fill="#d2cec0" />
        <circle cx="34" cy="25" r="5" fill="#9babb1" />
        <path d="M2 38h15M27 32h13" strokeWidth="2" />
      </>
    ),
    Reps: (
      <>
        <path d="m4 27 17-8 17 8-17 9z" fill="#849393" />
        <path d="m4 19 17-8 17 8-17 9z" fill="#b08f7d" />
        <path d="m4 11 17-8 17 8-17 9z" fill="#d9d7be" />
      </>
    ),
    Controls: (
      <>
        <path d="M5 8h32M5 20h32M5 32h32" strokeWidth="2" />
        <rect x="11" y="3" width="6" height="10" fill="#b87768" />
        <rect x="27" y="15" width="6" height="10" fill="#a9b29d" />
        <rect x="15" y="27" width="6" height="10" fill="#8da7ad" />
      </>
    ),
    Scenario: (
      <>
        <path d="m3 27 17-7 18 8-17 8z" fill="#a1ac9d" />
        <path d="M12 2v20M29 2v20" stroke="#ba6954" strokeWidth="3" />
        <path d="m8 17 4 7 4-7m9 0 4 7 4-7" fill="#ba6954" stroke="#ba6954" />
        <path d="M6 34v4m8-2v4m13-5v4m8-7v5" />
      </>
    ),
    "Model Update": (
      <>
        <path
          d="m10 14 11-5 11 6-11 6zM10 14v14l11 6V21M21 21l11-6v14l-11 5"
          fill="#ae9c81"
        />
        <path
          d="M4 23C-1 8 16-1 29 4m8 13c7 14-9 25-22 20"
          fill="none"
          stroke="#80998e"
          strokeWidth="3"
        />
        <path d="m25 1 7 5-9 2M18 33l-7 3 6 4" fill="#80998e" />
      </>
    ),
    Verification: (
      <>
        <rect x="7" y="5" width="29" height="32" fill="#e4e1cf" />
        <rect x="14" y="2" width="14" height="6" fill="#98a397" />
        <path
          d="m11 23 6 6 14-15"
          fill="none"
          stroke="#688a70"
          strokeWidth="4"
        />
      </>
    ),
    Comparison: (
      <>
        <rect x="2" y="6" width="17" height="28" fill="#d4dcd9" />
        <rect x="23" y="6" width="17" height="28" fill="#e3d2bf" />
        <path d="m5 24 5-12 6 7m10 5 5-8 6 3" fill="none" strokeWidth="2" />
        <path d="M19 17h4m-4 8h4" stroke="#b16b51" strokeWidth="3" />
      </>
    ),
  };
  if (icons[name])
    return (
      <svg
        className="hm-ribbon-glyph"
        viewBox="0 0 42 40"
        fill="none"
        stroke="#687772"
        strokeWidth="1.15"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {icons[name]}
      </svg>
    );
  return (
    <svg className="hm-ribbon-glyph" viewBox="0 0 42 40">
      <defs>
        <linearGradient
          id={`hm-${color.replace("#", "")}-${shape}`}
          x2="1"
          y2="1"
        >
          <stop stopColor="#f6f6e9" />
          <stop offset="1" stopColor={color} />
        </linearGradient>
      </defs>
      {shape === 3 ? (
        <>
          <path
            d="M7 30 21 18 33 27"
            fill="none"
            stroke={color}
            strokeWidth="4"
          />
          <path
            d="M21 18V5M21 18 5 13M21 18 35 11"
            stroke="#697b78"
            strokeWidth="2"
          />
          <path d="m21 4-3 6h6zM3 13l6-2-2 6M37 10l-6-1 3 6" fill="#b35245" />
        </>
      ) : shape === 2 ? (
        <>
          <circle
            cx="20"
            cy="20"
            r="14"
            fill={`url(#hm-${color.replace("#", "")}-${shape})`}
            stroke="#6c787b"
            strokeWidth="2"
          />
          <circle cx="20" cy="20" r="6" fill="#fafafa" stroke="#89948f" />
          <path d="M7 30 34 4" stroke="#b35044" strokeWidth="3" />
        </>
      ) : (
        <>
          <path
            d="m6 11 17-7 14 8-17 7z"
            fill={`url(#hm-${color.replace("#", "")}-${shape})`}
            stroke="#6f7771"
          />
          <path d="M6 11v20l14 7V19z" fill={color} stroke="#626e68" />
          <path d="M20 19 37 12v19l-17 7z" fill="#67726d" stroke="#606b65" />
          {shape === 1 ? (
            <>
              <path
                d="m11 9 5-2v27l-5-3zM26 9l5 2v24l-5 2z"
                fill="#b24f46"
                stroke="#f6c7b4"
                strokeWidth=".4"
              />
            </>
          ) : (
            <path d="m13 17 5 2v9l-5-2zM24 21l7-3v9l-7 3z" fill="#d6d8cc" />
          )}
        </>
      )}
    </svg>
  );
}
function Label({ title, children }: { title: string; children: ReactNode }) {
  return (
    <label className="hm-field">
      <span>{title}</span>
      {children}
    </label>
  );
}
const gridTheme = themeQuartz.withParams({
  fontFamily: "Arial,Segoe UI,sans-serif",
  fontSize: 11,
  rowHeight: 25,
  headerHeight: 28,
  headerFontSize: 11,
  headerBackgroundColor: "#edf0f2",
  accentColor: "#1b75a1",
  selectedRowBackgroundColor: "#c9e8f6",
  wrapperBorderRadius: 0,
  cellHorizontalPadding: 6,
});
function NodePlot({
  selected,
  onSelect,
}: {
  selected: NodeData | null;
  onSelect: (node: NodeData) => void;
}) {
  const ref = useRef<HTMLDivElement>(null),
    callback = useRef(onSelect);
  callback.current = onSelect;
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const data: any[] = [
      {
        x: resultNodes.map((n) => n.x),
        y: resultNodes.map((n) => n.uz),
        customdata: resultNodes.map((n) => n.id),
        type: "scatter",
        mode: "markers",
        marker: { size: 3, color: "#2275a2" },
        name: "Retained nodes",
        hovertemplate:
          "Node %{customdata}<br>x %{x:.6g}<br>Uz %{y:.6g}<extra></extra>",
      },
    ];
    if (selected)
      data.push({
        x: [selected.x],
        y: [selected.uz],
        customdata: [selected.id],
        type: "scatter",
        mode: "markers",
        marker: { size: 11, color: "#d47922" },
        name: "Selected",
      });
    Plotly.react(
      node,
      data,
      {
        paper_bgcolor: "#fff",
        plot_bgcolor: "#fff",
        font: { family: "Arial", size: 10 },
        margin: { l: 57, r: 12, t: 17, b: 37 },
        xaxis: {
          title: { text: "x · retained coordinate" },
          gridcolor: "#e0e4e7",
        },
        yaxis: {
          title: { text: `Uz [${resultInfo.unit}]` },
          gridcolor: "#e0e4e7",
        },
        showlegend: false,
        uirevision: "node-profile",
      },
      { displayModeBar: false, responsive: true },
    );
  }, [selected]);
  useEffect(() => {
    const node = ref.current as any;
    if (!node) return;
    const click = (e: any) => {
      const found = resultNodes.find(
        (n) => n.id === Number(e.points?.[0]?.customdata),
      );
      if (found) callback.current(found);
    };
    node.on("plotly_click", click);
    const observer = new ResizeObserver(() => Plotly.Plots.resize(node));
    observer.observe(node);
    return () => {
      observer.disconnect();
      node.removeListener("plotly_click", click);
      Plotly.purge(node);
    };
  }, []);
  return <div ref={ref} className="hm-node-plot" />;
}

export default function HyperMesh() {
  const [study, setStudy] = useState<Study>(load),
    [tab, setTab] = useState("Model"),
    [panel, setPanel] = useState<Panel>("properties"),
    [search, setSearch] = useState(""),
    [filter, setFilter] = useState("All"),
    [menu, setMenu] = useState<string | null>(null),
    [browserWidth, setBrowserWidth] = useState(254),
    [browserHeight, setBrowserHeight] = useState(320),
    [resultsOpen, setResultsOpen] = useState(false),
    [node, setNode] = useState<NodeData | null>(null),
    [nodeId, setNodeId] = useState(""),
    [probeMode, setProbeMode] = useState(false),
    [message, setMessage] = useState("Ready"),
    [validation, setValidation] = useState<string[]>([]),
    [closedGroups, setClosedGroups] = useState<string[]>([]),
    [guide, setGuide] = useState(""),
    [definitionTargets, setDefinitionTargets] = useState<string[]>([]),
    [materialDraft, setMaterialDraft] = useState<Material>({
      id: "",
      name: "Material",
      E: 210000,
      nu: 0.3,
      density: 7.85e-9,
      unit: "MPa",
    }),
    [conditionDraft, setConditionDraft] = useState<Condition>({
      id: "",
      name: "Boundary",
      entities: [],
      kind: "Displacement",
      direction: "uz",
      value: 0,
      unit: "mm",
    }),
    [camera, setCamera] = useState<{
      name: "fit" | "iso" | "front" | "top" | "right" | "zoomIn" | "zoomOut";
      tick: number;
    }>({ name: "iso", tick: 0 }),
    [historyCount, setHistoryCount] = useState(0);
  const undo = useRef<Study[]>([]),
    redo = useRef<Study[]>([]),
    inputRef = useRef<HTMLInputElement>(null),
    gridApi = useRef<any>(null);
  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(study));
    } catch {
      setMessage("Local storage unavailable. Save Study to keep changes.");
    }
  }, [study]);
  const change = (update: (previous: Study) => Study) =>
    setStudy((previous) => {
      const next = update(previous);
      if (JSON.stringify(next) === JSON.stringify(previous)) return previous;
      undo.current.push(previous);
      redo.current = [];
      setHistoryCount((c) => c + 1);
      return next;
    });
  const undoChange = () => {
    const previous = undo.current.pop();
    if (previous) {
      redo.current.push(study);
      setStudy(previous);
      setHistoryCount((c) => c + 1);
      setMessage("Undo");
    }
  };
  const redoChange = () => {
    const next = redo.current.pop();
    if (next) {
      undo.current.push(study);
      setStudy(next);
      setHistoryCount((c) => c + 1);
      setMessage("Redo");
    }
  };
  const view = (name: typeof camera.name) =>
    setCamera((previous) => ({ name, tick: previous.tick + 1 }));
  const select = (id: string, additive = false) => {
    if (!id) {
      change((s) => ({ ...s, selected: [] }));
      setMessage("Selection cleared");
      return;
    }
    change((previous) => ({
      ...previous,
      selected: additive
        ? previous.selected.includes(id)
          ? previous.selected.filter((s) => s !== id)
          : [...previous.selected, id]
        : [id],
    }));
    if (panel !== "material" && panel !== "condition") setPanel("properties");
    setMessage(`Selected ${id}`);
  };
  const allIds =
    study.dataset === "assembly"
      ? components.map((c) => c.id)
      : ["result-support"];
  const entities =
    study.dataset === "assembly"
      ? components
      : [
          {
            id: "result-support",
            name: "Retained support mesh",
            color: "#80999a",
            kind: "retained finite element result",
            faces: 0,
            triangles: 0,
          },
        ];
  const selectedEntity = entities.find((c) => c.id === study.selected[0]);
  const switchDataset = (dataset: Study["dataset"]) => {
    if(dataset === study.dataset) return;
    change((previous) => ({
      ...previous,
      dataset,
      selected: [],
      hidden: [],
      field: dataset === "result" ? "magnitude" : "none",
      explode: 0,
    }));
    setNode(null);
    setMessage(
      dataset === "result"
        ? "Retained support only. Assembly components are not this result source."
        : "Assembly tessellation loaded.",
    );
    view("fit");
  };
  const download = (name: string, text: string, type = "application/json") => {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const save = () => {
    download(
      `${study.name.replace(/[^a-zA-Z0-9_-]/g, "_") || "study"}.hmstudy.json`,
      JSON.stringify(study, null, 2),
    );
    setMessage(
      "Browser study saved. Original model/result files are unchanged.",
    );
  };
  const open = async (file: File) => {
    try {
      const data = JSON.parse(await file.text());
      if (!isStudy(data)) throw Error("Not a valid HyperMesh browser study.");
      const allowed = new Set([
        ...components.map((c) => c.id),
        "result-support",
      ]);
      if ([...data.selected, ...data.hidden].some((id) => !allowed.has(id)))
        throw Error("The study references an unavailable component.");
      change(() => data);
      setPanel("properties");
      setDefinitionTargets([]);
      setNode(null);
      setNodeId("");
      setGuide("");
      setProbeMode(false);
      setMessage(`Opened ${file.name}`);
      view("fit");
    } catch (e) {
      setMessage(`Open failed: ${(e as Error).message}`);
      setGuide(`Open failed: ${(e as Error).message}`);
    }
  };
  const showPanel = (next: Panel, title: string) => {
    setPanel(next);
    setGuide(title);
    setMessage(title);
  };
  const validate = () => {
    const finite = resultNodes.filter((n) =>
      [n.x, n.y, n.z, n.ux, n.uy, n.uz, n.magnitude].every(Number.isFinite),
    ).length;
    const rows =
      study.dataset === "assembly"
        ? [
            `Available components: ${components.length}`,
            `Rendered triangles: ${components.reduce((s, c) => s + c.triangles, 0).toLocaleString()}`,
            `Available face metadata: ${components.reduce((s, c) => s + c.faces, 0).toLocaleString()}`,
          ]
        : [
            `Retained nodes: ${resultNodes.length.toLocaleString()} (declared ${resultInfo.nodes.toLocaleString()})`,
            `Elements: ${resultInfo.elements.toLocaleString()} retained metadata`,
            `Finite coordinate/displacement rows: ${finite.toLocaleString()} / ${resultNodes.length.toLocaleString()}`,
          ];
    setValidation([
      ...rows,
      `Missing material assignments: ${entities.filter((c) => !study.assignments[c.id]).length}`,
      `Local condition definitions: ${study.conditions.length}`,
      "Jacobian, aspect ratio, manifold and solver checks require the native engine; not evaluated.",
    ]);
    showPanel("validate", "Model checker · checks available data only");
  };
  const runCommand = (action: string, label = action) => {
    setMenu(null);
    if (
      ["fit", "iso", "front", "top", "right", "zoomIn", "zoomOut"].includes(
        action,
      )
    ) {
      view(action as typeof camera.name);
      return;
    }
    if (action === "open") {
      inputRef.current?.click();
      return;
    }
    if (action === "save") {
      save();
      return;
    }
    if (action === "undo") {
      undoChange();
      return;
    }
    if (action === "redo") {
      redoChange();
      return;
    }
    if (action === "new") {
      change(() => fresh());
      setPanel("properties");
      setDefinitionTargets([]);
      setNode(null);
      setNodeId("");
      setProbeMode(false);
      setResultsOpen(false);
      setSearch("");
      setFilter("All");
      setTab("Model");
      setClosedGroups([]);
      view("fit");
      setGuide(
        "New browser study. The local geometry and retained result stay available.",
      );
      return;
    }
    if (action === "showall") {
      change((s) => ({ ...s, hidden: [] }));
      setMessage("All entities shown");
      return;
    }
    if (action === "hide") {
      change((s) => ({
        ...s,
        hidden: [...new Set([...s.hidden, ...s.selected])],
      }));
      setMessage(`${study.selected.length} selected entities hidden`);
      return;
    }
    if (action === "isolate") {
      if (!study.selected.length) {
        setGuide("Select one or more components to isolate.");
        return;
      }
      change((s) => ({
        ...s,
        hidden: allIds.filter((id) => !s.selected.includes(id)),
      }));
      setMessage("Selected components isolated");
      return;
    }
    if (action === "explode") {
      change((s) => ({ ...s, explode: s.explode ? 0 : 0.35 }));
      showPanel("display", "Exploded display · source geometry is preserved");
      return;
    }
    if (["wireframe", "edges", "shaded", "transparent"].includes(action)) {
      change((s) => ({
        ...s,
        representation: action as Study["representation"],
      }));
      return;
    }
    if (
      action === "result" ||
      action === "contour" ||
      action === "deform" ||
      action === "undeform"
    ) {
      switchDataset("result");
      if (action === "deform") change((s) => ({ ...s, deformation: 50 }));
      if (action === "undeform") change((s) => ({ ...s, deformation: 0 }));
      setResultsOpen(true);
      showPanel("display", "Post · retained displacement result");
      return;
    }
    if (action === "table") {
      switchDataset("result");
      setResultsOpen(true);
      setMessage(
        "Exact retained node values; spatial profile, not a time history.",
      );
      return;
    }
    if (action === "query") {
      switchDataset("result");
      setProbeMode(true);
      setResultsOpen(true);
      showPanel(
        "properties",
        "Query nodes · click the mesh or enter an exact node ID",
      );
      return;
    }
    if (action === "validate") {
      validate();
      return;
    }
    if (action === "exportnodes") {
      download(
        "retained-support-nodes.csv",
        "id,x,y,z,ux,uy,uz,magnitude\n" +
          resultNodes
            .map((n) =>
              [n.id, n.x, n.y, n.z, n.ux, n.uy, n.uz, n.magnitude].join(","),
            )
            .join("\n"),
        "text/csv",
      );
      setMessage("Retained node values exported without resampling.");
      return;
    }
    if (action === "section") {
      showPanel("section", "Section plane · clips displayed geometry");
      return;
    }
    if (action === "material") {
      setMaterialDraft({
        id: "",
        name: `Material-${study.materials.length + 1}`,
        E: 210000,
        nu: 0.3,
        density: 7.85e-9,
        unit: "MPa",
      });
      setDefinitionTargets([...study.selected]);
      showPanel("material", "New material definition · browser study only");
      return;
    }
    if (action === "condition") {
      setConditionDraft({
        id: "",
        name: `Boundary-${study.conditions.length + 1}`,
        entities: [...study.selected],
        kind: "Displacement",
        direction: "uz",
        value: 0,
        unit: "mm",
      });
      setDefinitionTargets([...study.selected]);
      showPanel(
        "condition",
        "New boundary / load definition · browser study only",
      );
      return;
    }
    if (action === "measure") {
      showPanel("measure", "Measure available retained coordinates");
      return;
    }
    if (action === "display" || action === "properties" || action === "mesh") {
      showPanel(action as Panel, `${label} · entity editor`);
      return;
    }
    if (action === "ids") {
      showPanel(
        "properties",
        "Available IDs are retained source IDs. They are not renumbered.",
      );
      return;
    }
    const missing: Record<string, string> = {
      remesh:
        "Native meshing engine is not connected. No elements have been created or modified.",
      solver:
        "Commercial/native solver execution is not connected. No job was submitted.",
      topology:
        "A CAD/topology kernel is not connected. Source tessellation remains unchanged.",
      move: "Geometry transformation is not connected. Use Explode for a reversible display displacement.",
      renumber:
        "Renumbering native entity IDs is not connected. Source IDs remain unchanged.",
      sketch:
        "Sketch geometry creation requires the native CAD kernel, which is not connected.",
      connector:
        "Connector realization requires native topology and solver cards, which are not connected.",
      morph:
        "Mesh morphing requires the native mesh engine, which is not connected.",
      explorer:
        "Design Explorer execution is not connected in this browser study. No samples or results were invented.",
    };
    showPanel(
      action === "solver" ? "solver" : "mesh",
      `${label}: ${missing[action] || "This native tool is not connected in the browser study."}`,
    );
  };
  const probe = (picked: NodeData) => {
    setNode(picked);
    setNodeId(String(picked.id));
    setResultsOpen(true);
    setMessage(
      `Node ${picked.id}: Uz ${picked.uz.toPrecision(7)} ${resultInfo.unit}`,
    );
  };
  useEffect(() => {
    if (!gridApi.current || !node) return;
    const row = gridApi.current.getRowNode(String(node.id));
    row?.setSelected(true);
    if (row) gridApi.current.ensureNodeVisible(row, "middle");
  }, [node]);
  const resize = (axis: "x" | "y", event: React.PointerEvent) => {
    event.preventDefault();
    const initial = axis === "x" ? browserWidth : browserHeight,
      origin = axis === "x" ? event.clientX : event.clientY;
    const move = (e: PointerEvent) => {
      const value = initial + (axis === "x" ? e.clientX : e.clientY) - origin;
      if (axis === "x") setBrowserWidth(Math.max(205, Math.min(440, value)));
      else
        setBrowserHeight(
          Math.max(170, Math.min(window.innerHeight - 330, value)),
        );
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end);
  };
  const bounds = resultNodes.reduce(
    (b, n) => ({
      low: [
        Math.min(b.low[0], n.x),
        Math.min(b.low[1], n.y),
        Math.min(b.low[2], n.z),
      ],
      high: [
        Math.max(b.high[0], n.x),
        Math.max(b.high[1], n.y),
        Math.max(b.high[2], n.z),
      ],
    }),
    {
      low: [Infinity, Infinity, Infinity],
      high: [-Infinity, -Infinity, -Infinity],
    },
  );
  const toggleGroup = (id: string) =>
    setClosedGroups((previous) =>
      previous.includes(id)
        ? previous.filter((i) => i !== id)
        : [...previous, id],
    );
  const measureBounds =
    study.dataset === "result"
      ? resultBounds
      : selectedEntity
        ? componentBounds[selectedEntity.id]
        : assemblyBounds;
  const propertyRows = selectedEntity
    ? [
        ["ID", selectedEntity.id],
        ["Name", study.names[selectedEntity.id] || selectedEntity.name],
        ["Type", selectedEntity.kind],
        ["Faces", String(selectedEntity.faces)],
        ["Triangles", String(selectedEntity.triangles)],
        [
          "Visibility",
          study.hidden.includes(selectedEntity.id) ? "Hidden" : "Displayed",
        ],
      ]
    : [["Selection", "None"]];
  const numberInput = (
    value: number,
    update: (number: number) => void,
    step = "any",
  ) => (
    <input
      type="number"
      step={step}
      value={value}
      onChange={(e) => {
        const v = Number(e.target.value);
        if (Number.isFinite(v)) update(v);
      }}
    />
  );
  const editor =
    panel === "material" ? (
      <>
        <div className="hm-editor-subtitle">
          {materialDraft.id ? "Edit material" : "New material"} · local
          definition
        </div>
        <button className="hm-action" onClick={() => runCommand("material")}>
          New material
        </button>
        <Label title="Name">
          <input
            value={materialDraft.name}
            onChange={(e) =>
              setMaterialDraft({ ...materialDraft, name: e.target.value })
            }
          />
        </Label>
        <Label title="Young's modulus">
          {numberInput(materialDraft.E, (v) =>
            setMaterialDraft({ ...materialDraft, E: v }),
          )}
        </Label>
        <Label title="Poisson's ratio">
          {numberInput(materialDraft.nu, (v) =>
            setMaterialDraft({ ...materialDraft, nu: v }),
          )}
        </Label>
        <Label title="Density">
          {numberInput(materialDraft.density, (v) =>
            setMaterialDraft({ ...materialDraft, density: v }),
          )}
        </Label>
        <Label title="Modulus unit">
          <input
            value={materialDraft.unit}
            onChange={(e) =>
              setMaterialDraft({ ...materialDraft, unit: e.target.value })
            }
          />
        </Label>
        <p className="hm-note">
          Definitions and component assignments are saved in this study. No
          native solver material card is written.
        </p>
        <p className="hm-note">
          Assignment targets: {definitionTargets.join(", ") || "None"}.
        </p>
        <button
          className="hm-action"
          onClick={() => setDefinitionTargets([...study.selected])}
        >
          Use selected entities
        </button>
        <button
          className="hm-action"
          onClick={() => {
            if (
              !materialDraft.name.trim() ||
              materialDraft.E <= 0 ||
              materialDraft.nu <= -1 ||
              materialDraft.nu >= 0.5 ||
              materialDraft.density < 0 ||
              !materialDraft.unit.trim()
            ) {
              setMessage(
                "Material requires E > 0, -1 < ν < 0.5, density ≥ 0 and a unit.",
              );
              return;
            }
            const material = {
              ...materialDraft,
              id: materialDraft.id || `MAT-${Date.now().toString(36)}`,
            };
            change((s) => ({
              ...s,
              materials: [
                ...s.materials.filter((m) => m.id !== material.id),
                material,
              ],
              assignments: {
                ...s.assignments,
                ...Object.fromEntries(
                  definitionTargets.map((id) => [id, material.id]),
                ),
              },
            }));
            setMaterialDraft(material);
            setMessage(
              `Saved ${material.name}; assigned to ${definitionTargets.length} entities.`,
            );
          }}
        >
          Apply material{definitionTargets.length ? " to targets" : ""}
        </button>
      </>
    ) : panel === "condition" ? (
      <>
        <div className="hm-editor-subtitle">
          {conditionDraft.id ? "Edit load collector" : "New load collector"} ·
          local definition
        </div>
        <button className="hm-action" onClick={() => runCommand("condition")}>
          New load collector
        </button>
        <Label title="Name">
          <input
            value={conditionDraft.name}
            onChange={(e) =>
              setConditionDraft({ ...conditionDraft, name: e.target.value })
            }
          />
        </Label>
        <Label title="Type">
          <select
            value={conditionDraft.kind}
            onChange={(e) =>
              setConditionDraft({ ...conditionDraft, kind: e.target.value })
            }
          >
            <option>Displacement</option>
            <option>Force</option>
            <option>Constraint</option>
          </select>
        </Label>
        <Label title="Direction">
          <select
            value={conditionDraft.direction}
            onChange={(e) =>
              setConditionDraft({
                ...conditionDraft,
                direction: e.target.value,
              })
            }
          >
            {["ux", "uy", "uz"].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </Label>
        <Label title="Value">
          {numberInput(conditionDraft.value, (v) =>
            setConditionDraft({ ...conditionDraft, value: v }),
          )}
        </Label>
        <Label title="Unit">
          <input
            value={conditionDraft.unit}
            onChange={(e) =>
              setConditionDraft({ ...conditionDraft, unit: e.target.value })
            }
          />
        </Label>
        <p className="hm-note">
          Target: {definitionTargets.join(", ") || "Select components first"}.
          No new displacement or force solution is computed.
        </p>
        <button
          className="hm-action"
          onClick={() => setDefinitionTargets([...study.selected])}
        >
          Use selected entities
        </button>
        <button
          className="hm-action"
          disabled={!definitionTargets.length}
          onClick={() => {
            if (!conditionDraft.name.trim() || !conditionDraft.unit.trim()) {
              setMessage("Enter condition name and unit.");
              return;
            }
            const condition = {
              ...conditionDraft,
              id: conditionDraft.id || `BC-${Date.now().toString(36)}`,
              entities: [...definitionTargets],
            };
            change((s) => ({
              ...s,
              conditions: [
                ...s.conditions.filter((c) => c.id !== condition.id),
                condition,
              ],
            }));
            setConditionDraft(condition);
            setMessage(
              `Saved ${condition.name} for ${condition.entities.length} entities.`,
            );
          }}
        >
          Apply definition
        </button>
      </>
    ) : panel === "measure" ? (
      <>
        <div className="hm-editor-subtitle">Coordinate bounds · mm</div>
        <p className="hm-note">
          {study.dataset === "result"
            ? "Retained support mesh"
            : selectedEntity
              ? `Selected component: ${selectedEntity.name}`
              : "Full retained assembly"}
        </p>
        <table className="hm-properties">
          <tbody>
            {["x", "y", "z"].map((axis, i) => (
              <tr key={axis}>
                <th>{axis} min / max</th>
                <td>
                  {measureBounds.min[i].toPrecision(7)} /{" "}
                  {measureBounds.max[i].toPrecision(7)}
                </td>
              </tr>
            ))}
            {["x", "y", "z"].map((axis, i) => (
              <tr key={`${axis}-length`}>
                <th>Δ{axis} [mm]</th>
                <td>{measureBounds.dimensions[i].toPrecision(7)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="hm-note">
          Actual source geometry / retained coordinates. Clipping and explode
          display do not alter these measurements.
        </p>
      </>
    ) : panel === "section" ? (
      <>
        <div className="hm-editor-subtitle">Section plane</div>
        <Label title="Enabled">
          <input
            type="checkbox"
            checked={study.clip.enabled}
            onChange={(e) =>
              change((s) => ({
                ...s,
                clip: { ...s.clip, enabled: e.target.checked },
              }))
            }
          />
        </Label>
        <Label title="Axis">
          <select
            value={study.clip.axis}
            onChange={(e) =>
              change((s) => ({
                ...s,
                clip: { ...s.clip, axis: e.target.value as "x" | "y" | "z" },
              }))
            }
          >
            <option>x</option>
            <option>y</option>
            <option>z</option>
          </select>
        </Label>
        <Label title="Position">
          <input
            type="range"
            min="0"
            max="1"
            step=".005"
            value={study.clip.position}
            onChange={(e) =>
              change((s) => ({
                ...s,
                clip: { ...s.clip, position: Number(e.target.value) },
              }))
            }
          />
        </Label>
        <p className="hm-note">
          {Math.round(study.clip.position * 100)}% of model bounds. Clipping
          affects display only.
        </p>
      </>
    ) : panel === "display" ? (
      <>
        <div className="hm-editor-subtitle">Display controls</div>
        <Label title="Dataset">
          <select
            value={study.dataset}
            onChange={(e) => switchDataset(e.target.value as Study["dataset"])}
          >
            <option value="assembly">Assembly</option>
            <option value="result">Retained support result</option>
          </select>
        </Label>
        <Label title="Representation">
          <select
            value={study.representation}
            onChange={(e) =>
              change((s) => ({
                ...s,
                representation: e.target.value as Study["representation"],
              }))
            }
          >
            {["shaded", "edges", "wireframe", "transparent"].map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </Label>
        {study.dataset === "assembly" ? (
          <Label title="Explode">
            <input
              type="range"
              min="0"
              max="1"
              step=".01"
              value={study.explode}
              onChange={(e) =>
                change((s) => ({ ...s, explode: Number(e.target.value) }))
              }
            />
          </Label>
        ) : (
          <>
            <Label title="Contour">
              <select
                value={study.field}
                onChange={(e) =>
                  change((s) => ({
                    ...s,
                    field: e.target.value as Study["field"],
                  }))
                }
              >
                {["none", "magnitude", "ux", "uy", "uz"].map((f) => (
                  <option key={f}>{f}</option>
                ))}
              </select>
            </Label>
            <Label title="Deformation scale">
              {numberInput(study.deformation, (v) => {
                if (v >= 0 && v <= 10000)
                  change((s) => ({ ...s, deformation: v }));
              })}
            </Label>
            <p className="hm-note">
              Coordinates + scale × retained U. One retained result frame; no
              animation history.
            </p>
          </>
        )}
        <Label title="Retained load nodes">
          <input
            type="checkbox"
            disabled={study.dataset !== "result"}
            checked={study.showLoads}
            onChange={(e) =>
              change((s) => ({ ...s, showLoads: e.target.checked }))
            }
          />
        </Label>
      </>
    ) : panel === "validate" ? (
      <>
        <div className="hm-editor-subtitle">Model checker</div>
        {validation.map((text, i) => (
          <div key={i} className="hm-check-row">
            <Check size={12} />
            <span>{text}</span>
          </div>
        ))}
        <button className="hm-action" onClick={validate}>
          Recheck available data
        </button>
      </>
    ) : panel === "mesh" || panel === "solver" ? (
      <>
        <div className="hm-editor-subtitle">
          {panel === "solver" ? "Solver connection" : "Mesh / native command"}
        </div>
        <p className="hm-command-explanation">{guide}</p>
        <table className="hm-properties">
          <tbody>
            <tr>
              <th>Displayed data</th>
              <td>
                {study.dataset === "assembly"
                  ? "Imported assembly tessellation"
                  : "Retained support finite element mesh"}
              </td>
            </tr>
            <tr>
              <th>New mesh</th>
              <td>Not generated</td>
            </tr>
            <tr>
              <th>Solver run</th>
              <td>Not performed</td>
            </tr>
          </tbody>
        </table>
        <button className="hm-action" onClick={() => runCommand("display")}>
          Review display
        </button>
        <button className="hm-action" onClick={validate}>
          Check available data
        </button>
      </>
    ) : (
      <>
        <div className="hm-editor-subtitle">
          {selectedEntity ? "Component" : "Entity"} attributes
        </div>
        <table className="hm-properties">
          <tbody>
            {propertyRows.map(([a, b]) => (
              <tr key={a}>
                <th>{a}</th>
                <td>{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {selectedEntity && (
          <>
            <Label title="Study label">
              <input
                value={study.names[selectedEntity.id] || selectedEntity.name}
                onChange={(e) =>
                  change((s) => ({
                    ...s,
                    names: { ...s.names, [selectedEntity.id]: e.target.value },
                  }))
                }
              />
            </Label>
            <Label title="Material">
              <select
                value={study.assignments[selectedEntity.id] || ""}
                onChange={(e) =>
                  change((s) => ({
                    ...s,
                    assignments: {
                      ...s.assignments,
                      [selectedEntity.id]: e.target.value,
                    },
                  }))
                }
              >
                <option value="">Unassigned</option>
                {study.materials.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </Label>
            <div className="hm-selection-actions">
              <button onClick={() => runCommand("hide")}>
                <EyeOff size={13} />
                Hide
              </button>
              <button onClick={() => runCommand("isolate")}>
                <Target size={13} />
                Isolate
              </button>
              <button onClick={() => runCommand("showall")}>
                <Eye size={13} />
                Show all
              </button>
            </div>
          </>
        )}
        {study.dataset === "result" && (
          <>
            <div className="hm-editor-subtitle">Exact node query</div>
            <div className="hm-node-query">
              <input
                aria-label="Exact node ID"
                placeholder="Node ID"
                value={nodeId}
                onChange={(e) => setNodeId(e.target.value)}
              />
              <button
                onClick={() => {
                  const found = resultNodes.find(
                    (n) => n.id === Number(nodeId),
                  );
                  if (found) probe(found);
                  else
                    setMessage(
                      `Node ${nodeId} does not exist in retained data.`,
                    );
                }}
              >
                <Search size={13} />
              </button>
            </div>
            {node && (
              <table className="hm-properties">
                <tbody>
                  {Object.entries(node).map(([a, b]) => (
                    <tr key={a}>
                      <th>{a}</th>
                      <td>
                        {typeof b === "number"
                          ? Number.isInteger(b) && a === "id"
                            ? b
                            : b.toPrecision(9)
                          : String(b)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </>
    );
  const grouped = (
    title: string,
    id: string,
    count: number,
    children: ReactNode,
  ) => (
    <div className="hm-tree-group">
      <button className="hm-tree-heading" onClick={() => toggleGroup(id)}>
        {closedGroups.includes(id) ? (
          <ChevronRight size={11} />
        ) : (
          <ChevronDown size={11} />
        )}
        <Layers size={12} />
        {title} ({count})
      </button>
      {!closedGroups.includes(id) && children}
    </div>
  );
  return (
    <div className="hm-shell" data-history-count={historyCount}>
      <input
        ref={inputRef}
        type="file"
        hidden
        accept=".json,.hmstudy.json"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) open(file);
          e.target.value = "";
        }}
      />
      <div className="hm-titlebar">
        <span className="hm-logo">H</span>
        <span>Altair HyperMesh 2026 - OptiStruct</span>
        <span className="hm-title-document">{study.name}</span>
        <span className="hm-window-tools">—　□　×</span>
      </div>
      <div className="hm-menubar">
        {["File", "Edit", "View", "HyperMesh"].map((name) => (
          <div key={name} className="hm-menu-wrap">
            <button
              className={menu === name ? "active" : ""}
              onClick={() => setMenu(menu === name ? null : name)}
            >
              {name}
            </button>
            {menu === name && (
              <div className="hm-menu-dropdown">
                {(name === "File"
                  ? [
                      ["New Study", "new"],
                      ["Open Study…", "open"],
                      ["Save Study…", "save"],
                      ["Export Retained Node Data…", "exportnodes"],
                    ]
                  : name === "Edit"
                    ? [
                        ["Undo", "undo"],
                        ["Redo", "redo"],
                        ["Material Definition…", "material"],
                        ["Boundary / Load Definition…", "condition"],
                      ]
                    : name === "View"
                      ? [
                          ["Fit", "fit"],
                          ["Isometric", "iso"],
                          ["Front", "front"],
                          ["Top", "top"],
                          ["Right", "right"],
                          ["Show All", "showall"],
                          ["Section Plane…", "section"],
                          ["Display Controls…", "display"],
                        ]
                      : [
                          ["Model Checker", "validate"],
                          ["Retained Results", "result"],
                          ["Solver Connection…", "solver"],
                        ]
                ).map(([label, action]) => (
                  <button
                    key={action}
                    onClick={() => runCommand(action, label)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        <div className="hm-quick-actions">
          <button title="Open study" onClick={() => runCommand("open")}>
            <FolderOpen size={12} />
          </button>
          <button title="Save study" onClick={save}>
            <Save size={12} />
          </button>
          <button
            title="Undo"
            disabled={!undo.current.length}
            onClick={undoChange}
          >
            <Undo2 size={12} />
          </button>
          <button
            title="Redo"
            disabled={!redo.current.length}
            onClick={redoChange}
          >
            <Redo2 size={12} />
          </button>
        </div>
        <span className="hm-search-command">
          <Search size={12} />
          <input
            placeholder="Search model"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </span>
      </div>
      <div className="hm-ribbon-tabs">
        {tabs.map((name) => (
          <button
            key={name}
            className={tab === name ? "active" : ""}
            onClick={() => {
              setTab(name);
              if (name === "Post") runCommand("result");
            }}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="hm-ribbon">
        {(groups[tab] || defaultGroups).map((group) => (
          <div className="hm-ribbon-group" key={group.title}>
            <div className="hm-ribbon-items">
              {group.commands.map((c) => (
                <button
                  key={c.name}
                  onClick={() => runCommand(c.action, c.name)}
                  title={c.name}
                >
                  <Glyph name={c.name} color={c.color} shape={c.shape} />
                  <span>{c.name}</span>
                </button>
              ))}
            </div>
            <div className="hm-ribbon-group-name">
              {group.title}
              <ChevronDown size={9} />
            </div>
          </div>
        ))}
      </div>
      <div className="hm-body">
        <aside className="hm-browser" style={{ width: browserWidth }}>
          <div className="hm-browser-tabs">
            <button onClick={() => setFilter("All")}>Session</button>
            <button className="active" onClick={() => setFilter("All")}>
              Model
            </button>
            <span />
            <button
              title="Collapse browser"
              onClick={() => setBrowserWidth(browserWidth === 205 ? 254 : 205)}
            >
              <PanelLeftClose size={11} />
            </button>
          </div>
          <div className="hm-browser-upper" style={{ height: browserHeight }}>
            <div className="hm-tree-search">
              <input
                placeholder="Search"
                aria-label="Search entities"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <Search size={12} />
            </div>
            <div className="hm-tree-column">
              Name{" "}
              <button title="Show all" onClick={() => runCommand("showall")}>
                <Eye size={11} />
              </button>
            </div>
            <div className="hm-tree-scroll">
              {grouped(
                "Components",
                "components",
                entities.length,
                entities
                  .filter(
                    (c) =>
                      (study.names[c.id] || c.name)
                        .toLowerCase()
                        .includes(search.toLowerCase()) &&
                      (filter !== "Displayed" ||
                        !study.hidden.includes(c.id)) &&
                      (filter !== "Selected" || study.selected.includes(c.id)),
                  )
                  .map((c) => (
                    <div
                      key={c.id}
                      className={`hm-tree-entity ${study.selected.includes(c.id) ? "selected" : ""}`}
                    >
                      <button
                        className="hm-visibility"
                        title={study.hidden.includes(c.id) ? "Show" : "Hide"}
                        onClick={() =>
                          change((s) => ({
                            ...s,
                            hidden: s.hidden.includes(c.id)
                              ? s.hidden.filter((id) => id !== c.id)
                              : [...s.hidden, c.id],
                          }))
                        }
                      >
                        {study.hidden.includes(c.id) ? (
                          <EyeOff size={12} />
                        ) : (
                          <Eye size={12} />
                        )}
                      </button>
                      <button
                        className="hm-entity-name"
                        onClick={(e) => select(c.id, e.ctrlKey || e.shiftKey)}
                      >
                        <span
                          style={{ background: c.color }}
                          className="hm-color"
                        />
                        {study.names[c.id] || c.name}
                      </button>
                    </div>
                  )),
              )}
              {grouped(
                "Materials",
                "materials",
                study.materials.length,
                study.materials.map((m) => (
                  <button
                    className="hm-tree-definition"
                    key={m.id}
                    onClick={() => {
                      setMaterialDraft(m);
                      setDefinitionTargets(
                        Object.entries(study.assignments)
                          .filter(([, material]) => material === m.id)
                          .map(([id]) => id),
                      );
                      showPanel("material", `Edit ${m.name}`);
                    }}
                  >
                    <Box size={12} />
                    {m.name}
                  </button>
                )),
              )}
              {grouped(
                "Load Collectors",
                "conditions",
                study.conditions.length,
                study.conditions.map((c) => (
                  <button
                    className="hm-tree-definition"
                    key={c.id}
                    onClick={() => {
                      setConditionDraft(c);
                      setDefinitionTargets([...c.entities]);
                      change((s) => ({ ...s, selected: c.entities }));
                      showPanel("condition", `Edit ${c.name}`);
                    }}
                  >
                    <ArrowUp size={12} />
                    {c.name}
                  </button>
                )),
              )}
              <button
                className="hm-tree-heading"
                onClick={() => {
                  switchDataset("result");
                  setResultsOpen(true);
                }}
              >
                <ChevronRight size={11} />
                <Circle size={12} />
                Nodes ({resultInfo.nodes.toLocaleString()})
              </button>
              <button
                className="hm-tree-heading"
                onClick={() => runCommand("mesh")}
              >
                <ChevronRight size={11} />
                <Grid3X3 size={12} />
                Elements ({resultInfo.elements.toLocaleString()})
              </button>
              <button
                className="hm-tree-heading"
                onClick={() => runCommand("section")}
              >
                <ChevronRight size={11} />
                <Scissors size={12} />
                Section Planes ({study.clip.enabled ? 1 : 0})
              </button>
            </div>
          </div>
          <div
            className="hm-horizontal-split"
            onPointerDown={(e) => resize("y", e)}
          />
          <div className="hm-editor">
            <div className="hm-editor-title">
              Entity Editor{" "}
              <select
                aria-label="Entity editor mode"
                value={panel}
                onChange={(e) =>
                  e.target.value === "material" ||
                  e.target.value === "condition"
                    ? runCommand(e.target.value)
                    : setPanel(e.target.value as Panel)
                }
              >
                {[
                  "properties",
                  "material",
                  "condition",
                  "display",
                  "section",
                  "measure",
                  "mesh",
                  "validate",
                  "solver",
                ].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </div>
            <div className="hm-editor-scroll">{editor}</div>
          </div>
        </aside>
        <div
          className="hm-vertical-split"
          onPointerDown={(e) => resize("x", e)}
        />
        <main className="hm-workspace">
          <div className="hm-selector-strip">
            <select
              aria-label="Entity selector"
              value={study.dataset === "result" ? "Nodes" : "Components"}
              onChange={(e) =>
                e.target.value === "Nodes"
                  ? runCommand("query")
                  : switchDataset("assembly")
              }
            >
              <option>Components</option>
              <option>Nodes</option>
            </select>
            <select
              aria-label="Visibility filter"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option>All</option>
              <option>Displayed</option>
              <option>Selected</option>
            </select>
            <button title="Show all" onClick={() => runCommand("showall")}>
              <Eye size={13} />
            </button>
            <button
              title="Hide selected"
              disabled={!study.selected.length}
              onClick={() => runCommand("hide")}
            >
              <EyeOff size={13} />
            </button>
            <button
              title="Isolate selected"
              disabled={!study.selected.length}
              onClick={() => runCommand("isolate")}
            >
              <Target size={13} />
            </button>
            <span />
            <button
              className={study.dataset === "assembly" ? "active" : ""}
              onClick={() => switchDataset("assembly")}
            >
              Assembly
            </button>
            <button
              className={study.dataset === "result" ? "active" : ""}
              onClick={() => runCommand("result")}
            >
              Retained Result
            </button>
          </div>
          {guide && (
            <div className="hm-guidebar">
              <Target size={15} />
              <span>{guide}</span>
              <button onClick={() => setGuide("")} title="Close guide">
                <X size={13} />
              </button>
            </div>
          )}
          <div className="hm-scene-wrap">
            <Scene
              theme="hypermesh"
              dataset={study.dataset}
              representation={study.representation}
              selected={study.selected}
              hidden={study.hidden}
              onSelect={select}
              onProbe={probe}
              command={camera}
              explode={study.explode}
              clip={study.clip}
              field={study.field}
              deformation={study.deformation}
              showLoads={study.showLoads}
              probeMode={probeMode}
              probeId={node?.id}
            />
            <div
              className={
                study.dataset === "result"
                  ? "hm-view-caption hm-result-caption"
                  : "hm-view-caption"
              }
            >
              {study.dataset === "assembly"
                ? `${components.length} component assembly`
                : `Displacement (${study.field === "magnitude" ? "Magnitude" : study.field}) [${resultInfo.unit}]`}
              {study.dataset === "result" && (
                <small>Retained support mesh · single frame</small>
              )}
            </div>
            <div className="hm-view-cube">
              <span className="hm-axis-z">Z</span>
              <span className="hm-axis-y">Y</span>
              <span className="hm-axis-x">X</span>
              <button className="hm-cube-top" onClick={() => view("top")}>
                TOP
              </button>
              <button className="hm-cube-front" onClick={() => view("front")}>
                FRONT
              </button>
              <button className="hm-cube-right" onClick={() => view("right")}>
                RIGHT
              </button>
            </div>
          </div>
          <div className="hm-view-toolbar">
            {[
              [Maximize, "fit", "Fit"],
              [RotateCcw, "iso", "Isometric"],
              [ZoomIn, "zoomIn", "Zoom in"],
              [ZoomOut, "zoomOut", "Zoom out"],
              [Box, "shaded", "Shaded"],
              [Grid3X3, "edges", "Edges"],
              [Layers, "wireframe", "Wireframe"],
              [Scissors, "section", "Section plane"],
              [Move3D, "explode", "Explode"],
              [Ruler, "measure", "Measure"],
              [Crosshair, "query", "Query nodes"],
            ].map(([Icon, action, title]) => {
              const I = Icon as typeof Box;
              return (
                <button
                  key={String(action)}
                  title={String(title)}
                  onClick={() => runCommand(String(action), String(title))}
                >
                  <I size={14} />
                </button>
              );
            })}
            <span />
            <button onClick={() => setResultsOpen(!resultsOpen)}>
              <FileText size={12} />
              {resultsOpen ? "Close table / plot" : "Table / plot"}
            </button>
            {probeMode && (
              <button className="active" onClick={() => setProbeMode(false)}>
                End query
              </button>
            )}
          </div>
        </main>
        {resultsOpen && (
          <section className="hm-results">
            <div className="hm-results-title">
              Retained support · exact nodal U
              <button onClick={() => setResultsOpen(false)}>
                <X size={12} />
              </button>
            </div>
            <div className="hm-results-source">
              {resultInfo.nodes.toLocaleString()} nodes ·{" "}
              {resultInfo.elements.toLocaleString()} elements
              <br />
              {resultInfo.source}
            </div>
            <NodePlot selected={node} onSelect={probe} />
            <div className="hm-profile-caption">
              Spatial scatter: x → Uz. No time history is available.
            </div>
            <div className="hm-node-table">
              <AgGridReact
                theme={gridTheme}
                rowData={resultNodes}
                getRowId={(p) => String(p.data.id)}
                columnDefs={[
                  {
                    field: "id",
                    headerName: "Node",
                    width: 70,
                    pinned: "left",
                  },
                  ...(
                    ["x", "y", "z", "ux", "uy", "uz", "magnitude"] as const
                  ).map((field) => ({
                    field,
                    width: 92,
                    valueFormatter: (p: any) => Number(p.value).toPrecision(6),
                  })),
                ]}
                defaultColDef={{ sortable: true, resizable: true }}
                rowSelection={{
                  mode: "singleRow",
                  checkboxes: false,
                  enableClickSelection: true,
                }}
                onGridReady={(e) => {
                  gridApi.current = e.api;
                }}
                onRowClicked={(e) => {
                  if (e.data) probe(e.data);
                }}
                animateRows={false}
              />
            </div>
            <div className="hm-results-footer">
              {node
                ? `Selected node ${node.id} · Uz ${node.uz.toPrecision(7)} ${resultInfo.unit}`
                : "Select a table row or a plotted node."}
            </div>
          </section>
        )}
      </div>
      <footer className="hm-status">
        <span>{message}</span>
        <span>
          {study.selected.length} selected ·{" "}
          {study.dataset === "assembly" ? "Assembly" : "Retained support"}
        </span>
        <span>Browser study · no native solver</span>
      </footer>
    </div>
  );
}
