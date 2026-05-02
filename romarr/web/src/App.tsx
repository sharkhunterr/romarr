/**
 * Spec 014 — application root.
 *
 * Wires:
 *   1. QueryProvider — TanStack Query client (slice 46).
 *   2. ThemeProvider — applies dark/light/auto on <html>.
 *   3. RouterProvider — React Router v6 data router, 11 page
 *      routes (Login / Setup public; everything else under
 *      AuthGuard → AppLayout → page outlet).
 *
 * I18nextProvider and Toaster will wrap RouterProvider once
 * their runtime deps land in their respective phases.
 */

import { Suspense, type ReactElement } from "react";
import {
  createBrowserRouter,
  RouterProvider,
  Outlet,
} from "react-router-dom";

import { AppLayout } from "@/components/shared/AppLayout";
import { AuthGuard } from "@/components/shared/AuthGuard";
import { ThemeProvider } from "@/components/shared/ThemeProvider";
import { QueryProvider } from "@/lib/api/QueryProvider";
import { ActivityPage } from "@/pages/Activity";
import { CalendarPage } from "@/pages/Calendar";
import { DashboardPage } from "@/pages/Dashboard";
import {
  AddNewPage,
  GameDetailPage,
  LibraryPage,
  LoginPage,
  NotFoundPage,
  SetupPage,
} from "@/pages/placeholders";
import { SettingsHome } from "@/pages/Settings/SettingsHome";
import { SettingsLayout } from "@/pages/Settings/SettingsLayout";
import { SettingsPlaceholder } from "@/pages/Settings/SettingsPlaceholder";
import { TagsPage } from "@/pages/Settings/Tags";
import { SystemPage } from "@/pages/System";
import { WantedPage } from "@/pages/Wanted";

const router = createBrowserRouter([
  // Public bootstrap routes — no AuthGuard.
  { path: "/login", element: <LoginPage /> },
  { path: "/setup", element: <SetupPage /> },

  // Protected routes — sit behind the AuthGuard outlet, then
  // inside the AppLayout (header + bottom nav).
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <DashboardPage /> },
          { path: "/library", element: <LibraryPage /> },
          { path: "/add", element: <AddNewPage /> },
          { path: "/game/:gameId", element: <GameDetailPage /> },
          { path: "/wanted", element: <WantedPage /> },
          { path: "/activity", element: <ActivityPage /> },
          { path: "/calendar", element: <CalendarPage /> },
          // Settings is a layout with sidebar nav (slice 53).
          // The Tags sub-page is shipped (slice 51); the rest
          // render the placeholder under the same sidebar shell
          // until their slice lands.
          {
            path: "/settings",
            element: <SettingsLayout />,
            children: [
              { index: true, element: <SettingsHome /> },
              { path: "tags", element: <TagsPage /> },
              { path: ":sub", element: <SettingsPlaceholder /> },
            ],
          },
          {
            path: "/system",
            element: <Outlet />,
            children: [
              { index: true, element: <SystemPage /> },
              { path: ":sub", element: <SystemPage /> },
            ],
          },
        ],
      },
    ],
  },

  { path: "*", element: <NotFoundPage /> },
]);

function I18nFallback(): ReactElement {
  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950" />
  );
}

export default function App(): ReactElement {
  return (
    <QueryProvider>
      <ThemeProvider>
        <Suspense fallback={<I18nFallback />}>
          <RouterProvider router={router} />
        </Suspense>
      </ThemeProvider>
    </QueryProvider>
  );
}
