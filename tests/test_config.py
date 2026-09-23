"""Tests for WorkshopConfig resolution — pure, off-platform.

Bring-your-own-catalog: `catalog` is required (the workshop never creates one).
"""

from __future__ import annotations

import pytest

from workshop import namespace, resolve_config
from workshop.config import DEFAULT_VOLUME, DOMAINS
from workshop.namespace import WORKSHOP_SCHEMA_PREFIX


def test_defaults_with_a_catalog():
    cfg = resolve_config(catalog="my_catalog")
    assert cfg.domain == "finance"
    assert cfg.catalog == "my_catalog"
    assert cfg.schema == "finance"  # schema defaults to the domain
    assert cfg.volume == DEFAULT_VOLUME


def test_schema_defaults_to_domain_for_each_domain():
    for domain in DOMAINS:
        assert resolve_config(catalog="c", domain=domain).schema == domain


def test_explicit_overrides_win():
    cfg = resolve_config(catalog="cat", domain="security", schema="sch", volume="vol")
    assert (cfg.domain, cfg.catalog, cfg.schema, cfg.volume) == (
        "security",
        "cat",
        "sch",
        "vol",
    )


def test_domain_is_case_and_space_insensitive():
    assert resolve_config(catalog="c", domain="  ITSM ").domain == "itsm"


def test_unknown_domain_raises():
    with pytest.raises(ValueError, match="Unknown domain"):
        resolve_config(catalog="c", domain="marketing")


def test_missing_catalog_raises():
    # Participants bring their own catalog; a blank value is a clear error.
    with pytest.raises(ValueError, match="catalog is required"):
        resolve_config(catalog=None)
    with pytest.raises(ValueError, match="catalog is required"):
        resolve_config(catalog="   ")


def test_blank_optional_strings_fall_back_to_defaults():
    # The notebook passes widget values through as "" -> None; resolve must not
    # produce empty schema/volume.
    cfg = resolve_config(catalog="c", domain="finance", schema=None, volume=None)
    assert cfg.schema and cfg.volume


def test_whitespace_only_schema_and_volume_fall_back_to_defaults():
    # A widget left as spaces ("   ") is truthy but must not collapse to an empty
    # identifier — it should use the default.
    cfg = resolve_config(catalog="c", domain="finance", schema="   ", volume="  ")
    assert cfg.schema == "finance"  # default = domain
    assert cfg.volume == DEFAULT_VOLUME


def test_suffix_is_appended_to_schema_and_sanitized():
    # The catalog is a shared, pre-existing resource, so isolation suffixes the
    # schema, not the catalog.
    cfg = resolve_config(catalog="my_catalog", schema="finance", suffix="Val-9F/2")
    assert cfg.catalog == "my_catalog"
    assert cfg.schema == "finance_val_9f_2"
    assert cfg.volume == "landing"


def test_identity_derives_namespaced_schema_when_no_explicit_schema():
    # The whole team shares one catalog, so with an identity and no explicit
    # schema, resolve_config derives the per-participant workshop_<...> schema.
    cfg = resolve_config(catalog="team_cat", domain="finance", identity="ada@a.com")
    assert cfg.schema.startswith(WORKSHOP_SCHEMA_PREFIX)
    assert cfg.schema == namespace("ada@a.com", domain="finance").schema


def test_two_identities_resolve_to_distinct_schemas_same_catalog():
    # The two-participant no-collision criterion at the config level.
    a = resolve_config(catalog="team_cat", domain="finance", identity="ada@a.com")
    b = resolve_config(catalog="team_cat", domain="finance", identity="grace@b.com")
    assert a.catalog == b.catalog
    assert a.schema != b.schema


def test_explicit_schema_overrides_identity():
    cfg = resolve_config(
        catalog="team_cat", domain="finance", schema="chosen", identity="ada@a.com"
    )
    assert cfg.schema == "chosen"


def test_no_identity_keeps_domain_default():
    # Off-platform callers (and the pre-namespacing default) resolve the domain.
    assert resolve_config(catalog="c", domain="security").schema == "security"


def test_identity_schema_still_accepts_isolation_suffix():
    cfg = resolve_config(
        catalog="c", domain="finance", identity="ada@a.com", suffix="run9"
    )
    assert cfg.schema == namespace("ada@a.com", domain="finance").schema + "_run9"


def test_quoted_helpers_and_volume_path():
    cfg = resolve_config(catalog="c", domain="finance", schema="s", volume="v")
    assert cfg.quoted_catalog() == "`c`"
    assert cfg.quoted_schema() == "`c`.`s`"
    assert cfg.quoted_volume() == "`c`.`s`.`v`"
    assert cfg.volume_path == "/Volumes/c/s/v"
