"""``WorkshopConfig`` — the one place that names a participant's environment.

The workshop is one shared curriculum across three domains (Finance, Security,
ITSM); only the dataset and pre-authored semantic content differ. Three things
need to agree on *where* a participant's data lives — the setup notebook that
creates the schema/volume, the seed hooks that populate them, and the
``00_setup`` checkpoint that asserts they exist — so the names are resolved once,
here, and passed around as a :class:`WorkshopConfig`.

Later notebooks (medallion, metric views, Genie, the app) read the same config,
which is why this lives in the framework rather than inside the setup notebook.

**Bring-your-own-catalog.** Participants do *not* have permission to create
catalogs; each team already has its own Unity Catalog catalog. So ``catalog`` is
a required input (the participant's existing catalog), and the workshop creates
only the schema and UC Volume inside it. There is deliberately no default catalog
name.

Everything is pure Python: no Spark, no network, no Databricks import. That keeps
it unit-testable off-platform and safe to import from the connection-free parts
of the framework.
"""

from __future__ import annotations

from dataclasses import dataclass

from .identifiers import fully_qualified, quote_identifier

#: The domains the workshop ships. A participant picks one in the setup notebook.
DOMAINS: tuple[str, ...] = ("finance", "security", "itsm")

#: Clean, participant-facing defaults. There is no default catalog — participants
#: bring their own — but the schema defaults to the domain and the volume to a
#: standard landing name.
DEFAULT_DOMAIN = "finance"
DEFAULT_VOLUME = "landing"


def _sanitize_suffix(suffix: str) -> str:
    """Reduce a free-form suffix to safe identifier characters.

    Used only for throwaway/validation namespaces (maintainers pass a run token
    to isolate a live provisioning test). Lowercased; anything that is not a
    letter, digit, or underscore becomes an underscore.
    """
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in suffix)
    return cleaned.strip("_").lower()


@dataclass(frozen=True)
class WorkshopConfig:
    """Resolved names for one participant's workshop environment.

    Attributes:
        domain: One of :data:`DOMAINS`.
        catalog: The participant's *existing* Unity Catalog catalog (not created).
        schema: Schema created within ``catalog``.
        volume: UC Volume created within ``catalog.schema`` where documents land.
    """

    domain: str
    catalog: str
    schema: str
    volume: str

    @property
    def volume_path(self) -> str:
        """The ``/Volumes/...`` filesystem path participants write files to."""
        return f"/Volumes/{self.catalog}/{self.schema}/{self.volume}"

    def quoted_catalog(self) -> str:
        """Backtick-quoted ``catalog`` (safe for ``... IN <catalog>``)."""
        return quote_identifier(self.catalog)

    def quoted_schema(self) -> str:
        """Backtick-quoted ``catalog.schema``."""
        return fully_qualified(self.catalog, self.schema)

    def quoted_volume(self) -> str:
        """Backtick-quoted ``catalog.schema.volume``."""
        return fully_qualified(self.catalog, self.schema, self.volume)


def resolve_config(
    *,
    catalog: str | None,
    domain: str | None = None,
    schema: str | None = None,
    volume: str | None = None,
    suffix: str | None = None,
) -> WorkshopConfig:
    """Resolve a :class:`WorkshopConfig`, applying defaults for anything omitted.

    Args:
        catalog: The participant's **existing** catalog name (required). The
            workshop never creates a catalog; a blank/omitted value is an error.
        domain: ``finance`` (default), ``security``, or ``itsm``. Case- and
            whitespace-insensitive.
        schema: Schema name; defaults to the resolved ``domain`` so one catalog
            can hold all three domains side by side.
        volume: Volume name; defaults to :data:`DEFAULT_VOLUME`.
        suffix: Optional token appended to the *schema* name (``<schema>_<suffix>``).
            For maintainer/validation isolation only — participants never set it.
            It suffixes the schema (not the catalog) because the catalog is a
            pre-existing shared resource.

    Raises:
        ValueError: If ``catalog`` is blank, or ``domain`` is not in :data:`DOMAINS`.
    """
    resolved_domain = (domain or DEFAULT_DOMAIN).strip().lower()
    if resolved_domain not in DOMAINS:
        raise ValueError(
            f"Unknown domain {resolved_domain!r}. Choose one of: "
            f"{', '.join(DOMAINS)}."
        )

    if not catalog or not catalog.strip():
        raise ValueError(
            "A catalog is required. Enter your team's existing Unity Catalog "
            "catalog name — the workshop creates a schema and UC Volume inside "
            "it, and does not create the catalog itself."
        )
    resolved_catalog = catalog.strip()
    # Strip *before* the fallback so a whitespace-only widget value ("   ") uses
    # the default instead of collapsing to an empty identifier.
    resolved_schema = schema.strip() if schema and schema.strip() else resolved_domain
    resolved_volume = volume.strip() if volume and volume.strip() else DEFAULT_VOLUME

    if suffix:
        token = _sanitize_suffix(suffix)
        if token:
            resolved_schema = f"{resolved_schema}_{token}"

    # Defaults are non-empty, so this is a safety net (e.g. a future default or
    # suffix change) rather than a reachable path today.
    if not resolved_schema or not resolved_volume:
        raise ValueError(
            "Resolved schema and volume names must be non-empty; got "
            f"schema={resolved_schema!r}, volume={resolved_volume!r}."
        )

    return WorkshopConfig(
        domain=resolved_domain,
        catalog=resolved_catalog,
        schema=resolved_schema,
        volume=resolved_volume,
    )
