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

import { type ReactElement } from "react";
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
import { DashboardPage } from "@/pages/Dashboard";
import {
  AddNewPage,
  CalendarPage,
  GameDetailPage,
  LibraryPage,
  LoginPage,
  NotFoundPage,
  SettingsPage,
  SetupPage,
  SystemPage,
} from "@/pages/placeholders";
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
          // Settings is a layout with sub-routes; today the
          // sub-routes share the same placeholder page.
          {
            path: "/settings",
            element: <Outlet />,
            children: [
              { index: true, element: <SettingsPage /> },
              { path: ":sub", element: <SettingsPage /> },
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

export default function App(): ReactElement {
  return (
    <QueryProvider>
      <ThemeProvider>
        <RouterProvider router={router} />
      </ThemeProvider>
    </QueryProvider>
  );
}
