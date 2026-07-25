#!/bin/sh
# Runtime entrypoint — pattern PUID/PGID à la LinuxServer.io.
#
# Pourquoi c'est là : les volumes montés sur Unraid (et autres NAS)
# appartiennent typiquement à `nobody:users` (99:100) ou à un UID
# maison choisi par l'opérateur. Un `USER romarr` figé au build
# (UID 1000) échoue à écrire dans le volume monté avec un autre
# owner → erreur `unable to open database file` classique.
#
# Solution : démarrer en root, aligner le UID/GID du user `romarr`
# sur les env `PUID`/`PGID`, chown le data dir, puis dégrader vers
# `romarr` pour le vrai process.
#
# Env :
#   PUID (défaut 1000) — UID cible pour le user romarr
#   PGID (défaut 1000) — GID cible pour le group romarr
#   ROMARR_DATA_DIR (défaut /data) — chown vers ces IDs
set -eu

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
DATA_DIR="${ROMARR_DATA_DIR:-/data}"

# UID/GID actuels du user romarr (créé au build en 1000:1000).
current_uid="$(id -u romarr)"
current_gid="$(id -g romarr)"

# Aligne group + user si divergence — silencieux si idempotent.
if [ "${PGID}" != "${current_gid}" ]; then
    groupmod -o -g "${PGID}" romarr
fi
if [ "${PUID}" != "${current_uid}" ]; then
    usermod -o -u "${PUID}" romarr
fi

# S'assure que le user romarr peut lire/écrire son data dir. Le
# chown -R est coûteux sur gros volumes mais nécessaire : sinon la
# première génération de covers ou un migrate SQLite plante avec
# EACCES. En prod, mkdir permet de démarrer sur un mount vide.
mkdir -p "${DATA_DIR}"
chown -R "${PUID}:${PGID}" "${DATA_DIR}" 2>/dev/null || {
    # Best-effort : sur certains bind mounts (NFS, CIFS) chown peut
    # échouer même en root. On continue quand même — SQLite ouvrira
    # avec les droits du mount ou lèvera une erreur explicite.
    echo "[entrypoint] warn: chown ${DATA_DIR} failed (mount options?)" >&2
}

# Dégrade vers romarr et exec la vraie commande. `exec` remplace le
# process shell → PID 1 = romarr, signaux (SIGTERM Docker) propagés
# proprement pour un shutdown gracieux.
exec gosu romarr "$@"
