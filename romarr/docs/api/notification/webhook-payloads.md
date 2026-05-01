# Webhook payload cross-walk (Sonarr v3 envelope → Romarr Game/Release)

> **Status**: canonical contract. Romarr emits Sonarr v3-shaped
> JSON over HTTP at the operator's configured webhook URL so
> downstream tooling (Notifiarr, Homepage, Tautulli, ...) treats
> Romarr events as drop-in Sonarr events.
>
> See spec [011 — notifications & health](../../../specs/011-notifications-health/spec.md)
> FR-006 / FR-006a / FR-007 for the requirement source.

The TV-domain keys in Sonarr's envelope (`series`, `episodes`,
`release.quality`, ...) are populated from Romarr's
`Game` / `Release` / `Indexer` / `DownloadClient` domain via the
mapping below. Consumers MUST treat the keys as **opaque
structural contracts** — Romarr is not asserting that a Mega
Drive cartridge dump is a TV episode, only that the *envelope
shape* matches Sonarr's so existing webhook consumers don't
reject the body.

## Invariants

* **Empty fields are emitted as `0` / `""`, never omitted.** The
  Sonarr v3 schema validators downstream will reject a missing
  key. Romarr always emits the full envelope with sentinel
  defaults for fields that don't have a Romarr equivalent.
* **`episodes[]` is always exactly one element.** It represents
  the `Release` carried by the event. Multi-disc releases are
  not flattened into multiple `episodes`; the parent `Release`
  is the single entry.
* **The mapping is one-way.** Romarr never ingests Sonarr-shaped
  payloads back into its model.

## Field-by-field

### `eventType`

| Romarr `EventType` | Sonarr `eventType` | Notes |
|---|---|---|
| `OnGrab` | `OnGrab` | Identical token. |
| `OnImport` | `Download` | Sonarr calls a successful import "Download". |
| `OnUpgrade` | `Download` | Same as Import; `isUpgrade = true` differentiates. |
| `OnFail` | `DownloadFailure` | |
| `OnHealthIssue` | `Health` | |
| `OnDatUpdate` | `ApplicationUpdate` | Romarr-specific extension keys nested under `romarr.*`. |
| `OnGameAdded` | `SeriesAdd` | Sonarr's "series added" event slot. |

### `series` ↔ `Game`

| Sonarr key | Romarr source | Default when missing |
|---|---|---|
| `series.id` | `game.id` | — (always present) |
| `series.title` | `game.title` | — |
| `series.titleSlug` | `game.platform_slug` | `""` |
| `series.path` | (library context — see note) | `""` |
| `series.tvdbId` | `game.igdb_id` | `0` |
| `series.tvMazeId` | — | `0` |
| `series.imdbId` | — | `""` |
| `series.type` | — | `"standard"` |
| `series.year` | — | `0` |
| `series.tags` | `list(game.tags)` | `[]` |

**Note on `series.path`**: Romarr's `Library.path` is the
on-disk root for the imported library, but the current event
payloads (`OnGrab` / `OnImport` / etc.) don't carry library
context — the search/import layers don't pass it down to the
notification emission point. `series.path` is therefore emitted
as `""` until a future slice plumbs library context through.
The Sonarr schema validates either way per the empty-string
invariant above.

### `episodes[0]` ↔ `Release`

| Sonarr key | Romarr source |
|---|---|
| `episodes[0].id` | `release.id` |
| `episodes[0].episodeNumber` | `release.id` |
| `episodes[0].seasonNumber` | `0` |
| `episodes[0].title` | `release.name` |
| `episodes[0].overview` | `""` |
| `episodes[0].airDate` / `airDateUtc` | `""` |
| `episodes[0].qualityVersion` | `0` |

`seasonNumber` is fixed at `0` because Romarr has no concept of
seasons; consumers that group by season see all releases of a
game collapsed into "season 0," which is the closest approximation
to "all variants of this game."

### `release.quality.quality` ↔ `Release` quality

Romarr's `Release` doesn't carry a Sonarr-equivalent "quality
profile" (Sonarr means "1080p / 720p / SDTV"). The closest
analogue is the **DAT naming convention** the release was
identified against (`no-intro`, `redump`, `tosec`, `goodtools`),
which encodes verification authority and rough quality tier in
the retro-ROM domain.

| Sonarr key | Romarr source | Default |
|---|---|---|
| `release.quality.quality.id` | — | `0` |
| `release.quality.quality.name` | `release.naming_convention` | `"unknown"` |
| `release.quality.revision.version` | — | `1` |
| `release.quality.revision.real` | — | `0` |
| `release.quality.revision.isRepack` | — | `false` |

### `release` envelope (OnGrab)

| Sonarr key | Romarr source |
|---|---|
| `release.releaseTitle` | `release.name` |
| `release.indexer` | `indexer.name` |
| `release.size` | `0` (Torznab `size` not yet plumbed) |
| `release.releaseGroup` | `""` (Romarr doesn't parse the scene group; future enhancement) |

### `episodeFile` (OnImport / OnUpgrade)

| Sonarr key | Romarr source |
|---|---|
| `episodeFile.relativePath` | `dump.path` |
| `episodeFile.path` | `dump.path` |
| `episodeFile.quality` | (see `release.quality` above) |
| `episodeFile.size` | `dump.size_bytes` (or `0`) |
| `episodeFile.sceneName` | `""` |
| `episodeFile.releaseGroup` | `""` |

### `downloadId`

| Source | When |
|---|---|
| `download_id` (info-hash / NZO-id) | `OnGrab` |
| `""` | `OnImport` / `OnUpgrade` (download is already complete) |

## Retry policy (FR-007)

* **Schedule**: 3 attempts total at 1 s → 5 s → 30 s backoff.
* **Retry on**: HTTP 5xx, `httpx.RequestError` (DNS, TCP, TLS).
* **Do not retry on**: 4xx — that's a configuration mistake; one
  failure is enough to mark `notification.last_status = "failed"`.
* **Implementation note**: the 30 s slot is in the schedule but
  never reached, because `tenacity.stop_after_attempt(3)` halts
  the loop after attempt 3. The schedule is kept as
  `(1, 5, 30)` for symmetry with the spec text and to make
  future "extend to 4 attempts" diffs minimal.

## Backwards / forwards compatibility

* New Romarr `EventType`s are added by extending
  `payload_builders.py`'s dispatch table; the envelope shape is
  unchanged. Notifiarr-style consumers ignore unknown
  `eventType` strings.
* Adding a Sonarr key (e.g. a new field Sonarr v4 introduces)
  is allowed — Romarr emits it with a sentinel default until
  the underlying Romarr field exists.
* **Removing** a Sonarr key is a breaking change; downstream
  consumers may rely on it. Don't.
