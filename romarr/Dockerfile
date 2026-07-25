# Romarr — single multi-stage image bundling the React SPA + the
# FastAPI backend (per the constitution: one Docker image, frontend
# bundled, multi-arch amd64 + arm64). Runs unprivileged with mappable
# PUID/PGID following the LinuxServer.io convention.
#
# Build:    docker build -t romarr .
# Run:      docker run -p 8585:8585 -v /srv/romarr/data:/data romarr
#
# Environment knobs (full list in romarr.config.settings):
#   ROMARR_AUTH_SECRET_KEY  required — Fernet master key (32+ chars)
#   ROMARR_DATA_DIR         data root (default /data inside the image)
#   ROMARR_BOOTSTRAP_ENABLED  true → seed defaults + Platform Pack +
#                              setup token at startup
#   ROMARR_AUTO_MIGRATE     true → run alembic upgrade head pre-boot
#   ROMARR_SPA_ENABLED      true → serve the React SPA at /
#   PUID / PGID             host-mapped uid/gid (default 1000)

# ---------------------------------------------------------------------------
# Stage 1 — frontend build (Vite -> /web/dist)
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /src/web

# Install pnpm via corepack so the lockfile stays authoritative.
RUN corepack enable

COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm build


# ---------------------------------------------------------------------------
# Stage 2 — runtime image (Python + the bundled SPA)
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Tini is a tiny init that reaps zombies and forwards SIGTERM
# correctly — important for graceful shutdown of the scheduler
# subsystem.
#
# ``unar`` is The Unarchiver, a free RAR1/2/3/5 extractor.
# Romarr's importer uses ``rarfile`` which auto-discovers
# ``unrar`` / ``unar`` / ``bsdtar`` in that order — without
# this binary every ``.rar`` torrent qBit hands us hits
# ``extract:bad-archive`` (slice 382).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       tini ca-certificates unar gosu \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user. PUID/PGID get applied at runtime via
# the entrypoint when set; otherwise we run as the build-time IDs.
ARG PUID=1000
ARG PGID=1000
RUN groupadd --gid ${PGID} romarr \
    && useradd --uid ${PUID} --gid romarr --shell /bin/bash --create-home romarr

WORKDIR /app

# Python dependency install. We copy pyproject + uv.lock first
# so changes to source code don't bust the dep-install cache.
COPY pyproject.toml ./
COPY uv.lock ./

# Install dependencies via pip directly so we don't pull uv into
# the runtime image. The lockfile pins exact versions; pip
# compiles wheels from the project sdist below.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir hatchling

# Project source — backend.
COPY src/ ./src/
COPY alembic.ini ./
COPY README.md ./
# Built-in platform-pack YAMLs — hatchling's force-include maps this
# folder into the wheel at romarr/builtin_packs/ (see pyproject.toml).
COPY examples/ ./examples/

# Install Romarr itself (resolves runtime deps from pyproject.toml).
RUN pip install --no-cache-dir .

# Bundled SPA from the build stage.
COPY --from=frontend-build /src/web/dist ./web/dist

# Default data directory. Mount a volume here for persistence.
# On chown à l'UID build par défaut ; l'entrypoint runtime réalignera
# selon PUID/PGID de l'opérateur (pattern LSIO).
RUN mkdir -p /data \
    && chown -R romarr:romarr /data /app

# Entrypoint qui applique PUID/PGID au runtime avant de dégrader
# vers `romarr` — permet à Unraid/Synology/autres NAS de contrôler
# l'ownership sans rebuild de l'image.
COPY --chmod=755 scripts/entrypoint.sh /entrypoint.sh

# On ne fige PAS `USER romarr` ici : le container démarre en root
# pour que l'entrypoint puisse faire usermod + chown, puis exec en
# romarr via `gosu` (voir scripts/entrypoint.sh).

# Bootstrap + migrate + SPA enabled by default in the image so
# `docker run romarr` produces a working install. Operators
# can flip these to false if they want explicit control.
#
# `ROMARR_DATABASE_URL` n'est PAS défini ici : Settings._derive_defaults
# construit automatiquement `sqlite+aiosqlite:///{ROMARR_DATA_DIR}/romarr.db`
# quand la variable est absente. Un opérateur qui veut PostgreSQL n'a
# qu'à set ROMARR_DATABASE_URL explicitement — pas besoin de connaître
# la mécanique interne des chemins SQLite.
ENV ROMARR_DATA_DIR=/data \
    ROMARR_BOOTSTRAP_ENABLED=true \
    ROMARR_AUTO_MIGRATE=true \
    ROMARR_SCHEDULER_ENABLED=true \
    ROMARR_SPA_ENABLED=true \
    ROMARR_SPA_DIST_PATH=/app/web/dist \
    PUID=1000 \
    PGID=1000

EXPOSE 8585
VOLUME ["/data"]

# tini → entrypoint (PUID/PGID + chown + gosu) → romarr
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh", "romarr"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8585"]
