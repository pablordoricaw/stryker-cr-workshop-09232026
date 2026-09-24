"""Pure, off-platform tests for per-participant namespacing.

A whole team shares one catalog and one workspace, so the two properties that
matter most are proven directly here at the unit level:

* **collision-resistance** means two distinct identities derive distinct schema and
  suffixes (the acceptance criterion that two participants never collide); and
* **stability** means the same identity always derives the same names, so a
  notebook's generated object and a later ``workshop.check`` resolve identical
  names.
"""

from __future__ import annotations

import re

import pytest

import workshop
from workshop.namespace import (
    DEFAULT_SERVING_BASE,
    WORKSHOP_SCHEMA_PREFIX,
    Namespace,
    namespace,
    sanitize_identity,
)

# A spread of realistic and adversarial identities. Pairs that sanitize to the
# same readable slug (dot vs underscore, differing domains) are deliberately
# included to exercise the collision-resistant digest.
IDENTITIES = [
    "ada@example.com",
    "ada.lovelace@stryker.com",
    "Ada.Lovelace@Stryker.COM",  # uppercase
    "grace_hopper@navy.mil",
    "a.b@x.com",
    "a_b@x.com",  # collides with "a.b@x.com" on the slug alone
    "ada@a.com",
    "ada@b.com",  # same local part, different domain
    "x!#$%@weird.io",  # symbol-heavy local part
    "  spaced@name.com  ",  # surrounding whitespace
]

_SQL_IDENTIFIER = re.compile(r"^[a-z0-9_]+$")
_DNS_NAME = re.compile(r"^[a-z0-9-]+$")


# --- derivation shape -------------------------------------------------------


def test_schema_has_common_prefix_and_is_sql_safe():
    ns = namespace("Ada.Lovelace@stryker.com", domain="finance")
    assert ns.schema.startswith(WORKSHOP_SCHEMA_PREFIX)
    assert _SQL_IDENTIFIER.match(ns.schema)
    # Readable slug preserved (lowercased, dots -> underscores) plus a digest.
    assert ns.schema.startswith("workshop_ada_lovelace_")


def test_suffix_and_dns_suffix_forms():
    ns = namespace("Ada.Lovelace@stryker.com", domain="finance")
    assert _SQL_IDENTIFIER.match(ns.suffix)
    assert _DNS_NAME.match(ns.dns_suffix)
    # Same identity, same digest tail in both forms.
    assert ns.suffix.replace("_", "-") == ns.dns_suffix


def test_symbol_only_local_part_falls_back_to_digest():
    ns = namespace("@@@@@@@@x.io", domain="finance")  # empty slug
    assert ns.schema == f"{WORKSHOP_SCHEMA_PREFIX}{ns.digest}"
    assert _SQL_IDENTIFIER.match(ns.schema)


def test_whitespace_is_trimmed_from_identity():
    padded = namespace("  ada@a.com  ", domain="finance")
    tight = namespace("ada@a.com", domain="finance")
    assert padded.schema == tight.schema
    assert padded.owner == "ada@a.com"  # owner is the trimmed raw identity


# --- collision-resistance (two participants never collide) ------------------


@pytest.mark.parametrize("domain", list(workshop.DOMAINS))
def test_distinct_identities_get_distinct_names(domain):
    schemas: set[str] = set()
    suffixes: set[str] = set()
    dns_suffixes: set[str] = set()
    for identity in IDENTITIES:
        ns = namespace(identity, domain=domain)
        schemas.add(ns.schema)
        suffixes.add(ns.suffix)
        dns_suffixes.add(ns.dns_suffix)
    # Every distinct identity maps to a distinct schema, SQL suffix, and DNS
    # suffix, so no two participants collide.
    unique = {i.strip() for i in IDENTITIES}
    assert len(schemas) == len(unique)
    assert len(suffixes) == len(unique)
    assert len(dns_suffixes) == len(unique)


def test_same_slug_different_domain_still_distinct():
    # The classic shared-catalog trap: two people whose emails share a local
    # part. The full-identity digest keeps them apart.
    a = namespace("ada@a.com", domain="finance")
    b = namespace("ada@b.com", domain="finance")
    assert a.schema != b.schema
    assert a.suffix != b.suffix
    assert a.app_name() != b.app_name()


def test_dot_vs_underscore_local_part_distinct():
    a = namespace("a.b@x.com", domain="finance")
    b = namespace("a_b@x.com", domain="finance")
    assert a.schema != b.schema  # same readable slug, different digest


# --- stability (generation and verification agree) --------------------------


@pytest.mark.parametrize("identity", IDENTITIES)
def test_derivation_is_stable(identity):
    first = namespace(identity, domain="finance")
    second = namespace(identity, domain="finance")
    assert first == second
    assert first.schema == second.schema
    assert first.genie_agent_name() == second.genie_agent_name()
    assert first.app_name() == second.app_name()


def test_schema_matches_sanitize_identity_helper():
    identity = "ada.lovelace@stryker.com"
    assert (
        namespace(identity, domain="finance").schema
        == WORKSHOP_SCHEMA_PREFIX + sanitize_identity(identity)
    )
    # The suffix does not depend on the domain.
    assert (
        namespace(identity, domain="security").suffix
        == namespace(identity, domain="finance").suffix
    )


# --- object names -----------------------------------------------------------


def test_genie_agent_name_includes_domain_and_suffix():
    ns = namespace("ada@a.com", domain="security")
    name = ns.genie_agent_name()
    assert name == f"workshop_genie_security_{ns.suffix}"
    assert _SQL_IDENTIFIER.match(name)


def test_synced_table_fqn_lives_in_callers_catalog_and_schema():
    ns = namespace("ada@a.com", domain="finance")
    fqn = ns.synced_table_fqn("team_cat", ns.schema)
    assert fqn == f"team_cat.{ns.schema}.{DEFAULT_SERVING_BASE}_{ns.suffix}"
    # The default is the named Finance base, not a hardcoded literal.
    assert DEFAULT_SERVING_BASE == "gold_contract_performance_served"
    assert ns.synced_table_name() == f"{DEFAULT_SERVING_BASE}_{ns.suffix}"
    # Domain reuse: an overridable base keeps it domain-appropriate.
    other = ns.synced_table_fqn("team_cat", ns.schema, base="gold_incidents_served")
    assert other.endswith(f"gold_incidents_served_{ns.suffix}")


def test_owner_and_owner_path():
    ns = namespace("ada@stryker.com", domain="finance")
    assert ns.owner == "ada@stryker.com"
    assert ns.owner_path() == "/Workspace/Users/ada@stryker.com"
    assert ns.owner_path(root="/Workspace/Shared") == "/Workspace/Shared/ada@stryker.com"


# --- length limits ----------------------------------------------------------


@pytest.mark.parametrize("identity", IDENTITIES + [
    "alexandra.bartholomew-worthington@verylongcorporatedomain.example.com",
])
def test_app_name_within_thirty_chars_and_keeps_digest(identity):
    ns = namespace(identity, domain="security")  # a longer domain word
    app = ns.app_name()
    assert len(app) <= 30
    assert _DNS_NAME.match(app)
    assert app.endswith(ns.digest)  # digest survives truncation


@pytest.mark.parametrize("identity", IDENTITIES + [
    "alexandra.bartholomew-worthington@verylongcorporatedomain.example.com",
])
def test_lakebase_project_within_sixtythree_chars_and_keeps_digest(identity):
    ns = namespace(identity, domain="security")
    project = ns.lakebase_project()
    assert len(project) <= 63
    assert _DNS_NAME.match(project)
    assert project.endswith(ns.digest)


def test_length_limited_names_stay_collision_resistant_after_truncation():
    # Two long identities that share a long readable prefix must still yield
    # distinct App names, because the always-retained digest differs.
    a = namespace("jonathan.livingston.seagull@aviary.example.com", domain="finance")
    b = namespace("jonathan.livingston.sparrow@aviary.example.com", domain="finance")
    assert a.app_name() != b.app_name()
    assert len(a.app_name()) <= 30 and len(b.app_name()) <= 30


# --- validation -------------------------------------------------------------


def test_blank_identity_raises():
    for bad in ("", "   ", None):
        with pytest.raises(ValueError, match="identity is required"):
            namespace(bad, domain="finance")  # type: ignore[arg-type]


def test_blank_domain_raises():
    with pytest.raises(ValueError, match="domain is required"):
        namespace("ada@a.com", domain="  ")


def test_from_identity_matches_factory():
    assert namespace("ada@a.com", domain="finance") == Namespace.from_identity(
        "ada@a.com", domain="finance"
    )


def test_exported_from_package():
    assert workshop.namespace is namespace
    assert workshop.Namespace is Namespace
    assert workshop.sanitize_identity is sanitize_identity
    assert workshop.WORKSHOP_SCHEMA_PREFIX == WORKSHOP_SCHEMA_PREFIX
