/**
 * Authenticated app shell — header, scroll region, bottom nav.
 *
 * Sits inside the AuthGuard's <Outlet>; every protected page
 * renders inside this layout. The padding-bottom reserves
 * space for the BottomNav so content isn't covered on mobile.
 *
 * The WebSocket bridge boots from here (slice 54): it's the
 * shallowest component that's only mounted once auth has
 * resolved, so the WS client connects exactly when the
 * principal is known and tears down on logout.
 */

import { type ReactElement } from "react";
import { Outlet } from "react-router-dom";

import { BottomNav } from "@/components/shared/BottomNav";
import {
  GlobalSearchModal,
  useGlobalSearchHotkey,
} from "@/components/shared/GlobalSearchModal";
import { Header } from "@/components/shared/Header";
import { OfflineIndicator } from "@/components/shared/OfflineIndicator";
import { ToastViewport } from "@/components/shared/ToastViewport";
import { usePreferencesHydration } from "@/lib/preferences";
import { useWebSocketBridge } from "@/lib/ws/useWebSocketBridge";

export function AppLayout(): ReactElement {
  useWebSocketBridge();
  useGlobalSearchHotkey();
  usePreferencesHydration();

  return (
    <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-50">
      <OfflineIndicator />
      <Header />
      <div className="flex-1 pb-16 md:pb-0">
        <Outlet />
      </div>
      <BottomNav />
      <GlobalSearchModal />
      <ToastViewport />
    </div>
  );
}
