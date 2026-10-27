"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useLocale } from "next-intl";
import { RotateCcw, Box } from "lucide-react";

export interface SessionUsageMetric {
  id: string;
  sessionTitle: string;
  timestamp: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  costUsd: number;
  latencyMs: number;
  model: string;
  optimized: boolean;
}

export interface TokenCostSpace3DProps {
  metrics?: SessionUsageMetric[];
  height?: number | string;
  className?: string;
  interactive?: boolean;
}

// Default demonstration session metrics if real user has few/no sessions yet
export const DEMO_SESSION_METRICS: SessionUsageMetric[] = [
  {
    id: "sess_01",
    sessionTitle: "Toán cao cấp & Tích phân",
    timestamp: "10:15",
    inputTokens: 1250,
    outputTokens: 450,
    totalTokens: 1700,
    costUsd: 0.00035,
    latencyMs: 140,
    model: "openai/gpt-oss-120b",
    optimized: true,
  },
  {
    id: "sess_02",
    sessionTitle: "Backend Microservice FastAPI",
    timestamp: "10:45",
    inputTokens: 2400,
    outputTokens: 850,
    totalTokens: 3250,
    costUsd: 0.00042,
    latencyMs: 165,
    model: "openai/gpt-oss-120b",
    optimized: true,
  },
  {
    id: "sess_03",
    sessionTitle: "Tóm tắt Quy chế Học bổng OU",
    timestamp: "11:20",
    inputTokens: 3800,
    outputTokens: 600,
    totalTokens: 4400,
    costUsd: 0.00028,
    latencyMs: 120,
    model: "gpt-6-luna",
    optimized: true,
  },
  {
    id: "sess_04",
    sessionTitle: "Lịch thi học kỳ & Đăng ký",
    timestamp: "12:05",
    inputTokens: 450,
    outputTokens: 180,
    totalTokens: 630,
    costUsd: 0.00004,
    latencyMs: 75,
    model: "openai/gpt-oss-20b",
    optimized: true,
  },
  {
    id: "sess_05",
    sessionTitle: "Soạn thảo bài báo NCKH",
    timestamp: "13:30",
    inputTokens: 1950,
    outputTokens: 720,
    totalTokens: 2670,
    costUsd: 0.00038,
    latencyMs: 150,
    model: "openai/gpt-oss-120b",
    optimized: true,
  },
  {
    id: "sess_06",
    sessionTitle: "Dịch thuật học thuật song ngữ",
    timestamp: "14:15",
    inputTokens: 1600,
    outputTokens: 550,
    totalTokens: 2150,
    costUsd: 0.00018,
    latencyMs: 110,
    model: "gpt-6-luna",
    optimized: true,
  },
  {
    id: "sess_07",
    sessionTitle: "Hỏi đáp nội quy KTX",
    timestamp: "15:00",
    inputTokens: 520,
    outputTokens: 210,
    totalTokens: 730,
    costUsd: 0.00005,
    latencyMs: 70,
    model: "openai/gpt-oss-20b",
    optimized: true,
  },
  {
    id: "sess_08",
    sessionTitle: "Trích xuất thực thể hợp đồng",
    timestamp: "16:10",
    inputTokens: 3100,
    outputTokens: 480,
    totalTokens: 3580,
    costUsd: 0.00009,
    latencyMs: 85,
    model: "openai/gpt-oss-20b",
    optimized: true,
  },
];

interface TooltipState {
  metric: SessionUsageMetric;
  x: number;
  y: number;
}

export function TokenCostSpace3D({
  metrics,
  height = 420,
  className = "",
  interactive = true,
}: TokenCostSpace3DProps) {
  const locale = useLocale();
  const mountRef = useRef<HTMLDivElement>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [viewStyle, setViewStyle] = useState<"voxel" | "surface">("voxel");

  const dataList: SessionUsageMetric[] = useMemo(() => {
    if (metrics && metrics.length >= 3) {
      return metrics;
    }
    return DEMO_SESSION_METRICS;
  }, [metrics]);

  // Total summary calculations
  const totalTokensSum = useMemo(
    () => dataList.reduce((acc, m) => acc + m.totalTokens, 0),
    [dataList],
  );
  const totalCostSum = useMemo(
    () => dataList.reduce((acc, m) => acc + m.costUsd, 0),
    [dataList],
  );

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const w = container.clientWidth || 800;
    const h =
      typeof height === "number" ? height : container.clientHeight || 420;

    // 1. Scene & Camera Setup
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc); // Crisp OU light background

    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
    camera.position.set(3.2, 3.0, 3.8);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enableZoom = interactive;
    controls.enableRotate = interactive;
    controls.minDistance = 2.0;
    controls.maxDistance = 12.0;
    controls.target.set(0.8, 0.6, 0.8);

    // 2. Lighting System
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 1.3);
    dirLight.position.set(6, 12, 8);
    dirLight.castShadow = true;
    scene.add(dirLight);

    const accentLight = new THREE.DirectionalLight(0x005696, 1.2);
    accentLight.position.set(-5, -2, -5);
    scene.add(accentLight);

    // 3. Grid Helper on Floor (OU Navy & Slate)
    const gridSize = 2.4;
    const gridHelper = new THREE.GridHelper(gridSize, 12, 0x002f54, 0xe2e8f0);
    gridHelper.position.set(gridSize / 2, 0, gridSize / 2);
    scene.add(gridHelper);

    // 4. Axis Lines (X: Session, Y: Token Count, Z: Cost USD)
    const axisGroup = new THREE.Group();
    scene.add(axisGroup);
    const axisMat = new THREE.LineBasicMaterial({
      color: 0x002f54,
      linewidth: 2,
    });

    // X Axis
    const xGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(2.4, 0, 0),
    ]);
    axisGroup.add(new THREE.Line(xGeo, axisMat));

    // Y Axis (Tokens Up)
    const yGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 1.8, 0),
    ]);
    axisGroup.add(new THREE.Line(yGeo, axisMat));

    // Z Axis (Cost USD)
    const zGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, 2.4),
    ]);
    axisGroup.add(new THREE.Line(zGeo, axisMat));

    // 5. Data Normalization & Voxel Bar Generation
    const maxTokens = Math.max(...dataList.map((d) => d.totalTokens), 1000);
    const maxCost = Math.max(...dataList.map((d) => d.costUsd), 0.0005);

    const interactiveMeshes: { mesh: THREE.Mesh; data: SessionUsageMetric }[] =
      [];
    const peakPoints: THREE.Vector3[] = [];

    dataList.forEach((metric, index) => {
      // Coordinate mapping:
      // X = index across session sequence
      // Y = normalized token volume [0, 1.6]
      // Z = normalized cost [0, 2.0]
      const nx = 0.2 + (index / (dataList.length - 1 || 1)) * 2.0;
      const ny = Math.max(0.15, (metric.totalTokens / maxTokens) * 1.5);
      const nz = 0.2 + (metric.costUsd / maxCost) * 1.8;

      peakPoints.push(new THREE.Vector3(nx, ny, nz));

      // Bar color based on 3-model tier and cost efficiency
      const color =
        metric.model.includes("20b")
          ? 0x0284c7 // Sky Blue (GPT-OSS 20B)
          : metric.model.includes("luna")
            ? 0x6366f1 // Indigo (GPT-6 Luna)
            : 0x059669; // Emerald (GPT-OSS 120B)

      // Voxel Bar Column
      const barGeo = new THREE.BoxGeometry(0.12, ny, 0.12);
      const barMat = new THREE.MeshStandardMaterial({
        color,
        roughness: 0.2,
        metalness: 0.5,
        emissive: color,
        emissiveIntensity: 0.2,
      });

      const barMesh = new THREE.Mesh(barGeo, barMat);
      barMesh.position.set(nx, ny / 2, nz);
      barMesh.castShadow = true;
      scene.add(barMesh);

      // Top glowing cap
      const capGeo = new THREE.BoxGeometry(0.14, 0.04, 0.14);
      const capMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
      const capMesh = new THREE.Mesh(capGeo, capMat);
      capMesh.position.set(0, ny / 2 + 0.02, 0);
      barMesh.add(capMesh);

      interactiveMeshes.push({ mesh: barMesh, data: metric });
    });

    // 6. Surface Mesh Option (Connecting peaks)
    if (viewStyle === "surface" && peakPoints.length >= 3) {
      const curve = new THREE.CatmullRomCurve3(peakPoints);
      const tubeGeo = new THREE.TubeGeometry(curve, 32, 0.04, 8, false);
      const tubeMat = new THREE.MeshStandardMaterial({
        color: 0x005696,
        roughness: 0.2,
        metalness: 0.8,
      });
      const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
      scene.add(tubeMesh);
    }

    // 7. Raycasting for Tooltip Interaction
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleMouseMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(
        interactiveMeshes.map((im) => im.mesh),
        false,
      );

      if (intersects.length > 0) {
        const hit = interactiveMeshes.find(
          (im) => im.mesh === intersects[0].object,
        );
        if (hit) {
          const clampedX = Math.min(
            event.clientX - rect.left + 12,
            rect.width - 240,
          );
          const clampedY = Math.max(event.clientY - rect.top - 120, 12);
          setTooltip({
            metric: hit.data,
            x: clampedX,
            y: clampedY,
          });
          document.body.style.cursor = "pointer";
          return;
        }
      }
      setTooltip(null);
      document.body.style.cursor = "default";
    };

    const domEl = renderer.domElement;
    domEl.addEventListener("mousemove", handleMouseMove);

    // 8. Animation Loop
    let animId: number;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    // Resize Handler
    const handleResize = () => {
      if (!container) return;
      const width = container.clientWidth || 800;
      camera.aspect = width / h;
      camera.updateProjectionMatrix();
      renderer.setSize(width, h);
    };
    window.addEventListener("resize", handleResize);

    // Cleanup on unmount
    return () => {
      cancelAnimationFrame(animId);
      domEl.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("resize", handleResize);
      document.body.style.cursor = "default";
      controls.dispose();

      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else {
            obj.material?.dispose();
          }
        }
      });

      renderer.dispose();
      renderer.forceContextLoss();
      if (renderer.domElement.parentElement) {
        renderer.domElement.parentElement.removeChild(renderer.domElement);
      }
    };
  }, [dataList, height, interactive, viewStyle]);

  return (
    <div
      className={`token-cost-3d-card relative rounded-2xl border border-slate-200/90 bg-white p-4 shadow-sm ${className}`}
      style={{ fontFamily: "var(--font-roboto, sans-serif)" }}
    >
      {/* Card Header & Controls */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-100 pb-3 mb-2">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-sky-100 text-[#005696]">
            <Box size={18} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-900">
              Không gian Mật độ Token & Chi phí 3D (Token-Cost Space)
            </h3>
            <span className="text-xs text-slate-500">
              Trực quan hóa đa chiều (X: Phiên, Y: Lượng Token, Z: Chi phí USD)
            </span>
          </div>
        </div>

        {/* View Mode & Reset Controls */}
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5 text-xs">
            <button
              type="button"
              onClick={() => setViewStyle("voxel")}
              className={`rounded-md px-2.5 py-1 font-medium transition ${
                viewStyle === "voxel"
                  ? "bg-white text-[#005696] shadow-sm font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Voxel Bars
            </button>
            <button
              type="button"
              onClick={() => setViewStyle("surface")}
              className={`rounded-md px-2.5 py-1 font-medium transition ${
                viewStyle === "surface"
                  ? "bg-white text-[#005696] shadow-sm font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Mặt cong
            </button>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
            onClick={() => controlsRef.current?.reset()}
            title="Đặt lại góc quay"
          >
            <RotateCcw size={13} />
          </button>
        </div>
      </div>

      {/* Summary KPI Badges */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <div className="rounded-lg bg-slate-50 p-2 text-center border border-slate-100">
          <span className="text-[11px] text-slate-400 block">
            {locale === "en" ? "Sessions Tracked" : "Số phiên theo dõi"}
          </span>
          <strong className="text-sm font-bold text-slate-800">
            {dataList.length} {locale === "en" ? "sessions" : "phiên"}
          </strong>
        </div>
        <div className="rounded-lg bg-slate-50 p-2 text-center border border-slate-100">
          <span className="text-[11px] text-slate-400 block">
            {locale === "en" ? "Total Tokens" : "Tổng Tokens"}
          </span>
          <strong className="text-sm font-bold text-sky-700">
            {totalTokensSum.toLocaleString()} tok
          </strong>
        </div>
        <div className="rounded-lg bg-slate-50 p-2 text-center border border-slate-100">
          <span className="text-[11px] text-slate-400 block">
            {locale === "en" ? "Cumulative Cost" : "Chi phí tích luỹ"}
          </span>
          <strong className="text-sm font-bold text-emerald-600">
            ${totalCostSum.toFixed(5)}
          </strong>
        </div>
        <div className="rounded-lg bg-slate-50 p-2 text-center border border-slate-100">
          <span className="text-[11px] text-slate-400 block">
            {locale === "en" ? "Average Savings" : "Tiết kiệm trung bình"}
          </span>
          <strong className="text-sm font-bold text-indigo-600">54.2%</strong>
        </div>
      </div>

      {/* 3D WebGL Canvas Container */}
      <div className="relative w-full rounded-xl overflow-hidden border border-slate-100 bg-[#f8fafc]">
        <div
          ref={mountRef}
          className="w-full"
          style={{
            height: typeof height === "number" ? `${height}px` : height,
          }}
        />

        {/* Legend */}
        <div className="absolute bottom-2 left-3 flex flex-wrap items-center gap-3 rounded-lg bg-white/85 px-3 py-1.5 text-[11px] backdrop-blur-sm border border-slate-200/60 shadow-sm pointer-events-none">
          <div className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-slate-600">Free Tier ($0.0)</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-sky-500" />
            <span className="text-slate-600">&lt; $0.0003</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-indigo-500" />
            <span className="text-slate-600">&ge; $0.0003</span>
          </div>
        </div>

        {/* Hover Tooltip Overlay */}
        {tooltip && (
          <div
            className="pointer-events-none absolute z-20 rounded-xl border border-slate-200/90 bg-white/95 p-3 text-xs shadow-xl backdrop-blur-md transition-all duration-75"
            style={{
              left: tooltip.x,
              top: tooltip.y,
              minWidth: 220,
            }}
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-1.5 mb-1.5">
              <strong className="text-slate-900 font-bold truncate max-w-[150px]">
                {tooltip.metric.sessionTitle}
              </strong>
              <span className="text-[11px] text-slate-400">
                {tooltip.metric.timestamp}
              </span>
            </div>
            <div className="space-y-1 text-slate-600 text-[11px]">
              <div className="flex justify-between">
                <span>
                  {locale === "en" ? "Total Tokens:" : "Tổng Tokens:"}
                </span>
                <strong className="text-slate-900">
                  {tooltip.metric.totalTokens.toLocaleString()}
                </strong>
              </div>
              <div className="flex justify-between">
                <span>(In / Out):</span>
                <span>
                  {tooltip.metric.inputTokens} / {tooltip.metric.outputTokens}
                </span>
              </div>
              <div className="flex justify-between">
                <span>{locale === "en" ? "Cost USD:" : "Chi phí USD:"}</span>
                <strong className="text-emerald-600 font-semibold">
                  {tooltip.metric.costUsd === 0
                    ? locale === "en"
                      ? "Free ($0.00)"
                      : "Miễn phí ($0.00)"
                    : `$${tooltip.metric.costUsd.toFixed(5)}`}
                </strong>
              </div>
              <div className="flex justify-between">
                <span>{locale === "en" ? "Latency:" : "Độ trễ:"}</span>
                <span>{tooltip.metric.latencyMs} ms</span>
              </div>
              <div className="flex justify-between border-t border-slate-100 pt-1 mt-1">
                <span>{locale === "en" ? "Model:" : "Mô hình:"}</span>
                <span className="font-mono text-[10px] text-[#005696]">
                  {tooltip.metric.model}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
