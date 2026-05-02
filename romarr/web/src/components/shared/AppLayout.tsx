/**
 * Authenticated app shell — header, scroll region, bottom nav.
 *
 * Sits inside the AuthGuard's <Outlet>; every protected page
 * renders inside this layout. The padding-bottom reserves
 * space for the BottomNav so content isn't covered on mobile.
 */

import { type ReactElement } from "react";
import { Outlet } from "react-router-dom";

import { BottomNav } from "@/components/shared/BottomNav";
import { Header } from "@/components/shared/Header";

export function AppLayout(): ReactElement {
  return (
    <div className="flex min-h-screen flex-col bg-zinc-950 text-zinc-50">
      <Header />
      <div className="flex-1 pb-16 md:pb-0">
        <Outlet />
      </div>
      <BottomNav />
    </div>
  );
}
