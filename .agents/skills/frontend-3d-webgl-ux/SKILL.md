---
name: frontend-3d-webgl-ux
description: Quy chuẩn và mẫu thiết kế trực quan hóa 3D không gian đánh đổi Pareto (Cost, Latency, Quality), luồng Attention Token Flows và mạng nơ-ron bằng Three.js/WebGL tối ưu cho React 19 và Next.js 16 App Router.
---

# Frontend 3D WebGL UX & Data Visualization

Kỹ năng chuyên sâu về xây dựng các thành phần giao diện 3D tương tác cao, trực quan hóa dữ liệu AI/ML phức tạp (không gian đánh đổi Pareto đa mục tiêu, luồng trọng số Attention, mạng nơ-ron) bằng Three.js và WebGL trong môi trường Next.js 16 App Router và React 19.

## 1. Nguyên tắc cốt lõi & Tối ưu hiệu năng (Performance Rules)

### 1.1. Chống lỗi SSR & Hydration Mismatch trong Next.js 16
- **Tuyệt đối không chạy WebGL ở Server Components**: Mọi canvas 3D phải được đánh dấu `'use client'` và import thông qua `next/dynamic` với tùy chọn `{ ssr: false }`.
- **Cơ chế khởi tạo an toàn**: Luôn kiểm tra `typeof window !== 'undefined'` và gắn canvas vào `ref` sau khi DOM node đã mount hoàn tất trong `useEffect`.

```tsx
// Pattern import an toàn vào trang Next.js:
import dynamic from 'next/dynamic';

const ParetoScatterSurface3D = dynamic(
  () => import('@/components/3d/pareto-surface-3d'),
  { ssr: false, loading: () => <div className="h-96 w-full animate-pulse bg-slate-100 rounded-xl" /> }
);
```

### 1.2. Vòng lặp Render theo sự kiện (Event-Driven / Dirty Loop)
- **Không chạy `requestAnimationFrame` liên tục 60fps khi cảnh tĩnh**: Việc render liên tục đốt tài nguyên GPU, làm nóng máy người dùng và gây giật lag luồng Chat.
- **Kích hoạt render khi có thay đổi (Dirty Checking)**:
  - Khi người dùng xoay/zoom camera qua `OrbitControls` (bắt sự kiện `controls.addEventListener('change', render)`).
  - Khi dữ liệu Pareto/Attention thay đổi (props update).
  - Khi cửa sổ thay đổi kích thước (`resize` event).
  - Chỉ duy trì animation loop khi đang hiển thị luồng particle di chuyển (particle animation), và lập tức dừng lại khi hoàn thành.

### 1.3. Giải phóng bộ nhớ GPU triệt để (Zero VRAM Leak)
Khi component unmount, bắt buộc phải dọn dẹp sạch sẽ:
- `geometry.dispose()`
- `material.dispose()` (nếu có texture, gọi `texture.dispose()`)
- `renderer.dispose()` và `renderer.forceContextLoss()`
- Hủy bỏ các event listener trên `window` và `controls`

---

## 2. Hệ thống Nhận diện Trực quan (OU Blue Aesthetic)

Tuân thủ bảng màu chuẩn của dự án:
- **Tông màu chủ đạo**:
  - OU Blue Primary: `#005696` (nút bấm, node được chọn, camera focus)
  - OU Blue Dark / Navy: `#002f54` (trục tọa độ chính, grid base)
  - Background: Trắng sáng tinh khiết `#f8fafc` hoặc `#ffffff` (phù hợp theme sáng chuẩn của trường)
  - Highlight Accent: `#0284c7` (Sky 600), `#10b981` (Emerald Pass), `#f43f5e` (Rose Failure)
- **Card & Tooltip**:
  - Glassmorphism nhẹ: `backdrop-blur-md bg-white/90 border border-slate-200/80 shadow-lg shadow-sky-950/5`
  - Typography: Font **Roboto** cục bộ, cỡ chữ rõ ràng, nhãn trục tọa độ dễ đọc.

---

## 3. Kiến trúc Component Mẫu: Trực quan hóa Pareto 3D

Dưới đây là component TypeScript chuẩn vẽ đám mây điểm candidate models và mặt cong lưới Pareto trong không gian 3 chiều:
- **Trục X**: Chi phí chuẩn hóa (Cost USD / 1k tokens)
- **Trục Y**: Độ trễ (P50/P90 Latency ms)
- **Trục Z**: Tỷ lệ đạt chất lượng (Quality / Pass Rate %)

```tsx
'use client';

import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export interface CandidatePoint {
  id: string;
  name: string;
  costUsd: number;      // Trục X (0 -> 1 normalized)
  latencyMs: number;    // Trục Y (0 -> 1 normalized)
  qualityRate: number;  // Trục Z (0 -> 1)
  isParetoOptimal: boolean;
}

interface ParetoViewerProps {
  candidates: CandidatePoint[];
  width?: number;
  height?: number;
}

export function ParetoScatterSurface3D({ candidates, width = 640, height = 420 }: ParetoViewerProps) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // 1. Scene, Camera, Renderer
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc); // Nền sáng sạch

    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.set(2.5, 2.0, 3.0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;

    // 2. Grid & Axes helper (OU Navy & Sky)
    const gridHelper = new THREE.GridHelper(2, 10, 0x002f54, 0xe2e8f0);
    gridHelper.position.set(0.5, 0, 0.5);
    scene.add(gridHelper);

    // 3. Render candidates as 3D Spheres
    const sphereGeometry = new THREE.SphereGeometry(0.04, 16, 16);
    const paretoMaterial = new THREE.MeshStandardMaterial({
      color: 0x005696, // OU Blue cho Pareto non-dominated
      roughness: 0.2,
      metalness: 0.8,
    });
    const subOptimalMaterial = new THREE.MeshStandardMaterial({
      color: 0x94a3b8, // Slate xám cho dominated
      roughness: 0.5,
    });

    const meshes: THREE.Mesh[] = [];
    candidates.forEach((cand) => {
      const mesh = new THREE.Mesh(
        sphereGeometry,
        cand.isParetoOptimal ? paretoMaterial : subOptimalMaterial
      );
      // Map to 3D coords: X=Cost, Y=Quality (lên cao), Z=Latency
      mesh.position.set(cand.costUsd, cand.qualityRate, cand.latencyMs);
      mesh.userData = cand;
      scene.add(mesh);
      meshes.push(mesh);
    });

    // 4. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);
    const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
    dirLight.position.set(5, 10, 7);
    scene.add(dirLight);

    // 5. Render Loop (Chỉ render khi tương tác)
    let animationFrameId: number;
    let isDirty = true;

    const requestRender = () => { isDirty = true; };
    controls.addEventListener('change', requestRender);

    const animate = () => {
      animationFrameId = requestAnimationFrame(animate);
      if (isDirty) {
        controls.update();
        renderer.render(scene, camera);
        isDirty = false;
      }
    };
    animate();

    // 6. Cleanup GPU resources khi unmount
    return () => {
      cancelAnimationFrame(animationFrameId);
      controls.removeEventListener('change', requestRender);
      controls.dispose();

      meshes.forEach((mesh) => {
        scene.remove(mesh);
      });
      sphereGeometry.dispose();
      paretoMaterial.dispose();
      subOptimalMaterial.dispose();
      gridHelper.dispose();

      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [candidates, width, height]);

  return (
    <div className="relative rounded-2xl border border-slate-200/80 bg-white/80 p-2 shadow-sm">
      <div className="absolute top-4 left-4 z-10 rounded-lg bg-white/90 p-2 text-xs backdrop-blur font-medium text-slate-700 shadow border border-slate-200">
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-[#005696] mr-1.5" /> Pareto Optimal (Tối ưu)
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-400 mr-1.5 ml-3" /> Dominated (Bị áp đảo)
      </div>
      <div ref={mountRef} className="overflow-hidden rounded-xl" />
    </div>
  );
}
```

---

## 4. Checklist Thẩm định Chất lượng 3D Frontend

- [ ] Canvas được gắn `key` duy nhất và không bị re-mount vô tận khi re-render cha.
- [ ] Không rò rỉ WebGL contexts (kiểm tra `MAX_WEBGL_CONTEXTS` không bị vượt quá khi chuyển trang).
- [ ] Đã tắt `ssr` khi dynamic import để chống crash Hydration.
- [ ] Sử dụng bảng màu sáng OU Blue, nền trong suốt hoặc trắng `#f8fafc`.
- [ ] Tắt continuous rendering loop khi cảnh đứng yên.
