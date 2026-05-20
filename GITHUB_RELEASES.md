# GitHub Releases — Romarr

> Release notes for each tagged release. The first ``# vX.Y.Z`` block
> is consumed by the GitLab CI `release:gitlab` / `release:github`
> jobs as the description posted to the GitLab and GitHub release
> pages. CHANGELOG.md is the commit-by-commit machine-generated
> record; this file is the **human-curated highlight reel**.

> **Workflow** : edit this file BEFORE running `npm run release:full`.
> Add a new ``# vX.Y.Z`` block at the top describing the user-visible
> changes. The release script bumps the version, regenerates
> CHANGELOG.md from conventional commits, then tags + pushes; CI picks
> up the tag and posts THIS file's first block as the release body.

---

# v0.14.0

## 🎮 Romarr — self-hosted ROM acquisition manager for the *arr ecosystem

Romarr brings a DAT-verified ROM library, a five-axis profile system
(quality / region / dump / language / naming), Torznab search across
Grabarr + Prowlarr, and a bundled React UI — all in one Docker image.

> [!IMPORTANT]
> SQLite migrations run automatically on first boot via Alembic;
> existing games, releases, profiles, settings and API keys are
> preserved across upgrades.

---

### ✨ Highlights

- **Library** — DAT-matched games + releases, per-game History tab,
  bulk monitor, cover art, metadata aggregation.
- **Profiles** — quality / region / dump / language / naming, each
  bound per library; quality profiles carry an `auto_grab_min_score`
  floor for the auto-grab paths.
- **Search & auto-grab** — manual search, RSS sync, missing search,
  cutoff search and on-add search all run the same DAT-aware scoring
  pipeline; the best eligible candidate per game is auto-grabbed and
  the queue entry binds the download back to its game for import.
- **Activity** — live download + scheduler-task queue, unified
  History feed with per-(indexer, game) search rows and a detail
  sheet showing the score breakdown.
- **Release pipeline** — tag-only GitLab → Docker Hub → GitHub
  workflow driven by `npm run release:full`.
