# Grabarr ↔ Romarr direct protocol

Status: draft v0.1
Owners: Romarr (this repo) + Grabarr (sharkhunterr/grabarr)
Goal: let Romarr resolve a Grabarr search result into a concrete
download instruction (HTTP-direct, magnet, or specific-file-in-meta-torrent)
**without going through Prowlarr** and **without guessing** which file
inside a meta-torrent matches the operator's pick.

## Why

The Romarr → Prowlarr → Grabarr chain has three pain points the
direct protocol fixes:

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

3. **Hash validation is impossible end-to-end.** Newznab/Torznab carries
   no per-file checksum. The importer matches files by name + token
   overlap. With sha1/md5/crc32 in the resolve response Romarr can
   verify the imported file against the no-intro/redump dat and refuse
   the import on mismatch.

## Non-goals

- Replace Grabarr's Newznab/Torznab surface — the protocol is **purely
  additive**. Sonarr/Radarr/Prowlarr keep working unchanged.
- Search via Grabarr direct — the search path stays Newznab/Torznab.
  This protocol only covers the **resolve + grab** phase, which is
  where the gain is.
- Cover non-Grabarr indexers. Other Newznab/Torznab indexers continue
  through Prowlarr + qBit as today.

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

- A `DirectGrabarrClient` registers as a `DownloadClient` of type
  `grabarr_direct`. Operator configures it from Settings → Download
  Clients with `base_url` + `api_key` + `timeout_seconds` (slice 420).
- The client implements the existing `DownloadClient` ABC:
  - `test_connection` → `GET /health` + protocol_version check
  - `add_torrent(source: TorrentUrl)` — `source.url` is the Grabarr
    search-result URL Romarr already has; the client extracts the guid
    from it (or carries it on a richer source type), POSTs resolve,
    dispatches to httpx/qBit per `method`, returns a native id
  - HTTP-direct native id = SHA-1 of `(url + started_at)` so qBit's
    info-hash dedup model still works for the queue table
- For `method=torrent_in_meta` and `torrent_magnet` the client
  delegates the actual `/torrents/add` + `filePrio` to the operator's
  configured qBit client. So `grabarr_direct` is **not** a replacement
  for qBit; it's a smart pre-resolver that *may* short-circuit to
  httpx for HTTP-direct sources. Operators with no qBit configured
  can only grab `http_direct` results — the dispatcher filters
  candidates accordingly.

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

- [ ] New downloader implementation `DirectGrabarrClient` under
      `src/romarr/downloaders/implementations/grabarr_direct.py`
- [ ] New `ClientType.GRABARR_DIRECT` literal + migration to widen the
      `download_client.type` CHECK
- [ ] `DownloadClientCreate` schema accepts `base_url` + `api_key`
- [ ] Connectivity test calls `/health` and surfaces
      `protocol_version` mismatch as a typed warning
- [ ] HTTP-direct streamer with hash validation post-download
- [ ] Routing capability flags: `enable_for_http_direct: bool` on the
      `grabarr_direct` row, surfaces in the dispatcher's candidate
      filter
- [ ] UI: Settings → Download Clients → Add → Grabarr Direct (form
      with base_url, api_key, timeout, enable_for_torrents=false by
      default, enable_for_http_direct=true)
- [ ] Tests: respx fixtures for each `method` branch + a checksum
      mismatch path
