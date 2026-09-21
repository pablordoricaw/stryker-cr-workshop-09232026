"""A no-op seed hook, so the seed mechanism is live from this ticket on.

It registers for *every* domain and does nothing but report that there is no
data to load yet. This keeps the setup notebook's "run seed hooks" step honest
(it produces real, green output today) and gives later data tickets a working
example to copy. Later tickets add domain-specific hooks alongside it; this one
can stay (harmless) or be removed once real seeds exist.
"""

from __future__ import annotations

from workshop.seeds import SeedContext, SeedResult, seed_hook

PLACEHOLDER_SEED_NAME = "placeholder"


@seed_hook(
    PLACEHOLDER_SEED_NAME,
    summary="No-op placeholder; later data tickets register real domain seeds.",
)
def seed_placeholder(ctx: SeedContext) -> SeedResult:
    """Do nothing but confirm the seed-hook mechanism ran for this domain."""
    return SeedResult(
        seed=PLACEHOLDER_SEED_NAME,
        ok=True,
        message=(
            f"No seed data to load for the '{ctx.domain}' domain yet. Later "
            f"tickets (#4/#5/#7) register real seed hooks here; setup is not "
            f"blocked."
        ),
        details={"placeholder": True, "domain": ctx.domain},
    )
