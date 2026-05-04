/// <reference types="vitest" />
// Vitest config for the Romarr SPA. Lives separate from the
// production vite.config.ts so `pnpm test` doesn't drag in
// the PWA service-worker plugin (workbox blows up under jsdom).
//
// Path aliases mirror tsconfig.json's "paths"; keep them in
// lockstep when adding a new alias.

import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}", "tests/**/*.{test,spec}.{ts,tsx}"],
    css: false,
  },
});
