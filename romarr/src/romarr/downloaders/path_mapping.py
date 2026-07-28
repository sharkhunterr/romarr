"""Radarr-style remote → local path remapping.

Some deployments run the download client on a different mount view
than Romarr. Typical example: qBit runs inside Docker with
``/downloads`` bind-mounted from ``/mnt/qbit/downloads`` on the
host, and Romarr runs natively on the host. qBit reports
``content_path=/downloads/foo.zip`` — a path that doesn't exist
on the host side.

This module exposes a single pure helper the reconciler + importer
use to rewrite the prefix. Both mapping fields NULL = passthrough.
"""

from __future__ import annotations


def remap_path(
    path: str | None,
    *,
    remote_path: str | None,
    local_path: str | None,
) -> str | None:
    """Rewrite ``path`` from the client's view to Romarr's view.

    Rules:

    * ``path`` None / empty → return as-is (nothing to remap).
    * Either mapping field None / empty → passthrough (no config).
    * ``path`` starts with ``remote_path`` → replace that prefix
      with ``local_path``. The remaining suffix keeps its
      leading separator so ``/downloads/foo`` with
      ``remote=/downloads local=/mnt/qbit`` becomes
      ``/mnt/qbit/foo``.
    * Otherwise → return ``path`` unchanged (the config doesn't
      cover this path — surface the original so downstream error
      messages point at the real problem).

    Deliberately does no filesystem I/O. Callers are free to
    ``os.path.exists`` on the result.
    """
    if not path:
        return path
    if not remote_path or not local_path:
        return path
    remote = remote_path.rstrip("/") or "/"
    local = local_path.rstrip("/") or ""
    # Exact match: ``/downloads`` with remote ``/downloads`` → local.
    if path == remote:
        return local or "/"
    # Prefix match: keep the separator so we don't glue tokens together.
    prefix = remote + "/"
    if path.startswith(prefix):
        return f"{local}/{path[len(prefix):]}" if local else "/" + path[len(prefix):]
    return path


__all__ = ["remap_path"]
