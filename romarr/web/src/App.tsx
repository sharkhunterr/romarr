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
import { SetupPage } from "@/pages/Setup";
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
import { QualityDefinitionsPage } from "@/pages/Settings/QualityDefinitions";
import { SettingsHome } from "@/pages/Settings/SettingsHome";
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
              {
                path: "quality-definitions",
                element: <QualityDefinitionsPage />,
              },
              { path: "dat-sources", element: <DatSourcesPage /> },
              {
                path: "media-management",
                element: <MediaManagementPage />,
              },
              { path: "platforms", element: <PlatformsPage /> },
              { path: "general", element: <GeneralPage /> },
              { path: "unidentified", element: <UnidentifiedPage /> },
              { path: "logs", element: <LogsPage /> },
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
