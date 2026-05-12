# Grabarr ↔ Romarr direct protocol

Status: draft v0.2
Owners: Romarr (this repo) + Grabarr (sharkhunterr/grabarr)
Goal: let Romarr resolve a Grabarr search result into a concrete
download instruction (HTTP-direct, magnet, or specific-file-in-meta-torrent)
**without going through Prowlarr** and **without guessing** which file
inside a meta-torrent matches the operator's pick.

## Changelog

- **v0.2 (2026-05-12)** — Pin the Romarr-side topology (one indexer row
  `implementation=grabarr` + one downloader row `type=grabarr_direct`,
  linked via `indexer.download_client_id`). Clarify that **search**
  stays on Newznab/Torznab in Grabarr (Romarr's existing multi-indexer
  fan-out in `search/rounds/manual.py` is already the Prowlarr-side
  equivalent — Prowlarr in our setup never proxied searches, it only
  push-synced indexer configs). Call out the BitTorrent-wrap detour
  that today makes "direct HTTP" sources transit BitTorrent for no
  reason — that's the large-file pain point this protocol kills.
- **v0.1** — Initial draft: resolve endpoint shape, three method
  variants (`http_direct`, `torrent_magnet`, `torrent_in_meta`),
  health + dat endpoints, error taxonomy, implementation checklists.

## Why

The Romarr → Prowlarr → Grabarr chain has four pain points the direct
protocol fixes:

1. **Meta-torrent file selection is heuristic.** Slice 416 picks a file
   from a multi-file torrent by token-overlap on the path. For the
   Minerva archive (46 000 files, 7.6 TB) this is right *most* of the
   time but wrong enough to break trust (e.g. an N64 GoldenEye grab
   picked a DS GoldenEye .zip because the archive shipped only the DS
   variant). Grabarr already knows the exact internal path of the file
   the operator picked — passing it through eliminates the guess.

2. **Internet-Archive sources go through BitTorrent for no reason.**
   Myrient is mirrored on archive.org which serves direct HTTP. Today
   Prowlarr only knows magnet URLs, so a 30 MB ROM transits the DHT.
   Grabarr can flag those results as `http_direct` and Romarr streams
   them with `httpx`.

3. **Grabarr currently wraps HTTP-direct sources in a single-file
   torrent.** To stay Newznab/Torznab-compatible, Grabarr serves
   `/torznab/{slug}/download/{token}.torrent` for every result —
   including pure HTTP-direct ones (Internet Archive, RomsFun,
   Edge Emulation, etc.). The torrent advertises Grabarr itself as a
   BEP-19 webseed (`/torznab/{slug}/seed/{token}`), so qBit fetches the
   file by HTTP **through** Grabarr instead of from the upstream source
   directly. For small ROMs this is invisible overhead; for large
   archives (the user's reported pain point) the proxy hop is where
   throughput collapses — Grabarr has to either prefetch or stream the
   full payload back out, and the upstream's own Range-supporting CDN
   gets bypassed. The direct protocol skips the wrap entirely:
   Romarr fetches the upstream URL itself with `httpx` Range support.

4. **Hash validation is impossible end-to-end.** Newznab/Torznab carries
   no per-file checksum. The importer matches files by name + token
   overlap. With sha1/md5/crc32 in the resolve response Romarr can
   verify the imported file against the no-intro/redump dat and refuse
   the import on mismatch.

## Non-goals

- Replace Grabarr's Newznab/Torznab surface — the protocol is **purely
  additive**. Sonarr/Radarr/Prowlarr keep working unchanged.
- Add a new search endpoint to Grabarr. The search path stays
  Newznab/Torznab; Grabarr already aggregates internally across its
  source plugins (`grabarr/core/orchestrator.py:orchestrate_search`
  with `aggregate_all`) so one Newznab call already returns merged
  results. Romarr's own multi-indexer fan-out (`search/rounds/
  manual.py:run_manual_search`) is the Prowlarr-side equivalent and
  already covers the search-aggregation role on Romarr's side.
  This protocol therefore only covers the **resolve + grab** phase,
  which is where all the gain is.
- Cover non-Grabarr indexers. Other Newznab/Torznab indexers continue
  through Prowlarr + qBit as today.
- Replace Prowlarr's *config-sync* (push notifications on indexer
  mutations). That path is orthogonal and operators who use it can
  keep using it.

## Romarr-side topology

The integration shows up as **two linked rows** in Romarr's settings,
created atomically by a single "Add Grabarr" wizard so the operator
never sees the split:

| Row             | Table             | Key fields                                                            |
| --------------- | ----------------- | --------------------------------------------------------------------- |
| Grabarr indexer | `indexer`         | `implementation='grabarr'`, `base_url`, `api_key`, `download_client_id` → grabarr_direct row |
| Grabarr client  | `download_client` | `type='grabarr_direct'`, `base_url`, `api_key`, `timeout_seconds`     |

Both rows share the same `base_url` + `api_key` (they target the same
Grabarr instance). The split exists because:

- **Search is an indexer responsibility.** Romarr's `IndexerRegistry`
  iterates `indexer` rows and asks each one to `search(query)`. For a
  `grabarr` indexer this hits the existing Torznab endpoint — no new
  search code is needed. The result list comes back as ordinary
  Newznab/Torznab releases with tokens in the `<guid>`.

- **Grab is a download-client responsibility.** Romarr's dispatcher
  routes a chosen release to the indexer's pinned `download_client_id`
  (this column already exists at `src/romarr/indexers/models.py:66`).
  For a Grabarr indexer the pinned client is `grabarr_direct`, which
  is the only kind that knows about `/romarr/api/v1/resolve`.

The `grabarr_direct` client delegates magnet handoffs to the operator's
configured qBit client (separate row, unchanged) — see "Romarr-side
behaviour" below. It is *not* a replacement for qBit; it's a smart
pre-resolver that **short-circuits to httpx for HTTP-direct sources**
and falls through to qBit for the torrent cases.

### How Romarr recognises a Grabarr release at grab time

The `indexer.implementation` column already carries `'newznab'` or
`'torznab'`. We add a third literal `'grabarr'` (DB CHECK widened in
migration 0022). At grab time `src/romarr/search/api/grab.py` already
fetches the originating `Indexer` row — extending the source-kind
sniff in `src/romarr/search/dispatch.py` to map `implementation =
'grabarr'` to the linked `grabarr_direct` client is the one extra
branch needed. Everything else (the queue table, the manual-search
UI, the existing qBit + SAB clients) is untouched.

## Auth model

Grabarr already issues operator-scoped API keys (the same key Romarr
sends as the Newznab/Torznab `apikey=` query param). Reuse it:

- Romarr stores the Grabarr base URL + API key as a
  **Download Client** row of type `grabarr_direct`.
- Every endpoint below accepts `Authorization: Bearer <key>` *or*
  `?apikey=<key>` (for symmetry with the existing surface).
- Grabarr can rate-limit per key as it already does on Newznab.
- 401 on bad key, 403 on key valid but ACL denies the resource
  (e.g. private tracker source the key isn't scoped for).

## Endpoints

### `GET /romarr/api/v1/health`

Smoke endpoint for the connectivity-test button. Returns:

```json
{
  "version": "1.4.2",
  "protocol_version": "1",
  "sources": ["myrient", "internet_archive", "minerva", "axekin"]
}
```

`protocol_version` is a single integer Romarr checks at config time to
refuse incompatible Grabarr deploys.

### `GET /romarr/api/v1/resolve?guid=<guid>`

Given the `guid` Romarr received from a Newznab/Torznab search result,
return the concrete download instruction. The `guid` is whatever
Grabarr already serialises in `<guid>` of the Newznab response — no
new format on the search path.

200 OK response shape (one of three discriminated by `method`):

#### method = `http_direct`

```json
{
  "method": "http_direct",
  "filename": "GoldenEye 007 (USA).z64",
  "url": "https://archive.org/download/no-intro_nintendo-64/GoldenEye%20007%20(USA).z64",
  "expected_size": 12582912,
  "headers": {},
  "checksums": {
    "sha1": "0a1b2c…",
    "md5":  "fedcba…",
    "crc32": "11223344"
  },
  "source": "myrient",
  "platform_slug": "n64",
  "region": "USA",
  "language": null,
  "revision": null,
  "release_year": 1997,
  "expires_at": null
}
```

Romarr streams `url` with `httpx`, writes to
`/downloads/<platform_slug>/<filename>`, validates **all** checksums
that are present (skips missing ones), and only flags the queue entry
as completed on a full match.

#### method = `torrent_magnet`

```json
{
  "method": "torrent_magnet",
  "magnet_uri": "magnet:?xt=urn:btih:…",
  "filename_hint": "GoldenEye 007 (USA).z64",
  "expected_size": 12582912,
  "checksums": { "sha1": "0a1b2c…" },
  "source": "axekin",
  "platform_slug": "n64",
  "region": "USA"
}
```

Romarr hands `magnet_uri` to qBit unchanged. Used for single-file
torrents where the magnet IS the file. `filename_hint` helps the
importer (and the operator) but Romarr doesn't constrain qBit to it.

#### method = `torrent_in_meta`

The killer feature. Grabarr already knows that *this* search result is
file index N inside a meta-torrent and tells Romarr so:

```json
{
  "method": "torrent_in_meta",
  "magnet_uri": "magnet:?xt=urn:btih:560fbbd1…",
  "internal_file_index": 31427,
  "internal_file_path": "No-Intro/Nintendo - Nintendo 64/GoldenEye 007 (USA).z64",
  "expected_size": 12582912,
  "checksums": { "sha1": "0a1b2c…" },
  "source": "minerva",
  "platform_slug": "n64",
  "region": "USA"
}
```

Romarr's grab flow:

1. POST qBit `/torrents/add` with `magnet_uri`, paused.
2. Wait `has_metadata=true` (existing slice 417 wait).
3. POST qBit `/torrents/filePrio` with `id=internal_file_index` →
   priority 1, all others priority 0. **No token-overlap heuristic.**
4. Resume the torrent.
5. After import: hash-validate against `checksums`.

`internal_file_index` is authoritative; `internal_file_path` is shipped
in the same payload only as a fallback if qBit's file list ordering
disagrees (which would mean the magnet's torrent file changed
out-of-band — log + abort).

### `GET /romarr/api/v1/dat/<platform_slug>`

Optional. Lets Romarr pre-load no-intro/redump dat files so it can
validate already-imported library files. Returns the dat as
`application/xml` (no-intro datfile shape) or `application/json` with
just the sha1/md5/crc32 + name list. Grabarr can serve from cache.

200 OK example (JSON shape):

```json
{
  "platform_slug": "n64",
  "system": "Nintendo 64",
  "source": "no-intro",
  "version": "2024-12-15",
  "entries": [
    {
      "name": "GoldenEye 007 (USA).z64",
      "size": 12582912,
      "sha1": "0a1b2c…",
      "md5": "fedcba…",
      "crc32": "11223344"
    }
  ]
}
```

## Error taxonomy

| HTTP | code                       | meaning                                                   |
| ---- | -------------------------- | --------------------------------------------------------- |
| 400  | `bad_guid`                 | guid format unrecognised                                  |
| 401  | `unauthenticated`          | missing/bad bearer or apikey                              |
| 403  | `forbidden`                | key valid but lacks ACL for this source                   |
| 404  | `guid_not_found`           | guid expired or never existed                             |
| 409  | `source_gone`              | upstream source removed the file since search             |
| 429  | `rate_limited`             | per-key rate limit hit (carry `Retry-After`)              |
| 502  | `upstream_unreachable`     | source down (archive.org 5xx, tracker offline, etc.)      |
| 503  | `protocol_mismatch`        | Romarr sent a protocol_version Grabarr can't speak        |

JSON body for all errors:

```json
{
  "code": "rate_limited",
  "message": "human-readable detail",
  "retry_after_seconds": 60
}
```

## Romarr-side behaviour (informative)

- A `GrabarrDirectClient` registers as a `DownloadClient` of type
  `grabarr_direct`. Operator does not configure it directly — the
  "Add Grabarr" wizard in Settings → Indexers creates the linked
  indexer + downloader pair atomically (shared `base_url`, `api_key`,
  `timeout_seconds` reusing slice 420's per-client timeout column).
  Removing the indexer cascades the removal of the linked client.
- The client implements the existing `DownloadClient` ABC:
  - `test_connection` → `GET /romarr/api/v1/health` + protocol_version
    check (refuse to enable on mismatch)
  - `add_torrent(source: TorrentUrl)` — `source.url` is the Grabarr
    Torznab `/download/{token}.torrent` URL Romarr already has from
    the search response; the client extracts the token, POSTs
    resolve, dispatches per `method`, returns a native id
  - HTTP-direct native id = SHA-1 of `(url + started_at)` so the queue
    table's info-hash-style dedup model keeps working
- For `method=torrent_in_meta` and `torrent_magnet` the client
  delegates the actual `/torrents/add` + `filePrio` to a **separately
  configured qBit client** (looked up by the existing
  `enable_for_torrents` routing). Operators with no qBit configured
  can only grab `http_direct` results — the dispatcher filters
  candidates accordingly (status surfaced in the manual-search UI as
  "needs qBit").
- Capability advertisement: the indexer's manual-search rows carry a
  `method_preview` field (sniffed from the result's `<attr>` set
  Grabarr adds on the Torznab response) so the UI can mark a
  candidate "HTTP direct" vs "torrent" *before* the operator clicks
  grab. This is a v0.3 addition — v0.2 ships without it; the
  dispatcher just calls `/resolve` blind and trusts the response.

## Implementation checklist for Grabarr

- [ ] Bump version, expose `/romarr/api/v1/health`
- [ ] `/romarr/api/v1/resolve` for each source plugin:
  - [ ] Myrient → emit `http_direct` (archive.org URL + IA-provided sha1)
  - [ ] Internet Archive → emit `http_direct`
  - [ ] Minerva → emit `torrent_in_meta` with the precomputed
        `internal_file_index` (Grabarr already indexes those — surface
        the index it already knows about)
  - [ ] Axekin / Erista / other single-file torrents → emit
        `torrent_magnet`
- [ ] Auth: accept the existing apikey header + bearer variant
- [ ] Per-key rate limit on `/resolve` (same bucket as Newznab search
      or a separate one — operator choice)
- [ ] OpenAPI doc autogenerated from the route handlers
- [ ] `/romarr/api/v1/dat/<platform_slug>` (P2 — useful but not
      blocking for the first cut)
- [ ] Tests: at least one fixture per source plugin returning the
      three method variants

## Implementation checklist for Romarr (this repo)

Order is incremental — each item leaves the tree green and the
existing Prowlarr/Newznab path untouched.

**Phase R1 — foundation (this branch, slice 422):**

- [ ] Migration 0022: widen the `download_client.type` CHECK to include
      `'grabarr_direct'` and the `indexer.implementation` CHECK to
      include `'grabarr'`. Idempotent downgrade.
- [ ] Add `ClientType.GRABARR_DIRECT = "grabarr_direct"` to
      `src/romarr/downloaders/types.py`.
- [ ] Stub `src/romarr/downloaders/implementations/grabarr_direct.py`
      with `available = False` (mirrors the transmission / deluge
      stubs) so the factory imports cleanly without exposing the type
      in the UI's `_CLIENT_TYPES` array yet.
- [ ] Add `'grabarr'` to the `IndexerImplementation` literal in
      `src/romarr/indexers/models.py` and the API schema, gated so the
      Add-Indexer modal does not surface it yet (kept off the
      `_IMPLEMENTATIONS` array until R2).

**Phase R2 — wiring:**

- [ ] `GrabarrDirectClient` real implementation (test_connection,
      add_torrent dispatching per resolve.method, get_status etc.).
- [ ] Indexer-side `GrabarrClient` (parallels `NewznabClient`) — talks
      to Grabarr's existing Torznab `/api` for search, no new search
      code in Grabarr.
- [ ] Extend `src/romarr/search/dispatch.py` to map
      `indexer.implementation == 'grabarr'` to the linked
      `grabarr_direct` client at grab time. Newznab/Torznab path
      remains the default branch.
- [ ] HTTP-direct streamer with hash validation post-download; failure
      modes surfaced as queue-row error states.
- [ ] "Add Grabarr" wizard (Settings → Indexers → New → Grabarr)
      creates the indexer + linked downloader rows atomically; removing
      the indexer cascades.
- [ ] Tests: respx fixtures for each `method` branch + checksum
      mismatch path + the indexer-side search test (mocked Torznab
      response).

**Phase R3 — UX polish (defer):**

- [ ] `method_preview` chip in manual-search row.
- [ ] `/dat/<platform_slug>` preload + library validation pass.
- [ ] Optional: replace Grabarr's BitTorrent-wrap path on the operator's
      Sonarr/Radarr-via-Prowlarr stack with an opt-in flag in Grabarr
      to short-circuit known HTTP-direct sources to redirects. Out of
      scope for this repo.

## Open questions (need decision before R2)

1. **Removing an indexer that has a linked downloader.** Cascade
   delete the downloader row, or detach and leave it dangling? Soft
   delete? Decision: cascade is simpler and matches "Add Grabarr is
   one logical thing". Confirm with operator UX.
2. **Two Grabarr instances on the same Romarr.** Allowed? The schema
   doesn't forbid it (multiple `download_client` rows with
   `type='grabarr_direct'`). UI wizard must keep them distinct (label
   them by base_url, not by type). No technical blocker.
3. **Token expiry.** Grabarr's existing `SearchToken` table has a TTL.
   What happens if Romarr's manual-search row sits in the UI past
   that TTL and the operator clicks grab? `404 guid_not_found` —
   surfaced as a "stale result, re-search" toast. Confirm TTL is long
   enough for realistic operator workflows (24h proposed).
4. **HTTP-direct partial-download resume.** If httpx fails mid-stream
   and the upstream supports Range, do we resume or retry from zero?
   Resume is the right answer (large IA files), but adds a state
   machine to the queue. v0.2 ships with retry-from-zero; v0.3 adds
   Range-resume.
