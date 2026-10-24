"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useLocale } from "next-intl";

export interface PolicyCandidateMetrics {
  id: string;
  name: string;
  costUsd: number; // e.g. 0.0002
  latencyMs: number; // e.g. 150
  passRate: number; // 0.0 - 1.0 (or 0 - 100)
  isParetoOptimal: boolean;
  trials?: number;
  calls?: number;
  errors?: number;
  p50_ms?: number;
  p95_ms?: number;
  savingsPct?: number;
}

export interface ParetoScatterSurface3DProps {
  policies: PolicyCandidateMetrics[];
  selectedPolicyId?: string | null;
  onSelectPolicy?: (id: string) => void;
  className?: string;
  width?: number | string;
  height?: number | string;
  interactive?: boolean;
}

interface TooltipData {
  policy: PolicyCandidateMetrics;
  screenX: number;
  screenY: number;
}

// Default demonstration candidates when mock or initial state is provided
export const DEMO_PARETO_POLICIES: PolicyCandidateMetrics[] = [
  {
    id: "ml_router",
    name: "ML Router (Pareto Dynamic)",
    costUsd: 0.00042,
    latencyMs: 125,
    passRate: 0.985,
    isParetoOptimal: true,
    trials: 200,
    calls: 200,
    errors: 0,
    savingsPct: 24,
  },
  {
    id: "rule_guarded",
    name: "Rule Guarded",
    costUsd: 0.00078,
    latencyMs: 180,
    passRate: 0.978,
    isParetoOptimal: true,
    trials: 200,
    calls: 210,
    errors: 1,
    savingsPct: 15,
  },
  {
    id: "cheapest_feasible",
    name: "Cheapest Feasible (Groq / Free)",
    costUsd: 0.00012,
    latencyMs: 95,
    passRate: 0.962,
    isParetoOptimal: true,
    trials: 200,
    calls: 205,
    errors: 2,
    savingsPct: 45,
  },
  {
    id: "fixed_reference",
    name: "Fixed Baseline Reference",
    costUsd: 0.00185,
    latencyMs: 420,
    passRate: 0.991,
    isParetoOptimal: true,
    trials: 200,
    calls: 200,
    errors: 0,
    savingsPct: 0,
  },
  {
    id: "random_feasible",
    name: "Random Feasible",
    costUsd: 0.00095,
    latencyMs: 310,
    passRate: 0.954,
    isParetoOptimal: false,
    trials: 200,
    calls: 215,
    errors: 3,
    savingsPct: 8,
  },
  {
    id: "suboptimal_candidate_1",
    name: "Fixed Candidate (Small)",
    costUsd: 0.00085,
    latencyMs: 280,
    passRate: 0.945,
    isParetoOptimal: false,
    trials: 200,
    calls: 208,
    errors: 4,
    savingsPct: 10,
  },
];

export function ParetoScatterSurface3D({
  policies,
  selectedPolicyId,
  onSelectPolicy,
  className = "",
  width = "100%",
  height = 420,
  interactive = true,
}: ParetoScatterSurface3DProps) {
  const locale = useLocale();
  const mountRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<TooltipData | null>(null);
  const [tooltip, setTooltip] = useState<TooltipData | null>(null);

  // Normalize incoming candidate data
  const dataList: PolicyCandidateMetrics[] = useMemo(() => {
    if (policies && policies.length > 0) {
      return policies.map((p) => ({
        ...p,
        passRate: p.passRate > 1.0 ? p.passRate / 100 : p.passRate,
      }));
    }
    return DEMO_PARETO_POLICIES;
  }, [policies]);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const w =
      container.clientWidth || (typeof width === "number" ? width : 640);
    const h =
      container.clientHeight || (typeof height === "number" ? height : 420);

    // 1. Scene & Camera Setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc); // Crisp OU light background

    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
    camera.position.set(2.8, 2.4, 3.2);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enableZoom = interactive;
    controls.enableRotate = interactive;
    controls.target.set(0.7, 0.6, 0.7);
    controls.minDistance = 1.5;
    controls.maxDistance = 10.0;

    let isDirty = true;
    let animationFrameId: number;
    const requestRender = () => {
      isDirty = true;
    };
    controls.addEventListener("change", requestRender);

    // 2. Lighting (OU Navy and Pure White)
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.1);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.4);
    dirLight.position.set(6, 12, 8);
    scene.add(dirLight);

    const fillLight = new THREE.DirectionalLight(0x005696, 1.5);
    fillLight.position.set(-5, -2, -5);
    scene.add(fillLight);

    // 3. Grid Helper on Floor (OU Navy & Sky)
    const gridSize = 2.0;
    const gridDivisions = 10;
    const gridHelper = new THREE.GridHelper(
      gridSize,
      gridDivisions,
      0x002f54,
      0xe2e8f0,
    );
    gridHelper.position.set(gridSize / 2, 0, gridSize / 2);
    scene.add(gridHelper);

    // 4. Axis Lines (X: Cost, Y: Quality/Pass Rate, Z: Latency)
    const axisGroup = new THREE.Group();
    scene.add(axisGroup);

    const axisMat = new THREE.LineBasicMaterial({
      color: 0x002f54,
      linewidth: 2,
    });
    // X Axis (Cost)
    const xAxisGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(2.0, 0, 0),
    ]);
    axisGroup.add(new THREE.Line(xAxisGeo, axisMat));

    // Y Axis (Pass Rate - Up)
    const yAxisGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 1.6, 0),
    ]);
    axisGroup.add(new THREE.Line(yAxisGeo, axisMat));

    // Z Axis (Latency)
    const zAxisGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, 2.0),
    ]);
    axisGroup.add(new THREE.Line(zAxisGeo, axisMat));

    // 5. Normalization Helpers for 3D mapping
    const minCost = Math.min(...dataList.map((d) => d.costUsd), 0.0001);
    const maxCost = Math.max(...dataList.map((d) => d.costUsd), 0.002);
    const minLat = Math.min(...dataList.map((d) => d.latencyMs), 50);
    const maxLat = Math.max(...dataList.map((d) => d.latencyMs), 500);

    const to3DCoords = (item: PolicyCandidateMetrics): THREE.Vector3 => {
      const normX =
        (item.costUsd - minCost) / Math.max(0.0001, maxCost - minCost);
      const normZ = (item.latencyMs - minLat) / Math.max(1, maxLat - minLat);
      const normY = item.passRate; // 0.0 to 1.0 (Quality going UP)

      return new THREE.Vector3(
        0.2 + normX * 1.6,
        0.2 + normY * 1.2,
        0.2 + normZ * 1.6,
      );
    };

    // 6. Candidate Spheres
    const pointsGroup = new THREE.Group();
    scene.add(pointsGroup);

    const sphereGeo = new THREE.SphereGeometry(0.065, 24, 24);
    const paretoMat = new THREE.MeshStandardMaterial({
      color: 0x005696, // OU Blue for Pareto-optimal points
      emissive: 0x0284c7,
      emissiveIntensity: 0.6,
      roughness: 0.2,
      metalness: 0.85,
    });

    const dominatedMat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8, // Slate grey for dominated points
      roughness: 0.45,
      metalness: 0.2,
    });

    const selectedMat = new THREE.MeshStandardMaterial({
      color: 0xeab308, // Gold for selected policy
      emissive: 0xf59e0b,
      emissiveIntensity: 0.8,
      roughness: 0.2,
      metalness: 0.9,
    });

    const sphereMeshes: THREE.Mesh[] = [];
    const paretoPositions: THREE.Vector3[] = [];

    dataList.forEach((cand) => {
      const pos = to3DCoords(cand);
      const isSelected = selectedPolicyId === cand.id;

      const mat = isSelected
        ? selectedMat
        : cand.isParetoOptimal
          ? paretoMat
          : dominatedMat;

      const mesh = new THREE.Mesh(sphereGeo, mat);
      mesh.position.copy(pos);
      if (isSelected) mesh.scale.set(1.4, 1.4, 1.4);
      mesh.userData = { policy: cand };
      pointsGroup.add(mesh);
      sphereMeshes.push(mesh);

      if (cand.isParetoOptimal) {
        paretoPositions.push(pos);

        // Ground drop-pin line connecting point to floor grid for 3D depth perception
        const dropLineGeo = new THREE.BufferGeometry().setFromPoints([
          pos,
          new THREE.Vector3(pos.x, 0, pos.z),
        ]);
        const dropLineMat = new THREE.LineDashedMaterial({
          color: 0x0284c7,
          dashSize: 0.05,
          gapSize: 0.03,
          transparent: true,
          opacity: 0.4,
        });
        const dropLine = new THREE.Line(dropLineGeo, dropLineMat);
        dropLine.computeLineDistances();
        pointsGroup.add(dropLine);
      }
    });

    // 7. Pareto Frontier Mesh / Triangulated Surface
    if (paretoPositions.length >= 3) {
      // Sort points by cost for consistent triangulation
      const sorted = [...paretoPositions].sort((a, b) => a.x - b.x);
      const vertices: number[] = [];

      for (let i = 0; i < sorted.length - 2; i++) {
        vertices.push(
          sorted[i].x,
          sorted[i].y,
          sorted[i].z,
          sorted[i + 1].x,
          sorted[i + 1].y,
          sorted[i + 1].z,
          sorted[i + 2].x,
          sorted[i + 2].y,
          sorted[i + 2].z,
        );
      }

      const frontierGeo = new THREE.BufferGeometry();
      frontierGeo.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(vertices, 3),
      );
      frontierGeo.computeVertexNormals();

      const frontierMat = new THREE.MeshStandardMaterial({
        color: 0x38bdf8,
        transparent: true,
        opacity: 0.28,
        side: THREE.DoubleSide,
        roughness: 0.3,
        metalness: 0.1,
      });

      const frontierMesh = new THREE.Mesh(frontierGeo, frontierMat);
      pointsGroup.add(frontierMesh);

      // Wireframe overlay on frontier surface
      const wireMat = new THREE.MeshBasicMaterial({
        color: 0x0284c7,
        wireframe: true,
        transparent: true,
        opacity: 0.45,
      });
      const wireMesh = new THREE.Mesh(frontierGeo, wireMat);
      pointsGroup.add(wireMesh);
    }

    // 8. Raycaster Pointer Interaction for Tooltips
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const onPointerMove = (e: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(sphereMeshes);

      if (hits.length > 0) {
        const item = hits[0].object.userData?.policy as
          PolicyCandidateMetrics | undefined;
        if (item) {
          renderer.domElement.style.cursor = "pointer";
          const newTooltip = {
            policy: item,
            screenX: e.clientX - rect.left,
            screenY: e.clientY - rect.top,
          };
          tooltipRef.current = newTooltip;
          setTooltip(newTooltip);
          isDirty = true;
          return;
        }
      }
      if (tooltipRef.current !== null) {
        tooltipRef.current = null;
        setTooltip(null);
        renderer.domElement.style.cursor = "default";
        isDirty = true;
      }
    };

    const onClick = (e: MouseEvent) => {
      if (!onSelectPolicy) return;
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const hits = raycaster.intersectObjects(sphereMeshes);
      if (hits.length > 0) {
        const item = hits[0].object.userData?.policy as
          PolicyCandidateMetrics | undefined;
        if (item) onSelectPolicy(item.id);
      }
    };

    if (interactive) {
      renderer.domElement.addEventListener("mousemove", onPointerMove);
      renderer.domElement.addEventListener("click", onClick);
    }

    // 9. Event-Driven Render Loop
    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      if (isDirty) {
        controls.update();
        renderer.render(scene, camera);
        isDirty = false;
      }
    };
    animate();

    // 10. ResizeObserver for responsive canvas
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width: newW, height: newH } = entry.contentRect;
        if (newW > 0 && newH > 0) {
          camera.aspect = newW / newH;
          camera.updateProjectionMatrix();
          renderer.setSize(newW, newH);
          requestRender();
        }
      }
    });
    resizeObserver.observe(container);

    // 11. Cleanup WebGL Memory on Unmount (Zero VRAM Leak)
    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      controls.removeEventListener("change", requestRender);
      controls.dispose();

      if (interactive) {
        renderer.domElement.removeEventListener("mousemove", onPointerMove);
        renderer.domElement.removeEventListener("click", onClick);
      }

      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh || obj instanceof THREE.Line) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else if (obj.material) {
            obj.material.dispose();
          }
        }
      });

      gridHelper.dispose();
      renderer.dispose();
      renderer.forceContextLoss();

      if (
        container &&
        renderer.domElement &&
        container.contains(renderer.domElement)
      ) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [dataList, selectedPolicyId, width, height, interactive, onSelectPolicy]);

  return (
    <div
      className={`pareto-3d-wrapper relative overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/70 shadow-sm ${className}`}
      style={{ height, width }}
    >
      {/* 3D WebGL Canvas */}
      <div ref={mountRef} className="h-full w-full" />

      {/* Top Header Legend Overlay */}
      <div className="pareto-overlay-header pointer-events-none absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2 rounded-xl border border-white/80 bg-white/85 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur-md">
        <span className="h-2.5 w-2.5 rounded-full bg-[#005696]" />
        <span>3D PARETO FRONTIER SPACE</span>
        <span className="hidden sm:inline text-slate-400">·</span>
        <span className="text-[11px] font-normal text-slate-500">
          {locale === "en" ? "Cost (X) × Latency (Z) × Pass Rate Quality (Y)" : "Chi phí (X) × Độ trễ (Z) × Chất lượng Pass Rate (Y)"}
        </span>
      </div>

      {/* Status Badges */}
      <div className="pareto-overlay-badges pointer-events-none absolute top-3 right-3 z-10 flex items-center gap-2">
        <div className="flex items-center gap-1.5 rounded-lg border border-sky-200/80 bg-sky-50/85 px-2.5 py-1 text-[11px] font-medium text-sky-900 shadow-sm backdrop-blur-md">
          <span className="h-2 w-2 rounded-full bg-[#005696]" />
          <span>Pareto Optimal</span>
        </div>
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-200/80 bg-white/85 px-2.5 py-1 text-[11px] font-medium text-slate-600 shadow-sm backdrop-blur-md">
          <span className="h-2 w-2 rounded-full bg-slate-400" />
          <span>Dominated</span>
        </div>
      </div>

      {/* Floating Raycaster Tooltip */}
      {tooltip && (
        <div
          className="pareto-tooltip pointer-events-none absolute z-20 min-w-[210px] -translate-x-1/2 -translate-y-full transform rounded-xl border border-sky-100 bg-white/95 p-3 text-xs shadow-xl backdrop-blur-md"
          style={{
            left: Math.max(
              110,
              Math.min(
                tooltip.screenX,
                (typeof width === "number" ? width : 600) - 110,
              ),
            ),
            top: tooltip.screenY - 12,
          }}
        >
          <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-1.5">
            <strong className="font-semibold text-slate-900 truncate max-w-[150px]">
              {tooltip.policy.name}
            </strong>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                tooltip.policy.isParetoOptimal
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {tooltip.policy.isParetoOptimal ? (locale === "en" ? "Optimal" : "Tối ưu") : (locale === "en" ? "Dominated" : "Bị áp đảo")}
            </span>
          </div>

          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-lg bg-slate-50 p-1.5">
              <span className="block text-[10px] text-slate-400 font-medium">
                {locale === "en" ? "Cost" : "Chi phí"}
              </span>
              <strong className="font-bold text-[#005696]">
                ${tooltip.policy.costUsd.toFixed(5)}
              </strong>
            </div>
            <div className="rounded-lg bg-slate-50 p-1.5">
              <span className="block text-[10px] text-slate-400 font-medium">
                {locale === "en" ? "Latency" : "Độ trễ"}
              </span>
              <strong className="font-bold text-slate-800">
                {tooltip.policy.latencyMs} ms
              </strong>
            </div>
            <div className="rounded-lg bg-slate-50 p-1.5">
              <span className="block text-[10px] text-slate-400 font-medium">
                Pass Rate
              </span>
              <strong className="font-bold text-emerald-700">
                {(tooltip.policy.passRate * 100).toFixed(1)}%
              </strong>
            </div>
          </div>

          {tooltip.policy.savingsPct !== undefined &&
            tooltip.policy.savingsPct > 0 && (
              <div className="mt-2 text-center text-[10px] font-semibold text-emerald-600">
                {locale === "en"
                  ? `⚡ ${tooltip.policy.savingsPct}% cost savings vs baseline`
                  : `⚡ Tiết kiệm ${tooltip.policy.savingsPct}% chi phí so với baseline`}
              </div>
            )}
        </div>
      )}

      {/* Axis Helper Footnote */}
      <div className="pareto-overlay-footer pointer-events-none absolute bottom-2.5 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] font-bold text-[#005696]">
            [X] Cost
          </span>
          <span className="text-slate-300">·</span>
          <span className="font-mono text-[10px] font-bold text-emerald-600">
            [Y] Pass Rate
          </span>
          <span className="text-slate-300">·</span>
          <span className="font-mono text-[10px] font-bold text-indigo-600">
            [Z] Latency
          </span>
        </span>
        <span className="hidden sm:inline text-slate-400">
          {locale === "en" ? "Rotate to inspect 3D angles · Click to select policy" : "Xoay để xem đa góc độ · Click để chọn policy"}
        </span>
      </div>
    </div>
  );
}

export default ParetoScatterSurface3D;
