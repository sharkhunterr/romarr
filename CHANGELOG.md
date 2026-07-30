# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

### [0.14.33](https://github.com/sharkhunterr/romarr/-/compare/v0.14.32...v0.14.33) (2026-07-30)

### [0.14.32](https://github.com/sharkhunterr/romarr/-/compare/v0.14.31...v0.14.32) (2026-07-29)


### Features

* **system:** version-check endpoint + UI badge + Settings About section ([60f90f4](https://github.com/sharkhunterr/romarr/-/commit/60f90f460dcab144e1b7f77f30ffe8f6a05eda21))

### [0.14.31](https://github.com/sharkhunterr/romarr/-/compare/v0.14.30...v0.14.31) (2026-07-29)


### Features

* **qbittorrent:** wire BEP-53 file selection for bundle magnets (fixes 0/N files selected) ([9dbf9df](https://github.com/sharkhunterr/romarr/-/commit/9dbf9dfed55c54459fdb78a8e72abea41133440d))


### Bug Fixes

* **backup:** REPLACE mode row-by-row delete with FK-catch (was 0-row nuke on IntegrityError) ([093c29f](https://github.com/sharkhunterr/romarr/-/commit/093c29fc04119268d1707ea8a49d546854c98e63))
* **importer:** 'match:no_game' now flags empty-source-dir explicitly (torrent-stuck case) ([5c6db4b](https://github.com/sharkhunterr/romarr/-/commit/5c6db4b7093d747642b2d646bbe57c017204a9bb))

### [0.14.30](https://github.com/sharkhunterr/romarr/-/compare/v0.14.29...v0.14.30) (2026-07-28)


### Features

* **activity:** Retry + Manual match actions on failed queue rows ([c65a8d4](https://github.com/sharkhunterr/romarr/-/commit/c65a8d4d8d212def0b186f8fa4691817bfc5dcf9))
* **downloaders:** Radarr-style remote path mapping (fixes 'completed file missing on disk') ([eb8bdf0](https://github.com/sharkhunterr/romarr/-/commit/eb8bdf0d26ade4299e985255dfc2f31c375b83e5))
* **profiles:** CF conditions over URLs / notes + rename misleading 'Rev 0' seed ([d361801](https://github.com/sharkhunterr/romarr/-/commit/d361801839370ad0081d3d9d93c038fa432ec1bf))
* **profiles:** merge Quality Definitions into Platforms + per-CF score breakdown ([f16c5a5](https://github.com/sharkhunterr/romarr/-/commit/f16c5a50a78426a3e5be32c8af698d27ebc9c875))
* **profiles:** Radarr-style Quality + Custom Format editors + title-field CF condition ([c0dc589](https://github.com/sharkhunterr/romarr/-/commit/c0dc58998017fccc4780bdec871f137be1bb07e2))
* **profiles:** seed 'MiNERVA Archive (preferred source)' CF + preset dropdown in the editor ([4dfd646](https://github.com/sharkhunterr/romarr/-/commit/4dfd64622b11d8cc708ea26f023388557b6f040f))


### Bug Fixes

* **downloaders:** surface qBit stalled/error reason in queue error_msg (was silent) ([df2bb77](https://github.com/sharkhunterr/romarr/-/commit/df2bb770a732d45a2b3019b8fe72c385b694ca52))
* **importer:** enrich opaque 'match:no_game' failure with actionable diagnostic ([2fe3176](https://github.com/sharkhunterr/romarr/-/commit/2fe31766090c178d351cf91e313d1efd2d5a7aa2))
* **qbittorrent:** tracker-aware diagnostic in error/stalled state (all-fail vs 0-peers) ([7c7c942](https://github.com/sharkhunterr/romarr/-/commit/7c7c942f702fdbcc9a4cb72a7ce774b2ff67d906))
* **search:** fuzzy matcher strips bracket tags before scoring ([a0b88cb](https://github.com/sharkhunterr/romarr/-/commit/a0b88cb0b49531acfe6de2f46df495365965bfb1))

### [0.14.29](https://github.com/sharkhunterr/romarr/-/compare/v0.14.28...v0.14.29) (2026-07-27)


### Bug Fixes

* three post-first-import papercuts (watcher default, magnet re-route, placeholder promotion) ([57ef86e](https://github.com/sharkhunterr/romarr/-/commit/57ef86ef68926726745d7163fa7cb01f27c859af))

### [0.14.28](https://github.com/sharkhunterr/romarr/-/compare/v0.14.27...v0.14.28) (2026-07-27)


### Bug Fixes

* **qbittorrent:** recognise qBit 5.x QBT_SID_<port> cookie + probe fallback ([786bfb1](https://github.com/sharkhunterr/romarr/-/commit/786bfb180fc9fe802311c02dcbe46ab68ee99699))

### [0.14.27](https://github.com/sharkhunterr/romarr/-/compare/v0.14.26...v0.14.27) (2026-07-27)

### [0.14.26](https://github.com/sharkhunterr/romarr/-/compare/v0.14.25...v0.14.26) (2026-07-27)


### Bug Fixes

* **dispatch:** resolve 302→magnet server-side so clients get TorrentMagnet ([942c9e3](https://github.com/sharkhunterr/romarr/-/commit/942c9e3f653fca261e818852ca3ee0476c23d276))

### [0.14.25](https://github.com/sharkhunterr/romarr/-/compare/v0.14.24...v0.14.25) (2026-07-27)


### Bug Fixes

* **dispatch:** skip unconfigured clients + surface real reason ([9cc0101](https://github.com/sharkhunterr/romarr/-/commit/9cc01016606203f4b1d65c9ad3b2971b4fe573d7))

### [0.14.24](https://github.com/sharkhunterr/romarr/-/compare/v0.14.23...v0.14.24) (2026-07-26)


### Bug Fixes

* **downloaders:** normalise host field — strip pasted scheme + port ([943eb7a](https://github.com/sharkhunterr/romarr/-/commit/943eb7ab5f207681ea1e3e4fb0232e8b6057d0a2))

### [0.14.23](https://github.com/sharkhunterr/romarr/-/compare/v0.14.22...v0.14.23) (2026-07-26)


### Bug Fixes

* **search:** platform-mismatch reject on release-scoped rounds + surface no_grab_reason ([9c94002](https://github.com/sharkhunterr/romarr/-/commit/9c94002455c76d4ceed6177fdaca8beccaba7989))

### [0.14.22](https://github.com/sharkhunterr/romarr/-/compare/v0.14.21...v0.14.22) (2026-07-26)


### Features

* **add-new:** auto-create a wanted Release when a monitored Game lands ([fec9dbc](https://github.com/sharkhunterr/romarr/-/commit/fec9dbc4c4eb7490ad45dc9624c65e620bd57e44))
* **examples:** community pack v2026.07.200 — .zip/.7z/.rar on every platform ([2a8e06c](https://github.com/sharkhunterr/romarr/-/commit/2a8e06c1ead4ad8a67a3682721aab1da8bca6ad6))

### [0.14.21](https://github.com/sharkhunterr/romarr/-/compare/v0.14.20...v0.14.21) (2026-07-26)


### Features

* **scanner:** auto-ingest unmatched files into Game+Release+Dump ([ca43bf2](https://github.com/sharkhunterr/romarr/-/commit/ca43bf2299f703608d85d0d11a21304323d9ce2b))

### [0.14.20](https://github.com/sharkhunterr/romarr/-/compare/v0.14.19...v0.14.20) (2026-07-26)


### Bug Fixes

* **backup:** import_bundle now commits — was silently rolling back ([76683c4](https://github.com/sharkhunterr/romarr/-/commit/76683c4f30c59dc78bf9a31570a72e4cb18e800c))

### [0.14.19](https://github.com/sharkhunterr/romarr/-/compare/v0.14.18...v0.14.19) (2026-07-26)


### Bug Fixes

* **tests:** deflake test_disabled_job_raises_unless_forced ([805754b](https://github.com/sharkhunterr/romarr/-/commit/805754b149e8ec4529268e82ba8d1e22d5f76d76))

### [0.14.18](https://github.com/sharkhunterr/romarr/-/compare/v0.14.17...v0.14.18) (2026-07-26)


### Features

* **indexers:** edit modal pre-fills api_key + eye toggle ([e892228](https://github.com/sharkhunterr/romarr/-/commit/e892228998151cff980e3a2e655eb2c1e54db0f8))
* **metadata:** edit existing provider secrets in place + eye toggle ([9d16f61](https://github.com/sharkhunterr/romarr/-/commit/9d16f6126d1904bcdba2693c32eceae179ad49e0))

### [0.14.17](https://github.com/sharkhunterr/romarr/-/compare/v0.14.16...v0.14.17) (2026-07-25)


### Features

* **library:** browse container paths from the create-library modal ([287c7b9](https://github.com/sharkhunterr/romarr/-/commit/287c7b99a22faa5a52836a9126fe9598fac98414))

### [0.14.16](https://github.com/sharkhunterr/romarr/-/compare/v0.14.15...v0.14.16) (2026-07-25)


### Features

* **platform-packs:** config surface — builtin toggle + priority ([b8e1678](https://github.com/sharkhunterr/romarr/-/commit/b8e1678cf0f27ebeba91463ee50d557ee70febd0))

### [0.14.15](https://github.com/sharkhunterr/romarr/-/compare/v0.14.14...v0.14.15) (2026-07-25)


### Bug Fixes

* **docker:** copy examples/ into build context ([45e875a](https://github.com/sharkhunterr/romarr/-/commit/45e875a89f055c61be4fec45d12a17c3c144add3))

### [0.14.14](https://github.com/sharkhunterr/romarr/-/compare/v0.14.13...v0.14.14) (2026-07-25)


### Bug Fixes

* **tests:** reconcile with in-session changes ([ffe6019](https://github.com/sharkhunterr/romarr/-/commit/ffe6019f316aac7580224acb64a452a0df2b1ae6))

### [0.14.13](https://github.com/sharkhunterr/romarr/-/compare/v0.14.12...v0.14.13) (2026-07-25)


### Features

* **backup:** à la carte backup/restore for 11 resource types ([ae34012](https://github.com/sharkhunterr/romarr/-/commit/ae340120dbe40428b2d18b27fafe2658beef853f))
* **deluge:** implémentation complète du DownloadClient Deluge 2.0+ ([9f61cd8](https://github.com/sharkhunterr/romarr/-/commit/9f61cd87929e16f4ee22e7064183f9a299c3cfd6))
* **deluge:** webhook importer accepte download_client_kind='deluge' ([bc35598](https://github.com/sharkhunterr/romarr/-/commit/bc35598fc1ac91ff489a28ca88cb213b486a9847))
* **platform-packs:** GitHub-sourced platform pack sync ([e5dba3a](https://github.com/sharkhunterr/romarr/-/commit/e5dba3a8a0c4071220b0ff51b2e691b2b826dcf3))
* **platform-packs:** preview modal + scheduled auto-sync ([1653481](https://github.com/sharkhunterr/romarr/-/commit/1653481937865e31356e4a4c1faba9080a276d3a))


### Bug Fixes

* **ui:** modals accessibles sur mobile — footer toujours visible ([640910f](https://github.com/sharkhunterr/romarr/-/commit/640910f8d2438aef98f0c8b4a2fe295039bcb5aa))

### [0.14.12](https://github.com/sharkhunterr/romarr/-/compare/v0.14.11...v0.14.12) (2026-07-25)


### Bug Fixes

* **docker:** PUID/PGID au runtime + gosu — installe zéro-friction sur Unraid ([53aaa02](https://github.com/sharkhunterr/romarr/-/commit/53aaa028cbca9dfc5512b2d104d54a70e3ee6f42))

### [0.14.11](https://github.com/sharkhunterr/romarr/-/compare/v0.14.10...v0.14.11) (2026-07-25)

### [0.14.10](https://github.com/sharkhunterr/romarr/-/compare/v0.14.9...v0.14.10) (2026-07-25)


### Bug Fixes

* **config:** SQLite auto-placée sous data_dir + favicons PNG (fallback SVG) ([5e8407b](https://github.com/sharkhunterr/romarr/-/commit/5e8407bffc0413bf5b1ea5e7daddc539f8fcc653))

### [0.14.9](https://github.com/sharkhunterr/romarr/-/compare/v0.14.8...v0.14.9) (2026-07-13)


### Bug Fixes

* **tests:** patch dispatcher _logger with MagicMock to survive full CI ([9120771](https://github.com/sharkhunterr/romarr/-/commit/91207715361ae20b2419c124bf8885e22b39325e))

### [0.14.8](https://github.com/sharkhunterr/romarr/-/compare/v0.14.7...v0.14.8) (2026-07-13)


### Bug Fixes

* **tests:** pin event_dispatch caplog to a direct handler ([0c5f3ee](https://github.com/sharkhunterr/romarr/-/commit/0c5f3eef294e091e89bed4a984080940abf660f4))

### [0.14.7](https://github.com/sharkhunterr/romarr/-/compare/v0.14.6...v0.14.7) (2026-07-12)


### Features

* **activity:** redesign history + fix search fan-out + dispatch noise ([32c86ff](https://github.com/sharkhunterr/romarr/-/commit/32c86fff3e9eb2560b0d9b2344b279229847053f))
* **integration:** platforms endpoint + tolerate concurrent game adds ([712f9d4](https://github.com/sharkhunterr/romarr/-/commit/712f9d4b81ba707eed4eab4bf52d8decbccbcfc9))
* **metadata:** IGDB-native integration endpoints for request managers ([d682996](https://github.com/sharkhunterr/romarr/-/commit/d682996e8970535adc1276541b67d549c2135198))
* **search:** one canonical match_score for display and grab ([6539957](https://github.com/sharkhunterr/romarr/-/commit/6539957791661f839e33cff10d0571739a20d94a))


### Bug Fixes

* **importer:** coalesce duplicates instead of a bogus match:no_game ([1f2e64a](https://github.com/sharkhunterr/romarr/-/commit/1f2e64af6b728b114d28e3b13c007c2cd6367264))
* **search:** record canonical match_score in search history ([1ed22cc](https://github.com/sharkhunterr/romarr/-/commit/1ed22cc7a593c8020725f808ab9ce7f763c10329))
* **search:** report best_score as the canonical match_score ([f8d4d34](https://github.com/sharkhunterr/romarr/-/commit/f8d4d34d7f37225a3d3c99e57fabf53a63590c91))
* **search:** stop logging unidentified torznab noise as a failed grab ([97ffead](https://github.com/sharkhunterr/romarr/-/commit/97ffead32d08396f603cf09d6ce5c3b908619e2e))
* **tasks:** AutoCheckAdded now grabs, not just searches ([81c22d5](https://github.com/sharkhunterr/romarr/-/commit/81c22d5e13ac39dacfaf1693fce171205ae0cbf4))

### [0.14.6](https://github.com/sharkhunterr/romarr/-/compare/v0.14.5...v0.14.6) (2026-05-20)

### [0.14.5](https://github.com/sharkhunterr/romarr/-/compare/v0.14.4...v0.14.5) (2026-05-20)

### [0.14.4](https://github.com/sharkhunterr/romarr/-/compare/v0.14.3...v0.14.4) (2026-05-20)

### [0.14.3](https://github.com/sharkhunterr/romarr/-/compare/v0.14.2...v0.14.3) (2026-05-20)

### [0.14.2](https://github.com/sharkhunterr/romarr/-/compare/v0.14.1...v0.14.2) (2026-05-20)

### 0.14.1 (2026-05-20)


### Features

* **001-foundation:** DAT manager + hash-match cascade + Identifier façade ([06b534b](https://github.com/sharkhunterr/romarr/-/commit/06b534bb4150fea9cdad2b91d37008d53b2cbe5d))
* **001-foundation:** full filename parser cascade + header readers + merger ([7afd7d4](https://github.com/sharkhunterr/romarr/-/commit/7afd7d4196bfe1eeb42a43c027071e1534d93081))
* **001-foundation:** persistence + schemas + filename parser scaffolding ([803c7a4](https://github.com/sharkhunterr/romarr/-/commit/803c7a4a6ca4c24efb57d2bf16826eb1de920b5e))
* **001-foundation:** project skeleton + domain model + Hasher ([30daaa8](https://github.com/sharkhunterr/romarr/-/commit/30daaa88a84e603de225fa3034b398983b24838a))
* **002-metadata:** FRAME + AGG — provider ABC, registry, pure aggregator ([56b10d2](https://github.com/sharkhunterr/romarr/-/commit/56b10d210017b58c625691a02f34a2e7f8aa55b6)), closes [Romm-#1770](https://github.com/sharkhunterr/Romm-/-/issues/1770)
* **002-metadata:** IGDB provider — OAuth + Apicalypse + cover CDN ([9f06071](https://github.com/sharkhunterr/romarr/-/commit/9f060717ae529e2926f43121cfe009300d196a5f))
* **002-metadata:** LaunchBox + Hasheous + PlayMatch — 9/9 providers ([9a4a463](https://github.com/sharkhunterr/romarr/-/commit/9a4a463e478fd4ae95ea2672473b534f1e129a2d))
* **002-metadata:** refresh orchestrator + admin API stubs ([26d2cea](https://github.com/sharkhunterr/romarr/-/commit/26d2cea9ae8e487476b5737e712986a63fbee3c0))
* **002-metadata:** SCAF + PERS — encryption, 3 tables, cache + covers ([b635172](https://github.com/sharkhunterr/romarr/-/commit/b63517242a512d8c74f48f015d5b44eba09d6a3e))
* **002-metadata:** ScreenScraper + MobyGames providers (full multi-field) ([b514483](https://github.com/sharkhunterr/romarr/-/commit/b5144833498b1b7a3542722de49da4d8f5de5c48))
* **002-metadata:** SGDB + RA + HLTB providers (single-field trio) ([3bd3ccf](https://github.com/sharkhunterr/romarr/-/commit/3bd3ccfaf041dafd82d48f13676f75df9c1a273c))
* **003-platform-packs:** INGEST + BUILTIN — transactional ingestor + 20-platform pack ([7fd236d](https://github.com/sharkhunterr/romarr/-/commit/7fd236df0abbd2e0b19ebf3f3d5e241b2b96a1c9))
* **003-platform-packs:** OVR + API — overrides + admin endpoints ([24ecf95](https://github.com/sharkhunterr/romarr/-/commit/24ecf95e1c6ca2fd9b349afd1de021a8bbfaedda))
* **003-platform-packs:** SCAF + PERS + VALID — module skeleton + validator ([4f318fa](https://github.com/sharkhunterr/romarr/-/commit/4f318fa5d3fb51fa8dc0f8c5beeaa2c1f0c75a45))
* **004-indexers:** CLIENT + RATE — NewznabClient + per-indexer rate limiter ([07ecd8c](https://github.com/sharkhunterr/romarr/-/commit/07ecd8cbcf96f97cc07c7d811e106b618a05a389))
* **004-indexers:** CONN + RSSHEALTH — registry, connectivity, RSS sync, health ([f822e98](https://github.com/sharkhunterr/romarr/-/commit/f822e987ec82f84c71935d07ffd3147ad59a3d42))
* **004-indexers:** PROW + IDXAPI + HARD — admin API + 0.4.0a1 ([17717f9](https://github.com/sharkhunterr/romarr/-/commit/17717f9cd67bb330a8ff2b06ff9d07af03aec9cf))
* **004-indexers:** SCAF + PERS + PARSE — module skeleton + XML parsers ([d3df4da](https://github.com/sharkhunterr/romarr/-/commit/d3df4da83e5eb45b5ce1ce9baff6ccf5222f6e7d))
* **005-download-clients:** API + HARD — admin endpoints + 0.5.0a1 ([9724d57](https://github.com/sharkhunterr/romarr/-/commit/9724d57e7acb973f3054eb4a2bf09baf77ed5f74))
* **005-download-clients:** QBIT — qBittorrent client + CL001 idempotency + CL003 version gate ([cbabd08](https://github.com/sharkhunterr/romarr/-/commit/cbabd08f034e2ebfd2639501a92a7f3e49a102df))
* **005-download-clients:** RETRY + CIRCUIT — pure-function retry state machine + per-client breaker ([dc139ef](https://github.com/sharkhunterr/romarr/-/commit/dc139ef7fcae8e5ebfa20ab96279ae33dc757bb5))
* **005-download-clients:** ROUTE — pure-function route_release + source-form preference ([05598b2](https://github.com/sharkhunterr/romarr/-/commit/05598b27551dec6eb7820b0159f63f547fea95c0))
* **005-download-clients:** SAB + CONN — SABnzbd client + connectivity orchestrator ([8f30863](https://github.com/sharkhunterr/romarr/-/commit/8f3086340fafa2246f638bf35927652032928cc7))
* **005-download-clients:** SCAF + PERS + ABC + STUBS — module skeleton, models + 0005 migration, ABC, three v1 stubs ([dea9b86](https://github.com/sharkhunterr/romarr/-/commit/dea9b86194c3efe8500d7a22aa1c0b5f9f76bcec))
* **006-profiles:** API — six CRUD routers + naming preview + JSON Schema ([f9df544](https://github.com/sharkhunterr/romarr/-/commit/f9df544af37573e03ef1074d1a048c9f3c55f46d))
* **006-profiles:** EVAL — pure-function evaluator + Custom Format scorer ([fbe3fc8](https://github.com/sharkhunterr/romarr/-/commit/fbe3fc85e09d884aa61fbb9f16456aaa48fa906a))
* **006-profiles:** NAME — sandboxed Jinja2 naming engine ([fc24f87](https://github.com/sharkhunterr/romarr/-/commit/fc24f871baa57c2f1f4192c61a7517046800e429))
* **006-profiles:** SCAF + PERS — module skeleton, six profile tables, 0006 migration ([5244760](https://github.com/sharkhunterr/romarr/-/commit/5244760686e5a60aba15c55073ba2672f20d2900))
* **006-profiles:** SEED — JSON catalogue + idempotent first-boot runner ([fa541ac](https://github.com/sharkhunterr/romarr/-/commit/fa541ac25ad5914d6cada03cd669d0cbe5532454))
* **007-search-decision-engine:** API + DISPATCH — 5 admin-gated routers, route_release bridge ([285baf9](https://github.com/sharkhunterr/romarr/-/commit/285baf908e6410097745da9ffda5c8cdd2f047bd))
* **007-search-decision-engine:** PIPE — pure-function decision engine ([388e6cc](https://github.com/sharkhunterr/romarr/-/commit/388e6cc4b6b0e5570aa204f22875795d8c1c548e))
* **007-search-decision-engine:** ROUNDS — manual + RSS orchestrators + preload ([e470cd2](https://github.com/sharkhunterr/romarr/-/commit/e470cd26bdea4a62c43addae40e9e0d99cce74cd))
* **007-search-decision-engine:** SCAF + PERS — module skeleton, 3 tables, 0007 migration ([ed63097](https://github.com/sharkhunterr/romarr/-/commit/ed630976356499652770ef3cb1c1db8d58403b84))
* **007-search-decision-engine:** STATE — async cache + blocklist + history helpers ([32d551e](https://github.com/sharkhunterr/romarr/-/commit/32d551e87a88b96dd68c33552850a4bc6c1b7efe))
* **008-import-pipeline:** API (read endpoints) — history list + unidentified list/delete ([ac0dcf2](https://github.com/sharkhunterr/romarr/-/commit/ac0dcf2e825a9a35d2ffcba82f4cb0b9997a7f40))
* **008-import-pipeline:** DBUPDATE + LIFECYCLE — persist Dump + dispatch download-client cleanup ([e78ae48](https://github.com/sharkhunterr/romarr/-/commit/e78ae480b6659c547ddd34bfb88b138b5498ddcf))
* **008-import-pipeline:** EXTRACT — zip/7z/rar with depth limit + bomb defense + idempotent skip ([b1397a0](https://github.com/sharkhunterr/romarr/-/commit/b1397a0ddea44ccc6d41a1e02136981b7b0b4ed7))
* **008-import-pipeline:** GAMEMATCH — title-based fuzzy match with suggested-game fallback ([c659c3e](https://github.com/sharkhunterr/romarr/-/commit/c659c3e26fe2d62e7bea81f7a979e21f9a6378b4))
* **008-import-pipeline:** HASH + DATMATCH + IDENTIFY — three foundation-wrapping pipeline steps ([7e19161](https://github.com/sharkhunterr/romarr/-/commit/7e1916121fb71d0e4fbf556dd0fd4113817e25cd))
* **008-import-pipeline:** MOVE — atomic mover with hardlink-first + cross-fs fallback ([779ba8a](https://github.com/sharkhunterr/romarr/-/commit/779ba8a796b0f40765b7261a21024bb34a695054))
* **008-import-pipeline:** MULTIDISC + PROFILEGATE + RENDER — three pure pipeline steps ([0af4b3f](https://github.com/sharkhunterr/romarr/-/commit/0af4b3f12c79f8ed8435fc76afbfa62cce82ec81))
* **008-import-pipeline:** NOTIFY — in-process event bus + OnImport/OnUpgrade emitter ([d3ba0e2](https://github.com/sharkhunterr/romarr/-/commit/d3ba0e2e5490327b2d1e8fba85a46131c8c5a441))
* **008-import-pipeline:** SCAF — module skeleton, ImportHistory, locks, migration 0008 ([fd78d3d](https://github.com/sharkhunterr/romarr/-/commit/fd78d3d7aabf36e7aeb8a18770f4cce36da46cbf))
* **008-import-pipeline:** WATCH (webhook) — bearer-token auth + sliding-window rate limit ([eee4ad2](https://github.com/sharkhunterr/romarr/-/commit/eee4ad2992bc1bbfe494f00928a9268d415aaa1e))
* **009-library-exporters:** API — library CRUD endpoints + force-delete cascade gate ([d8e5bc1](https://github.com/sharkhunterr/romarr/-/commit/d8e5bc193e8cf53b64d330075a9c58c0f71b744e))
* **009-library-exporters:** EXP-ESDE — pure gamelist.xml renderer + atomic write + media mirror ([b1e8107](https://github.com/sharkhunterr/romarr/-/commit/b1e8107cd36036c4eb1f73a4be1783eab299ee70))
* **009-library-exporters:** EXP-PEGASUS + EXP-LAUNCHBOX — pure renderers + shared atomic writer ([6edfde4](https://github.com/sharkhunterr/romarr/-/commit/6edfde4ba6874cf511eb8213c513482f2baaab40))
* **009-library-exporters:** EXP-ROMM — best-effort HTTP push with tenacity retry ([ca4a8d3](https://github.com/sharkhunterr/romarr/-/commit/ca4a8d35f4d575dae2f259e58912411e756dede3))
* **009-library-exporters:** HEART — pure heartbeat probe + 5-min debounce primitive ([e6661f4](https://github.com/sharkhunterr/romarr/-/commit/e6661f4f28c069d2fd80e15571959d79c68b4a1f))
* **009-library-exporters:** ROUTE + DISK — pure-function router + pre-import disk-space gate ([e6cf5ca](https://github.com/sharkhunterr/romarr/-/commit/e6cf5ca3ab103f07f9cff042fd0b323b5a53c89d))
* **009-library-exporters:** SCAF + PERS — module skeleton, models, migration 0009 ([e0daa74](https://github.com/sharkhunterr/romarr/-/commit/e0daa74439f3f1dc3bf76816b05b10d79eaea0e2))
* **009-library-exporters:** SCAN-FULL — full filesystem walk + idempotent re-scan + orphan sweep ([38d15a2](https://github.com/sharkhunterr/romarr/-/commit/38d15a2a49030f531ca7ae15de963cbcb3e76c3c))
* **010-auth:** admin user-CRUD + trusted-proxy auto-create ([c11a863](https://github.com/sharkhunterr/romarr/-/commit/c11a863e26c97c3244c8ec85946a69826645683d))
* **010-auth:** FastAPI app + /api/v3/auth/* endpoints ([e00637f](https://github.com/sharkhunterr/romarr/-/commit/e00637f91689d4eeb090617adf0bd061428b4d93))
* **010-auth:** schema layer + spec 001 wrap-up polish ([6520bfd](https://github.com/sharkhunterr/romarr/-/commit/6520bfd58e47f96fc4b0063978ba8646f4cc4af9))
* **010-auth:** services layer — setup, login, sessions, API keys, chain, RBAC ([fabb54c](https://github.com/sharkhunterr/romarr/-/commit/fabb54cc3e032b334cf7eda145bb1187c58f5cf1))
* **011-notifications-health:** CHANNEL — in-process pub/sub + Apprise wrapper ([770c601](https://github.com/sharkhunterr/romarr/-/commit/770c60102831d0f7c018ab57fbd8113bf4cb8e27))
* **011-notifications-health:** DISPATCH — per-(notification, event) routing ([1172a19](https://github.com/sharkhunterr/romarr/-/commit/1172a19521f4a9422a8e819a515bef05f33aa1a2))
* **011-notifications-health:** HEALTH — engine core + debouncer + 4 checks ([a3efb10](https://github.com/sharkhunterr/romarr/-/commit/a3efb10d08e52bcf3986fcf7ed5fb4d3490fe519))
* **011-notifications-health:** SCAF + PERS — module skeleton, models, migration 0011 ([a946ec3](https://github.com/sharkhunterr/romarr/-/commit/a946ec318bb1822e7ea91d27d94be0ce2e285201))
* **011-notifications-health:** TEMPLATES — sandboxed renderer + 7 default templates ([04bd09c](https://github.com/sharkhunterr/romarr/-/commit/04bd09c101b7b69b63e8a7bb4c306a5e39582188))
* **011-notifications-health:** TESTEP + API — CRUD, health, test endpoint ([0bccd34](https://github.com/sharkhunterr/romarr/-/commit/0bccd341f7ec4138aec43485764d43e8f550b773))
* **011-notifications-health:** WEBHOOK — Sonarr v3-shape webhooks + retry ([97af37d](https://github.com/sharkhunterr/romarr/-/commit/97af37db3d998af8ffd524b1fbb20b1ecd008e3f))
* **012-tasks-scheduler:** API — tasks + runs + cancel REST endpoints ([34e5ef8](https://github.com/sharkhunterr/romarr/-/commit/34e5ef897b3af3327642366c01904479cd8b4934))
* **012-tasks-scheduler:** CMD — Sonarr-compat command alias endpoint ([897d6e3](https://github.com/sharkhunterr/romarr/-/commit/897d6e380efca0a067c9661bc51cc37207a83baf))
* **012-tasks-scheduler:** EXEC-A — lifecycle helpers + progress throttle ([7593888](https://github.com/sharkhunterr/romarr/-/commit/7593888f72749bb50f318c15dc83583801461dd4))
* **012-tasks-scheduler:** EXEC-B — cancellation registry + auto-pause ([fbea99f](https://github.com/sharkhunterr/romarr/-/commit/fbea99f15c606805702bb58be737328c46910112))
* **012-tasks-scheduler:** RUNNER — JobRunner Protocol + 9 adapters ([cb187d6](https://github.com/sharkhunterr/romarr/-/commit/cb187d66386358bf9a7ac250ae6fe89e11a2818d))
* **012-tasks-scheduler:** SCAF + PERS — module skeleton, models, migration 0012 ([743c5b7](https://github.com/sharkhunterr/romarr/-/commit/743c5b7fd8c3c7c50001e80472ac8554e3acdb74))
* **012-tasks-scheduler:** SCHED — APScheduler bootstrap + SchedulerService ([281d9d2](https://github.com/sharkhunterr/romarr/-/commit/281d9d2e3ab4b00ab0ae9789d407436e4c04862f))
* **012-tasks-scheduler:** SEED — factory-default job catalogue ([429a505](https://github.com/sharkhunterr/romarr/-/commit/429a505280c0c79dd78812ec199c58c72a45ae7f))
* **012-tasks-scheduler:** SHUTDOWN — graceful lifespan + scheduler wiring ([edc197f](https://github.com/sharkhunterr/romarr/-/commit/edc197f17560ba3eae999d075028d0fd6a679604))
* **013-rest-api-websocket:** CMD — DELETE /api/v3/command/{id} cancel (T085-T089) ([d39c132](https://github.com/sharkhunterr/romarr/-/commit/d39c132284be24e010bd171b9d5e48daac3e7663))
* **013-rest-api-websocket:** ENVELOPES — canonical pagination + error shapes ([f3fa286](https://github.com/sharkhunterr/romarr/-/commit/f3fa28689ae17fb9429649b33331b445e6b47377))
* **013-rest-api-websocket:** FACTORY — canonical create_app re-export + lifespan tests ([f908a93](https://github.com/sharkhunterr/romarr/-/commit/f908a9334fe7f97c1465ab7b1b7aa7a245b11475))
* **013-rest-api-websocket:** MW — CSRF double-submit cookie middleware (T021/T022/T023/T033) ([92f5f4d](https://github.com/sharkhunterr/romarr/-/commit/92f5f4df4eeec8ce7476f6f538847cf25bcf8788))
* **013-rest-api-websocket:** MW — GZip + CORS middleware (FR-029, FR-030) ([1ab2f93](https://github.com/sharkhunterr/romarr/-/commit/1ab2f9355120467f738f7e336ef0d706b219d2f7))
* **013-rest-api-websocket:** MW — Idempotency-Key middleware (FR-020/021/025) ([548e78f](https://github.com/sharkhunterr/romarr/-/commit/548e78f1162904621a111085bbb6dde22a40bcf2))
* **013-rest-api-websocket:** MW — rate-limit middleware (T024-T034) ([dd91c66](https://github.com/sharkhunterr/romarr/-/commit/dd91c66ca81aa4607969f7ae3ccbc0f1c8e4d53b))
* **013-rest-api-websocket:** OPENAPI — 3.1 customizer + security schemes (T075/T076/T078/T079/T080) ([a29c86a](https://github.com/sharkhunterr/romarr/-/commit/a29c86a1b94e3f1ecd530eaf2a55f8dfd871ebd2))
* **013-rest-api-websocket:** ROUTERS — Backup management (T040, T055) ([82304c6](https://github.com/sharkhunterr/romarr/-/commit/82304c63465ab924596cf002a57e327778f4f384))
* **013-rest-api-websocket:** ROUTERS — Calendar MVP empty endpoint (T049, T059) ([67a0f9e](https://github.com/sharkhunterr/romarr/-/commit/67a0f9ef2e8f6a014c5d16d39a5164fc2de0f33b))
* **013-rest-api-websocket:** ROUTERS — Log endpoints + FR-001 floor reached (T038/T039/T054/T083) ([f6f74b1](https://github.com/sharkhunterr/romarr/-/commit/f6f74b15c93f6950e60b0f1435221c9b9430e4e2))
* **013-rest-api-websocket:** ROUTERS — Queue list endpoint (T044, T057 partial) ([481d6d9](https://github.com/sharkhunterr/romarr/-/commit/481d6d9a3af054ece1b66a2d7da3e75c3a5f00b9))
* **013-rest-api-websocket:** ROUTERS — Sonarr-shape /api/v3/system/status (US1, T053) ([ee16540](https://github.com/sharkhunterr/romarr/-/commit/ee16540ab451a7acb10648fadc751e417e34de00))
* **013-rest-api-websocket:** ROUTERS — Tag CRUD + polymorphic detail (T060) ([7d95b5a](https://github.com/sharkhunterr/romarr/-/commit/7d95b5aaaeb823f7d45625581eff3e55804fddee))
* **013-rest-api-websocket:** ROUTERS — Unified history (UNION) endpoint (T047, T048, T058) ([ba5223e](https://github.com/sharkhunterr/romarr/-/commit/ba5223ed4f15dcc36c821bf222085163410096f4))
* **013-rest-api-websocket:** ROUTERS — Wanted /missing + /cutoff lists (T042, T056 partial) ([03480fb](https://github.com/sharkhunterr/romarr/-/commit/03480fb531e59838bcc6c49199b073dced43b837))
* **013-rest-api-websocket:** SCAF — Tag/QueueEntry/IdempotencyCache models + migration 0013 ([e3c3306](https://github.com/sharkhunterr/romarr/-/commit/e3c330656118f510add7daf0925b6181947a76fa)), closes [#9BBC0](https://github.com/sharkhunterr/romarr/-/issues/9BBC0)
* **013-rest-api-websocket:** SONARR — peer-recognition probe fixture (T090-T093) ([aefe223](https://github.com/sharkhunterr/romarr/-/commit/aefe2236cd26aaa35fc87f90a4cfc905d9081e41))
* **013-rest-api-websocket:** WIRE — endpoint coverage audit (T081/T082/T083/T084) ([8634fcf](https://github.com/sharkhunterr/romarr/-/commit/8634fcf30e676d0af7e09092a21b5bd987b2e1e7))
* **013-rest-api-websocket:** WS — /signalr/messages foundation (T061-T074) ([f509d0e](https://github.com/sharkhunterr/romarr/-/commit/f509d0e69f26a886a4a0f6766d9bbc4f0f80e004))
* **013-rest-api-websocket:** WS — message coverage + lossy-channel contract (T066, T067) ([3fd1430](https://github.com/sharkhunterr/romarr/-/commit/3fd1430fd1dbcd8037eee9fa78dd1334e1562113))
* **014-frontend-pwa:** CODEGEN — openapi-typescript types from /api/v3 (T010-T013) ([67dd345](https://github.com/sharkhunterr/romarr/-/commit/67dd3456e0d3332af66fef9829b4881b54489f42)), closes [#9BBC0](https://github.com/sharkhunterr/romarr/-/issues/9BBC0)
* **014-frontend-pwa:** P-ACT — Activity page (Queue | History tabs) (T093 partial) ([604580a](https://github.com/sharkhunterr/romarr/-/commit/604580a95aa9004da925d0b42171282d3c1d15b9))
* **014-frontend-pwa:** P-DASH — first real page (Dashboard) with stats / health / activity / quick actions (T062) ([ec3bdb5](https://github.com/sharkhunterr/romarr/-/commit/ec3bdb52a0f86177b4af2b8e887c69e1dc5c4f23))
* **014-frontend-pwa:** P-SET — Settings > Tags CRUD sub-page (T098.5) ([7c28fda](https://github.com/sharkhunterr/romarr/-/commit/7c28fda8db248807c04d01e331553076d2dc543b)), closes [#9BBC0](https://github.com/sharkhunterr/romarr/-/issues/9BBC0)
* **014-frontend-pwa:** P-SYS — System page with Status / Tasks / Logs / Backup tabs (T107 partial) ([196d910](https://github.com/sharkhunterr/romarr/-/commit/196d910e42e204a658c1fe80ced56c30f3ed48e0))
* **014-frontend-pwa:** P-WANT — Wanted page (Missing | Cutoff tabs) + ROM-component composition (T090 partial) ([f1c3eda](https://github.com/sharkhunterr/romarr/-/commit/f1c3eda0210d073e2e0c54734f0a028b58197ff9))
* **014-frontend-pwa:** ROM — 10 ROM-specific components (T027-T037) ([905b8b1](https://github.com/sharkhunterr/romarr/-/commit/905b8b17a8ff5aaeffa7db23a0dbb5f88770e777))
* **014-frontend-pwa:** ROUTING — react-router + auth guard + theme provider (T038-T044) ([3cf0543](https://github.com/sharkhunterr/romarr/-/commit/3cf05430dbffafea6a93a43f309ae70472f13b12))
* **014-frontend-pwa:** SCAF — web/ workspace bootstrap (T001-T008) ([787a47a](https://github.com/sharkhunterr/romarr/-/commit/787a47a7b36fe41a378b67d94c447bbe68f0733b)), closes [#9BBC0](https://github.com/sharkhunterr/romarr/-/issues/9BBC0)
* **014-frontend-pwa:** SHARED — app shell, header, bottom nav, layout primitives (T019/T020/T022/T023/T025) ([84b2b8a](https://github.com/sharkhunterr/romarr/-/commit/84b2b8a38bb5ae715b6ce00c9beda20de1d848d4))
* **014-frontend-pwa:** TanStack Query + real /api/v3/auth/me probe (T041 / T042 / login mutation) ([ca3049b](https://github.com/sharkhunterr/romarr/-/commit/ca3049b758a4c2a9468493f59793df2e317fa370))


### Bug Fixes

* drop stray builtin-2026.05.001.yaml left over from slice 401 rename ([c3cb5aa](https://github.com/sharkhunterr/romarr/-/commit/c3cb5aa066bf20a594ce32c06645fefe1a1dd3a3))
* **spa:** serve /locales/* as static files instead of SPA fallback ([641c435](https://github.com/sharkhunterr/romarr/-/commit/641c4358391ba27eb731fbf1cb262f74a6035511))
* **tests:** align quality evaluator + seeder tests to slice 403 ([2ec66f6](https://github.com/sharkhunterr/romarr/-/commit/2ec66f6c8296bb52a0a448d551c72f2b00fc90ae))
* **tests:** profile_gate tests use non-container format ([edc90c5](https://github.com/sharkhunterr/romarr/-/commit/edc90c527dd9db458ab3b961fc7064a3228ae66c))
