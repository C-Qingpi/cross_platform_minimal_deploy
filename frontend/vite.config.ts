import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const MODE_PORTS: Record<string, [number, number]> = {
  dev: [8920, 5174],
  prod: [8921, 5175],
};

function readDeployPorts(deployRoot: string): { backendPort: number; frontendPort: number } {
  const cfgPath = path.join(deployRoot, "deploy.config");
  if (!fs.existsSync(cfgPath)) {
    return { backendPort: 8920, frontendPort: 5174 };
  }
  let mode = "";
  let backendPort = "";
  let frontendPort = "";
  for (const raw of fs.readFileSync(cfgPath, "utf8").split(/\r?\n/)) {
    const line = raw.replace(/#.*$/, "").trim();
    if (!line || !line.includes("=")) continue;
    const [keyRaw, valRaw] = line.split("=", 2);
    const key = keyRaw.trim().toLowerCase();
    const val = valRaw.trim();
    if (key === "mode") mode = val.toLowerCase();
    if (key === "backend_port") backendPort = val;
    if (key === "frontend_port") frontendPort = val;
  }
  const defaults = MODE_PORTS[mode] ?? MODE_PORTS.dev;
  return {
    backendPort: Number(process.env.BACKEND_PORT || backendPort || defaults[0]),
    frontendPort: Number(process.env.FRONTEND_PORT || frontendPort || defaults[1]),
  };
}

export default defineConfig(() => {
  const deployRoot = path.resolve(__dirname, "..");
  const { backendPort, frontendPort } = readDeployPorts(deployRoot);

  return {
    plugins: [tailwindcss(), react()],
    server: {
      port: frontendPort,
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${backendPort}`,
          changeOrigin: true,
        },
      },
    },
  };
});
