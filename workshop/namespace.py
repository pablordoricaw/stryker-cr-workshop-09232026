"""Per-participant namespacing — one identity-derived namespace, used everywhere.

A whole workshop team shares **one** Unity Catalog catalog and **one** workspace,
so every object a participant creates in a shared space must be uniquely named,
and every check must validate the **caller's own** object rather than a fixed,
shared name. This module is the single source of truth for those names: given a
participant's identity (their ``current_user()``), it derives a stable,
collision-resistant, SQL-safe **schema** name plus the identity **suffix** that
workspace-scoped objects — the Genie agent, the Databricks App, the Lakebase
project, the synced table — carry.

Deriving the names here, rather than ad hoc in each notebook, is what makes
*generation* (the notebook that creates the object) and *verification* (the
``workshop.check`` that asserts it) agree by construction: both call the same
helper with the same identity and get byte-identical names.

**Derivation rule** (deterministic and documented):

1. The **readable slug** is the local part of the identity (before ``@``),
   lowercased, with every run of characters outside ``[a-z0-9]`` collapsed to a
   single separator and leading/trailing separators stripped. ``_`` is the
   separator for SQL identifiers (schema, tables, the Genie title); ``-`` for
   RFC 1123 / DNS names (the Databricks App, the Lakebase project).
2. A **digest** — the first 8 hex characters of ``sha256`` of the *full* raw
   identity — is appended (``<slug>_<digest>``). The digest is what makes the
   suffix collision-resistant: two distinct identities that sanitize to the same
   slug (``ada@a.com`` vs ``ada@b.com``) still get different suffixes. It is
   stable (same identity → same digest, always) and, being pure hex, is
   identical in the ``_`` and ``-`` forms.
3. For length-limited names (a Databricks App is ≤ 30 chars, a Lakebase project
   ≤ 63) the readable slug is truncated to fit, but the digest is always kept,
   so uniqueness survives truncation.

The schema is ``workshop_<suffix>``; the common ``workshop_`` prefix means every
participant's schema sorts together in Catalog Explorer and none collides with a
teammate's.

Everything here is pure Python — no Spark, no SDK, no network — so it is unit
testable off-platform and safe to import from the connection-free framework.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

#: The common prefix every participant schema carries, so they sort together in
#: Catalog Explorer and share an obvious, greppable family name.
WORKSHOP_SCHEMA_PREFIX = "workshop_"

#: Hex characters of the identity digest appended for collision-resistance. Eight
#: hex chars (32 bits) is far more than enough to separate a workshop team while
#: staying short enough for the length-limited App / Lakebase names.
_DIGEST_LEN = 8

#: The default serving-table base for the synced-table name — the Finance gold
#: serving mart. It is only a *default*: a domain reusing the helper passes its
#: own base (``synced_table_name(base=...)`` / ``synced_table_fqn(base=...)``),
#: and the ``07_app`` checkpoint forwards a ``serving_base`` extra to it, so the
#: name is never Finance-hardcoded for Security (#13) / ITSM (#14).
DEFAULT_SERVING_BASE = "gold_contract_performance_served"

#: Any maximal run of characters outside this set becomes a single separator.
_NON_IDENTIFIER = re.compile(r"[^a-z0-9]+")


def _slug(text: str, separator: str) -> str:
    """Lowercase ``text`` and collapse non-``[a-z0-9]`` runs to ``separator``.

    Leading/trailing separators are stripped. ``"Ada.Lovelace"`` with ``_`` ->
    ``"ada_lovelace"``; with ``-`` -> ``"ada-lovelace"``. An all-symbol input
    (e.g. ``"@@"``) yields ``""``.
    """
    return _NON_IDENTIFIER.sub(separator, text.lower()).strip(separator)


def _digest(identity: str) -> str:
    """First :data:`_DIGEST_LEN` hex chars of ``sha256(identity)``.

    Computed over the *full* raw identity (including the domain) so two accounts
    with the same local part but different domains never collide.
    """
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:_DIGEST_LEN]


@dataclass(frozen=True)
class Namespace:
    """One participant's resolved namespace, derived from their identity.

    Build one with :func:`namespace` (or :meth:`from_identity`); never construct
    it field-by-field, so the derivation rule stays in one place.

    Attributes:
        identity: The raw identity the names were derived from (e.g.
            ``current_user()`` — ``ada@stryker.com``). Used verbatim as the app
            owner and workspace ``owner_path``.
        domain: The workshop domain (``finance`` / ``security`` / ``itsm``); a
            component of the *workspace-scoped* object names (Genie agent,
            Databricks App, Lakebase project) so those stay distinct across
            domains. The namespace isolates **participants** — each participant
            runs a single domain per the workshop design. The :attr:`schema` is
            deliberately NOT domain-scoped, so a same-identity run of two domains
            would still collide on shared table names (``bronze_docs`` /
            ``silver_docs`` / gold); that is out of scope for #22. The maintainer
            CI (#17) that runs all three domains needs its own per-domain
            isolation, tracked there.
        digest: The collision-resistant hex tail (see module docstring).
        slug_sql: The readable slug in ``_`` form (may be empty).
        slug_dns: The readable slug in ``-`` form (may be empty).
    """

    identity: str
    domain: str
    digest: str
    slug_sql: str
    slug_dns: str

    @classmethod
    def from_identity(cls, identity: str, *, domain: str) -> Namespace:
        """Derive a namespace from a raw identity and domain.

        Raises:
            ValueError: If ``identity`` or ``domain`` is blank.
        """
        if not identity or not identity.strip():
            raise ValueError(
                "identity is required to derive a namespace; pass your "
                "current_user() (e.g. spark.sql('SELECT current_user()')"
                ".collect()[0][0])."
            )
        if not domain or not domain.strip():
            raise ValueError("domain is required to derive a namespace.")
        cleaned = identity.strip()
        return cls(
            identity=cleaned,
            domain=domain.strip().lower(),
            digest=_digest(cleaned),
            slug_sql=_slug(cleaned.split("@", 1)[0], "_"),
            slug_dns=_slug(cleaned.split("@", 1)[0], "-"),
        )

    # --- per-participant tokens ---------------------------------------------

    @property
    def suffix(self) -> str:
        """SQL-safe per-participant token: ``<slug>_<digest>`` (or just digest)."""
        return f"{self.slug_sql}_{self.digest}" if self.slug_sql else self.digest

    @property
    def dns_suffix(self) -> str:
        """RFC 1123 per-participant token: ``<slug>-<digest>`` (or just digest)."""
        return f"{self.slug_dns}-{self.digest}" if self.slug_dns else self.digest

    # --- resolved object names ----------------------------------------------

    @property
    def schema(self) -> str:
        """The participant's schema: ``workshop_<suffix>``.

        Identity-derived and unique, with the common ``workshop_`` prefix so all
        workshop schemas sort together. This is the one schema the participant
        provisions and every downstream notebook and check resolves.
        """
        return f"{WORKSHOP_SCHEMA_PREFIX}{self.suffix}"

    @property
    def owner(self) -> str:
        """The caller's identity, used to bind app / synced-table ownership."""
        return self.identity

    def owner_path(self, root: str = "/Workspace/Users") -> str:
        """The caller's workspace namespace, e.g. ``/Workspace/Users/<me>``.

        This is what binds a workspace-scoped object (a Genie agent) to the
        caller so a teammate's same-titled object is never adopted.
        """
        return f"{root.rstrip('/')}/{self.identity}"

    def genie_agent_name(self, *, prefix: str = "workshop_genie") -> str:
        """Per-participant Genie agent title: ``<prefix>_<domain>_<suffix>``."""
        return f"{prefix}_{self.domain}_{self.suffix}"

    def synced_table_name(self, *, base: str = DEFAULT_SERVING_BASE) -> str:
        """Per-participant synced-table object name: ``<base>_<suffix>``.

        ``base`` defaults to :data:`DEFAULT_SERVING_BASE` (Finance); a domain
        reusing this passes its own serving-table base so the name stays
        domain-appropriate.
        """
        return f"{base}_{self.suffix}"

    def synced_table_fqn(
        self,
        catalog: str,
        schema: str,
        *,
        base: str = DEFAULT_SERVING_BASE,
    ) -> str:
        """The synced table's fully-qualified UC name in the caller's catalog/schema.

        The synced-table id doubles as a UC entity ``<catalog>.<schema>.<table>``
        and a Postgres table in the participant's *existing* catalog — no catalog
        is ever created.
        """
        return f"{catalog}.{schema}.{self.synced_table_name(base=base)}"

    def app_name(self, *, prefix: str = "stryker", maxlen: int = 30) -> str:
        """Per-participant Databricks App name (``[a-z0-9-]``, ``maxlen`` cap).

        ``<prefix>-<domain>-<dns-slug>-<digest>`` truncated to ``maxlen`` with
        the digest always retained, so uniqueness survives the length limit.
        """
        return self._dns_name((prefix, self.domain), maxlen)

    def lakebase_project(self, *, prefix: str = "lb", maxlen: int = 63) -> str:
        """Per-participant Lakebase project id (RFC 1123, ``maxlen`` cap)."""
        return self._dns_name((prefix, self.domain), maxlen)

    def _dns_name(self, lead_parts: tuple[str, ...], maxlen: int) -> str:
        """Assemble ``<lead>-<slug>-<digest>`` within ``maxlen``, keeping the digest.

        The readable slug is trimmed to whatever room is left after the fixed
        lead and digest; if none is left the name is ``<lead>-<digest>``.
        """
        lead = "-".join(part for part in lead_parts if part)
        room = maxlen - len(lead) - len(self.digest) - 2  # two "-" separators
        slug = self.slug_dns[:room].strip("-") if room > 0 else ""
        body = f"{lead}-{slug}-{self.digest}" if slug else f"{lead}-{self.digest}"
        return body[:maxlen].rstrip("-")


def namespace(identity: str, *, domain: str) -> Namespace:
    """Derive the per-participant :class:`Namespace` for ``identity`` + ``domain``.

    The one entry point notebooks and checks use::

        me = spark.sql("SELECT current_user()").collect()[0][0]
        ns = workshop.namespace(me, domain=config.domain)
        config = workshop.resolve_config(catalog=..., domain=..., identity=me)
        # ns.schema == config.schema; ns.genie_agent_name(), ns.app_name(), ...

    Raises:
        ValueError: If ``identity`` or ``domain`` is blank.
    """
    return Namespace.from_identity(identity, domain=domain)


def sanitize_identity(identity: str) -> str:
    """The SQL-safe, collision-resistant per-participant suffix for ``identity``.

    This is the ``<slug>_<digest>`` token the schema and SQL object names are
    built from — ``namespace(identity, domain=...).suffix`` without needing a
    domain (the suffix does not depend on it). The schema is
    ``WORKSHOP_SCHEMA_PREFIX + sanitize_identity(identity)``.

    Raises:
        ValueError: If ``identity`` is blank.
    """
    # Domain is irrelevant to the suffix; pass a valid placeholder to reuse the
    # single derivation path (and its identity validation).
    return Namespace.from_identity(identity, domain="finance").suffix
