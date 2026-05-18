import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
var BACKEND_TARGET = "http://127.0.0.1:8000";
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        strictPort: false,
        proxy: {
            "/agent": { target: BACKEND_TARGET, changeOrigin: true },
            "/dashboard": { target: BACKEND_TARGET, changeOrigin: true },
            "/devices": { target: BACKEND_TARGET, changeOrigin: true },
            "/healthz": { target: BACKEND_TARGET, changeOrigin: true },
        },
    },
    build: {
        outDir: "dist",
        sourcemap: false,
    },
});
