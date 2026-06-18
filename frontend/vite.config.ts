import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig(({ mode }) => {
  const deployRoot = path.resolve(__dirname, "..");
  const env = loadEnv(mode, deployRoot, "");
  const backendPort = (env.BACKEND_PORT || "8920").trim();

  return {
    plugins: [tailwindcss(), react()],
    server: {
      port: 5174,
      proxy: { "/api": { target: `http://127.0.0.1:${backendPort}` } },
    },
  };
});
