"""The seed-hook registry — the extension point later data tickets fill in.

This ticket ships the *mechanism* plus a no-op placeholder. Later tickets add
real data loading by dropping a module into ``workshop/seeds/`` and decorating a
function with :func:`seed_hook` — auto-discovered on ``import workshop``, no
central list to edit (exactly like ``workshop/checkpoints/``)::

    # workshop/seeds/finance_transactional.py  (a later ticket)
    from workshop import seed_hook, SeedResult

    @seed_hook("finance_transactional", domains="finance",
               summary="Load the pre-seeded Delta transactional rows into bronze")
    def load(ctx):
        spark = ctx.require_spark()
        ...  # write into ctx.config.catalog / ctx.config.schema
        return SeedResult("finance_transactional", True, "Loaded 2,500 rows.")

A hook may target one domain (``domains="finance"``), several
(``domains=("finance", "security")``), or all of them (``domains=None``, the
default). ``run_seeds`` runs exactly the hooks that match the run's domain.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Union

from workshop.config import DOMAINS

from ._context import SeedContext, SeedResult

# What a seed hook may return; the runner normalizes it into a SeedResult.
SeedReturn = Union[SeedResult, bool, "tuple[bool, str]", None]
SeedFn = Callable[[SeedContext], SeedReturn]


class DuplicateSeedError(ValueError):
    """Raised when two seed hooks try to claim the same name."""


def _normalize_domains(domains: str | Iterable[str] | None) -> frozenset[str] | None:
    """Coerce the ``domains`` argument to a validated frozenset, or ``None`` (all)."""
    if domains is None:
        return None
    names = [domains] if isinstance(domains, str) else list(domains)
    resolved = frozenset(name.strip().lower() for name in names)
    unknown = resolved - set(DOMAINS)
    if unknown:
        raise ValueError(
            f"Unknown seed domain(s): {', '.join(sorted(unknown))}. "
            f"Valid domains: {', '.join(DOMAINS)}."
        )
    return resolved


@dataclass(frozen=True)
class SeedHook:
    """A registered seed hook: its name, function, target domains, and summary.

    ``domains is None`` means the hook runs for every domain.
    """

    name: str
    fn: SeedFn
    domains: frozenset[str] | None = None
    summary: str = ""

    def applies_to(self, domain: str) -> bool:
        return self.domains is None or domain in self.domains


class SeedRegistry:
    """A keyed collection of seed hooks (mirrors ``CheckpointRegistry``)."""

    def __init__(self) -> None:
        self._hooks: dict[str, SeedHook] = {}

    def register(
        self,
        name: str,
        fn: SeedFn | None = None,
        *,
        domains: str | Iterable[str] | None = None,
        summary: str = "",
        replace: bool = False,
    ) -> SeedFn | Callable[[SeedFn], SeedFn]:
        """Register a seed hook, as a decorator or a direct call.

        Args:
            name: Unique hook name.
            fn: The hook function. Omit to use as a decorator.
            domains: Domain(s) this hook runs for, or ``None`` for all.
            summary: One-line description.
            replace: Allow overwriting an existing name (default ``False``).

        Raises:
            DuplicateSeedError: If ``name`` is taken and ``replace`` is ``False``.
            ValueError: If ``name`` is empty or a domain is unknown.
        """
        resolved_domains = _normalize_domains(domains)

        def _register(func: SeedFn) -> SeedFn:
            if not name:
                raise ValueError("seed hook name must be a non-empty string")
            if name in self._hooks and not replace:
                raise DuplicateSeedError(
                    f"Seed hook '{name}' is already registered. Use a different "
                    f"name, or register(..., replace=True) to override."
                )
            self._hooks[name] = SeedHook(
                name=name, fn=func, domains=resolved_domains, summary=summary
            )
            return func

        if fn is not None:
            return _register(fn)
        return _register

    def seed_hook(
        self,
        name: str,
        *,
        domains: str | Iterable[str] | None = None,
        summary: str = "",
        replace: bool = False,
    ) -> Callable[[SeedFn], SeedFn]:
        """Decorator alias for :meth:`register`."""
        return self.register(  # type: ignore[return-value]
            name, domains=domains, summary=summary, replace=replace
        )

    def hooks_for(self, domain: str) -> list[SeedHook]:
        """The hooks that apply to ``domain``, sorted by name for stable order."""
        return sorted(
            (h for h in self._hooks.values() if h.applies_to(domain)),
            key=lambda h: h.name,
        )

    def names(self) -> list[str]:
        return sorted(self._hooks)

    def describe(self) -> dict[str, str]:
        return {h.name: h.summary for h in self._hooks.values()}

    def __contains__(self, name: object) -> bool:
        return name in self._hooks

    def __len__(self) -> int:
        return len(self._hooks)


# The default registry every participant-facing call uses.
seed_registry = SeedRegistry()


def register_seed(
    name: str,
    fn: SeedFn | None = None,
    *,
    domains: str | Iterable[str] | None = None,
    summary: str = "",
    replace: bool = False,
) -> SeedFn | Callable[[SeedFn], SeedFn]:
    """Register a seed hook on the default :data:`seed_registry`."""
    return seed_registry.register(
        name, fn, domains=domains, summary=summary, replace=replace
    )


def seed_hook(
    name: str,
    *,
    domains: str | Iterable[str] | None = None,
    summary: str = "",
    replace: bool = False,
) -> Callable[[SeedFn], SeedFn]:
    """Decorator: register a seed hook on the default :data:`seed_registry`."""
    return seed_registry.seed_hook(
        name, domains=domains, summary=summary, replace=replace
    )
