"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { useLocale } from "next-intl";
import katex from "katex";
import {
  Play,
  Pause,
  RotateCcw,
  Layers,
  Database,
  Cpu,
  TrendingDown,
  Zap,
  Server,
  Binary,
  BarChart3,
  Send,
  ChevronRight,
  ChevronLeft,
  Eye,
} from "lucide-react";

export interface CandidateTokenLogit {
  token: string;
  prob: number;
  isWinner: boolean;
}

export interface PipelineSimulationPreset {
  id: string;
  name: string;
  category: string;
  prompt: string;
  inputTokens: number;
  memorySlotsHit: number;
  memoryFact: string;
  compactedTokens: number;
  compactionPct: number;
  attentionScores: {
    math: number;
    code: number;
    reasoning: number;
    extraction: number;
    writing: number;
    multilingual: number;
  };
  winnerModelId: string;
  winnerModelName: string;
  estimatedLatencyMs: number;
  estimatedCostUsd: number;
  winnerToken: string;
  candidateTokens: CandidateTokenLogit[];
  transformerHeads: number;
  mlpExpansion: string;
}

export const SIMULATION_PRESETS: PipelineSimulationPreset[] = [
  {
    id: "math_advanced",
    name: "Toán Cao Cấp & Vi Tích Phân Đa Bước (Advanced Calculus)",
    category: "Frontier Reasoning / Math",
    prompt:
      "Tính tích phân bội hai của hàm f(x,y) = x^2 * exp(-y) trên miền giới hạn D và chứng minh sự hội tụ theo tiêu chuẩn Weierstrass.",
    inputTokens: 1680,
    memorySlotsHit: 3,
    memoryFact: "Ký ức: Người dùng yêu cầu chứng minh chặt chẽ từng bước bằng ký hiệu LaTeX chuẩn",
    compactedTokens: 720,
    compactionPct: 57,
    attentionScores: {
      math: 0.98,
      code: 0.15,
      reasoning: 0.95,
      extraction: 0.1,
      writing: 0.4,
      multilingual: 0.3,
    },
    winnerModelId: "openai-gpt-5.6-terra",
    winnerModelName: "GPT-5.6 Terra (OpenAI Frontier)",
    estimatedLatencyMs: 185,
    estimatedCostUsd: 0.00042,
    winnerToken: "Tích",
    candidateTokens: [
      { token: "Tích", prob: 0.68, isWinner: true },
      { token: "phân", prob: 0.14, isWinner: false },
      { token: "bội", prob: 0.09, isWinner: false },
      { token: "hàm", prob: 0.05, isWinner: false },
      { token: "Để", prob: 0.04, isWinner: false },
    ],
    transformerHeads: 64,
    mlpExpansion: "24,576 (4x SwiGLU)",
  },
  {
    id: "coding_system",
    name: "Kiến Trúc Concurrency & Hệ Phân Tán (Concurrent Architecture)",
    category: "Frontier Coding / Architecture",
    prompt:
      "Thiết kế kiến trúc Concurrency chống Race Condition trong SQLite WAL pool cho microservice FastAPI chịu tải cao.",
    inputTokens: 2450,
    memorySlotsHit: 4,
    memoryFact: "Ký ức: Tech stack gồm FastAPI, Python 3.12, SQLite WAL pool, Redis advisory locks",
    compactedTokens: 1050,
    compactionPct: 57,
    attentionScores: {
      math: 0.1,
      code: 0.98,
      reasoning: 0.92,
      extraction: 0.35,
      writing: 0.3,
      multilingual: 0.25,
    },
    winnerModelId: "openai-gpt-6.1-sol",
    winnerModelName: "GPT-6.1 Sol (OpenAI Frontier)",
    estimatedLatencyMs: 145,
    estimatedCostUsd: 0.00035,
    winnerToken: "class",
    candidateTokens: [
      { token: "class", prob: 0.7, isWinner: true },
      { token: "def", prob: 0.15, isWinner: false },
      { token: "async", prob: 0.08, isWinner: false },
      { token: "import", prob: 0.05, isWinner: false },
      { token: "#", prob: 0.02, isWinner: false },
    ],
    transformerHeads: 48,
    mlpExpansion: "16,384 (4x SwiGLU)",
  },
  {
    id: "academic_regulation",
    name: "Trích Xuất Quy Chế Học Vụ OU (OU Academic Regulations)",
    category: "Tài liệu OU / Extraction",
    prompt:
      "Trích xuất nhanh các điều kiện xét học bổng khuyến khích học tập và mức cảnh báo học vụ từ quy chế OU 2026.",
    inputTokens: 3800,
    memorySlotsHit: 3,
    memoryFact: "Ký ức: Sinh viên Khoa CNTT khóa 2022, chương trình chuẩn Trường ĐH Mở TP.HCM",
    compactedTokens: 1590,
    compactionPct: 58,
    attentionScores: {
      math: 0.08,
      code: 0.05,
      reasoning: 0.65,
      extraction: 0.97,
      writing: 0.6,
      multilingual: 0.45,
    },
    winnerModelId: "openai-gpt-6-luna",
    winnerModelName: "GPT-6 Luna (OpenAI Frontier)",
    estimatedLatencyMs: 120,
    estimatedCostUsd: 0.00018,
    winnerToken: "Theo",
    candidateTokens: [
      { token: "Theo", prob: 0.64, isWinner: true },
      { token: "Căn", prob: 0.2, isWinner: false },
      { token: "Điều", prob: 0.1, isWinner: false },
      { token: "Quy", prob: 0.04, isWinner: false },
      { token: "Sinh", prob: 0.02, isWinner: false },
    ],
    transformerHeads: 32,
    mlpExpansion: "16,384 (4x GeGLU)",
  },
  {
    id: "algorithms_dsa",
    name: "Cấu Trúc Dữ Liệu & Thuật Toán LeetCode (Algorithms & DSA)",
    category: "Software Engineering / DSA",
    prompt:
      "Cài đặt thuật toán Dijkstra tìm đường đi ngắn nhất với Priority Queue trong Python và phân tích độ phức tạp O((V + E) log V).",
    inputTokens: 1350,
    memorySlotsHit: 2,
    memoryFact: "Ký ức: Ưu tiên mã nguồn Python 3 tối ưu bộ nhớ và kèm type hints",
    compactedTokens: 620,
    compactionPct: 54,
    attentionScores: {
      math: 0.35,
      code: 0.95,
      reasoning: 0.85,
      extraction: 0.2,
      writing: 0.3,
      multilingual: 0.2,
    },
    winnerModelId: "groq-qwen-2.5-coder-32b",
    winnerModelName: "Qwen 3.8 27B (Groq Coding)",
    estimatedLatencyMs: 110,
    estimatedCostUsd: 0.00028,
    winnerToken: "import",
    candidateTokens: [
      { token: "import", prob: 0.72, isWinner: true },
      { token: "from", prob: 0.15, isWinner: false },
      { token: "def", prob: 0.07, isWinner: false },
      { token: "class", prob: 0.04, isWinner: false },
      { token: "#", prob: 0.02, isWinner: false },
    ],
    transformerHeads: 40,
    mlpExpansion: "13,824 (4x SwiGLU)",
  },
  {
    id: "general_knowledge",
    name: "Tri Thức Bách Khoa & Tổng Quan Tài Liệu (Literature Review)",
    category: "Multidisciplinary / Literature",
    prompt:
      "Tổng quan các công trình nghiên cứu nổi bật về Attention Routing và FrugalGPT trong giai đoạn 2024-2026.",
    inputTokens: 1850,
    memorySlotsHit: 2,
    memoryFact: "Ký ức: Định dạng trích dẫn theo phong cách IEEE / NeurIPS",
    compactedTokens: 820,
    compactionPct: 56,
    attentionScores: {
      math: 0.2,
      code: 0.25,
      reasoning: 0.85,
      extraction: 0.75,
      writing: 0.9,
      multilingual: 0.8,
    },
    winnerModelId: "groq-llama-3.3-70b-versatile",
    winnerModelName: "GPT OSS 120B (Groq Flagship)",
    estimatedLatencyMs: 135,
    estimatedCostUsd: 0.00032,
    winnerToken: "Tổng",
    candidateTokens: [
      { token: "Tổng", prob: 0.65, isWinner: true },
      { token: "Trong", prob: 0.18, isWinner: false },
      { token: "Nghiên", prob: 0.1, isWinner: false },
      { token: "Các", prob: 0.05, isWinner: false },
      { token: "Bài", prob: 0.02, isWinner: false },
    ],
    transformerHeads: 64,
    mlpExpansion: "18,432 (4x SwiGLU)",
  },
  {
    id: "daily_dialogue",
    name: "Hội Thoại Thường Nhật & Hỏi Đáp Nhanh (Daily Dialogue)",
    category: "Casual Inquiries / Fast",
    prompt: "Chào bạn, hôm nay thời tiết thế nào và bạn có thể gợi ý cho tôi kế hoạch học tập buổi tối không?",
    inputTokens: 380,
    memorySlotsHit: 1,
    memoryFact: "Ký ức: Người dùng là sinh viên năm cuối đang chuẩn bị đồ án tốt nghiệp",
    compactedTokens: 190,
    compactionPct: 50,
    attentionScores: {
      math: 0.05,
      code: 0.05,
      reasoning: 0.35,
      extraction: 0.3,
      writing: 0.8,
      multilingual: 0.75,
    },
    winnerModelId: "groq-llama-3.1-8b-instant",
    winnerModelName: "GPT OSS 20B (Groq Fast)",
    estimatedLatencyMs: 78,
    estimatedCostUsd: 0.00005,
    winnerToken: "Chào",
    candidateTokens: [
      { token: "Chào", prob: 0.75, isWinner: true },
      { token: "Xin", prob: 0.14, isWinner: false },
      { token: "Rất", prob: 0.06, isWinner: false },
      { token: "Hôm", prob: 0.03, isWinner: false },
      { token: "Chúc", prob: 0.02, isWinner: false },
    ],
    transformerHeads: 32,
    mlpExpansion: "14,336 (4x SwiGLU)",
  },
];

export interface PipelineFlow3DProps {
  className?: string;
  initialPresetId?: string;
}

// 8 Distinct Layers along the vertical Y-axis (expanded to accommodate 1.5x-2.0x larger geometries)
export const LAYER_Y = [8.4, 6.0, 3.6, 1.2, -1.2, -3.6, -6.0, -8.4];

export const LAYER_INFO = [
  {
    id: 1,
    title: "Tầng 1: Input Tensor & Token Embedding",
    module: "Tiếp nhận & Mã hóa",
    color: "#00d2ff",
    formula: "X_0 = \\text{Embedding}(W) + \\text{RoPE}(m, \\theta)",
    description:
      "Tách từ vựng (Tokenization) sang vector nhúng không gian 4096 chiều. Áp dụng ma trận xoay góc RoPE (Rotary Position Embedding) giúp mô hình nắm bắt vị trí tương đối và tuần hoàn không gian ngữ cảnh.",
  },
  {
    id: 2,
    title: "Tầng 2: Holographic KV Fact Memory Vault",
    module: "Module Khoa (Session Memory)",
    color: "#10b981",
    formula: "K_{retrieved}, V_{retrieved} = \\text{TopK}_{\\cos}(\\vec{q}, \\mathcal{M}_{facts})",
    description:
      "Kho lưu trữ ký ức dài hạn dạng vòng đồng tâm. Tự động truy xuất các sự thật đã ghim (Pinned Facts) và ngữ cảnh hội thoại đa lượt bằng chùm laser hologram để tiêm vào chuỗi token.",
  },
  {
    id: 3,
    title: "Tầng 3: Adaptive Entropy Token Sieve",
    module: "Module Tân (Prompt Compactor)",
    color: "#38bdf8",
    formula: "H(x_i) = -\\sum p \\log p \\ge \\tau_{entropy} \\implies \\text{Retain}(x_i)",
    description:
      "Mặt phẳng quét laser Entropy phân tách các từ đệm dễ đoán tan biến thành bụi ánh sáng. Giữ nguyên 100% cấu trúc Toán, Code và Thực thể quan trọng, nén chặt 52% - 58% kích thước tensor.",
  },
  {
    id: 4,
    title: "Tầng 4: 6D Attention Prism & Pareto Decision Lens",
    module: "Module Huy (ML Multi-task Router)",
    color: "#8b5cf6",
    formula: "\\vec{\\alpha}_{6D} = \\text{SDPA}(Q_{task}, K_{x}, V_{x}), \\quad \\kappa = \\vec{\\alpha} \\cdot \\vec{w}_{task}",
    description:
      "Lăng kính thạch anh 6 chiều chiếu các vector tác vụ (Toán, Code, Suy luận, Trích xuất, Viết, Đa ngữ) qua 3 đĩa thấu kính Pareto (Chi phí, Độ trễ, Chất lượng) và Task Complexity Head κ để chọn mô hình tối ưu.",
  },
  {
    id: 5,
    title: "Tầng 5: Target Model Compute Array",
    module: "Bệ Máy Chủ Đích (Compute Cluster)",
    color: "#f59e0b",
    formula: "\\mathcal{M}^* = \\arg\\max_{\\mathcal{M} \\in \\mathcal{P}} \\mathcal{U}(\\mathcal{M} \\mid \\text{Cost}, \\text{Latency}, \\text{PassRate})",
    description:
      "Bệ máy chủ bán nguyệt obsidian bóng gương chứa các mô hình: GPT OSS 120B, Qwen 3.8 27B, GPT OSS 20B, GPT-6 Luna, GPT-5.6 Terra, GPT-6.1 Sol. Cột sáng laser kích hoạt máy chủ chiến thắng.",
  },
  {
    id: 6,
    title: "Tầng 6: Transformer Core Decoder Stack (3Blue1Brown)",
    module: "Lõi Giải Mã Transformer (Decoder Blocks)",
    color: "#00d2ff",
    formula: "\\text{Attention}(Q,K,V) = \\text{softmax}\\left(\\frac{QK^T}{\\sqrt{d_k}}\\right)V, \\quad \\text{FFN}(x) = \\text{SwiGLU}(x)",
    description:
      "Mô phỏng 3D chính xác cơ chế của 3Blue1Brown & bbycroft: Phép chiếu ma trận Q, K, V, bản đồ nhiệt Attention Score Map, bộ nhớ FlashAttention KV-Cache, tầng mở rộng SwiGLU 4x và ống dẫn tắt Skip Connection RMSNorm.",
  },
  {
    id: 7,
    title: "Tầng 7: LM Head & Softmax Probability Tower (3Blue1Brown)",
    module: "Tháp Xác Suất Softmax (Unembedding & Sampling)",
    color: "#f59e0b",
    formula: "P(w_i) = \\frac{e^{z_i / T}}{\\sum_j e^{z_j / T}}, \\quad \\sum_{i \\in V^{(p)}} P(w_i) \\ge p",
    description:
      "Chiếu ngược ẩn trạng thái (Unembedding) sang không gian 128.000 logits. Tháp biểu đồ cột 3D hiển thị phân phối Softmax cho các token ứng viên; con trỏ Top-p / Nhiệt độ Temperature chọn token chiến thắng cao nhất.",
  },
  {
    id: 8,
    title: "Tầng 8: Autoregressive SSE Stream & Chat Delivery",
    module: "Vòng Hồi Quy & Kênh SSE Phát Thời Gian Thực",
    color: "#10b981",
    formula: "x_{t+1} \\hookrightarrow \\text{KV-Cache}(t+1) \\quad \\& \\quad x_{t+1} \\xrightarrow{\\text{SSE Chunk}} \\text{Chat Typewriter}",
    description:
      "Token chiến thắng tách làm 2 nhánh: Nhánh 1 bay ngược theo đường cong spline phát sáng nạp vào KV-Cache tầng 6 cho bước giải mã kế tiếp; Nhánh 2 phóng thẳng qua cáp quang hiển thị ngay lên khung Chat qua SSE.",
  },
];

export const SERVER_MODEL_DEFS = [
  {
    id: "groq-llama-3.3-70b-versatile",
    name: "GPT OSS 120B",
    tier: "🧠 Frontier Reasoning",
    tierColor: "#38bdf8",
    pos: [-3.5, 0.75, -0.6] as const,
    color: 0x0284c7,
  },
  {
    id: "groq-qwen-2.5-coder-32b",
    name: "Qwen 3.8 27B",
    tier: "💻 Code Tier",
    tierColor: "#c084fc",
    pos: [-2.1, 0.75, 0.5] as const,
    color: 0x8b5cf6,
  },
  {
    id: "groq-llama-3.1-8b-instant",
    name: "GPT OSS 20B",
    tier: "⚡ Fast Tier",
    tierColor: "#34d399",
    pos: [-0.7, 0.75, 1.1] as const,
    color: 0x00d2ff,
  },
  {
    id: "openai-gpt-6-luna",
    name: "GPT-6 Luna",
    tier: "⚡ Fast Tier",
    tierColor: "#10b981",
    pos: [0.7, 0.75, 1.1] as const,
    color: 0x10b981,
  },
  {
    id: "openai-gpt-5.6-terra",
    name: "GPT-5.6 Terra",
    tier: "🧠 Frontier Reasoning",
    tierColor: "#fbbf24",
    pos: [2.1, 0.75, 0.5] as const,
    color: 0xf59e0b,
  },
  {
    id: "openai-gpt-6.1-sol",
    name: "GPT-6.1 Sol",
    tier: "💻 Code Tier",
    tierColor: "#f472b6",
    pos: [3.5, 0.75, -0.6] as const,
    color: 0xec4899,
  },
];

export function createTextSprite(
  text: string,
  color: string = "#ffffff",
  bgColor: string = "rgba(15, 23, 42, 0.75)",
  fontSize: number = 24,
): THREE.Sprite {
  if (typeof document === "undefined") return new THREE.Sprite();
  try {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = bgColor;
      if (typeof ctx.roundRect === "function") {
        ctx.beginPath();
        ctx.roundRect(6, 6, canvas.width - 12, canvas.height - 12, 10);
        ctx.fill();
      } else {
        ctx.fillRect(6, 6, canvas.width - 12, canvas.height - 12);
      }
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(6, 6, canvas.width - 12, canvas.height - 12);
      ctx.fillStyle = color;
      ctx.font = `bold ${fontSize}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(text, canvas.width / 2, canvas.height / 2);
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.1, 0.28, 1);
    return sprite;
  } catch {
    return new THREE.Sprite();
  }
}

export function PipelineFlow3D({
  className = "",
  initialPresetId = "math_advanced",
}: PipelineFlow3DProps) {
  const locale = useLocale();
  const mountRef = useRef<HTMLDivElement>(null);
  const [selectedPresetId, setSelectedPresetId] = useState(initialPresetId);
  const [activeLayer, setActiveLayer] = useState<number>(1);
  const [isPlaying, setIsPlaying] = useState(true);
  const isPlayingRef = useRef(isPlaying);
  useEffect(() => {
    isPlayingRef.current = isPlaying;
  }, [isPlaying]);

  const currentPreset = useMemo(() => {
    return (
      SIMULATION_PRESETS.find((p) => p.id === selectedPresetId) ??
      SIMULATION_PRESETS[0]
    );
  }, [selectedPresetId]);

  const sceneRef = useRef<THREE.Scene | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);

  // Smooth camera interpolation targets
  const targetCamPosRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 1.2, 24.0));
  const targetLookAtRef = useRef<THREE.Vector3>(new THREE.Vector3(0, 0, 0));
  const isTransitioningCameraRef = useRef<boolean>(false);

  // Layer groups array for active highlight / dimming
  const layerGroupsRef = useRef<THREE.Group[]>([]);
  const haloBoundingBoxRef = useRef<THREE.Group | null>(null);
  const haloLineMatRef = useRef<THREE.LineBasicMaterial | null>(null);
  const haloPlaneMatRef = useRef<THREE.MeshBasicMaterial | null>(null);

  // Dynamic mesh references for animations
  const prismMeshRef = useRef<THREE.Mesh | null>(null);
  const paretoRingsRef = useRef<THREE.Mesh[]>([]);
  const scannerPlaneRef = useRef<THREE.Mesh | null>(null);
  const shockwaveRingRef = useRef<THREE.Mesh | null>(null);
  const serverLaserBeamRef = useRef<THREE.Mesh | null>(null);
  const serverTowersRef = useRef<
    { id: string; mesh: THREE.Mesh; beacon: THREE.Mesh; defColor: number }[]
  >([]);
  const probBarsGroupRef = useRef<THREE.Group | null>(null);
  const probabilityBarsRef = useRef<THREE.Mesh[]>([]);
  const winningBarBeaconRef = useRef<THREE.Mesh | null>(null);
  const particlesDownRef = useRef<THREE.Mesh[]>([]);
  const particlesReturnRef = useRef<THREE.Mesh[]>([]);
  const particlesSseRef = useRef<THREE.Mesh[]>([]);
  const synapsePhotonsRef = useRef<{ mesh: THREE.Mesh; points: THREE.Vector3[]; speed: number; offset: number }[]>([]);
  const ropeWaveRibbonRef = useRef<THREE.Line | null>(null);
  const mistParticlesRef = useRef<THREE.Points | null>(null);
  const jewelMeshRef = useRef<THREE.Mesh | null>(null);

  // Setup 8-Tier Sci-Fi Glassmorphism Three.js Scene
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth || 960;
    const height = container.clientHeight || 620;

    // 1. Scene & Camera setup (Centered along vertical Y axis: X=0, Z=0)
    const scene = new THREE.Scene();
    sceneRef.current = scene;
    scene.background = new THREE.Color(0xf8fafc);
    scene.fog = new THREE.FogExp2(0xf8fafc, 0.016);

    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    cameraRef.current = camera;
    camera.position.set(0, 1.2, 24.0);

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    rendererRef.current = renderer;
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.25));
    renderer.shadowMap.enabled = false;
    container.innerHTML = "";
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.06;
    controls.minDistance = 3.5;
    controls.maxDistance = 36.0;
    controls.target.set(0, 0, 0);

    // Stop automated camera transition on manual user interaction
    controls.addEventListener("start", () => {
      isTransitioningCameraRef.current = false;
    });

    // 2. Lighting System
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.35);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 1.3);
    dirLight1.position.set(8, 18, 10);
    dirLight1.castShadow = true;
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x00d2ff, 0.9);
    dirLight2.position.set(-8, -12, 8);
    scene.add(dirLight2);

    const ouBlueLight = new THREE.PointLight(0x005696, 2.4, 24);
    ouBlueLight.position.set(0, 4, 6);
    scene.add(ouBlueLight);

    const amberLight = new THREE.PointLight(0xf59e0b, 2.0, 20);
    amberLight.position.set(0, -5, 6);
    scene.add(amberLight);

    // Architectural Ground Grid
    const grid = new THREE.GridHelper(26, 28, 0x005696, 0xe2e8f0);
    grid.position.y = -10.5;
    scene.add(grid);

    // Central Vertical Spline Conduit Line (Y-axis X=0, Z=0)
    const centralLineGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, LAYER_Y[0] + 0.8, 0),
      new THREE.Vector3(0, LAYER_Y[7] - 0.8, 0),
    ]);
    const centralLineMat = new THREE.LineBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.35,
    });
    scene.add(new THREE.Line(centralLineGeo, centralLineMat));

    const layerGroups: THREE.Group[] = [];

    // =========================================================================
    // LAYER 1: Input Tensor & Token Embedding (Y = 8.4)
    // 2D Token Activation Matrix + 3D RoPE Sinusoidal Wave Ribbon
    // =========================================================================
    const l1Group = new THREE.Group();
    l1Group.position.set(0, LAYER_Y[0], 0);
    scene.add(l1Group);
    layerGroups.push(l1Group);

    // Glass Slab Container (1.6x larger)
    const l1BoxGeo = new THREE.BoxGeometry(7.6, 0.55, 3.2);
    const l1BoxMat = new THREE.MeshStandardMaterial({
      color: 0x005696,
      emissive: 0x003366,
      emissiveIntensity: 0.35,
      roughness: 0.15,
      metalness: 0.25,
      transparent: true,
      opacity: 0.88,
    });
    const l1BoxMesh = new THREE.Mesh(l1BoxGeo, l1BoxMat);
    l1Group.add(l1BoxMesh);

    // Cyber Cyan Edge Glow
    const l1Edges = new THREE.EdgesGeometry(l1BoxGeo);
    const l1EdgeLine = new THREE.LineSegments(
      l1Edges,
      new THREE.LineBasicMaterial({ color: 0x00d2ff, linewidth: 2 }),
    );
    l1Group.add(l1EdgeLine);

    // 2D Input Token Activation Matrix: 2 Rows x 8 Columns = 16 Token Blocks
    for (let row = 0; row < 2; row++) {
      for (let col = 0; col < 8; col++) {
        const tx = -2.8 + col * 0.8;
        const tz = -0.65 + row * 1.3;
        const cubeGeo = new THREE.BoxGeometry(0.5, 0.22, 0.5);
        const cubeMat = new THREE.MeshStandardMaterial({
          color: 0x005696,
          emissive: 0x00d2ff,
          emissiveIntensity: 0.55 + ((row + col) % 3) * 0.25,
          roughness: 0.2,
          metalness: 0.85,
        });
        const cube = new THREE.Mesh(cubeGeo, cubeMat);
        cube.position.set(tx, 0.18, tz);
        l1Group.add(cube);
      }
    }

    // 3D RoPE Sinusoidal Wave Ribbon across the front
    const wavePoints: THREE.Vector3[] = [];
    for (let w = -3.2; w <= 3.2; w += 0.08) {
      wavePoints.push(
        new THREE.Vector3(
          w,
          0.25 + Math.sin(w * 2.8) * 0.22,
          1.7 + Math.cos(w * 2.8) * 0.15,
        ),
      );
    }
    const waveGeo = new THREE.BufferGeometry().setFromPoints(wavePoints);
    const waveMat = new THREE.LineBasicMaterial({
      color: 0x00d2ff,
      linewidth: 3,
    });
    const waveLine = new THREE.Line(waveGeo, waveMat);
    l1Group.add(waveLine);
    ropeWaveRibbonRef.current = waveLine;

    // 3D In-scene Label Sprite
    const l1Sprite = createTextSprite("T1: Token Embeddings + RoPE", "#00d2ff", "rgba(15, 23, 42, 0.82)", 24);
    l1Sprite.position.set(0, 0.8, 1.8);
    l1Group.add(l1Sprite);

    // =========================================================================
    // LAYER 2: Holographic KV Fact Memory Vault (Khoa) (Y = 6.0)
    // Concentric Obsidian & Glass Ring Base, Memory Slots, Laser Rays
    // =========================================================================
    const l2Group = new THREE.Group();
    l2Group.position.set(0, LAYER_Y[1], 0);
    scene.add(l2Group);
    layerGroups.push(l2Group);

    // Concentric Obsidian & Glass Ring Base (1.6x larger)
    const l2BaseGeo = new THREE.CylinderGeometry(3.6, 4.0, 0.35, 40);
    const l2BaseMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      metalness: 0.85,
      roughness: 0.18,
      transparent: true,
      opacity: 0.92,
    });
    const l2BaseMesh = new THREE.Mesh(l2BaseGeo, l2BaseMat);
    l2Group.add(l2BaseMesh);

    // 3 Concentric Glowing Neon Rings (Torus)
    const ringRadii = [1.8, 2.7, 3.6];
    ringRadii.forEach((r, idx) => {
      const ringGeo = new THREE.TorusGeometry(r, 0.05, 16, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        color: idx === 1 ? 0x10b981 : 0x00d2ff,
        transparent: true,
        opacity: 0.85,
      });
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.rotation.x = Math.PI / 2;
      ring.position.y = 0.05 + idx * 0.04;
      l2Group.add(ring);
    });

    // 10 Distinct Memory Slots arranged circularly
    for (let s = 0; s < 10; s++) {
      const angle = (s * Math.PI * 2) / 10;
      const sx = Math.cos(angle) * 2.5;
      const sz = Math.sin(angle) * 2.5;
      const isPinned = s === 1 || s === 4 || s === 7;
      const isConv = s === 2 || s === 5;
      const podGeo = new THREE.CylinderGeometry(0.26, 0.26, 0.52, 20);
      const podMat = new THREE.MeshStandardMaterial({
        color: isPinned ? 0x10b981 : isConv ? 0x00d2ff : 0x64748b,
        emissive: isPinned ? 0x059669 : isConv ? 0x0284c7 : 0x1e293b,
        emissiveIntensity: isPinned ? 0.95 : isConv ? 0.75 : 0.25,
        metalness: 0.85,
        roughness: 0.18,
      });
      const pod = new THREE.Mesh(podGeo, podMat);
      pod.position.set(sx, 0.26, sz);
      l2Group.add(pod);

      // Context Retrieval Laser Beam shooting upwards
      if (isPinned || isConv) {
        const rayGeo = new THREE.CylinderGeometry(0.02, 0.02, 2.2, 8);
        const rayMat = new THREE.MeshBasicMaterial({
          color: isPinned ? 0x10b981 : 0x00d2ff,
          transparent: true,
          opacity: 0.8,
        });
        const ray = new THREE.Mesh(rayGeo, rayMat);
        ray.position.set(sx, 1.25, sz);
        l2Group.add(ray);
      }
    }

    const l2Sprite = createTextSprite("T2: Khoa KV Memory Vault", "#10b981", "rgba(15, 23, 42, 0.82)", 24);
    l2Sprite.position.set(0, 0.9, 2.8);
    l2Group.add(l2Sprite);

    // =========================================================================
    // LAYER 3: Adaptive Entropy Token Sieve (Tân) (Y = 3.6)
    // Multi-tier Entropy Pooling: Uncompressed Slab, Sweeping Sieve, 55% Compacted Slab
    // =========================================================================
    const l3Group = new THREE.Group();
    l3Group.position.set(0, LAYER_Y[2], 0);
    scene.add(l3Group);
    layerGroups.push(l3Group);

    // Upper Input Slab (Uncompressed tokens)
    const l3UpperGeo = new THREE.BoxGeometry(7.2, 0.42, 2.8);
    const l3UpperMat = new THREE.MeshStandardMaterial({
      color: 0x005696,
      roughness: 0.15,
      metalness: 0.25,
      transparent: true,
      opacity: 0.85,
    });
    const l3UpperMesh = new THREE.Mesh(l3UpperGeo, l3UpperMat);
    l3UpperMesh.position.set(0, 0.55, 0);
    l3Group.add(l3UpperMesh);

    // Sweeping Entropy Threshold Scanner Plane H(x) >= tau
    const l3ScannerGeo = new THREE.PlaneGeometry(7.6, 3.2);
    const l3ScannerMat = new THREE.MeshBasicMaterial({
      color: 0x8b5cf6,
      transparent: true,
      opacity: 0.5,
      side: THREE.DoubleSide,
    });
    const l3ScannerMesh = new THREE.Mesh(l3ScannerGeo, l3ScannerMat);
    l3ScannerMesh.rotation.x = Math.PI / 2;
    l3ScannerMesh.position.set(0, 0.0, 0);
    l3Group.add(l3ScannerMesh);
    scannerPlaneRef.current = l3ScannerMesh;

    // Lower Compact Slab (Packed 55% dense tensor)
    const l3LowerGeo = new THREE.BoxGeometry(3.8, 0.48, 2.4);
    const l3LowerMat = new THREE.MeshStandardMaterial({
      color: 0x10b981,
      roughness: 0.12,
      metalness: 0.3,
      emissive: 0x047857,
      emissiveIntensity: 0.6,
      transparent: true,
      opacity: 0.92,
    });
    const l3LowerMesh = new THREE.Mesh(l3LowerGeo, l3LowerMat);
    l3LowerMesh.position.set(0, -0.55, 0);
    l3Group.add(l3LowerMesh);

    // Dissolving Mist Particles (Filler tokens dissipating)
    const mistCount = 85;
    const mistGeo = new THREE.BufferGeometry();
    const mistPositions = new Float32Array(mistCount * 3);
    for (let m = 0; m < mistCount; m++) {
      mistPositions[m * 3] = (Math.random() - 0.5) * 6.5;
      mistPositions[m * 3 + 1] = (Math.random() - 0.5) * 0.8;
      mistPositions[m * 3 + 2] = (Math.random() - 0.5) * 3.0;
    }
    mistGeo.setAttribute("position", new THREE.BufferAttribute(mistPositions, 3));
    const mistMat = new THREE.PointsMaterial({
      color: 0x94a3b8,
      size: 0.065,
      transparent: true,
      opacity: 0.65,
    });
    const mist = new THREE.Points(mistGeo, mistMat);
    l3Group.add(mist);
    mistParticlesRef.current = mist;

    const l3Sprite = createTextSprite("T3: Tân Entropy Sieve (-55%)", "#38bdf8", "rgba(15, 23, 42, 0.82)", 24);
    l3Sprite.position.set(0, 1.0, 1.8);
    l3Group.add(l3Sprite);

    // =========================================================================
    // LAYER 4: 6D Multi-task Attention Prism & Pareto Lens (Huy) (Y = 1.2)
    // 6D Quartz Prism + 3D Concentric Pareto Lens (Cost, Latency, Quality)
    // =========================================================================
    const l4Group = new THREE.Group();
    l4Group.position.set(0, LAYER_Y[3], 0);
    scene.add(l4Group);
    layerGroups.push(l4Group);

    // Hexagonal Attention Prism (1.6x larger)
    const l4PrismGeo = new THREE.CylinderGeometry(2.4, 2.4, 1.0, 6);
    const l4PrismMat = new THREE.MeshStandardMaterial({
      color: 0x8b5cf6,
      roughness: 0.12,
      metalness: 0.25,
      transparent: true,
      opacity: 0.9,
      emissive: 0x4c1d95,
      emissiveIntensity: 0.45,
    });
    const l4PrismMesh = new THREE.Mesh(l4PrismGeo, l4PrismMat);
    l4Group.add(l4PrismMesh);
    prismMeshRef.current = l4PrismMesh;

    // 6 Radial Task Head Beams (Math, Code, Reasoning, Extraction, Writing, Multilingual)
    const taskDefs = [
      { name: "Math", color: 0xef4444 },
      { name: "Code", color: 0x00d2ff },
      { name: "Reasoning", color: 0x8b5cf6 },
      { name: "Extract", color: 0x06b6d4 },
      { name: "Writing", color: 0x10b981 },
      { name: "MultiLang", color: 0xf59e0b },
    ];
    for (let r = 0; r < 6; r++) {
      const angle = (r * Math.PI) / 3;
      const rx = Math.cos(angle) * 2.8;
      const rz = Math.sin(angle) * 2.8;
      const rayGeo = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(rx, 0, rz),
      ]);
      const rayMat = new THREE.LineBasicMaterial({
        color: taskDefs[r].color,
        linewidth: 3,
      });
      l4Group.add(new THREE.Line(rayGeo, rayMat));

      const headSphereGeo = new THREE.SphereGeometry(0.14, 14, 14);
      const headSphereMat = new THREE.MeshBasicMaterial({ color: taskDefs[r].color });
      const headSphere = new THREE.Mesh(headSphereGeo, headSphereMat);
      headSphere.position.set(rx, 0, rz);
      l4Group.add(headSphere);

      const taskSprite = createTextSprite(taskDefs[r].name, `#${taskDefs[r].color.toString(16).padStart(6, "0")}`, "rgba(15, 23, 42, 0.75)", 20);
      taskSprite.position.set(rx * 1.18, 0.35, rz * 1.18);
      taskSprite.scale.set(0.7, 0.2, 1);
      l4Group.add(taskSprite);
    }

    // Dynamic Concentric Pareto Decision Lens (Cost, Latency, Quality rings)
    const paretoRings: THREE.Mesh[] = [];
    const ringConfigs = [
      { r: 3.0, color: 0xf59e0b }, // Cost (Amber)
      { r: 3.6, color: 0x00d2ff }, // Latency (Cyan)
      { r: 4.2, color: 0x10b981 }, // Quality (Emerald)
    ];
    ringConfigs.forEach((rc) => {
      const rGeo = new THREE.RingGeometry(rc.r, rc.r + 0.08, 64);
      const rMat = new THREE.MeshBasicMaterial({
        color: rc.color,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.8,
      });
      const rMesh = new THREE.Mesh(rGeo, rMat);
      rMesh.rotation.x = Math.PI / 2;
      rMesh.position.y = -0.65;
      l4Group.add(rMesh);
      paretoRings.push(rMesh);
    });
    paretoRingsRef.current = paretoRings;

    const l4Sprite = createTextSprite("T4: Huy 6D Attention & Pareto Lens", "#8b5cf6", "rgba(15, 23, 42, 0.82)", 24);
    l4Sprite.position.set(0, 1.0, 2.6);
    l4Group.add(l4Sprite);

    // =========================================================================
    // LAYER 5: Target Model Compute Array (Y = -1.2)
    // Semicircular Obsidian Pedestal + Server Blades (GPT OSS 120B, Qwen 3.8 27B, GPT OSS 20B, Gemini 3.8 Flash, DeepSeek R1)
    // =========================================================================
    const l5Group = new THREE.Group();
    l5Group.position.set(0, LAYER_Y[4], 0);
    scene.add(l5Group);
    layerGroups.push(l5Group);

    // Semicircular Metallic Obsidian Pedestal (1.6x larger)
    const l5PedGeo = new THREE.CylinderGeometry(4.8, 5.2, 0.35, 48);
    const l5PedMat = new THREE.MeshStandardMaterial({
      color: 0x0a1128,
      metalness: 0.9,
      roughness: 0.18,
    });
    const l5PedMesh = new THREE.Mesh(l5PedGeo, l5PedMat);
    l5Group.add(l5PedMesh);

    // 5 Server Blades along the semicircle arc
    const towers: { id: string; mesh: THREE.Mesh; beacon: THREE.Mesh; defColor: number }[] = [];
    const defaultWinnerId = SIMULATION_PRESETS[0].winnerModelId;
    SERVER_MODEL_DEFS.forEach((def) => {
      const towerGeo = new THREE.BoxGeometry(0.8, 1.3, 0.8);
      const isWinner = def.id === defaultWinnerId;
      const towerMat = new THREE.MeshStandardMaterial({
        color: def.color,
        emissive: isWinner ? def.color : 0x0f172a,
        emissiveIntensity: isWinner ? 1.1 : 0.25,
        metalness: 0.88,
        roughness: 0.15,
      });
      const towerMesh = new THREE.Mesh(towerGeo, towerMat);
      towerMesh.position.set(def.pos[0], def.pos[1], def.pos[2]);
      l5Group.add(towerMesh);

      // Light beacon on top
      const beaconGeo = new THREE.SphereGeometry(0.14, 14, 14);
      const beaconMat = new THREE.MeshBasicMaterial({
        color: isWinner ? 0xffffff : def.color,
      });
      const beacon = new THREE.Mesh(beaconGeo, beaconMat);
      beacon.position.set(def.pos[0], def.pos[1] + 0.8, def.pos[2]);
      l5Group.add(beacon);

      // Server Blade Name Label
      const serverSprite = createTextSprite(def.name, `#${def.color.toString(16).padStart(6, "0")}`, "rgba(15, 23, 42, 0.82)", 20);
      serverSprite.position.set(def.pos[0], def.pos[1] + 1.15, def.pos[2]);
      serverSprite.scale.set(0.85, 0.24, 1);
      l5Group.add(serverSprite);

      // Capability Tier Badge
      if (def.tier) {
        const tierSprite = createTextSprite(def.tier, def.tierColor || "#ffffff", "rgba(15, 23, 42, 0.88)", 16);
        tierSprite.position.set(def.pos[0], def.pos[1] + 1.48, def.pos[2]);
        tierSprite.scale.set(0.85, 0.20, 1);
        l5Group.add(tierSprite);
      }

      towers.push({ id: def.id, mesh: towerMesh, beacon, defColor: def.color });
    });
    serverTowersRef.current = towers;

    // Focused Router Laser Beam from Layer 4 to Winner Blade
    const winningDef =
      SERVER_MODEL_DEFS.find((d) => d.id === defaultWinnerId) ||
      SERVER_MODEL_DEFS[0];
    const laserBeamGeo = new THREE.CylinderGeometry(0.04, 0.04, 2.4, 12);
    const laserBeamMat = new THREE.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.85,
    });
    const laserBeam = new THREE.Mesh(laserBeamGeo, laserBeamMat);
    laserBeam.position.set(winningDef.pos[0] * 0.5, 1.2, winningDef.pos[2] * 0.5);
    l5Group.add(laserBeam);
    serverLaserBeamRef.current = laserBeam;

    // Shockwave Ring around Winner Tower
    const shockwaveGeo = new THREE.TorusGeometry(0.8, 0.04, 16, 40);
    const shockwaveMat = new THREE.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.85,
    });
    const shockwave = new THREE.Mesh(shockwaveGeo, shockwaveMat);
    shockwave.rotation.x = Math.PI / 2;
    shockwave.position.set(winningDef.pos[0], 0.18, winningDef.pos[2]);
    l5Group.add(shockwave);
    shockwaveRingRef.current = shockwave;

    // =========================================================================
    // LAYER 6: Transformer Core Decoder Stack (3Blue1Brown/bbycroft) (Y = -3.6)
    // Separate Q, K, V Projection Matrices, Attention Heatmap Grid, FlashAttention KV-Cache, SwiGLU 4x MLP, RMSNorm Skip
    // =========================================================================
    const l6Group = new THREE.Group();
    l6Group.position.set(0, LAYER_Y[5], 0);
    scene.add(l6Group);
    layerGroups.push(l6Group);

    // Q, K, V Projection Matrices (1.6x larger)
    const qkvDefs = [
      { name: "Q (Query)", x: -1.5, color: 0x00d2ff },
      { name: "K (Key)", x: 0.0, color: 0x8b5cf6 },
      { name: "V (Value)", x: 1.5, color: 0x10b981 },
    ];
    qkvDefs.forEach((qkv) => {
      const qGeo = new THREE.BoxGeometry(1.1, 0.45, 1.1);
      const qMat = new THREE.MeshStandardMaterial({
        color: qkv.color,
        roughness: 0.15,
        metalness: 0.3,
        emissive: qkv.color,
        emissiveIntensity: 0.45,
        transparent: true,
        opacity: 0.88,
      });
      const qMesh = new THREE.Mesh(qGeo, qMat);
      qMesh.position.set(qkv.x, 0.6, 0);
      l6Group.add(qMesh);

      const qkvSprite = createTextSprite(qkv.name, "#ffffff", "rgba(15, 23, 42, 0.82)", 24);
      qkvSprite.position.set(qkv.x, 1.05, 0);
      qkvSprite.scale.set(0.65, 0.2, 1);
      l6Group.add(qkvSprite);
    });

    // Attention Score Matrix Heatmap (10x10 grid plane)
    const attnGridGeo = new THREE.PlaneGeometry(2.4, 2.4);
    const attnGridMat = new THREE.MeshBasicMaterial({
      color: 0x005696,
      wireframe: true,
    });
    const attnGrid = new THREE.Mesh(attnGridGeo, attnGridMat);
    attnGrid.rotation.x = Math.PI / 2;
    attnGrid.position.set(0, 0.15, 0);
    l6Group.add(attnGrid);

    // FlashAttention KV-Cache Bank on left flank
    for (let c = 0; c < 4; c++) {
      const cacheGeo = new THREE.BoxGeometry(1.0, 0.16, 0.6);
      const cacheMat = new THREE.MeshStandardMaterial({
        color: 0x10b981,
        emissive: 0x059669,
        emissiveIntensity: 0.7,
        metalness: 0.85,
        roughness: 0.18,
      });
      const cacheMesh = new THREE.Mesh(cacheGeo, cacheMat);
      cacheMesh.position.set(-2.8, 0.15 + c * 0.22, 0);
      l6Group.add(cacheMesh);
    }
    const cacheLabel = createTextSprite("KV-Cache Bank", "#10b981", "rgba(15, 23, 42, 0.8)", 20);
    cacheLabel.position.set(-2.8, 1.15, 0);
    cacheLabel.scale.set(0.75, 0.2, 1);
    l6Group.add(cacheLabel);

    // SwiGLU 4x MLP Expansion Slab (wide amber block)
    const mlpExpGeo = new THREE.BoxGeometry(5.8, 0.38, 2.0);
    const mlpExpMat = new THREE.MeshStandardMaterial({
      color: 0xf59e0b,
      roughness: 0.15,
      metalness: 0.25,
      emissive: 0xd97706,
      emissiveIntensity: 0.45,
      transparent: true,
      opacity: 0.88,
    });
    const mlpExp = new THREE.Mesh(mlpExpGeo, mlpExpMat);
    mlpExp.position.set(0, -0.55, 0);
    l6Group.add(mlpExp);

    const ffnSprite = createTextSprite("SwiGLU FFN (4x d_model)", "#f59e0b", "rgba(15, 23, 42, 0.82)", 24);
    ffnSprite.position.set(0, -0.9, 0.6);
    ffnSprite.scale.set(1.2, 0.26, 1);
    l6Group.add(ffnSprite);

    // Skip Connection Conduits (RMSNorm + Residual Loop)
    const skipCurve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(2.6, 0.65, 0),
      new THREE.Vector3(3.2, 0.0, 0.6),
      new THREE.Vector3(2.6, -0.65, 0),
    ]);
    const skipGeo = new THREE.TubeGeometry(skipCurve, 32, 0.05, 8, false);
    const skipMat = new THREE.MeshBasicMaterial({ color: 0x00d2ff });
    l6Group.add(new THREE.Mesh(skipGeo, skipMat));

    // =========================================================================
    // LAYER 7: LM Head & Softmax Probability Tower (3Blue1Brown) (Y = -6.0)
    // Unembedding Projection Frustum, 3D Bar Histogram, Top-p/Temperature Plane
    // =========================================================================
    const l7Group = new THREE.Group();
    l7Group.position.set(0, LAYER_Y[6], 0);
    scene.add(l7Group);
    layerGroups.push(l7Group);

    // Unembedding Projection Frustum (1.6x larger)
    const unembGeo = new THREE.CylinderGeometry(1.0, 4.4, 0.45, 40);
    const unembMat = new THREE.MeshStandardMaterial({
      color: 0x005696,
      roughness: 0.15,
      metalness: 0.25,
      transparent: true,
      opacity: 0.85,
    });
    const unembMesh = new THREE.Mesh(unembGeo, unembMat);
    unembMesh.position.set(0, 0.65, 0);
    l7Group.add(unembMesh);

    // Dynamic group for probability bars and candidate token sprites
    const probBarsGroup = new THREE.Group();
    l7Group.add(probBarsGroup);
    probBarsGroupRef.current = probBarsGroup;

    // Top-p / Temperature Sampling Pointer Plane
    const toppGeo = new THREE.PlaneGeometry(4.8, 0.06);
    const toppMat = new THREE.MeshBasicMaterial({
      color: 0xef4444,
      side: THREE.DoubleSide,
    });
    const topp = new THREE.Mesh(toppGeo, toppMat);
    topp.position.set(0, 0.85, 0.3);
    l7Group.add(topp);

    const toppLabel = createTextSprite("Top-p Cutoff (p=0.90)", "#ef4444", "rgba(15, 23, 42, 0.8)", 20);
    toppLabel.position.set(2.6, 0.85, 0.3);
    toppLabel.scale.set(0.9, 0.22, 1);
    l7Group.add(toppLabel);

    // =========================================================================
    // LAYER 8: Autoregressive SSE Stream & Chat Delivery (Y = -8.4)
    // Dual Output Paths: Loop 1 (Return to Layer 6 KV-Cache) & Loop 2 (SSE to Chat)
    // =========================================================================
    const l8Group = new THREE.Group();
    l8Group.position.set(0, LAYER_Y[7], 0);
    scene.add(l8Group);
    layerGroups.push(l8Group);

    // Materialized Winning Token Jewel (large glowing diamond)
    const jewelGeo = new THREE.OctahedronGeometry(0.55, 1);
    const jewelMat = new THREE.MeshStandardMaterial({
      color: 0xf59e0b,
      roughness: 0.1,
      metalness: 0.35,
      emissive: 0xd97706,
      emissiveIntensity: 0.95,
      transparent: true,
      opacity: 0.92,
    });
    const jewelMesh = new THREE.Mesh(jewelGeo, jewelMat);
    jewelMesh.position.set(0, 0.3, 0);
    l8Group.add(jewelMesh);
    jewelMeshRef.current = jewelMesh;

    // --- LOOP 1: Autoregressive Return Spline Conduit (Looping back to Layer 6) ---
    const returnSpline = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0, LAYER_Y[7] + 0.3, 0),
      new THREE.Vector3(-3.8, (LAYER_Y[7] + LAYER_Y[5]) / 2, 1.2),
      new THREE.Vector3(-2.8, LAYER_Y[5] + 0.2, 0),
    ]);
    const returnTubeGeo = new THREE.TubeGeometry(returnSpline, 48, 0.055, 8, false);
    const returnTubeMat = new THREE.MeshBasicMaterial({
      color: 0x8b5cf6,
      transparent: true,
      opacity: 0.7,
    });
    scene.add(new THREE.Mesh(returnTubeGeo, returnTubeMat));
    const returnPoints = returnSpline.getPoints(36);

    // --- LOOP 2: Realtime SSE Stream Optical Fiber (Flowing towards Chat preview) ---
    const sseSpline = new THREE.CatmullRomCurve3([
      new THREE.Vector3(0, LAYER_Y[7] + 0.3, 0),
      new THREE.Vector3(0, LAYER_Y[7] - 0.6, 1.8),
      new THREE.Vector3(0, LAYER_Y[7] - 1.0, 3.6),
    ]);
    const sseTubeGeo = new THREE.TubeGeometry(sseSpline, 32, 0.065, 8, false);
    const sseTubeMat = new THREE.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.8,
    });
    scene.add(new THREE.Mesh(sseTubeGeo, sseTubeMat));
    const ssePoints = sseSpline.getPoints(24);

    const l8Sprite = createTextSprite("T8: Autoregressive Loop & SSE Stream", "#10b981", "rgba(15, 23, 42, 0.82)", 24);
    l8Sprite.position.set(0, 1.1, 1.8);
    l8Group.add(l8Sprite);

    layerGroupsRef.current = layerGroups;

    // =========================================================================
    // DENSE NEURAL SYNAPSE WEB (Connecting all consecutive layers)
    // Modeled after 3D CNN / Deep Learning neural network feature map synapse fibers
    // =========================================================================
    const synapseGroup = new THREE.Group();
    scene.add(synapseGroup);

    const synapsePhotons: { mesh: THREE.Mesh; points: THREE.Vector3[]; speed: number; offset: number }[] = [];
    const photonSphereGeo = new THREE.SphereGeometry(0.048, 8, 8);
    const photonSphereMat = new THREE.MeshBasicMaterial({ color: 0xffffff });

    for (let stage = 0; stage < 7; stage++) {
      const topY = LAYER_Y[stage] - 0.35;
      const botY = LAYER_Y[stage + 1] + 0.35;
      const topColor = new THREE.Color(LAYER_INFO[stage].color);
      const botColor = new THREE.Color(LAYER_INFO[stage + 1].color);
      const stageColor = topColor.clone().lerp(botColor, 0.5);

      const synapseMat = new THREE.LineBasicMaterial({
        color: stageColor,
        transparent: true,
        opacity: 0.38,
      });

      // 24 interweaving neural synapse fibers per stage
      const fiberCount = 24;
      for (let f = 0; f < fiberCount; f++) {
        const uAngle = (f * Math.PI * 2) / fiberCount;
        const uRadius = 1.2 + ((f * 7) % 5) * 0.45;
        const x1 = Math.cos(uAngle) * uRadius;
        const z1 = Math.sin(uAngle) * (uRadius * 0.65);

        const bAngle = uAngle + 0.45 + (f % 3) * 0.2;
        const bRadius = 1.0 + ((f * 3) % 5) * 0.45;
        const x2 = Math.cos(bAngle) * bRadius;
        const z2 = Math.sin(bAngle) * (bRadius * 0.65);

        const midX = (x1 + x2) * 0.5 + Math.sin(f + stage) * 0.25;
        const midY = (topY + botY) * 0.5;
        const midZ = (z1 + z2) * 0.5 + Math.cos(f + stage) * 0.25;

        const curve = new THREE.CatmullRomCurve3([
          new THREE.Vector3(x1, topY, z1),
          new THREE.Vector3(midX, midY, midZ),
          new THREE.Vector3(x2, botY, z2),
        ]);

        const points = curve.getPoints(16);
        const fiberGeo = new THREE.BufferGeometry().setFromPoints(points);
        synapseGroup.add(new THREE.Line(fiberGeo, synapseMat));

        // Precompute 24 points along the curve for instant O(1) photon positioning
        const photonSampledPoints = curve.getPoints(24);
        const photon = new THREE.Mesh(photonSphereGeo, photonSphereMat);
        synapseGroup.add(photon);
        synapsePhotons.push({
          mesh: photon,
          points: photonSampledPoints,
          speed: 0.6 + (f % 4) * 0.15,
          offset: (f / fiberCount) * 1.0,
        });
      }
    }
    synapsePhotonsRef.current = synapsePhotons;

    // =========================================================================
    // LUMINOUS NEON HALO BOUNDING BOX FOR PROMINENT ACTIVE LAYER HIGHLIGHT
    // =========================================================================
    const haloGroup = new THREE.Group();
    haloGroup.position.set(0, LAYER_Y[0], 0);

    const haloBoxGeo = new THREE.BoxGeometry(9.2, 1.8, 4.6);
    const haloEdges = new THREE.EdgesGeometry(haloBoxGeo);
    const haloLineMat = new THREE.LineBasicMaterial({
      color: 0x00d2ff,
      linewidth: 3,
      transparent: true,
      opacity: 0.95,
    });
    haloLineMatRef.current = haloLineMat;
    const haloLine = new THREE.LineSegments(haloEdges, haloLineMat);
    haloGroup.add(haloLine);

    const haloPlaneGeo = new THREE.PlaneGeometry(9.0, 4.4);
    const haloPlaneMat = new THREE.MeshBasicMaterial({
      color: 0x00d2ff,
      transparent: true,
      opacity: 0.08,
      side: THREE.DoubleSide,
    });
    haloPlaneMatRef.current = haloPlaneMat;
    const haloPlane = new THREE.Mesh(haloPlaneGeo, haloPlaneMat);
    haloPlane.rotation.x = Math.PI / 2;
    haloGroup.add(haloPlane);

    scene.add(haloGroup);
    haloBoundingBoxRef.current = haloGroup;

    // =========================================================================
    // CONTINUOUS CONDUIT PARTICLES (Central spine, Return loop, SSE Stream)
    // =========================================================================
    const particlesGroup = new THREE.Group();
    scene.add(particlesGroup);

    // Cascading downward particles along central vertical conduit
    const downCount = 75;
    const pGeo = new THREE.SphereGeometry(0.045, 8, 8);
    const pMat = new THREE.MeshBasicMaterial({ color: 0x00d2ff });
    const pDownList: THREE.Mesh[] = [];
    for (let p = 0; p < downCount; p++) {
      const pm = new THREE.Mesh(pGeo, pMat);
      const frac = p / downCount;
      pm.position.y = LAYER_Y[0] - frac * (LAYER_Y[0] - LAYER_Y[7]);
      pm.position.x = (Math.random() - 0.5) * 0.8;
      pm.position.z = (Math.random() - 0.5) * 0.8;
      particlesGroup.add(pm);
      pDownList.push(pm);
    }
    particlesDownRef.current = pDownList;

    // Loop 1 return particles (Layer 8 -> Layer 6 KV-Cache)
    const returnCount = 20;
    const pRetMat = new THREE.MeshBasicMaterial({ color: 0xa855f7 });
    const pRetList: THREE.Mesh[] = [];
    for (let r = 0; r < returnCount; r++) {
      const pm = new THREE.Mesh(pGeo, pRetMat);
      particlesGroup.add(pm);
      pRetList.push(pm);
    }
    particlesReturnRef.current = pRetList;

    // Loop 2 SSE stream particles (Layer 8 -> Chat Delivery)
    const sseCount = 16;
    const pSseMat = new THREE.MeshBasicMaterial({ color: 0x10b981 });
    const pSseList: THREE.Mesh[] = [];
    for (let s = 0; s < sseCount; s++) {
      const pm = new THREE.Mesh(pGeo, pSseMat);
      particlesGroup.add(pm);
      pSseList.push(pm);
    }
    particlesSseRef.current = pSseList;

    // =========================================================================
    // ANIMATION & RENDER LOOP (High-Performance 60 FPS, O(1) Precomputed Lookups)
    // =========================================================================
    let animId: number;
    const clock = new THREE.Clock();
    let pulseTime = 0;
    let isVisible = true;

    const observer = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting;
      },
      { threshold: 0.05 }
    );
    observer.observe(container);

    const animate = () => {
      animId = requestAnimationFrame(animate);

      // Skip render when offscreen or browser tab is hidden to save GPU/CPU
      if (!isVisible || document.hidden) return;

      const delta = Math.min(clock.getDelta(), 0.1);
      pulseTime += delta;

      // Smooth camera and controls interpolation
      if (isTransitioningCameraRef.current && camera && controls) {
        camera.position.lerp(targetCamPosRef.current, 0.08);
        controls.target.lerp(targetLookAtRef.current, 0.08);

        if (
          camera.position.distanceTo(targetCamPosRef.current) < 0.05 &&
          controls.target.distanceTo(targetLookAtRef.current) < 0.05
        ) {
          camera.position.copy(targetCamPosRef.current);
          controls.target.copy(targetLookAtRef.current);
          isTransitioningCameraRef.current = false;
        }
      }

      // Smooth Neon Halo Bounding Box lerp & pulse
      if (haloBoundingBoxRef.current) {
        const targetY = LAYER_Y[activeLayer - 1];
        haloBoundingBoxRef.current.position.y = THREE.MathUtils.lerp(
          haloBoundingBoxRef.current.position.y,
          targetY,
          0.1,
        );

        if (haloLineMatRef.current) {
          haloLineMatRef.current.opacity = 0.75 + Math.sin(pulseTime * 4.5) * 0.24;
        }
        if (haloPlaneMatRef.current) {
          haloPlaneMatRef.current.opacity = 0.07 + Math.sin(pulseTime * 4.5) * 0.04;
        }
      }

      if (isPlayingRef.current) {
        // Layer 1: RoPE Wave phase animation
        if (ropeWaveRibbonRef.current) {
          const positions = ropeWaveRibbonRef.current.geometry.attributes.position;
          for (let i = 0; i < positions.count; i++) {
            const x = positions.getX(i);
            positions.setY(i, 0.25 + Math.sin(x * 2.8 + pulseTime * 3.2) * 0.22);
            positions.setZ(i, 1.7 + Math.cos(x * 2.8 + pulseTime * 3.2) * 0.15);
          }
          positions.needsUpdate = true;
        }

        // Layer 3: Scanner plane sweep
        if (scannerPlaneRef.current) {
          scannerPlaneRef.current.position.y = Math.sin(pulseTime * 2.5) * 0.35;
        }

        // Layer 4: Rotate 6D Prism and Pareto Rings
        if (prismMeshRef.current) {
          prismMeshRef.current.rotation.y += delta * 0.45;
        }
        paretoRingsRef.current.forEach((ring, idx) => {
          ring.rotation.z += delta * (0.35 + idx * 0.2);
        });

        // Layer 5: Shockwave expansion on winning model
        if (shockwaveRingRef.current) {
          const scale = 1.0 + (pulseTime % 1.5) * 1.8;
          shockwaveRingRef.current.scale.set(scale, scale, scale);
          const mat = shockwaveRingRef.current.material as THREE.MeshBasicMaterial;
          mat.opacity = Math.max(0, 1.0 - (pulseTime % 1.5) / 1.5);
        }

        // Layer 7: Winning bar diamond beacon spin
        if (winningBarBeaconRef.current) {
          winningBarBeaconRef.current.rotation.y += delta * 2.0;
        }

        // Token jewel spin
        if (jewelMeshRef.current) {
          jewelMeshRef.current.rotation.y += delta * 1.5;
          jewelMeshRef.current.rotation.z += delta * 0.8;
        }

        // Cascade particles down central spine
        pDownList.forEach((pm) => {
          pm.position.y -= delta * 3.8;
          if (pm.position.y < LAYER_Y[7]) {
            pm.position.y = LAYER_Y[0];
            pm.position.x = (Math.random() - 0.5) * 0.8;
            pm.position.z = (Math.random() - 0.5) * 0.8;
          }
        });

        // Loop 1 particles (up return spline) - Instant O(1) Precomputed Lookup
        pRetList.forEach((pm, idx) => {
          const t = (pulseTime * 0.5 + idx / returnCount) % 1.0;
          const pt = returnPoints[Math.min(36, Math.floor(t * 36))];
          pm.position.set(pt.x, pt.y, pt.z);
        });

        // Loop 2 particles (down SSE optical fiber) - Instant O(1) Precomputed Lookup
        pSseList.forEach((pm, idx) => {
          const t = (pulseTime * 0.8 + idx / sseCount) % 1.0;
          const pt = ssePoints[Math.min(24, Math.floor(t * 24))];
          pm.position.set(pt.x, pt.y, pt.z);
        });

        // Synapse web traveling photon pulses - Instant O(1) Precomputed Lookup
        for (let i = 0; i < synapsePhotons.length; i++) {
          const sp = synapsePhotons[i];
          const t = (pulseTime * sp.speed + sp.offset) % 1.0;
          const idx = Math.min(24, Math.floor(t * 24));
          const pt = sp.points[idx];
          sp.mesh.position.set(pt.x, pt.y, pt.z);
        }
      }

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    const handleResize = () => {
      if (!container) return;
      const w = container.clientWidth || 960;
      const h = container.clientHeight || 620;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };
    window.addEventListener("resize", handleResize);

    return () => {
      observer.disconnect();
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", handleResize);
      controls.dispose();

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
  }, []);

  // Prominently highlight active layer: halo color update, boosted emissive, dimming inactive layers
  const applyLayerVisualStates = (activeId: number) => {
    const activeColorHex = LAYER_INFO[activeId - 1].color;
    if (haloLineMatRef.current) {
      haloLineMatRef.current.color.set(activeColorHex);
    }
    if (haloPlaneMatRef.current) {
      haloPlaneMatRef.current.color.set(activeColorHex);
    }

    // Traverse all layer groups to apply active highlight vs. inactive dimming
    layerGroupsRef.current.forEach((group, idx) => {
      const isActive = idx + 1 === activeId;
      group.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          if (obj.material instanceof THREE.MeshPhysicalMaterial) {
            obj.material.opacity = isActive ? 0.95 : 0.32;
            obj.material.transmission = isActive ? 0.85 : 0.95;
            if (obj.material.emissive) {
              obj.material.emissiveIntensity = isActive ? 1.4 : 0.15;
            }
          } else if (obj.material instanceof THREE.MeshStandardMaterial) {
            obj.material.transparent = !isActive;
            obj.material.opacity = isActive ? 1.0 : 0.32;
            if (obj.material.emissive) {
              obj.material.emissiveIntensity = isActive ? 1.5 : 0.15;
            }
          } else if (obj.material instanceof THREE.MeshBasicMaterial) {
            if (obj.material.transparent) {
              obj.material.opacity = isActive ? 0.85 : 0.28;
            }
          }
        } else if (obj instanceof THREE.Line || obj instanceof THREE.LineSegments) {
          if (obj.material instanceof THREE.LineBasicMaterial) {
            obj.material.transparent = true;
            obj.material.opacity = isActive ? 1.0 : 0.28;
          }
        }
      });
    });
  };

  useEffect(() => {
    applyLayerVisualStates(activeLayer);
  }, [activeLayer]);

  // Reactive Update Effect: Update dynamic meshes when scenario preset changes without WebGL context recreation
  useEffect(() => {
    // 1. Update Layer 5 Server Towers emissive & beacons
    serverTowersRef.current.forEach((t) => {
      const isWinner = t.id === currentPreset.winnerModelId;
      const mat = t.mesh.material as THREE.MeshStandardMaterial;
      mat.emissive.set(isWinner ? t.defColor : 0x0f172a);
      mat.emissiveIntensity = isWinner ? 1.1 : 0.25;
      const bMat = t.beacon.material as THREE.MeshBasicMaterial;
      bMat.color.set(isWinner ? 0xffffff : t.defColor);
    });

    // 2. Position Shockwave Ring and Focused Router Laser Beam at active server tower
    const winningDef =
      SERVER_MODEL_DEFS.find((d) => d.id === currentPreset.winnerModelId) ||
      SERVER_MODEL_DEFS[0];
    if (shockwaveRingRef.current) {
      shockwaveRingRef.current.position.set(winningDef.pos[0], 0.18, winningDef.pos[2]);
    }
    if (serverLaserBeamRef.current) {
      serverLaserBeamRef.current.position.set(winningDef.pos[0] * 0.5, 1.2, winningDef.pos[2] * 0.5);
      serverLaserBeamRef.current.lookAt(winningDef.pos[0], 0.75, winningDef.pos[2]);
    }

    // 3. Update Layer 7 Probability Bars & In-scene Candidate Token Sprites
    if (probBarsGroupRef.current) {
      while (probBarsGroupRef.current.children.length > 0) {
        const child = probBarsGroupRef.current.children[0];
        probBarsGroupRef.current.remove(child);
        if (child instanceof THREE.Mesh) {
          child.geometry?.dispose();
        }
        const mat = (child as any).material;
        if (mat) {
          if (Array.isArray(mat)) {
            mat.forEach((m) => {
              if (m && "map" in m && m.map) m.map.dispose();
              m?.dispose();
            });
          } else {
            if ("map" in mat && mat.map) mat.map.dispose();
            mat.dispose();
          }
        }
      }

      const probBars: THREE.Mesh[] = [];
      const candidates = currentPreset.candidateTokens;
      candidates.forEach((cand, idx) => {
        const barHeight = Math.max(0.25, cand.prob * 2.2);
        const barGeo = new THREE.BoxGeometry(0.45, barHeight, 0.45);
        const barMat = new THREE.MeshStandardMaterial({
          color: cand.isWinner ? 0xf59e0b : 0x0284c7,
          emissive: cand.isWinner ? 0xf59e0b : 0x002f54,
          emissiveIntensity: cand.isWinner ? 1.1 : 0.25,
          roughness: 0.15,
          metalness: 0.85,
        });
        const barMesh = new THREE.Mesh(barGeo, barMat);
        const bx = -1.6 + idx * 0.65;
        barMesh.position.set(bx, -0.15 + barHeight / 2, 0);
        probBarsGroupRef.current?.add(barMesh);
        probBars.push(barMesh);

        // 3D Text Sprite showing token string
        const tokenSprite = createTextSprite(
          cand.token,
          cand.isWinner ? "#f59e0b" : "#94a3b8",
          cand.isWinner ? "rgba(245, 158, 11, 0.25)" : "rgba(15, 23, 42, 0.65)",
          26,
        );
        tokenSprite.position.set(bx, -0.38, 0.3);
        tokenSprite.scale.set(0.55, 0.18, 1);
        probBarsGroupRef.current?.add(tokenSprite);

        // Winning bar diamond beacon
        if (cand.isWinner) {
          const diamondGeo = new THREE.OctahedronGeometry(0.16, 0);
          const diamondMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
          const diamond = new THREE.Mesh(diamondGeo, diamondMat);
          diamond.position.set(bx, -0.15 + barHeight + 0.25, 0);
          probBarsGroupRef.current?.add(diamond);
          winningBarBeaconRef.current = diamond;
        }
      });
      probabilityBarsRef.current = probBars;

      // Re-apply current activeLayer highlight or dimming state to newly created Layer 7 meshes
      applyLayerVisualStates(activeLayer);
    }
  }, [currentPreset, activeLayer]);

  // Smoothly lerp camera target and position to center selected layer
  const handleSelectLayer = (layerId: number) => {
    setActiveLayer(layerId);
    const targetY = LAYER_Y[layerId - 1];
    targetLookAtRef.current.set(0, targetY, 0);
    targetCamPosRef.current.set(0, targetY + 1.2, 10.5);
    isTransitioningCameraRef.current = true;
  };

  const handleResetCamera = () => {
    targetLookAtRef.current.set(0, 0, 0);
    targetCamPosRef.current.set(0, 1.2, 24.0);
    isTransitioningCameraRef.current = true;
  };

  const activeLayerData = LAYER_INFO[activeLayer - 1];

  return (
    <div
      className={`pipeline-flow-container flex flex-col gap-5 p-4 lg:p-6 h-full overflow-y-auto ${className}`}
      style={{
        maxWidth: 1440,
        margin: "0 auto",
        width: "100%",
        fontFamily: "var(--font-roboto, sans-serif)",
      }}
    >
      {/* Header & Architecture Summary */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-sky-100 px-2.5 py-0.5 text-xs font-semibold text-sky-800">
              <Layers size={14} /> KIẾN TRÚC 8 TẦNG HOÀN CHỈNH (END-TO-END TRANSFORMER)
            </span>
          </div>
          <h1 className="mt-1 text-2xl font-bold text-slate-900 tracking-tight">
            Luồng Trực Quan Hóa 3D Toàn Trình (End-to-End Pipeline & Transformer Core)
          </h1>
          <p className="text-sm text-slate-500">
            Hành trình dữ liệu từ Input Tensor, KV Memory Khoa, Nén Tân, Router Huy, Máy chủ,
            giải mã Transformer QKV & SwiGLU, tháp Logits Softmax đến dòng phát SSE thời gian thực.
          </p>
        </div>

        {/* Play/Pause & Reset View Controller */}
        <div className="flex items-center gap-2 self-stretch md:self-auto">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
            onClick={() => setIsPlaying(!isPlaying)}
          >
            {isPlaying ? (
              <>
                <Pause size={14} className="text-amber-600" /> Tạm dừng
              </>
            ) : (
              <>
                <Play size={14} className="text-emerald-600" /> Tiếp tục chạy
              </>
            )}
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition"
            onClick={handleResetCamera}
          >
            <RotateCcw size={14} /> Toàn cảnh (Reset View)
          </button>
        </div>
      </div>

      {/* Preset Scenarios Selector Bar */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2 block">
          Chọn tình huống thử nghiệm (Simulation Scenarios):
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-2">
          {SIMULATION_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              onClick={() => setSelectedPresetId(preset.id)}
              className={`flex flex-col text-left p-3 rounded-lg border transition ${
                selectedPresetId === preset.id
                  ? "border-[#005696] bg-sky-50/70 ring-1 ring-[#005696]"
                  : "border-slate-200 hover:border-slate-300 bg-white"
              }`}
            >
              <span className="text-[11px] font-medium text-slate-400">
                {preset.category}
              </span>
              <strong className="text-xs font-semibold text-slate-800 line-clamp-1 mt-0.5">
                {preset.name}
              </strong>
              <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                <span>{preset.inputTokens} tok</span>
                <span className="font-semibold text-emerald-600">
                  -{preset.compactionPct}%
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Step-by-Step Layer Navigator (1 to 8) */}
      <div className="flex items-center justify-between bg-white border border-slate-200 rounded-xl p-2.5 shadow-sm">
        <div className="flex items-center gap-1 text-xs text-slate-600 font-semibold px-2">
          <Eye size={14} className="text-[#005696]" /> Bước duyệt tầng (Step Controller):
        </div>
        <div className="flex items-center gap-1.5 overflow-x-auto py-1">
          <button
            type="button"
            disabled={activeLayer <= 1}
            onClick={() => handleSelectLayer(Math.max(1, activeLayer - 1))}
            className="p-1.5 rounded border border-slate-200 text-slate-600 disabled:opacity-40 hover:bg-slate-50"
            title="Tầng trước"
          >
            <ChevronLeft size={16} />
          </button>
          {LAYER_INFO.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => handleSelectLayer(l.id)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                activeLayer === l.id
                  ? "bg-[#005696] text-white shadow-sm font-bold"
                  : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              T{l.id}
            </button>
          ))}
          <button
            type="button"
            disabled={activeLayer >= 8}
            onClick={() => handleSelectLayer(Math.min(8, activeLayer + 1))}
            className="p-1.5 rounded border border-slate-200 text-slate-600 disabled:opacity-40 hover:bg-slate-50"
            title="Tầng tiếp theo"
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* 3D Canvas Visualizer & Active Layer Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* Left/Center: WebGL Canvas Frame */}
        <div className="lg:col-span-8 flex flex-col rounded-2xl border border-slate-200/90 bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-4 py-2.5">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs font-semibold text-slate-700">
                WebGL 3D Engine · 8 Tầng Thần Kinh Liên Tầng (Synapse Web & Lerp Focus)
              </span>
            </div>
            <span className="text-xs text-slate-400">
              Nhấp & kéo chuột để xoay 360° · Cuộn để zoom · Chọn tầng T1-T8 để zoom chi tiết
            </span>
          </div>

          <div
            ref={mountRef}
            className="relative h-[620px] w-full bg-[#f8fafc]"
          />

          {/* 8 Layer Bottom Selector Bar */}
          <div className="grid grid-cols-4 sm:grid-cols-8 border-t border-slate-200 bg-slate-50 text-center divide-x divide-slate-200 text-xs">
            {[
              { id: 1, name: "T1: Input", icon: Database },
              { id: 2, name: "T2: Khoa KV", icon: Cpu },
              { id: 3, name: "T3: Tân Sieve", icon: TrendingDown },
              { id: 4, name: "T4: Huy 6D", icon: Zap },
              { id: 5, name: "T5: Model", icon: Server },
              { id: 6, name: "T6: Decoders", icon: Binary },
              { id: 7, name: "T7: LM Head", icon: BarChart3 },
              { id: 8, name: "T8: SSE Loop", icon: Send },
            ].map((layer) => {
              const Icon = layer.icon;
              return (
                <button
                  key={layer.id}
                  type="button"
                  onClick={() => handleSelectLayer(layer.id)}
                  className={`p-2.5 text-xs font-medium flex flex-col items-center gap-1 transition ${
                    activeLayer === layer.id
                      ? "bg-white text-[#005696] font-bold shadow-inner border-b-2 border-[#005696]"
                      : "text-slate-600 hover:bg-slate-100/80"
                  }`}
                >
                  <Icon size={15} />
                  <span className="truncate">{layer.name}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Layer Inspector Detail Card */}
        <div className="lg:col-span-4 flex flex-col gap-4">
          {/* Active Layer Deep Dive Card */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-sky-600">
                  {activeLayerData.module}
                </span>
                <h3 className="font-bold text-slate-900 text-base mt-0.5">
                  {activeLayerData.title}
                </h3>
              </div>
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: activeLayerData.color }}
              />
            </div>

            {/* Scientific Mathematical Formulation Rendered with KaTeX */}
            <div className="mt-3 rounded-lg bg-slate-900 p-3 text-white">
              <span className="text-[10px] uppercase tracking-wider text-slate-400 block mb-1">
                Công thức Toán học (Mathematical Formulation):
              </span>
              <div
                className="text-xs text-emerald-300 overflow-x-auto py-1 katex-formula"
                dangerouslySetInnerHTML={{
                  __html: katex.renderToString(activeLayerData.formula, {
                    displayMode: true,
                    throwOnError: false,
                  }),
                }}
              />
            </div>

            {/* Plain Vietnamese Scientific Explanation */}
            <p className="mt-3 text-xs text-slate-600 leading-relaxed">
              {activeLayerData.description}
            </p>

            {/* Layer-Specific Quantitative Metrics */}
            <div className="mt-4 space-y-2 rounded-lg bg-slate-50 p-3 text-xs border border-slate-100">
              {activeLayer === 1 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Raw Token Count:" : "Số lượng Token thô:"}</span>
                    <strong className="text-slate-800">{currentPreset.inputTokens} tokens</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Tensor Dimension:" : "Kích thước Tensor:"}</span>
                    <strong className="text-slate-800">[1, {currentPreset.inputTokens}, 4096]</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Positional Encoding:" : "Mã hóa vị trí:"}</span>
                    <strong className="text-sky-700">RoPE 3D Wave Ribbon</strong>
                  </div>
                </>
              )}

              {activeLayer === 2 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Activated Memory Slots:" : "Số Slots ký ức kích hoạt:"}</span>
                    <strong className="text-emerald-700">{currentPreset.memorySlotsHit} / 10 slots</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Recovered Fact:" : "Sự thật hồi phục:"}</span>
                    <span className="text-slate-800 font-medium italic text-right max-w-[200px]">
                      {currentPreset.memoryFact}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Retrieval Accuracy:" : "Độ chính xác truy xuất:"}</span>
                    <strong className="text-emerald-700">99.4%</strong>
                  </div>
                </>
              )}

              {activeLayer === 3 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Pre-compaction Tokens:" : "Token trước nén:"}</span>
                    <strong className="text-slate-800">{currentPreset.inputTokens}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Post-compaction Tokens:" : "Token sau nén:"}</span>
                    <strong className="text-emerald-600">{currentPreset.compactedTokens}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Reduction Ratio:" : "Tỷ lệ giảm tải:"}</span>
                    <strong className="text-emerald-600">-{currentPreset.compactionPct}%</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Entity Preservation:" : "Bảo toàn thực thể:"}</span>
                    <strong className="text-sky-700">100% (Math & Code Invariant)</strong>
                  </div>
                </>
              )}

              {activeLayer === 4 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Winning Model:" : "Mô hình chiến thắng:"}</span>
                    <strong className="text-indigo-700">{currentPreset.winnerModelName}</strong>
                  </div>
                  <div className="mt-2 space-y-1">
                    {Object.entries(currentPreset.attentionScores).map(([dim, val]) => (
                      <div key={dim} className="flex items-center justify-between text-[11px]">
                        <span className="capitalize text-slate-500">{dim}:</span>
                        <div className="flex items-center gap-1.5">
                          <div className="w-20 h-1 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-indigo-600 rounded-full"
                              style={{ width: `${val * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-slate-700 w-7 text-right">
                            {(val * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {activeLayer === 5 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Dispatched Model:" : "Mô hình được điều động:"}</span>
                    <strong className="text-slate-900">{currentPreset.winnerModelName}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Estimated P50 Latency:" : "Độ trễ P50 ước tính:"}</span>
                    <strong className="text-slate-800">{currentPreset.estimatedLatencyMs} ms</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Serving Cost:" : "Chi phí phục vụ:"}</span>
                    <strong className="text-emerald-600">${currentPreset.estimatedCostUsd.toFixed(5)}</strong>
                  </div>
                </>
              )}

              {activeLayer === 6 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Attention Heads:" : "Số Attention Heads:"}</span>
                    <strong className="text-slate-900">{currentPreset.transformerHeads} heads</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "SwiGLU FFN Dimension:" : "Kích thước SwiGLU FFN:"}</span>
                    <strong className="text-amber-700">{currentPreset.mlpExpansion}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "KV-Cache Optimization:" : "Tối ưu KV-Cache:"}</span>
                    <strong className="text-emerald-600">FlashAttention-2 Kernel</strong>
                  </div>
                </>
              )}

              {activeLayer === 7 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Winning Next Token:" : "Token chiến thắng:"}</span>
                    <strong className="text-amber-700 font-mono text-sm">
                      &quot;{currentPreset.winnerToken}&quot;
                    </strong>
                  </div>
                  <div className="mt-2 space-y-1">
                    {currentPreset.candidateTokens.map((cand) => (
                      <div key={cand.token} className="flex items-center justify-between text-[11px]">
                        <span className="font-mono text-slate-600">&quot;{cand.token}&quot;:</span>
                        <div className="flex items-center gap-1.5">
                          <div className="w-20 h-1 bg-slate-200 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                cand.isWinner ? "bg-amber-500" : "bg-sky-500"
                              }`}
                              style={{ width: `${cand.prob * 100}%` }}
                            />
                          </div>
                          <span className="font-mono text-slate-700 w-8 text-right">
                            {(cand.prob * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              {activeLayer === 8 && (
                <>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Autoregressive (Loop 1):" : "Vòng lặp tự hồi quy (Loop 1):"}</span>
                    <strong className="text-purple-700">{locale === "en" ? "Append to KV-Cache (t+1)" : "Nạp vào KV-Cache (t+1)"}</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Real-time SSE (Loop 2):" : "Luồng SSE phát trực tiếp (Loop 2):"}</span>
                    <strong className="text-emerald-700">Typewriter Effect</strong>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{locale === "en" ? "Generated Token:" : "Token đã sinh:"}</span>
                    <span className="text-amber-800 font-mono bg-amber-50 px-2 py-0.5 rounded font-bold">
                      {currentPreset.winnerToken}
                    </span>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Real-time Architecture Status Card */}
          <div className="rounded-2xl border border-slate-200 bg-slate-900 p-5 text-white shadow-sm">
            <span className="text-[11px] font-semibold tracking-wider uppercase text-sky-400">
              {locale === "en" ? "Architecture Pipeline Status" : "Trạng thái Luồng Kiến trúc"}
            </span>
            <div className="mt-3 space-y-2 text-xs text-slate-300">
              <div className="flex justify-between border-b border-slate-800 pb-2">
                <span className="text-slate-400">{locale === "en" ? "Current Subsystem:" : "Phân hệ đang xem:"}</span>
                <strong className="text-white">{locale === "en" ? `Layer ${activeLayer}: ${activeLayerData.title}` : `Tầng ${activeLayer}: ${activeLayerData.title}`}</strong>
              </div>
              <div className="flex justify-between border-b border-slate-800 pb-2">
                <span className="text-slate-400">{locale === "en" ? "Processing Engine:" : "Cơ chế xử lý:"}</span>
                <span className="text-emerald-400 font-medium">NumPy CPU Vectorization (&lt;0.5ms)</span>
              </div>
              <div className="flex justify-between pt-1">
                <span className="text-slate-400">{locale === "en" ? "Ablation Benchmark:" : "Đo lường Ablation:"}</span>
                <a href="/research" className="text-sky-400 hover:underline font-medium">
                  {locale === "en" ? "View 500-sample Benchmark Matrix →" : "Xem bảng Benchmark 500 mẫu →"}
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
