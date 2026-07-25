"""Handlers backup — les 5 profiles utilisateur.

Chacun est mono-table, dedup par ``name``, aucun secret, tous les
champs sont safe. Pattern répété via `SimpleModelHandler`.
"""
from __future__ import annotations

from romarr.backup.handlers._shared import SimpleModelHandler
from romarr.backup.registry import register
from romarr.backup.schemas import ResourceKey
from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


class QualityProfileHandler(SimpleModelHandler):
    key = ResourceKey.QUALITY_PROFILES
    label = "Quality Profiles"
    model_class = QualityProfile
    FIELDS = [
        "name",
        "allowed_formats",
        "preferred_format",
        "require_dat_verified",
        "allow_archive_double_compression",
        "upgrade_until_format",
        "auto_grab_min_score",
        "seed_key",
        "is_user_modified",
        "is_factory_default",
    ]


class RegionProfileHandler(SimpleModelHandler):
    key = ResourceKey.REGION_PROFILES
    label = "Region Profiles"
    model_class = RegionProfile
    FIELDS = [
        "name",
        "priorities",
        "allow_fallback_outside_priorities",
        "exclude_regions",
        "seed_key",
        "is_user_modified",
        "is_factory_default",
    ]


class DumpProfileHandler(SimpleModelHandler):
    key = ResourceKey.DUMP_PROFILES
    label = "Dump Profiles"
    model_class = DumpProfile
    FIELDS = [
        "name",
        "allowed_dump_status",
        "allow_proto_beta",
        "allow_hacks",
        "allow_trainers",
        "allow_translations",
        "prefer_revision",
        "seed_key",
        "is_user_modified",
        "is_factory_default",
    ]


class LanguageProfileHandler(SimpleModelHandler):
    key = ResourceKey.LANGUAGE_PROFILES
    label = "Language Profiles"
    model_class = LanguageProfile
    FIELDS = [
        "name",
        "required_languages",
        "preferred_languages",
        "exclude_japanese_only",
        "seed_key",
        "is_user_modified",
        "is_factory_default",
    ]


class NamingProfileHandler(SimpleModelHandler):
    key = ResourceKey.NAMING_PROFILES
    label = "Naming Profiles"
    model_class = NamingProfile
    FIELDS = [
        "name",
        "convention",
        "template",
        "platform_subfolder",
        "replace_illegal_chars",
        "multi_disc_subfolder",
        "seed_key",
        "is_user_modified",
        "is_factory_default",
    ]


register(QualityProfileHandler())
register(RegionProfileHandler())
register(DumpProfileHandler())
register(LanguageProfileHandler())
register(NamingProfileHandler())
