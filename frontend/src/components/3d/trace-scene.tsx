"use client";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  PIPELINE,
  pipelineState,
  callPaths,
  type Execution,
  type RuntimeModel,
} from "@/lib/execution-view";

const COLORS = [0x0284c7, 0x005696, 0x10b981];
const STATUS: Record<string, number> = {
  unknown: 0x94a3b8,
  skipped: 0xcbd5e1,
  succeeded: 0x10b981,
  running: 0x0284c7,
  failed: 0xef4444,
  interrupted: 0xf59e0b,
};

function label(text: string, pillColor: string = "rgba(0, 47, 84, 0.85)", textColor: string = "#ffffff") {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 140;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, 1024, 140);

  // Elegant rounded pill container with subtle glow border
  ctx.fillStyle = pillColor;
  ctx.beginPath();
  ctx.roundRect(16, 16, 992, 108, 24);
  ctx.fill();

  ctx.strokeStyle = "rgba(255, 255, 255, 0.25)";
  ctx.lineWidth = 4;
  ctx.stroke();

  ctx.font = "bold 44px Roboto, sans-serif";
  ctx.fillStyle = textColor;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, 512, 70, 960);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, depthTest: false, transparent: true }),
  );
  sprite.scale.set(3.7, 0.5, 1);
  return sprite;
}

export function TraceScene({
  mode,
  models,
  execution,
  locale,
  motion,
  simulation = false,
}: {
  mode: "routing" | "architecture";
  models: RuntimeModel[];
  execution?: Execution;
  locale: string;
  motion: boolean;
  simulation?: boolean;
}) {
  const mount = useRef<HTMLDivElement>(null);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const host = mount.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return;
    } // HTML below remains the complete accessible representation.
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc);
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(
      mode === "routing" ? 0 : 6,
      mode === "routing" ? 2 : 3,
      mode === "routing" ? 13 : 16,
    );
    camera.lookAt(0, 0, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    host.append(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.minDistance = 7;
    controls.maxDistance = 25;
    scene.add(new THREE.AmbientLight(0xffffff, 2));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(4, 8, 10);
    scene.add(light);
    const line = (a: THREE.Vector3, b: THREE.Vector3, color: number) => {
      const geometry = new THREE.BufferGeometry().setFromPoints([a, b]);
      scene.add(
        new THREE.Line(geometry, new THREE.LineBasicMaterial({ color })),
      );
    };
    const pulsers: THREE.Mesh[] = [];
    const demoBlocks: THREE.Mesh<
      THREE.BoxGeometry,
      THREE.MeshStandardMaterial
    >[] = [];
    const flowParticles: THREE.Mesh[] = [];
    if (mode === "routing") {
      const origin = new THREE.Vector3(0, 2.4, 0);
      const router = new THREE.Mesh(
        new THREE.BoxGeometry(0.7, 0.7, 0.7),
        new THREE.MeshStandardMaterial({ color: 0x005696 }),
      );
      router.position.copy(origin);
      scene.add(router);
      const title = label("ML + Attention");
      title.position.set(0, 3.2, 0);
      scene.add(title);
      const paths = callPaths(execution, models);
      // Exactly the backend catalog's three current model planets. A legacy
      // trace never injects an extra planet or guesses an alias/provider.
      models.slice(0, 3).forEach((model, i) => {
        const position = new THREE.Vector3(
          (i - 1) * 3.6,
          -0.2,
          i === 1 ? 0.65 : 0,
        );
        const selected =
          execution?.status === "succeeded" &&
          execution.route?.model_id === model.model_id;
        const material = new THREE.MeshStandardMaterial({
          color: COLORS[i],
          roughness: 0.4,
          emissive: selected ? COLORS[i] : 0,
          emissiveIntensity: selected ? 0.35 : 0,
        });
        const planet = new THREE.Mesh(
          new THREE.SphereGeometry(selected ? 0.75 : 0.6, 28, 20),
          material,
        );
        planet.position.copy(position);
        scene.add(planet);
        if (selected) pulsers.push(planet);
        const text = label(model.label);
        text.position.copy(position).add(new THREE.Vector3(0, -1.25, 0));
        text.scale.multiplyScalar(0.8);
        scene.add(text);
        const provider = label(
          model.provider === "openai" ? "OpenAI" : "OpenRouter",
        );
        provider.position.copy(position).add(new THREE.Vector3(0, -1.8, 0));
        provider.scale.multiplyScalar(0.6);
        scene.add(provider);
        const used = paths.filter((p) => p.model?.model_id === model.model_id);
        if (used.length)
          line(
            origin,
            position,
            used.every((p) => p.failed) ? STATUS.failed : COLORS[i],
          );
      });
    } else {
      PIPELINE.forEach((step, i) => {
        const y = 4.2 - i * 1.4;
        const state = simulation
          ? "unknown"
          : pipelineState(execution, step.events);
        const block = new THREE.Mesh(
          new THREE.BoxGeometry(5.6, 0.8, 0.65),
          new THREE.MeshStandardMaterial({
            color: STATUS[state],
            transparent: true,
            opacity: 0.75,
          }),
        );
        block.position.set(0, y, 0);
        scene.add(block);
        if (simulation) demoBlocks.push(block);
        if (state === "running") pulsers.push(block);
        const text = label(`${i + 1}. ${locale === "en" ? step.en : step.vi}`);
        text.position.set(0, y, 0.5);
        text.scale.set(5.3, 0.66, 1);
        scene.add(text);
        if (i < PIPELINE.length - 1)
          line(
            new THREE.Vector3(0, y - 0.4, 0),
            new THREE.Vector3(0, y - 1, 0),
            0x005696,
          );
      });
      if (simulation) {
        for (let i = 0; i < 9; i++) {
          const particle = new THREE.Mesh(
            new THREE.SphereGeometry(0.065, 8, 6),
            new THREE.MeshBasicMaterial({ color: 0x0284c7 }),
          );
          particle.position.set(0, 4.6 - i, 0.9);
          scene.add(particle);
          flowParticles.push(particle);
        }
      }
    }
    const draw = () => renderer.render(scene, camera);
    const resize = () => {
      const width = host.clientWidth || 600;
      const height = mode === "routing" ? 310 : 480;
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      draw();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    controls.addEventListener("change", draw);
    let frame = 0,
      visible = true;
    let lastDraw = 0;
    const canAnimate = () =>
      visible &&
      !document.hidden &&
      motion &&
      (simulation || execution?.status === "running");
    const animate = (now: number) => {
      if (!canAnimate()) {
        frame = 0;
        return;
      }
      frame = requestAnimationFrame(animate);
      if (now - lastDraw < 1000 / 30) return;
      lastDraw = now;
      if (simulation) {
        const active = Math.floor(now / 1300) % PIPELINE.length;
        host.dataset.flowStage = String(active + 1);
        demoBlocks.forEach((block, index) => {
          block.material.color.setHex(
            index === active
              ? STATUS.running
              : index < active
                ? STATUS.succeeded
                : STATUS.unknown,
          );
          block.material.emissive.setHex(index === active ? 0x005696 : 0);
          block.material.emissiveIntensity = index === active ? 0.25 : 0;
        });
        flowParticles.forEach((particle, index) => {
          const progress = (now / 9100 + index / flowParticles.length) % 1;
          particle.position.set(
            0.15 * Math.sin(progress * Math.PI * 14),
            4.7 - progress * 9.4,
            0.9,
          );
        });
      }
      pulsers.forEach((mesh) =>
        mesh.scale.setScalar(1 + 0.035 * Math.sin(now / 250)),
      );
      draw();
    };
    const visibility = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      host.dataset.animationState = canAnimate() ? "running" : "paused";
      if (canAnimate()) frame = requestAnimationFrame(animate);
    };
    const intersection = new IntersectionObserver((entries) => {
      visible = entries[0]?.isIntersecting ?? false;
      visibility();
    });
    intersection.observe(host);
    const lost = (event: Event) => {
      event.preventDefault();
      cancelAnimationFrame(frame);
      setUnavailable(true);
    };
    renderer.domElement.addEventListener("webglcontextlost", lost);
    document.addEventListener("visibilitychange", visibility);
    resize();
    visibility();
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      intersection.disconnect();
      document.removeEventListener("visibilitychange", visibility);
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      controls.removeEventListener("change", draw);
      controls.dispose();
      scene.traverse((object) => {
        const item = object as THREE.Mesh;
        item.geometry?.dispose();
        const materials = item.material
          ? Array.isArray(item.material)
            ? item.material
            : [item.material]
          : [];
        for (const material of materials) {
          (material as THREE.SpriteMaterial).map?.dispose();
          material.dispose();
        }
      });
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [mode, models, execution, locale, motion, simulation]);
  return (
    <div
      className="trace-scene"
      data-simulation={simulation ? "true" : "false"}
      ref={mount}
      aria-hidden="true"
      hidden={unavailable}
    />
  );
}
