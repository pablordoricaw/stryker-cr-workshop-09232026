"""``workshop`` is the single validation seam for the Stryker Databricks workshop.

Participants call :func:`check` at each checkpoint to get an unambiguous
pass/fail plus a targeted message::

    import workshop
    print(workshop.check("smoke"))
    # [✅ PASS] smoke: workshop.check() is wired up correctly. ...

In a Databricks Git folder the repo root is on ``sys.path``, so ``import
workshop`` works from any notebook with no install step.

Checks assert only externally-observable state (catalog objects, row counts,
tag/comment presence, metric-view resolvability, Genie answer sanity,
synced-table row parity), never notebook cell structure or intermediate
variables. Later tickets extend the workshop by registering new checkpoints; see
:mod:`workshop.registry` for the registration API.
"""

from __future__ import annotations

from .bootstrap import bootstrap, find_repo_root
from .cdf_source import (
    CdfSourceReport,
    ensure_txn_cdf_source,
    shape_seed_to_cdc,
)
from .config import DOMAINS, WorkshopConfig, resolve_config
from .context import CheckContext
from .domains import DOMAIN_SPECS, DomainSpec, MetricViewSpec, domain_spec
from .genie_instructions import build_injection_block, merge_block, strip_block
from .identifiers import fully_qualified, quote_identifier
from .namespace import (
    WORKSHOP_SCHEMA_PREFIX,
    Namespace,
    namespace,
    sanitize_identity,
)
from .provisioning import ProvisionReport, provision
from .registry import (
    Checkpoint,
    CheckpointRegistry,
    DuplicateCheckpointError,
    UnknownCheckpointError,
    checkpoint,
    register,
    registry,
)
from .results import CheckResult
from .runner import check
from .seeds import (
    DuplicateSeedError,
    SeedContext,
    SeedHook,
    SeedRegistry,
    SeedResult,
    register_seed,
    run_seeds,
    seed_hook,
    seed_registry,
)

# Import the checkpoint modules so their @checkpoint decorators self-register on
# the default registry. Done here (after the registry is defined) so a plain
# ``import workshop`` makes every checkpoint immediately available to
# workshop.check(). That is the smoke check today, and everything later tickets add.
from . import checkpoints as _checkpoints  # noqa: E402
from . import seeds as _seeds  # noqa: E402

_checkpoints.load_all()
_seeds.load_all()

# module name -> import exception for any checkpoint module that failed to load.
# Empty in normal operation; a broken later-ticket module lands here instead of
# breaking ``import workshop`` (the module is also surfaced as an unavailable
# checkpoint keyed by its module name).
checkpoint_load_errors = _checkpoints.LOAD_ERRORS

# Same, for seed modules; a broken later-ticket seed is surfaced by run_seeds.
seed_load_errors = _seeds.LOAD_ERRORS

__all__ = [
    "check",
    "checkpoint",
    "register",
    "registry",
    "bootstrap",
    "find_repo_root",
    "checkpoint_load_errors",
    "CheckResult",
    "CheckContext",
    "Checkpoint",
    "CheckpointRegistry",
    "DuplicateCheckpointError",
    "UnknownCheckpointError",
    # Config + provisioning (ticket #3)
    "resolve_config",
    "WorkshopConfig",
    "DOMAINS",
    # Per-domain transactional-track spec (ticket #25)
    "domain_spec",
    "DomainSpec",
    "MetricViewSpec",
    "DOMAIN_SPECS",
    "provision",
    "ProvisionReport",
    "quote_identifier",
    "fully_qualified",
    # Genie Code hint-ladder injection into ~/.assistant_instructions.md (#27)
    "build_injection_block",
    "merge_block",
    "strip_block",
    # Per-participant namespacing (ticket #22)
    "namespace",
    "Namespace",
    "sanitize_identity",
    "WORKSHOP_SCHEMA_PREFIX",
    # Seed hooks (ticket #3; later data tickets extend)
    "run_seeds",
    "seed_hook",
    "register_seed",
    "seed_registry",
    "SeedContext",
    "SeedResult",
    "SeedHook",
    "SeedRegistry",
    "DuplicateSeedError",
    "seed_load_errors",
    # CDF source provisioning (ticket #40)
    "ensure_txn_cdf_source",
    "CdfSourceReport",
    "shape_seed_to_cdc",
]
