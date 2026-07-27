import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/echarts/") || id.includes("/node_modules/zrender/")) {
            return "charts";
          }
          if (id.includes("/node_modules/react") || id.includes("/node_modules/scheduler/")) {
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
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
