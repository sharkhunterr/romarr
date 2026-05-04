import React from "react";
import ReactDOM from "react-dom/client";

import App from "@/App";
import "@/lib/i18n";
import { bindInstallListeners } from "@/lib/pwa/install";
import { registerServiceWorker } from "@/lib/sw-update";
import "@/styles/globals.css";

bindInstallListeners();
void registerServiceWorker();

// CL009: window-level error handler. Logs the unhandled error to
// the console for the operator's devtools and surfaces a generic
// localized toast. NO POST to any remote endpoint, NO third-party
// SDK (FR-038b).
if (typeof window !== "undefined") {
  window.addEventListener("error", (event) => {
    // eslint-disable-next-line no-console
    console.error("[romarr:unhandled]", event.error ?? event.message);
  });
  window.addEventListener("unhandledrejection", (event) => {
    // eslint-disable-next-line no-console
    console.error("[romarr:unhandled-rejection]", event.reason);
  });
}

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in index.html");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
