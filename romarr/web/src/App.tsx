// SCAF + ROM showcase. The real route surface lands with the
// ROUTING phase; today's App.tsx renders one of every ROM
// component so the build pipeline (TS strict + Tailwind +
// React 18) and the components themselves are exercised
// end-to-end.
//
// The eslint-disable comments are local — the real i18n
// integration lands with the I18N phase, at which point every
// hardcoded string here moves into the FR + EN bundles and the
// ESLint react/jsx-no-literals rule (T007) starts enforcing.

/* eslint-disable react/jsx-no-literals */

import {
  ConventionBadge,
  CoverImage,
  DatVerifiedBadge,
  DumpStatusIcon,
  HashBadge,
  LanguagePills,
  MultiDiscAccordion,
  PlatformIcon,
  RegionBadge,
  ScoreBadge,
} from "@/components/rom";

export default function App() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <div className="mx-auto max-w-md px-4 py-12">
        <h1 className="font-mono text-2xl font-semibold text-brand">
          Romarr
        </h1>
        <p className="mt-3 text-sm text-zinc-400">
          Self-hosted ROM acquisition manager.
        </p>

        <h2 className="mt-10 font-mono text-xs uppercase tracking-widest text-zinc-500">
          ROM components
        </h2>

        <section className="mt-4 space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <RegionBadge code="USA" />
            <RegionBadge code="EUR" />
            <RegionBadge code="JPN" />
            <RegionBadge code="WLD" />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <ConventionBadge convention="no-intro" />
            <ConventionBadge convention="redump" />
            <ConventionBadge convention="tosec" />
            <ConventionBadge convention="goodtools" />
            <ConventionBadge convention="scene" />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <DumpStatusIcon status="verified" />
            <DumpStatusIcon status="hack" />
            <DumpStatusIcon status="proto" />
            <DumpStatusIcon status="baddump" />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <HashBadge type="SHA1" value="da39a3ee5e6b4b0d3255bfef95601890afd80709" />
            <ScoreBadge
              score={42}
              breakdown={[
                { format: "Region:USA", contribution: 30 },
                { format: "DumpStatus:verified", contribution: 12 },
              ]}
            />
            <DatVerifiedBadge verified source="No-Intro 2026-04" />
          </div>

          <LanguagePills codes={["en", "fr", "ja", "de", "es", "it", "pt"]} />

          <div className="flex items-center gap-3">
            <PlatformIcon
              slug="mega-drive"
              name="Mega Drive"
              manufacturer="Sega"
            />
            <PlatformIcon slug="snes" name="Super Nintendo" manufacturer="Nintendo" />
            <PlatformIcon slug="ps1" name="PlayStation" manufacturer="Sony" />
            <CoverImage alt="Sonic the Hedgehog" />
          </div>

          <MultiDiscAccordion
            parentTitle="Final Fantasy VII (USA)"
            totalDiscs={3}
          >
            <div className="text-xs text-zinc-400">
              Disc 2/3 — Final Fantasy VII (USA) (Disc 2)
            </div>
            <div className="text-xs text-zinc-400">
              Disc 3/3 — Final Fantasy VII (USA) (Disc 3)
            </div>
          </MultiDiscAccordion>
        </section>

        <p className="mt-10 font-mono text-xs uppercase tracking-widest text-zinc-600">
          v0.0.0 · scaffolding
        </p>
      </div>
    </main>
  );
}
