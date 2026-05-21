import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
var BACKEND_TARGET = "http://127.0.0.1:8765";
var proxyConfig = {
    target: BACKEND_TARGET,
    changeOrigin: true,
    configure: function (proxy) {
        proxy.on("proxyReq", function () {
            var args = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                args[_i] = arguments[_i];
            }
            var proxyReq = args[0];
            var req = args[1];
            console.log("[vite-proxy] ".concat(req.method, " ").concat(req.url, " -> ").concat(BACKEND_TARGET).concat(proxyReq.path));
        });
        proxy.on("error", function () {
            var args = [];
            for (var _i = 0; _i < arguments.length; _i++) {
                args[_i] = arguments[_i];
            }
            var err = args[0];
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
            "/auth": proxyConfig,
            "/dashboard": proxyConfig,
            "/devices": proxyConfig,
            "/observability": proxyConfig,
            "/healthz": proxyConfig,
        },
    },
    build: {
        outDir: "dist",
        sourcemap: false,
    },
});
