"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export interface AttentionWeights {
  math?: number;
  code?: number;
  reasoning?: number;
  extraction?: number;
  writing?: number;
  multilingual?: number;
  [key: string]: number | undefined;
}

export interface DimensionScore {
  name: string;
  score: number;
}

export interface ModelNodeDef {
  id: string;
  name: string;
  provider: "groq" | "huggingface" | "openrouter" | "openai" | "baseline";
  isFree?: boolean;
  position: [number, number, number];
  color: number;
}

export interface NeuralRoutingCosmos3DProps {
  attention?: AttentionWeights | number[] | null;
  dimensions?: DimensionScore[];
  routedModel?: string | null;
  routedModelId?: string | null;
  isRouting?: boolean;
  onSelectModel?: (modelId: string) => void;
  className?: string;
  height?: number | string;
  width?: number | string;
  interactive?: boolean;
  compact?: boolean;
}

const DEFAULT_MODELS: ModelNodeDef[] = [
  {
    id: "groq/llama-3.3-70b",
    name: "Groq Llama 3.3 70B",
    provider: "groq",
    isFree: true,
    position: [2.5, 0.7, -0.6],
    color: 0x0284c7, // Sky Blue
  },
  {
    id: "groq/qwen-2.5-coder-32b",
    name: "Groq Qwen 2.5 Coder",
    provider: "groq",
    isFree: true,
    position: [1.6, -1.4, 1.5],
    color: 0x6366f1, // Indigo
  },
  {
    id: "huggingface/serverless",
    name: "HF Serverless",
    provider: "huggingface",
    isFree: true,
    position: [-1.5, 1.9, -0.8],
    color: 0xf59e0b, // Amber
  },
  {
    id: "openrouter/free",
    name: "OpenRouter :free",
    provider: "openrouter",
    isFree: true,
    position: [-2.4, -0.8, 0.9],
    color: 0x10b981, // Emerald
  },
  {
    id: "openai/gpt-4o-mini",
    name: "GPT-4o Mini",
    provider: "openai",
    isFree: false,
    position: [0.6, 2.3, 1.2],
    color: 0x005696, // OU Blue
  },
  {
    id: "foundation-reference",
    name: "Baseline Reference",
    provider: "baseline",
    isFree: false,
    position: [-0.8, -2.2, -1.2],
    color: 0x64748b, // Slate
  },
];

const ATTENTION_KEYS = [
  {
    key: "math",
    label: "Toán (Math)",
    color: 0x38bdf8,
    hex: "#38bdf8",
    defaultPos: [0, 1.25, 0.45] as [number, number, number],
  },
  {
    key: "code",
    label: "Lập trình (Code)",
    color: 0x818cf8,
    hex: "#818cf8",
    defaultPos: [1.15, 0.5, 0.55] as [number, number, number],
  },
  {
    key: "reasoning",
    label: "Lý luận (Reasoning)",
    color: 0xa78bfa,
    hex: "#a78bfa",
    defaultPos: [0.85, -0.8, 0.5] as [number, number, number],
  },
  {
    key: "extraction",
    label: "Trích xuất (Extraction)",
    color: 0x34d399,
    hex: "#34d399",
    defaultPos: [-0.85, -0.8, 0.5] as [number, number, number],
  },
  {
    key: "writing",
    label: "Viết lách (Writing)",
    color: 0xfbbf24,
    hex: "#fbbf24",
    defaultPos: [-1.15, 0.5, 0.55] as [number, number, number],
  },
  {
    key: "multilingual",
    label: "Đa ngữ (Multilingual)",
    color: 0xf472b6,
    hex: "#f472b6",
    defaultPos: [0, -0.35, -1.2] as [number, number, number],
  },
];

function createGlowTexture(colorHex: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    gradient.addColorStop(0, colorHex);
    gradient.addColorStop(0.3, colorHex + "aa");
    gradient.addColorStop(0.7, colorHex + "33");
    gradient.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 64, 64);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

function createTextSprite(
  text: string,
  bgColor: string = "rgba(0,47,84,0.75)",
  textColor: string = "#ffffff",
): THREE.Sprite {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = bgColor;
    ctx.beginPath();
    ctx.roundRect(8, 12, 240, 40, 8);
    ctx.fill();

    ctx.strokeStyle = "rgba(255, 255, 255, 0.25)";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.fillStyle = textColor;
    ctx.font = "bold 20px Roboto, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, 128, 32);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const material = new THREE.SpriteMaterial({
    map: texture,
    transparent: true,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(1.4, 0.35, 1);
  return sprite;
}

export function NeuralRoutingCosmos3D({
  attention,
  dimensions,
  routedModel,
  routedModelId,
  isRouting = false,
  onSelectModel,
  className = "",
  height = 360,
  width = "100%",
  interactive = true,
  compact = false,
}: NeuralRoutingCosmos3DProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const hoveredNodeRef = useRef<string | null>(null);
  const [, setHoveredNodeState] = useState<string | null>(null);

  // Normalize attention values into array of 6 numbers
  const scores: number[] = React.useMemo(() => {
    if (Array.isArray(attention)) {
      const arr = [0, 0, 0, 0, 0, 0];
      for (let i = 0; i < 6; i++) {
        arr[i] =
          typeof attention[i] === "number"
            ? Math.max(0, Math.min(1, attention[i]))
            : 0.5;
      }
      return arr;
    }
    if (dimensions && dimensions.length > 0) {
      const map = new Map(
        dimensions.map((d) => [d.name.toLowerCase(), d.score]),
      );
      return ATTENTION_KEYS.map((k) => map.get(k.key) ?? 0.5);
    }
    if (attention && typeof attention === "object") {
      return ATTENTION_KEYS.map((k) => {
        const val = attention[k.key] ?? attention[`task_attention_${k.key}`];
        return typeof val === "number" ? Math.max(0, Math.min(1, val)) : 0.5;
      });
    }
    return [0.65, 0.8, 0.55, 0.45, 0.6, 0.7]; // default well-rounded balance
  }, [attention, dimensions]);

  const targetModelId =
    routedModel ?? routedModelId ?? (isRouting ? null : "groq/llama-3.3-70b");

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // Dimensions
    const w =
      container.clientWidth || (typeof width === "number" ? width : 600);
    const h =
      container.clientHeight || (typeof height === "number" ? height : 360);

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc); // Crisp OU light background

    const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
    camera.position.set(0, 2.8, compact ? 4.8 : 4.4);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
    container.appendChild(renderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.enableZoom = interactive;
    controls.enableRotate = interactive;
    controls.minDistance = 2.0;
    controls.maxDistance = 8.0;

    // Track dirty state for event-driven rendering (0% idle GPU usage)
    let isDirty = true;
    let isBeamAnimating = true;
    let animationFrameId: number;
    let beamProgress = 0;
    let rippleScale = 0;

    const requestRender = () => {
      isDirty = true;
    };
    controls.addEventListener("change", requestRender);

    // 2. Ambient & Directional Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
    scene.add(ambientLight);

    const mainLight = new THREE.DirectionalLight(0xffffff, 1.5);
    mainLight.position.set(5, 10, 7);
    scene.add(mainLight);

    const blueRimLight = new THREE.DirectionalLight(0x005696, 2.0);
    blueRimLight.position.set(-5, -3, -5);
    scene.add(blueRimLight);

    // 3. Central Prompt Core at (0, 0, 0)
    const coreGroup = new THREE.Group();
    scene.add(coreGroup);

    // Inner prompt glowing sphere
    const coreGeo = new THREE.SphereGeometry(0.3, 32, 32);
    const coreMat = new THREE.MeshStandardMaterial({
      color: 0x005696,
      emissive: 0x0284c7,
      emissiveIntensity: 0.8,
      roughness: 0.2,
      metalness: 0.9,
    });
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    coreGroup.add(coreMesh);

    // Outer wireframe dodecahedron
    const dodecaGeo = new THREE.DodecahedronGeometry(0.48, 0);
    const dodecaMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      wireframe: true,
      transparent: true,
      opacity: 0.5,
    });
    const dodecaMesh = new THREE.Mesh(dodecaGeo, dodecaMat);
    coreGroup.add(dodecaMesh);

    // Prompt core label
    const coreSprite = createTextSprite(
      "Prompt Core",
      "rgba(0, 47, 84, 0.85)",
      "#e0f2fe",
    );
    coreSprite.position.set(0, -0.55, 0);
    coreSprite.scale.set(1.0, 0.25, 1);
    coreGroup.add(coreSprite);

    // 4. 6-Dimensional Attention Constellation
    const constellationGroup = new THREE.Group();
    scene.add(constellationGroup);

    const starGeo = new THREE.SphereGeometry(0.09, 16, 16);
    const starMeshes: THREE.Mesh[] = [];
    const starPositions: THREE.Vector3[] = [];

    ATTENTION_KEYS.forEach((dim, idx) => {
      const score = scores[idx] ?? 0.5;
      const radiusFactor = 0.75 + score * 0.7; // score scales distance
      const [dx, dy, dz] = dim.defaultPos;
      const pos = new THREE.Vector3(
        dx * radiusFactor,
        dy * radiusFactor,
        dz * radiusFactor,
      );
      starPositions.push(pos);

      const starMat = new THREE.MeshStandardMaterial({
        color: dim.color,
        emissive: dim.color,
        emissiveIntensity: 0.7 + score * 0.5,
        roughness: 0.2,
        metalness: 0.8,
      });
      const star = new THREE.Mesh(starGeo, starMat);
      star.position.copy(pos);
      star.userData = { isStar: true, dim, score };
      constellationGroup.add(star);
      starMeshes.push(star);

      // Star label sprite
      const starSprite = createTextSprite(
        `${dim.label.split(" ")[0]} ${(score * 100).toFixed(0)}%`,
        "rgba(15, 23, 42, 0.85)",
        dim.hex,
      );
      starSprite.position.set(pos.x, pos.y + 0.22, pos.z);
      starSprite.scale.set(0.9, 0.22, 1);
      constellationGroup.add(starSprite);
    });

    // Connecting lines of the attention polyhedron
    const polyLineIndices = [
      [0, 1],
      [1, 2],
      [2, 3],
      [3, 4],
      [4, 0], // Outer loop
      [0, 5],
      [1, 5],
      [2, 5],
      [3, 5],
      [4, 5], // Connecting to bottom vertex 5
      [0, 2],
      [1, 3],
      [2, 4],
      [3, 0],
      [4, 1], // Cross diagonals
    ];
    const polyPoints: THREE.Vector3[] = [];
    polyLineIndices.forEach(([i, j]) => {
      polyPoints.push(starPositions[i], starPositions[j]);
    });
    const polyGeo = new THREE.BufferGeometry().setFromPoints(polyPoints);
    const polyMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.35,
    });
    const polyLines = new THREE.LineSegments(polyGeo, polyMat);
    constellationGroup.add(polyLines);

    // 5. Candidate Model Nodes (in orbital galaxy shell)
    const modelsGroup = new THREE.Group();
    scene.add(modelsGroup);

    const modelGeo = new THREE.SphereGeometry(0.14, 24, 24);
    const modelMeshes: THREE.Mesh[] = [];
    const modelRingMeshes: THREE.Mesh[] = [];

    // Subtle orbital ring representing the model registry
    const orbitRingGeo = new THREE.RingGeometry(2.38, 2.42, 64);
    const orbitRingMat = new THREE.MeshBasicMaterial({
      color: 0x005696,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.15,
    });
    const orbitRing = new THREE.Mesh(orbitRingGeo, orbitRingMat);
    orbitRing.rotation.x = Math.PI / 2.3;
    modelsGroup.add(orbitRing);

    DEFAULT_MODELS.forEach((model) => {
      const isTarget = targetModelId
        ? model.id.includes(targetModelId) || targetModelId.includes(model.id)
        : false;
      const modelMat = new THREE.MeshStandardMaterial({
        color: isTarget ? 0x0284c7 : model.color,
        emissive: isTarget ? 0x0284c7 : 0x002f54,
        emissiveIntensity: isTarget ? 1.0 : 0.3,
        roughness: 0.25,
        metalness: 0.85,
      });

      const mesh = new THREE.Mesh(modelGeo, modelMat);
      mesh.position.set(...model.position);
      mesh.userData = { isModel: true, model };
      modelsGroup.add(mesh);
      modelMeshes.push(mesh);

      // Selection indicator halo ring
      const haloGeo = new THREE.RingGeometry(0.2, 0.24, 32);
      const haloMat = new THREE.MeshBasicMaterial({
        color: isTarget ? 0x38bdf8 : 0x94a3b8,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: isTarget ? 0.9 : 0.2,
      });
      const halo = new THREE.Mesh(haloGeo, haloMat);
      halo.position.set(...model.position);
      halo.lookAt(camera.position);
      modelsGroup.add(halo);
      modelRingMeshes.push(halo);

      // Model label sprite
      const labelText = `${model.isFree ? "⚡ " : ""}${model.name}`;
      const sprite = createTextSprite(
        labelText,
        isTarget ? "rgba(0, 86, 150, 0.95)" : "rgba(15, 23, 42, 0.8)",
        isTarget ? "#ffffff" : "#cbd5e1",
      );
      sprite.position.set(
        model.position[0],
        model.position[1] + 0.3,
        model.position[2],
      );
      modelsGroup.add(sprite);
    });

    // 6. Cubic-Bezier Energy Particle Beam to Target Model Node
    const beamGroup = new THREE.Group();
    scene.add(beamGroup);

    // Identify target model position
    const resolvedTarget =
      DEFAULT_MODELS.find(
        (m) =>
          targetModelId &&
          (m.id.includes(targetModelId) || targetModelId.includes(m.id)),
      ) || DEFAULT_MODELS[0];

    const targetPos = new THREE.Vector3(...resolvedTarget.position);
    const startPos = new THREE.Vector3(0, 0, 0);

    // Determine the dominant attention vector to curve towards
    let maxIdx = 0;
    scores.forEach((s, idx) => {
      if (s > (scores[maxIdx] ?? 0)) maxIdx = idx;
    });
    const dominantStarPos = starPositions[maxIdx] || new THREE.Vector3(0, 1, 0);

    // Control points for smooth 3D cubic Bezier
    const cp1 = dominantStarPos.clone().multiplyScalar(1.1);
    const cp2 = targetPos
      .clone()
      .multiplyScalar(0.7)
      .add(new THREE.Vector3(0, 0.4, 0));

    const curve = new THREE.CubicBezierCurve3(startPos, cp1, cp2, targetPos);

    // Glow line along curve path
    const curvePoints = curve.getPoints(60);
    const curveGeo = new THREE.BufferGeometry().setFromPoints(curvePoints);
    const curveMat = new THREE.LineBasicMaterial({
      color: 0x38bdf8,
      transparent: true,
      opacity: 0.6,
      linewidth: 2,
    });
    const curveLine = new THREE.Line(curveGeo, curveMat);
    beamGroup.add(curveLine);

    // Flowing particles along the curve
    const PARTICLE_COUNT = 45;
    const particleGeo = new THREE.BufferGeometry();
    const particlePositions = new Float32Array(PARTICLE_COUNT * 3);
    const particleColors = new Float32Array(PARTICLE_COUNT * 3);
    const glowTexture = createGlowTexture("#38bdf8");

    const particleMat = new THREE.PointsMaterial({
      size: 0.18,
      map: glowTexture,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      vertexColors: true,
    });

    const particles = new THREE.Points(particleGeo, particleMat);
    beamGroup.add(particles);

    // Impact ripple ring at target node
    const rippleGeo = new THREE.RingGeometry(0.1, 0.16, 32);
    const rippleMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.8,
    });
    const rippleMesh = new THREE.Mesh(rippleGeo, rippleMat);
    rippleMesh.position.copy(targetPos);
    beamGroup.add(rippleMesh);

    // 7. Raycasting for Model Selection and Hover Tooltip
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    const onPointerMove = (event: MouseEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(modelMeshes);

      if (intersects.length > 0) {
        const hit = intersects[0].object.userData?.model?.id;
        if (hit && hit !== hoveredNodeRef.current) {
          hoveredNodeRef.current = hit;
          setHoveredNodeState(hit);
          renderer.domElement.style.cursor = "pointer";
          isDirty = true;
        }
      } else {
        if (hoveredNodeRef.current !== null) {
          hoveredNodeRef.current = null;
          setHoveredNodeState(null);
          renderer.domElement.style.cursor = "default";
          isDirty = true;
        }
      }
    };

    const onClick = (event: MouseEvent) => {
      if (!onSelectModel) return;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      raycaster.setFromCamera(pointer, camera);
      const intersects = raycaster.intersectObjects(modelMeshes);
      if (intersects.length > 0) {
        const hit = intersects[0].object.userData?.model?.id;
        if (hit) onSelectModel(hit);
      }
    };

    if (interactive) {
      renderer.domElement.addEventListener("mousemove", onPointerMove);
      renderer.domElement.addEventListener("click", onClick);
    }

    // 8. Event-Driven Dirty Animation Loop
    let lastTime = performance.now();
    let totalBeamCycles = 0;

    const animate = (time: number) => {
      animationFrameId = requestAnimationFrame(animate);

      const delta = (time - lastTime) / 1000;
      lastTime = time;

      // When routing is active or beam is animating, advance particles
      if (isBeamAnimating || isRouting) {
        beamProgress += delta * 1.25;
        if (beamProgress > 1.0) {
          beamProgress -= 1.0;
          totalBeamCycles++;
          // When not explicitly in continuous routing, gracefully settle after 3 full energy pulses
          if (!isRouting && totalBeamCycles > 3) {
            isBeamAnimating = false;
          }
        }

        // Update flowing particles
        for (let i = 0; i < PARTICLE_COUNT; i++) {
          const t = (beamProgress + i / PARTICLE_COUNT) % 1.0;
          const pt = curve.getPoint(t);
          particlePositions[i * 3] = pt.x;
          particlePositions[i * 3 + 1] = pt.y;
          particlePositions[i * 3 + 2] = pt.z;

          // Gradient color: OU Blue (start) -> Sky Blue -> Cyan (end)
          const r = 0.0 + 0.2 * t;
          const g = 0.35 + 0.55 * t;
          const b = 0.6 + 0.4 * t;
          particleColors[i * 3] = r;
          particleColors[i * 3 + 1] = g;
          particleColors[i * 3 + 2] = b;
        }
        particleGeo.setAttribute(
          "position",
          new THREE.BufferAttribute(particlePositions, 3),
        );
        particleGeo.setAttribute(
          "color",
          new THREE.BufferAttribute(particleColors, 3),
        );
        particleGeo.attributes.position.needsUpdate = true;
        particleGeo.attributes.color.needsUpdate = true;

        // Animate prompt core rotation and breathing scale
        coreGroup.rotation.y += delta * 0.4;
        dodecaMesh.rotation.x += delta * 0.2;
        const breath = 1.0 + Math.sin(time * 0.005) * 0.06;
        coreMesh.scale.set(breath, breath, breath);

        // Ripple expansion at target node
        rippleScale = (rippleScale + delta * 1.5) % 1.0;
        rippleMesh.scale.set(
          1.0 + rippleScale * 1.8,
          1.0 + rippleScale * 1.8,
          1.0,
        );
        (rippleMat as THREE.MeshBasicMaterial).opacity = Math.max(
          0,
          0.9 - rippleScale * 0.9,
        );
        rippleMesh.lookAt(camera.position);

        // Always render during active beam
        isDirty = true;
      }

      // Check dirty flag: render only when necessary (0% idle GPU usage)
      if (isDirty) {
        controls.update();

        // Keep model halos facing camera
        modelRingMeshes.forEach((m) => m.lookAt(camera.position));

        renderer.render(scene, camera);
        if (!isBeamAnimating && !isRouting) {
          isDirty = false;
        }
      }
    };

    animate(performance.now());

    // 9. Resize Observer for dynamic container sizing
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

    // 10. Comprehensive WebGL Cleanup on Unmount (Zero VRAM Leak)
    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      controls.removeEventListener("change", requestRender);
      controls.dispose();

      if (interactive) {
        renderer.domElement.removeEventListener("mousemove", onPointerMove);
        renderer.domElement.removeEventListener("click", onClick);
      }

      // Traverse and dispose all scene resources
      scene.traverse((obj) => {
        if (
          obj instanceof THREE.Mesh ||
          obj instanceof THREE.Line ||
          obj instanceof THREE.Points ||
          obj instanceof THREE.Sprite
        ) {
          obj.geometry?.dispose();
          if (Array.isArray(obj.material)) {
            obj.material.forEach((m) => m.dispose());
          } else if (obj.material) {
            obj.material.dispose();
          }
        }
      });

      glowTexture.dispose();
      renderer.dispose();
      renderer.forceContextLoss(); // Guarantees browser revokes WebGL context immediately

      if (
        container &&
        renderer.domElement &&
        container.contains(renderer.domElement)
      ) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [
    scores,
    targetModelId,
    isRouting,
    interactive,
    compact,
    width,
    height,
    onSelectModel,
  ]);

  return (
    <div
      className={`cosmos-3d-wrapper relative overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/70 shadow-sm ${className}`}
      style={{ height, width }}
    >
      {/* 3D Canvas Mount Point */}
      <div ref={mountRef} className="h-full w-full" />

      {/* Floating Glassmorphism Brand Capsule */}
      <div className="cosmos-overlay-header pointer-events-none absolute top-3 left-3 z-10 flex items-center gap-2 rounded-xl border border-white/80 bg-white/85 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm backdrop-blur-md">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[#005696]" />
        <span>NEURAL ROUTING COSMOS 3D</span>
        {isRouting && (
          <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-bold text-sky-800">
            DISPATCHING...
          </span>
        )}
      </div>

      {/* Routed Target Model Indicator Badge */}
      <div className="cosmos-overlay-target pointer-events-none absolute top-3 right-3 z-10 rounded-xl border border-sky-200/90 bg-sky-50/90 px-3 py-1.5 text-xs text-sky-950 shadow-sm backdrop-blur-md">
        <span className="text-[10px] font-medium text-slate-500 uppercase tracking-wider block">
          Mô hình đích
        </span>
        <strong className="font-semibold text-[#005696]">
          {targetModelId ?? "Đang phân tích..."}
        </strong>
      </div>

      {/* Interactive Legend Footnote */}
      <div className="cosmos-overlay-footer pointer-events-none absolute bottom-2.5 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[#005696]" /> Core Prompt
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[#38bdf8]" /> 6D Attention
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-[#10b981]" /> Model Nodes
          </span>
        </div>
        <span className="hidden sm:inline text-slate-400">
          Kéo xoay 360° · Cuộn để phóng to
        </span>
      </div>
    </div>
  );
}

export default NeuralRoutingCosmos3D;
