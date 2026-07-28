import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, ".", "");
  const frontendPort = Number(environment.ECOM_DEMO_FRONTEND_PORT ?? "5174");
  const apiTarget = environment.ECOM_VITE_API_TARGET ?? "http://127.0.0.1:8010";

  return {
    plugins: [react()],
    build: {
      chunkSizeWarningLimit: 900,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (
              id.includes("/node_modules/echarts/") ||
              id.includes("/node_modules/zrender/")
            ) {
              return "charts";
            }
            if (
              id.includes("/node_modules/react") ||
              id.includes("/node_modules/scheduler/")
            ) {
              return "react";
            }
            if (id.includes("/node_modules/@tanstack/")) {
              return "query";
            }
          },
        },
      },
    },
    server: {
      host: "127.0.0.1",
      port: frontendPort,
      strictPort: true,
      proxy: {
        "/api": apiTarget,
      },
    },
  };
});
