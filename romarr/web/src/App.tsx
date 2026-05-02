// Minimal SCAF-phase landing page. The real route surface lands
// with the ROUTING phase (T036+); today's App.tsx just proves the
// build pipeline (TS strict + Tailwind + React 18) compiles end-
// to-end and renders an intentional 360 px-friendly mobile view.

export default function App() {
  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-50">
      <div className="mx-auto max-w-md px-4 py-12 text-center">
        <h1 className="font-mono text-2xl font-semibold text-brand">
          Romarr
        </h1>
        <p className="mt-3 text-sm text-zinc-400">
          {/* eslint-disable-next-line react/jsx-no-literals --
              SCAF placeholder; replaced by i18n strings in the
              ROUTING phase. */}
          Self-hosted ROM acquisition manager.
        </p>
        <p className="mt-8 font-mono text-xs uppercase tracking-widest text-zinc-600">
          {/* eslint-disable-next-line react/jsx-no-literals */}
          v0.0.0 · scaffolding
        </p>
      </div>
    </main>
  );
}
