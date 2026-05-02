/**
 * CODEGEN-phase smoke check (T010, FR-005).
 *
 * Imports a handful of generated schemas and constructs typed
 * fixtures so the build fails if a known-good type regresses.
 * The full smoke-test suite (Vitest + Testing Library) lands in
 * the testing phase; this file is the lightweight stand-in that
 * runs as part of `pnpm typecheck`.
 *
 * Add a line per resource the frontend depends on as the SPA
 * grows. Keep the assertions minimal — expensive runtime checks
 * belong in unit tests, not in a typecheck-time smoke file.
 */

import type { components } from "@/types/api/schema";

type Schemas = components["schemas"];

// Every entry below is a compile-time assertion that the
// generated type both EXISTS and matches the documented shape.
// A field rename or a removal in the backend's OpenAPI surface
// would surface as a typecheck error here at codegen time.

const _backupFileEntry: Schemas["BackupFileEntry"] = {
  filename: "romarr_backup_2026-04-30.zip",
  lastWriteTime: "2026-04-30T12:00:00Z",
  size: 1024,
};

const _calendarEvent: Schemas["CalendarEvent"] = {
  id: 1,
  title: "Sonic ROM hack",
  kind: "rom-hack",
  releaseDate: "2026-06-01",
  releaseDateUtc: "2026-06-01T00:00:00Z",
  monitored: true,
};

// Note: ``color`` carries a Pydantic default of #9BBC0F (the
// brand colour) but openapi-typescript v7 emits defaulted fields
// as required. The smoke fixture includes it explicitly so the
// type assertion compiles.
const _createTagRequest: Schemas["CreateTagRequest"] = {
  name: "family-friendly",
  label: "Family Friendly",
  color: "#9BBC0F",
};

// Reference each entry so a future linter doesn't strip them as
// dead code. ``void`` keeps the runtime cost zero.
void _backupFileEntry;
void _calendarEvent;
void _createTagRequest;
