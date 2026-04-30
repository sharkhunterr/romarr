"""Built-in platform packs shipped with the Romarr wheel.

Each pack is a YAML file at ``builtin-<pack_version>.yaml``. The
runtime path resolver in :mod:`romarr.platform_packs.builtin` reads
the active pack via :mod:`importlib.resources`.
"""
