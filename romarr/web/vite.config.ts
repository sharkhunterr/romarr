import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Spec 014 SCAF: minimal Vite config. PWA plugin (T008), service
// worker (T056), and proxy-to-backend wiring (for `pnpm dev`) land
// in subsequent slices. Today's config is just enough to compile
// React + TypeScript + Tailwind.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    // Output goes into `dist/` here; the Docker image (T009)
    // copies it into /opt/romarr/web/.
    outDir: "dist",
    sourcemap: true,
  },
  server: {
    port: 5173,
    // The backend's API surface lives at /api/v3/*; the dev
    // server proxies it to the local FastAPI instance so the
    // SPA can call relative URLs without CORS gymnastics.
    proxy: {
      "/api/v3": "http://localhost:8585",
      "/signalr": {
        target: "ws://localhost:8585",
        ws: true,
      },
    },
  },
});
