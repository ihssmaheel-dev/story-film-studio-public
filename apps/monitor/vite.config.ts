import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: process.env.STUDIO_MONITOR_API || "http://127.0.0.1:8765",
        changeOrigin: true,
        configure: (proxy) => {
          const targetOrigin = new URL(
            process.env.STUDIO_MONITOR_API || "http://127.0.0.1:8765",
          ).origin;
          proxy.on("proxyReq", (proxyReq) => {
            const origin = proxyReq.getHeader("origin");
            if (!origin) return;
            try {
              const parsed = new URL(String(origin));
              if (
                parsed.hostname === "127.0.0.1" ||
                parsed.hostname === "localhost"
              ) {
                proxyReq.setHeader("origin", targetOrigin);
              }
            } catch {
              // Preserve malformed origin so the backend rejects it.
            }
          });
        },
      },
      "/logo.png": {
        target: process.env.STUDIO_MONITOR_API || "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  build: { target: "es2022", sourcemap: false },
});
