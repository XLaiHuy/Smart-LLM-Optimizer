import { chromium } from "playwright";

async function runStressTest() {
  console.log("=== STARTING WEBGL 25x MOUNT/UNMOUNT STRESS TEST ===");
  const browser = await chromium.launch({
    headless: true,
    args: ["--use-gl=angle", "--use-angle=swiftshader"], // Ensure WebGL is active in headless
  });
  const context = await browser.newContext();
  const page = await context.newPage();

  const warnings = [];
  const errors = [];
  page.on("console", (msg) => {
    const text = msg.text();
    if (msg.type() === "warning" || text.includes("WARNING") || text.includes("WebGL")) {
      warnings.push(text);
      console.log(`[BROWSER WARNING]: ${text}`);
    }
    if (msg.type() === "error") {
      errors.push(text);
      console.log(`[BROWSER ERROR]: ${text}`);
    }
  });

  // Load a minimal page that includes Three.js via CDN or local bundle
  await page.setContent(`
    <!DOCTYPE html>
    <html>
      <head><title>WebGL Stress</title></head>
      <body>
        <div id="container" style="width: 640px; height: 480px;"></div>
        <script type="importmap">
          {
            "imports": {
              "three": "https://unpkg.com/three@0.186.1/build/three.module.js"
            }
          }
        </script>
        <script type="module">
          import * as THREE from 'three';
          window.THREE = THREE;
          window.stressResults = { mounted: 0, unmounted: 0 };

          // Test mounting and unmounting 25 times with cleanup protocol
          window.runMountCycleWithCleanup = async function(count) {
            const container = document.getElementById('container');
            const logs = [];

            for (let i = 0; i < count; i++) {
              // 1. Mount (simulate NeuralRoutingCosmos3D & ParetoScatterSurface3D)
              const scene = new THREE.Scene();
              const camera = new THREE.PerspectiveCamera(45, 640 / 480, 0.1, 100);
              const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
              renderer.setSize(640, 480);
              container.appendChild(renderer.domElement);

              // Add geometries and materials as in components
              const sphereGeo = new THREE.SphereGeometry(0.04, 16, 16);
              const mat1 = new THREE.MeshStandardMaterial({ color: 0x005696 });
              const mat2 = new THREE.MeshStandardMaterial({ color: 0x94a3b8 });
              const mesh1 = new THREE.Mesh(sphereGeo, mat1);
              const mesh2 = new THREE.Mesh(sphereGeo, mat2);
              scene.add(mesh1);
              scene.add(mesh2);

              const grid = new THREE.GridHelper(2, 10, 0x002f54, 0xe2e8f0);
              scene.add(grid);

              renderer.render(scene, camera);
              window.stressResults.mounted++;

              // Small yield to simulate frame
              await new Promise(r => setTimeout(r, 10));

              // 2. Unmount with full cleanup protocol:
              scene.traverse((obj) => {
                if (obj.geometry) obj.geometry.dispose();
                if (obj.material) {
                  if (Array.isArray(obj.material)) obj.material.forEach(m => m.dispose());
                  else obj.material.dispose();
                }
              });
              grid.dispose();
              renderer.dispose();
              renderer.forceContextLoss(); // The critical fix!

              if (container.contains(renderer.domElement)) {
                container.removeChild(renderer.domElement);
              }
              window.stressResults.unmounted++;
            }
            return {
              mounted: window.stressResults.mounted,
              unmounted: window.stressResults.unmounted
            };
          };

          // Test WITHOUT forceContextLoss (to prove that warnings/leaks DO occur without it)
          window.runMountCycleWITHOUTCleanup = async function(count) {
            const container = document.getElementById('container');
            let contextLossWarnings = 0;

            for (let i = 0; i < count; i++) {
              const renderer = new THREE.WebGLRenderer();
              container.appendChild(renderer.domElement);
              // Deliberately do NOT call forceContextLoss or dispose
              await new Promise(r => setTimeout(r, 10));
              if (container.contains(renderer.domElement)) {
                container.removeChild(renderer.domElement);
              }
            }
            return { attempted: count };
          };
        </script>
      </body>
    </html>
  `);

  console.log("Testing 25x mount/unmount WITH full cleanup (forceContextLoss + dispose)...");
  const resultWithCleanup = await page.evaluate(async () => {
    return await window.runMountCycleWithCleanup(25);
  });

  console.log("Result with cleanup:", resultWithCleanup);
  console.log(`Warnings captured during cleaned cycles: ${warnings.length}`);

  const hasContextLimitWarning = warnings.some(w => w.includes("Too many active WebGL contexts"));
  console.log(`Context limit warning present with cleanup? ${hasContextLimitWarning ? "YES (FAILED)" : "NO (PASSED)"}`);

  // Now clear warnings and run WITHOUT cleanup to demonstrate that the browser DOES warn/leak
  warnings.length = 0;
  console.log("\nTesting 25x mount/unmount WITHOUT forceContextLoss (negative control)...");
  await page.evaluate(async () => {
    return await window.runMountCycleWITHOUTCleanup(25);
  });
  console.log(`Warnings captured WITHOUT cleanup: ${warnings.length}`);
  const warnedWithoutCleanup = warnings.some(w => w.includes("Too many active WebGL contexts"));
  console.log(`Context limit warning present WITHOUT cleanup? ${warnedWithoutCleanup ? "YES (Confirmed vulnerability reproduced)" : "NO"}`);

  await browser.close();

  return {
    cycles: 25,
    resultWithCleanup,
    cleanCycleWarnings: warnings.length,
    forceContextLossPreventsLeak: !hasContextLimitWarning,
    vulnerabilityReproducedWithoutDisposal: warnedWithoutCleanup,
  };
}

runStressTest()
  .then((res) => {
    console.log("\n=== WEBGL STRESS TEST SUMMARY ===");
    console.log(JSON.stringify(res, null, 2));
    process.exit(0);
  })
  .catch((err) => {
    console.error("Stress test failed with error:", err);
    process.exit(1);
  });
