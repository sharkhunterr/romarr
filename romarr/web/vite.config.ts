import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// Spec 014 PWA: Vite + React + Tailwind + service worker via
// vite-plugin-pwa (slice 57). The plugin generates a Workbox
// service worker, the web app manifest, and the registration
// shim. Runtime caching rules are tuned for Romarr:
//
//   * /api/v3/* → NetworkFirst (5 min cache fallback). Mutating
//     verbs (POST/PUT/PATCH/DELETE) skip the SW entirely so
//     they never replay from cache.
//   * /signalr/* → never cached (WebSocket upgrade).
//   * static assets (css / js / svg / png / woff2) → CacheFirst.
//   * /locales/{lng}/{ns}.json → StaleWhileRevalidate so the
//     i18n bundle pops fast and refreshes in the background.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      injectRegister: "auto",
      includeAssets: [
        "icon-192.png",
        "icon-512.png",
        "icon-512-maskable.png",
      ],
      manifest: {
        name: "Romarr",
        short_name: "Romarr",
        description:
          "Self-hosted ROM acquisition manager — search, grab, and import retro game ROMs.",
        theme_color: "#9bbc0f",
        background_color: "#0a0a0a",
        display: "standalone",
        orientation: "portrait",
        scope: "/",
        start_url: "/",
        icons: [
          {
            src: "icon-192.png",
            sizes: "192x192",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "icon-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "any",
          },
          {
            src: "icon-512-maskable.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/signalr\//],
        // Don't precache locale/openapi snapshots — they change
        // independently of the app revision.
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2}"],
        runtimeCaching: [
          {
            urlPattern: /^.*\/api\/v3\/.*$/,
            method: "GET",
            handler: "NetworkFirst",
            options: {
              cacheName: "romarr-api-v3",
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 5 * 60,
              },
              networkTimeoutSeconds: 5,
              cacheableResponse: { statuses: [200] },
            },
          },
          {
            urlPattern: /^.*\/locales\/[a-z]{2}\/.*\.json$/,
            method: "GET",
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "romarr-locales",
              expiration: {
                maxEntries: 30,
                maxAgeSeconds: 30 * 24 * 60 * 60,
              },
            },
          },
          {
            urlPattern: /\.(?:js|css|woff2|svg|png|ico)$/,
            method: "GET",
            handler: "CacheFirst",
            options: {
              cacheName: "romarr-static",
              expiration: {
                maxEntries: 200,
                maxAgeSeconds: 30 * 24 * 60 * 60,
              },
            },
          },
        ],
      },
      devOptions: {
        // Disabled — the dev workflow uses the Vite dev server
        // directly. Operators run a production build to exercise
        // the SW.
        enabled: false,
      },
    }),
  ],
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
