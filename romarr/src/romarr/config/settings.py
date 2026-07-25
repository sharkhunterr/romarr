"""Pydantic-settings driven application configuration.

All env vars are prefixed ``ROMARR_``. Optional bearer tokens for
hash-match endpoints are populated only when set; an empty value
means "use anonymous public access" (spec 001 FR-026a).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration. Read once at startup."""

    model_config = SettingsConfigDict(
        env_prefix="ROMARR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Database — chaîne vide par défaut. La valeur effective est
    # calculée par `_derive_defaults()` : `sqlite+aiosqlite:///
    # {data_dir}/romarr.db`. Ainsi un `data_dir` custom (via env
    # ROMARR_DATA_DIR ou via l'image Docker) suffit à repositionner
    # aussi la base — pas besoin de dupliquer ROMARR_DATABASE_URL.
    # Un URL explicite (PostgreSQL par exemple) reste prioritaire.
    database_url: str = Field(
        default="",
        description="SQLAlchemy connection URL. Vide (défaut) → SQLite "
        "posé sous ``{data_dir}/romarr.db``. Renseigner explicitement "
        "pour PostgreSQL ou un autre backend, ex: "
        "``postgresql+asyncpg://user:pass@host/db``.",
    )

    # Hashing
    hash_buffer_bytes: int = Field(
        default=1 << 20,
        ge=4096,
        le=1 << 24,
        description="Streaming hash buffer size. 1 MiB default; tunable "
        "between 4 KiB and 16 MiB.",
    )

    # Hash-match cascade endpoints (spec 001 FR-026a)
    hasheous_base_url: str = Field(
        default="https://api.hasheous.org",
        description="Hasheous remote API base URL.",
    )
    hasheous_token: str = Field(
        default="",
        description="Optional bearer token for authenticated Hasheous "
        "access. Empty = anonymous public endpoint.",
    )
    playmatch_base_url: str = Field(
        default="https://api.playmatch.org",
        description="PlayMatch remote API base URL.",
    )
    playmatch_token: str = Field(
        default="",
        description="Optional bearer token for authenticated PlayMatch "
        "access. Empty = anonymous public endpoint.",
    )

    # Auth secret
    auth_secret_key: str = Field(
        default="",
        description="Master key used to derive Fernet encryption keys "
        "for credentials at rest. MUST be set in production.",
    )

    # Spec 010 auth knobs (T005). The dedicated
    # ``src/romarr/auth/settings.py`` the spec called for
    # never materialised — auth settings colocate here so
    # there's a single Settings surface across the project
    # (mirroring the spec-002 / 003 / 004 / 014 pattern).
    auth_session_ttl_seconds: int = Field(
        default=86_400,
        ge=60,
        description=(
            "Spec 010 — server-side session TTL. Sessions older "
            "than this are revoked on the next request. Default "
            "24h."
        ),
    )
    bcrypt_cost: int = Field(
        default=12,
        ge=4,
        le=20,
        description=(
            "Spec 010 — bcrypt hashing cost factor. Default 12 "
            "balances login latency and brute-force resistance "
            "on contemporary hardware."
        ),
    )
    trust_proxy_auth: bool = Field(
        default=False,
        description=(
            "Spec 010 — when true, the auth chain consults "
            "``trusted_proxy_headers`` (e.g., "
            "``X-Forwarded-User``) for an upstream-proxy "
            "identity. Off by default to avoid header-spoof "
            "vectors when the deployment isn't behind a "
            "trusted reverse proxy."
        ),
    )
    trusted_proxy_headers: list[str] = Field(
        default_factory=list,
        description=(
            "Spec 010 — JSON-encoded list of header names "
            "(e.g., [\"X-Forwarded-User\", \"X-Auth-User\"]) "
            "the auth chain treats as authoritative when "
            "``trust_proxy_auth`` is on."
        ),
    )
    oidc_issuer_url: str = Field(
        default="",
        description=(
            "Spec 010 — OIDC issuer (.well-known/openid-"
            "configuration is fetched from "
            "``<issuer>/.well-known/openid-configuration``). "
            "Empty disables OIDC."
        ),
    )
    oidc_client_id: str = Field(
        default="",
        description="Spec 010 — OIDC client id.",
    )
    oidc_client_secret: str = Field(
        default="",
        description="Spec 010 — OIDC client secret.",
    )
    redis_url: str = Field(
        default="",
        description=(
            "Spec 010 — Redis URL for the optional session "
            "cache. Empty falls back to the DB-backed session "
            "store (the FR-013 default)."
        ),
    )

    # Importer webhook
    importer_webhook_token: str = Field(
        default="",
        description="Bearer token expected on the "
        "POST /api/v3/webhook/download-complete endpoint. Empty = the "
        "webhook is closed (every call returns 401). Set per "
        "download client in the operator's qBittorrent / SAB hook "
        "configuration.",
    )
    importer_watcher_enabled: bool = Field(
        default=False,
        description="Enable the polling watcher (FR-001 fallback to "
        "the webhook surface). When True, the lifespan starts a "
        "background loop that polls every enabled download client "
        "for completed downloads on a 30 s cadence. Default OFF for "
        "the test suite + dev workflows; production deployments "
        "set ROMARR_IMPORTER_WATCHER_ENABLED=true.",
    )

    # Cover storage
    data_dir: str = Field(
        default="./data",
        description="Root data directory for covers, backups, and runtime files.",
    )

    # Spec 003 — Platform Packs
    builtin_pack_path: str | None = Field(
        default=None,
        description=(
            "Spec 003 T005 — explicit path to the built-in "
            "Platform Pack YAML. When unset, the resolver "
            "falls back to /opt/romarr/builtin-packs/ and the "
            "wheel resource. Setting this overrides the "
            "env-only ``ROMARR_BUILTIN_PACK_PATH`` (which now "
            "feeds this field via the SettingsConfigDict env "
            "prefix)."
        ),
    )

    # API middleware (spec 013)
    gzip_min_size_bytes: int = Field(
        default=1024,
        ge=0,
        description="Spec 013 FR-029. Response bodies at or above this "
        "byte threshold are gzip-compressed. Set to 0 to compress every "
        "response.",
    )
    cors_allowed_origins: list[str] = Field(
        default_factory=list,
        description="Spec 013 FR-030. JSON-encoded list of allowed "
        "Origin headers; empty = same-origin only. Reverse proxies "
        "fronting Romarr should leave this empty and pass the original "
        "Host through unchanged.",
    )

    # Logs (spec 013)
    log_dir: str = Field(
        default="./data/logs",
        description="Directory where Romarr writes rotating log "
        "files. Read by the /api/v3/system/log/file endpoint to "
        "enumerate and stream log files for the operator UI.",
    )

    # Backups (spec 013, spec 012 BackupRunner output)
    backup_path: str = Field(
        default="./data/backups",
        description="Directory where the spec 012 BackupRunner "
        "writes archive files. Read by the "
        "/api/v3/system/backup endpoint to enumerate and "
        "manage backup files for the operator UI.",
    )

    # Lifespan toggles (slice 187 — make-it-run factoring)
    bootstrap_enabled: bool = Field(
        default=False,
        description="When True, the FastAPI lifespan runs the "
        "spec 003 + spec 006 seeders (default profiles + "
        "built-in Platform Pack) plus spec 010's "
        "maybe_bootstrap_setup_token. All seeders are idempotent "
        "so re-runs are no-ops. Defaults to False so the test "
        "suite (which builds the app many times per session) "
        "doesn't pay the seeding cost. Production sets "
        "ROMARR_BOOTSTRAP_ENABLED=true.",
    )
    scheduler_enabled: bool = Field(
        default=False,
        description="When True, the FastAPI lifespan starts the "
        "spec 012 SchedulerService (APScheduler-backed). "
        "Defaults to False for the same test-suite reasons as "
        "bootstrap_enabled. Production sets "
        "ROMARR_SCHEDULER_ENABLED=true.",
    )
    auto_migrate: bool = Field(
        default=False,
        description="When True, the FastAPI lifespan runs "
        "``alembic upgrade head`` against the configured "
        "database before any other startup step. Convenient for "
        "containers that don't have a separate migrate-then-run "
        "phase; operators with a CI/CD migration step should "
        "leave this False and run migrations explicitly.",
    )
    heartbeat_enabled: bool = Field(
        default=False,
        description="Spec 009 T030. When True, the FastAPI "
        "lifespan starts the HeartbeatLoop background task that "
        "stat()s every library.path on its configured cadence "
        "(default 30 s) and persists transitions to "
        "library.status. Defaults to False so the test suite "
        "doesn't pay the loop bootstrap cost. Production sets "
        "ROMARR_HEARTBEAT_ENABLED=true.",
    )
    spa_enabled: bool = Field(
        default=False,
        description="Spec 014 T009. When True, the app serves "
        "the built React SPA from ``spa_dist_path`` at the "
        "root (``/`` returns ``index.html``, ``/assets/*`` "
        "returns the hashed bundle, anything not matching a "
        "router falls through to the SPA so React Router "
        "handles the route). Defaults to False so the test "
        "suite keeps the JSON ``GET /`` smoke-info response. "
        "Production sets ROMARR_SPA_ENABLED=true.",
    )
    spa_dist_path: str = Field(
        default="./web/dist",
        description="Filesystem path to the built SPA. "
        "Honoured only when ``spa_enabled`` is True. The "
        "directory must contain ``index.html`` plus the "
        "Vite-emitted ``assets/`` subdirectory.",
    )

    # CSRF protection (spec 013, FR-027)
    csrf_protect: bool = Field(
        default=False,
        description="Spec 013 FR-027. When True, mutating "
        "requests (POST / PUT / PATCH / DELETE) authenticated "
        "via cookie session MUST carry the X-CSRF-Token header "
        "matching the csrf_token cookie value (double-submit "
        "cookie pattern). API-key and Bearer-JWT callers always "
        "bypass — they aren't subject to CSRF. Defaults to "
        "False today; the spec 014 frontend wiring enables it "
        "via ROMARR_CSRF_PROTECT=true once the SPA reads the "
        "cookie + echoes the header on every mutation.",
    )

    # Rate limiting (spec 013, FR-022 / FR-023 / FR-024)
    rate_limit_enabled: bool = Field(
        default=False,
        description="Spec 013 FR-022. When True, per-IP and "
        "per-API-key rate limits apply. Defaults to False so "
        "the test suite (which fires repeated POSTs at "
        "/login / /setup) doesn't 429 on the 6th call. "
        "Production deployments should set "
        "ROMARR_RATE_LIMIT_ENABLED=true.",
    )
    rate_limit_login_per_minute: int = Field(
        default=5,
        ge=1,
        description="Spec 013 FR-022. Max attempts on "
        "/api/v3/auth/login per IP per 60-second window.",
    )
    rate_limit_setup_per_minute: int = Field(
        default=1,
        ge=1,
        description="Spec 013 FR-023. Max attempts on "
        "/api/v3/auth/setup per IP per 60-second window.",
    )
    rate_limit_default_per_minute: int = Field(
        default=100,
        ge=1,
        description="Spec 013 FR-024. Default per-key "
        "rate limit on every other endpoint per 60-second "
        "window. Keyed by API key id (or session user id) "
        "rather than IP — multiple operators behind a NAT "
        "shouldn't share a single budget.",
    )

    @model_validator(mode="after")
    def _derive_defaults(self) -> "Settings":
        """Dérive `database_url` de `data_dir` + s'assure que le
        dossier existe.

        Objectif : « ça marche out-of-the-box quel que soit `data_dir` ».
        Historiquement `database_url` avait un chemin relatif hardcodé
        (`./romarr.db`) — sur Docker où le cwd n'est pas monté, ça
        échouait avec `unable to open database file` alors même que
        `/data` était bien monté. Ici on garantit :

        - Si `database_url` vide  → SQLite auto-placée sous `data_dir`
        - Si `database_url` explicite (PostgreSQL, ou SQLite custom)
          → respect intégral, aucune modif
        - Le `data_dir` est créé si absent (idempotent) pour ne pas
          faire crasher SQLite au premier boot avec un dossier vide.
        """
        # `data_dir` peut être relatif à cwd (défaut `./data`) ou absolu.
        # Path().mkdir gère les 2 sans transformation.
        try:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        except OSError:
            # Best-effort : si les droits ne le permettent pas, on
            # laisse SQLite lever une erreur plus explicite au boot.
            pass

        if not self.database_url:
            # Chemin absolu résolu → évite `./romarr.db` qui dépend du
            # cwd du process (variable selon lanceur : uvicorn, tini,
            # systemd, cronjob, tests…).
            db_path = Path(self.data_dir).resolve() / "romarr.db"
            self.database_url = f"sqlite+aiosqlite:///{db_path}"
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance.

    Cached so settings are read once. Tests that need to override
    values should call ``get_settings.cache_clear()`` after mutating
    environment variables.
    """
    return Settings()
