import React from "react";
import ReactDOM from "react-dom/client";

import App from "@/App";
import "@/lib/i18n";
import { bindInstallListeners } from "@/lib/pwa/install";
import "@/styles/globals.css";

bindInstallListeners();

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in index.html");
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
