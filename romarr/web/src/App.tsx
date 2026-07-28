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
  Navigate,
  RouterProvider,
  Outlet,
} from "react-router-dom";

import { AppLayout } from "@/components/shared/AppLayout";
import { AuthGuard } from "@/components/shared/AuthGuard";
import { PageErrorBoundary } from "@/components/shared/PageErrorBoundary";
import { SwUpdateToast } from "@/components/shared/SwUpdateToast";
import { ThemeProvider } from "@/components/shared/ThemeProvider";
import { QueryProvider } from "@/lib/api/QueryProvider";
import { ActivityPage } from "@/pages/Activity";
import { AddNewPage } from "@/pages/AddNew";
import { CalendarPage } from "@/pages/Calendar";
import { DashboardPage } from "@/pages/Dashboard";
import { GameDetailPage } from "@/pages/GameDetail";
import { LibraryPage } from "@/pages/Library";
import { LoginPage } from "@/pages/Login";
import { NotFoundPage } from "@/pages/placeholders";
import { RomPacksPage } from "@/pages/RomPacks";
import { SetupPage } from "@/pages/Setup";
import { BackupPage } from "@/pages/Settings/Backup";
import { ConnectPage } from "@/pages/Settings/Connect";
import { DatSourcesPage } from "@/pages/Settings/DatSources";
import { DownloadClientsPage } from "@/pages/Settings/DownloadClients";
import { GeneralPage } from "@/pages/Settings/General";
import { IndexersPage } from "@/pages/Settings/Indexers";
import { LogsPage } from "@/pages/Settings/Logs";
import { MediaManagementPage } from "@/pages/Settings/MediaManagement";
import { MetadataSourcesPage } from "@/pages/Settings/MetadataSources";
import { PlatformsPage } from "@/pages/Settings/Platforms";
import { ProfilesPage } from "@/pages/Settings/Profiles";
import { RomPackSettingsPage } from "@/pages/Settings/RomPackSettings";
import { SettingsLayout } from "@/pages/Settings/SettingsLayout";
import { SettingsPlaceholder } from "@/pages/Settings/SettingsPlaceholder";
import { TagsPage } from "@/pages/Settings/Tags";
import { SettingsUiPage } from "@/pages/Settings/Ui";
import { UnidentifiedPage } from "@/pages/Settings/Unidentified";
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
          {
            element: (
              <PageErrorBoundary>
                <Outlet />
              </PageErrorBoundary>
            ),
            children: [
          // ``/`` redirects to the Library — the Dashboard page
          // is intentionally not surfaced in the primary nav
          // anymore (slice: remove dashboard from menus). It
          // stays reachable by typing /dashboard so we don't
          // lose the work, just the prime real-estate.
          { path: "/", element: <Navigate to="/library" replace /> },
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/library", element: <LibraryPage /> },
          { path: "/add", element: <AddNewPage /> },
          { path: "/game/:gameId", element: <GameDetailPage /> },
          { path: "/wanted", element: <WantedPage /> },
          { path: "/activity", element: <ActivityPage /> },
          { path: "/rom-packs", element: <RomPacksPage /> },
          { path: "/calendar", element: <CalendarPage /> },
          // Settings is a layout with sidebar nav (slice 53).
          // The Tags sub-page is shipped (slice 51); the rest
          // render the placeholder under the same sidebar shell
          // until their slice lands.
          {
            path: "/settings",
            element: <SettingsLayout />,
            children: [
              {
                index: true,
                element: <Navigate to="/settings/general" replace />,
              },
              { path: "tags", element: <TagsPage /> },
              { path: "ui", element: <SettingsUiPage /> },
              { path: "indexers", element: <IndexersPage /> },
              {
                path: "download-clients",
                element: <DownloadClientsPage />,
              },
              { path: "connect", element: <ConnectPage /> },
              {
                path: "metadata-sources",
                element: <MetadataSourcesPage />,
              },
              { path: "profiles", element: <ProfilesPage /> },
              { path: "dat-sources", element: <DatSourcesPage /> },
              { path: "rom-packs", element: <RomPackSettingsPage /> },
              {
                path: "media-management",
                element: <MediaManagementPage />,
              },
              { path: "platforms", element: <PlatformsPage /> },
              { path: "general", element: <GeneralPage /> },
              { path: "unidentified", element: <UnidentifiedPage /> },
              { path: "logs", element: <LogsPage /> },
              { path: "backup", element: <BackupPage /> },
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
          <SwUpdateToast />
        </Suspense>
      </ThemeProvider>
    </QueryProvider>
  );
}
