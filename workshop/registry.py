"""The checkpoint registry — the extension point for every later ticket.

This ticket ships an (almost) empty registry plus a smoke checkpoint. Later
tickets add checkpoints by dropping a module into ``workshop/checkpoints/`` and
decorating a function with :func:`checkpoint`; the module is auto-discovered on
``import workshop`` (see ``workshop/checkpoints/__init__.py``). No monolith to
edit, no central list to keep in sync.

Registration API (what later tickets use)::

    from workshop import checkpoint, CheckResult
    from workshop.context import CheckContext

    @checkpoint("bronze_docs", summary="Documents landed in the UC Volume")
    def check_bronze_docs(ctx: CheckContext) -> CheckResult:
        spark = ctx.require_spark()
        count = spark.sql(f"SELECT count(*) FROM {ctx.fully_qualified('bronze_docs')}").collect()[0][0]
        passed = count >= 20
        return CheckResult(
            checkpoint="bronze_docs",
            passed=passed,
            message=(f"Found {count} documents (need >= 20)." if not passed
                     else f"{count} documents landed."),
            details={"row_count": count},
        )

A checkpoint function may also return a bare ``bool`` or a ``(bool, message)``
tuple for brevity; the runner normalizes those into a :class:`CheckResult`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Union

from .context import CheckContext
from .results import CheckResult

# What a registered checkpoint function may return; the runner normalizes it.
CheckpointReturn = Union[CheckResult, bool, "tuple[bool, str]"]
CheckpointFn = Callable[[CheckContext], CheckpointReturn]


class DuplicateCheckpointError(ValueError):
    """Raised when two checkpoints try to claim the same id."""


class UnknownCheckpointError(KeyError):
    """Raised when a checkpoint id is not registered."""


@dataclass(frozen=True)
class Checkpoint:
    """A registered checkpoint: its id, its function, and a short summary."""

    id: str
    fn: CheckpointFn
    summary: str = ""


class CheckpointRegistry:
    """A keyed collection of checkpoints.

    A module-level default registry (:data:`registry`) is what
    ``workshop.check`` uses. Tests and CI can build isolated registries to avoid
    touching global state.
    """

    def __init__(self) -> None:
        self._checkpoints: dict[str, Checkpoint] = {}

    def register(
        self,
        checkpoint_id: str,
        fn: CheckpointFn | None = None,
        *,
        summary: str = "",
        replace: bool = False,
    ) -> CheckpointFn | Callable[[CheckpointFn], CheckpointFn]:
        """Register a checkpoint, as a decorator or a direct call.

        As a decorator::

            @registry.register("smoke", summary="...")
            def check_smoke(ctx): ...

        As a direct call::

            registry.register("smoke", check_smoke, summary="...")

        Args:
            checkpoint_id: Unique id participants pass to ``workshop.check``.
            fn: The checkpoint function. Omit to use as a decorator.
            summary: One-line description, surfaced by :meth:`describe`.
            replace: Allow overwriting an existing id (default ``False`` guards
                against two tickets colliding on a name).

        Raises:
            DuplicateCheckpointError: If ``checkpoint_id`` is already registered
                and ``replace`` is ``False``.
        """

        def _register(func: CheckpointFn) -> CheckpointFn:
            if not checkpoint_id:
                raise ValueError("checkpoint id must be a non-empty string")
            if checkpoint_id in self._checkpoints and not replace:
                raise DuplicateCheckpointError(
                    f"Checkpoint '{checkpoint_id}' is already registered. Use a "
                    f"different id, or register(..., replace=True) to override."
                )
            self._checkpoints[checkpoint_id] = Checkpoint(
                id=checkpoint_id, fn=func, summary=summary
            )
            return func

        # Direct call: register immediately. Decorator use: return the wrapper.
        if fn is not None:
            return _register(fn)
        return _register

    def checkpoint(
        self, checkpoint_id: str, *, summary: str = "", replace: bool = False
    ) -> Callable[[CheckpointFn], CheckpointFn]:
        """Decorator alias for :meth:`register` (reads well at call sites)."""
        return self.register(  # type: ignore[return-value]
            checkpoint_id, summary=summary, replace=replace
        )

    def get(self, checkpoint_id: str) -> Checkpoint:
        """Return the registered checkpoint or raise :class:`UnknownCheckpointError`."""
        try:
            return self._checkpoints[checkpoint_id]
        except KeyError:
            raise UnknownCheckpointError(checkpoint_id) from None

    def ids(self) -> list[str]:
        """All registered checkpoint ids, sorted."""
        return sorted(self._checkpoints)

    def describe(self) -> dict[str, str]:
        """Map of ``id -> summary`` for every registered checkpoint."""
        return {cp.id: cp.summary for cp in self._checkpoints.values()}

    def __contains__(self, checkpoint_id: object) -> bool:
        return checkpoint_id in self._checkpoints

    def __len__(self) -> int:
        return len(self._checkpoints)


# The default registry every participant-facing call uses.
registry = CheckpointRegistry()


def register(
    checkpoint_id: str,
    fn: CheckpointFn | None = None,
    *,
    summary: str = "",
    replace: bool = False,
) -> CheckpointFn | Callable[[CheckpointFn], CheckpointFn]:
    """Register a checkpoint on the default :data:`registry`."""
    return registry.register(checkpoint_id, fn, summary=summary, replace=replace)


def checkpoint(
    checkpoint_id: str, *, summary: str = "", replace: bool = False
) -> Callable[[CheckpointFn], CheckpointFn]:
    """Decorator: register a checkpoint on the default :data:`registry`."""
    return registry.checkpoint(checkpoint_id, summary=summary, replace=replace)
