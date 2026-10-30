import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, Vite proxies API calls to the FastAPI server, so the browser sees one origin
// (no CORS setup needed). In production FastAPI serves the built files itself.
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true, timeout: 300000, proxyTimeout: 300000 },
      "/health": { target: backend, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: false },
  test: { environment: "jsdom", include: ["tests/**/*.test.js"] },
});
