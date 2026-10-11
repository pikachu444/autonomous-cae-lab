import React from "react";
import { createRoot } from "react-dom/client";
import Abaqus from "./replicas/Abaqus";
import HyperMesh from "./replicas/HyperMesh";
import "./replicas/base.css";
const abaqus =
  location.pathname.endsWith("abaqus.html") || location.hash === "#abaqus";
createRoot(document.getElementById("root")!).render(
  abaqus ? <Abaqus /> : <HyperMesh />,
);
