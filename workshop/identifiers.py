"""Backtick-safe Unity Catalog / Spark SQL identifier quoting.

Catalog, schema, volume, and table names in Unity Catalog may legally contain
hyphens, spaces, and even reserved words. Interpolating such a name straight
into a SQL string produces either a parse error or, worse, a silently wrong
reference. Every place in the workshop that builds SQL from a name (the
provisioning helpers, the config's fully-qualified names, the checkpoints)
routes through here so the escaping rule lives in exactly one spot.

``CheckContext.fully_qualified`` (shipped by the framework foundation) uses the
same doubling rule; ``tests/test_identifiers.py`` pins the two to identical
output so they can never drift.
"""

from __future__ import annotations


def quote_identifier(identifier: str) -> str:
    """Backtick-quote one SQL identifier, escaping embedded backticks by doubling.

    ``stryker-finance`` -> ``` `stryker-finance` ```; ``a`b`` -> ``` `a``b` ```.
    """
    return "`" + identifier.replace("`", "``") + "`"


def fully_qualified(*parts: str) -> str:
    """Join and backtick-quote each part into a dotted identifier.

    ``fully_qualified("main", "finance", "landing")`` ->
    ``` `main`.`finance`.`landing` ```. Every part is quoted independently.
    """
    if not parts:
        raise ValueError("fully_qualified needs at least one identifier part")
    return ".".join(quote_identifier(part) for part in parts)
