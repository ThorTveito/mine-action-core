import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    // maplibre-gl (~800 kB) is a vendor chunk that only the Map tab loads.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: { manualChunks: { maplibre: ["maplibre-gl"] } },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": process.env.API_PROXY_TARGET ?? "http://localhost:8000",
    },
  },
});
