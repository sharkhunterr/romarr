/**
 * PathPicker — browse the Romarr container's filesystem to pick a
 * directory, with manual text-entry as a fallback.
 *
 * Backed by ``GET /api/v3/system/filesystem?path=...`` — the root
 * listing surfaces the operator's mounted volumes (``/data``,
 * ``/roms``, ``/media``, ...) and every descent shows subdirectories.
 *
 * Usage:
 *   <PathPicker value={path} onChange={setPath} disabled={submitting} />
 */

import { useEffect, useState, type ReactElement } from "react";
import { useTranslation } from "react-i18next";

import { apiFetch, ApiError } from "@/lib/api/client";
import { useQuery } from "@tanstack/react-query";

interface Entry {
  name: string;
  path: string;
  is_dir: boolean;
  is_mount: boolean;
}

interface Listing {
  path: string;
  parent: string | null;
  entries: Entry[];
}

interface PathPickerProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

const API = "/api/v3/system/filesystem";

function _parentOf(path: string): string {
  if (!path || path === "/") return "/";
  const trimmed = path.replace(/\/+$/, "");
  const idx = trimmed.lastIndexOf("/");
  return idx <= 0 ? "/" : trimmed.slice(0, idx);
}

function _crumbs(path: string): { label: string; path: string }[] {
  if (!path || path === "/") return [{ label: "/", path: "/" }];
  const parts = path.split("/").filter(Boolean);
  const acc: { label: string; path: string }[] = [{ label: "/", path: "/" }];
  let cur = "";
  for (const part of parts) {
    cur = `${cur}/${part}`;
    acc.push({ label: part, path: cur });
  }
  return acc;
}

export function PathPicker(props: PathPickerProps): ReactElement {
  const { t } = useTranslation("settings");
  const [browseOpen, setBrowseOpen] = useState(false);
  // Current directory being LISTED in the browser (independent from
  // props.value — the operator can navigate around before picking).
  const [browsePath, setBrowsePath] = useState<string>(
    props.value ? _parentOf(props.value) : "/",
  );

  // Re-anchor the browser to the current value each time it opens
  // (so re-opening the picker after an edit doesn't strand you in
  // a stale directory).
  useEffect(() => {
    if (browseOpen) {
      setBrowsePath(props.value ? _parentOf(props.value) : "/");
    }
  }, [browseOpen, props.value]);

  const listing = useQuery<Listing, ApiError>({
    queryKey: ["filesystem", browsePath],
    queryFn: () =>
      apiFetch<Listing>(
        `${API}?path=${encodeURIComponent(browsePath)}`,
      ),
    enabled: browseOpen,
    retry: false,
  });

  return (
    <div className="space-y-1.5">
      {/* Manual text entry — always visible. */}
      <div className="flex gap-1.5">
        <input
          type="text"
          value={props.value}
          onChange={(e) => props.onChange(e.target.value)}
          placeholder={props.placeholder ?? "/data/roms/megadrive"}
          disabled={props.disabled}
          className="flex-1 rounded-md bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-100 ring-1 ring-inset ring-zinc-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
        />
        <button
          type="button"
          onClick={() => setBrowseOpen((v) => !v)}
          disabled={props.disabled}
          aria-expanded={browseOpen}
          aria-label={t("pathPicker.toggle", "Browse container paths")}
          className="rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-100 hover:bg-zinc-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-60"
        >
          {browseOpen
            ? t("pathPicker.close", "Close")
            : t("pathPicker.browse", "Browse…")}
        </button>
      </div>

      {browseOpen && (
        <div className="rounded-md border border-zinc-800 bg-zinc-950/60 p-2">
          {/* Breadcrumbs */}
          <div className="mb-1.5 flex flex-wrap items-baseline gap-1 font-mono text-xs">
            {_crumbs(browsePath).map((c, i, arr) => (
              <span key={c.path} className="flex items-baseline gap-1">
                <button
                  type="button"
                  onClick={() => setBrowsePath(c.path)}
                  className="rounded px-1 text-brand hover:bg-zinc-800"
                >
                  {c.label}
                </button>
                {i < arr.length - 1 && (
                  <span className="text-zinc-600">/</span>
                )}
              </span>
            ))}
          </div>

          {/* Loading / error */}
          {listing.isPending && (
            <p className="p-2 text-xs text-zinc-500">
              {t("pathPicker.loading", "Loading…")}
            </p>
          )}
          {listing.isError && (
            <p role="alert" className="p-2 text-xs text-red-300">
              {listing.error.message}
            </p>
          )}

          {/* Directory listing */}
          {listing.isSuccess && (
            <ul className="max-h-52 space-y-0.5 overflow-y-auto">
              {listing.data.parent !== null && (
                <li>
                  <button
                    type="button"
                    onClick={() => setBrowsePath(listing.data.parent!)}
                    className="flex w-full items-center gap-2 rounded px-2 py-1 text-left font-mono text-xs text-zinc-400 hover:bg-zinc-800/60"
                  >
                    <span aria-hidden="true">↑</span>
                    <span>..</span>
                  </button>
                </li>
              )}
              {listing.data.entries.length === 0 && (
                <li className="p-2 text-xs text-zinc-500">
                  {t("pathPicker.empty", "(no subdirectories)")}
                </li>
              )}
              {listing.data.entries.map((entry) => (
                <li key={entry.path} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setBrowsePath(entry.path)}
                    className="flex flex-1 items-center gap-2 rounded px-2 py-1 text-left font-mono text-xs text-zinc-100 hover:bg-zinc-800/60"
                  >
                    <span aria-hidden="true" className="text-zinc-500">
                      📁
                    </span>
                    <span className="truncate">{entry.name}</span>
                    {entry.is_mount && (
                      <span
                        title={t(
                          "pathPicker.mountHint",
                          "Different filesystem — likely a Docker volume",
                        )}
                        className="rounded-sm bg-brand/20 px-1.5 py-0.5 text-[0.55rem] uppercase tracking-wider text-brand"
                      >
                        {t("pathPicker.mountBadge", "mount")}
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      props.onChange(entry.path);
                      setBrowseOpen(false);
                    }}
                    className="rounded px-2 py-1 text-[0.7rem] text-brand hover:bg-zinc-800"
                    title={t("pathPicker.pickHint", "Select this directory")}
                  >
                    {t("pathPicker.pick", "Pick")}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Pick-current-directory shortcut */}
          {listing.isSuccess && browsePath !== "/" && (
            <div className="mt-1.5 border-t border-zinc-800 pt-1.5">
              <button
                type="button"
                onClick={() => {
                  props.onChange(browsePath);
                  setBrowseOpen(false);
                }}
                className="w-full rounded-md bg-brand px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-brand-300"
              >
                {t("pathPicker.pickCurrent", "Pick current: ")}{" "}
                <span className="font-mono">{browsePath}</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
