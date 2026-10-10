import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { Box, Maximize, Grid2x2, RotateCcw } from "lucide-react";
import { Button } from "./common";

// Synthetic geometry for interaction design, never an imported CAD/solver result.
export function Viewport({
  field = false,
  source = "A",
  selected = "body",
  sizes,
  cameraLinkKey,
  time = 1,
  rangeMax = 0.059,
  onSelect,
}: {
  field?: boolean;
  source?: string;
  selected?: string;
  sizes?: Record<string, number>;
  cameraLinkKey?: string;
  time?: number;
  rangeMax?: number;
  onSelect?: (id: string) => void;
}) {
  const mount = useRef<HTMLDivElement>(null);
  const objects = useRef<THREE.Mesh[]>([]);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const [wire, setWire] = useState(field);
  const [view, setView] = useState("등각");
  const linkRef = useRef(cameraLinkKey);
  linkRef.current = cameraLinkKey;
  useEffect(() => {
    const node = mount.current;
    if (!node) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(field ? "#eef2f6" : "#e9eef3");
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      preserveDrawingBuffer: false,
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    node.appendChild(renderer.domElement);
    const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
    camera.position.set(9, 8, 10);
    cameraRef.current = camera;
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 0.4, 0);
    controls.enableDamping = true;
    controls.dampingFactor = 0.1;
    controlsRef.current = controls;
    let syncing = false;
    const cameraChanged = () => {
      if (!syncing && linkRef.current)
        window.dispatchEvent(
          new CustomEvent("cae-camera", {
            detail: {
              key: linkRef.current,
              source,
              position: camera.position.toArray(),
              target: controls.target.toArray(),
            },
          }),
        );
    };
    const cameraReceived = (event: Event) => {
      const d = (event as CustomEvent).detail;
      if (d.key !== linkRef.current || d.source === source) return;
      syncing = true;
      camera.position.fromArray(d.position);
      controls.target.fromArray(d.target);
      controls.update();
      syncing = false;
    };
    controls.addEventListener("change", cameraChanged);
    window.addEventListener("cae-camera", cameraReceived);
    scene.add(new THREE.AmbientLight(0xffffff, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3);
    key.position.set(4, 10, 8);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xb7c9df, 1);
    fill.position.set(-5, 4, -6);
    scene.add(fill);
    const grid = new THREE.GridHelper(15, 30, 0xabbaca, 0xd7dfe6);
    grid.position.y = -0.39;
    scene.add(grid);
    const meshes: THREE.Mesh[] = [];
    function solid(
      geo: THREE.BufferGeometry,
      id: string,
      color: string,
      x = 0,
      y = 0,
      z = 0,
    ) {
      const material = new THREE.MeshStandardMaterial({
        color,
        metalness: 0.15,
        roughness: 0.48,
      });
      const mesh = new THREE.Mesh(geo, material);
      mesh.position.set(x, y, z);
      mesh.userData.id = id;
      mesh.userData.base = color;
      scene.add(mesh);
      meshes.push(mesh);
      const edge = new THREE.LineSegments(
        new THREE.EdgesGeometry(geo, 20),
        new THREE.LineBasicMaterial({
          color: 0x506d85,
          transparent: true,
          opacity: 0.55,
        }),
      );
      mesh.add(edge);
      return mesh;
    }
    if (field) {
      const geo = new THREE.BoxGeometry(7, 0.65, 2, 28, 3, 10);
      const p = geo.attributes.position;
      geo.setAttribute("originalPosition", p.clone());
      const c = [];
      const col = new THREE.Color();
      for (let i = 0; i < p.count; i++) {
        const x = (p.getX(i) + 3.5) / 7;
        col.setHSL(0.62 - 0.6 * x, 0.7, 0.48);
        c.push(col.r, col.g, col.b);
        p.setY(
          i,
          p.getY(i) - Math.pow(x, 2) * 0.6 * (source === "B" ? 1.3 : 1),
        );
      }
      geo.setAttribute("color", new THREE.Float32BufferAttribute(c, 3));
      geo.computeVertexNormals();
      const mesh = solid(geo, "field", "#ffffff");
      (mesh.material as THREE.MeshStandardMaterial).vertexColors = true;
      mesh.userData.base = "#ffffff";
      const meshLines = new THREE.LineSegments(
        new THREE.WireframeGeometry(geo),
        new THREE.LineBasicMaterial({
          color: 0x354d61,
          transparent: true,
          opacity: 0.2,
        }),
      );
      meshLines.name = "mesh-wire";
      mesh.add(meshLines);
    } else {
      const shape = new THREE.Shape();
      shape.moveTo(-3.4, -1.5);
      shape.lineTo(3.4, -1.5);
      shape.lineTo(3.4, 1.5);
      shape.lineTo(-3.4, 1.5);
      shape.closePath();
      for (const x of [-2.65, 2.65])
        for (const y of [-0.93, 0.93]) {
          const hole = new THREE.Path();
          hole.absarc(x, y, 0.27, 0, Math.PI * 2, true);
          shape.holes.push(hole);
        }
      const geo = new THREE.ExtrudeGeometry(shape, {
        depth: 0.38,
        bevelEnabled: true,
        bevelThickness: 0.055,
        bevelSize: 0.055,
        bevelSegments: 3,
        curveSegments: 32,
      });
      geo.rotateX(-Math.PI / 2);
      solid(geo, "body", "#a3b3c3");
      solid(
        new THREE.BoxGeometry(1.2, 1.2, 2.2),
        "support",
        "#899eaf",
        -1.5,
        0.96,
        0,
      );
      solid(
        new THREE.BoxGeometry(4.2, 0.38, 0.7),
        "arm",
        "#bac6cf",
        0.15,
        1.75,
        0,
      );
      const pin = solid(
        new THREE.CylinderGeometry(0.25, 0.25, 1.9, 40),
        "pin",
        "#718a9e",
        -1.5,
        1.1,
        0,
      );
      pin.rotation.x = Math.PI / 2;
    }
    objects.current = meshes;
    const ray = new THREE.Raycaster();
    let down = { x: 0, y: 0 };
    const downEvent = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY };
    };
    const click = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      const r = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - r.left) / r.width) * 2 - 1,
          (-(e.clientY - r.top) / r.height) * 2 + 1,
        ),
        camera,
      );
      const hit = ray.intersectObjects(meshes, false)[0];
      if (hit) selectRef.current?.(hit.object.userData.id);
    };
    renderer.domElement.addEventListener("pointerdown", downEvent);
    renderer.domElement.addEventListener("pointerup", click);
    const observer = new ResizeObserver(() => {
      const w = node.clientWidth,
        h = node.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    observer.observe(node);
    let frame = 0;
    const draw = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(draw);
    };
    draw();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.removeEventListener("change", cameraChanged);
      window.removeEventListener("cae-camera", cameraReceived);
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", downEvent);
      renderer.domElement.removeEventListener("pointerup", click);
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.LineSegments) {
          o.geometry.dispose();
          const mats = Array.isArray(o.material) ? o.material : [o.material];
          mats.forEach((m) => m.dispose());
        }
      });
      renderer.dispose();
      node.removeChild(renderer.domElement);
    };
  }, [field, source]);
  useEffect(() => {
    for (const mesh of objects.current) {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.color.set(
        !field && mesh.userData.id === selected
          ? "#77aacc"
          : mesh.userData.base,
      );
      if (!field && sizes) {
        const defaults: Record<string, number> = {
          body: 68,
          support: 12,
          arm: 40,
          pin: 5,
        };
        mesh.scale.x = sizes[mesh.userData.id] / defaults[mesh.userData.id];
      }
      if (field) {
        const geometry = mesh.geometry;
        const original = geometry.getAttribute("originalPosition");
        const position = geometry.getAttribute("position");
        const color = geometry.getAttribute("color");
        const shade = new THREE.Color();
        for (let i = 0; i < position.count; i++) {
          const x = (original.getX(i) + 3.5) / 7;
          const displacement = (source === "B" ? 0.059 : 0.043) * time * x * x;
          position.setY(i, original.getY(i) - displacement * 14);
          shade.setHSL(
            0.62 - 0.6 * Math.min(1, displacement / rangeMax),
            0.7,
            0.48,
          );
          color.setXYZ(i, shade.r, shade.g, shade.b);
        }
        position.needsUpdate = true;
        color.needsUpdate = true;
        geometry.computeVertexNormals();
        for (const child of mesh.children)
          if (child instanceof THREE.LineSegments) {
            child.geometry.dispose();
            child.geometry =
              child.name === "mesh-wire"
                ? new THREE.WireframeGeometry(geometry)
                : new THREE.EdgesGeometry(geometry, 20);
          }
      }
      const lines = mesh.getObjectByName("mesh-wire");
      if (lines) lines.visible = wire;
    }
  }, [selected, wire, field, source, sizes, time, rangeMax]);
  function orient(front = false) {
    const camera = cameraRef.current,
      controls = controlsRef.current;
    if (!camera || !controls) return;
    camera.position.set(
      ...((front ? [0, 1, 14] : [9, 8, 10]) as [number, number, number]),
    );
    controls.target.set(0, 0.4, 0);
    controls.update();
    setView(front ? "정면" : "등각");
  }
  return (
    <div className="viewport">
      <div className="viewport-heading">
        <span>
          {field
            ? `${source} · Displacement / UZ`
            : "Fixture assembly · 합성 조립 모델"}
        </span>
        <span className="viewport-sub">
          {view} · {field ? `합성 변형 · t = ${time.toFixed(2)} s` : "mm"}
        </span>
      </div>
      <div ref={mount} className="viewport-canvas" />
      <div className="viewport-controls">
        <Button icon={Maximize} title="모델 맞춤" onClick={() => orient()} />
        <Button icon={Box} title="정면 보기" onClick={() => orient(true)} />
        <Button icon={RotateCcw} title="등각 보기" onClick={() => orient()} />
        {field && (
          <Button
            icon={Grid2x2}
            className={wire ? "active" : ""}
            title="메시 선 표시"
            onClick={() => setWire(!wire)}
          />
        )}
      </div>
      <div className="axis-triad">
        <span className="axis-y">Y</span>
        <span className="axis-z">Z</span>
        <span className="axis-x">X</span>
        <svg width="55" height="50">
          <path
            d="M25 28L48 36M25 28L5 38M25 28L25 3"
            fill="none"
            stroke="#74889a"
            strokeWidth="1.5"
          />
        </svg>
      </div>
      {field && (
        <div className="field-legend">
          <span>UZ [mm]</span>
          <div />
          <label>0.000</label>
          <label>−{(rangeMax / 3).toFixed(3)}</label>
          <label>−{((rangeMax * 2) / 3).toFixed(3)}</label>
          <label>−{rangeMax.toFixed(3)}</label>
        </div>
      )}
      <div className="viewport-note">
        합성 형상 ·{" "}
        {field
          ? "모의 결과 · 수치 검증 자료 아님"
          : "클릭 선택 · 드래그 회전 · 휠 확대"}
      </div>
    </div>
  );
}
