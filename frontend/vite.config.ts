import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BACKEND_TARGET = "http://127.0.0.1:8765";

const proxyConfig = {
  target: BACKEND_TARGET,
  changeOrigin: true,
  configure: (proxy: { on: (event: string, cb: (...args: unknown[]) => void) => void }) => {
    proxy.on("proxyReq", (...args: unknown[]) => {
      const proxyReq = args[0] as { path: string };
      const req = args[1] as { url?: string; method?: string };
      console.log(`[vite-proxy] ${req.method} ${req.url} -> ${BACKEND_TARGET}${proxyReq.path}`);
    });
    proxy.on("error", (...args: unknown[]) => {
      const err = args[0] as Error;
      console.error("[vite-proxy] error:", err.message);
    });
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/agent": proxyConfig,
      "/dashboard": proxyConfig,
      "/devices": proxyConfig,
      "/healthz": proxyConfig,
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
