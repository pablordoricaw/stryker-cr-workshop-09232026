# Tier-3 stretch modules

These are **optional** modules for strong engineers. They are strictly
**additive**: they build *on top of* the work you already finished (the graded
`00_setup` → `07_app` path) and change **nothing** about how any checkpoint
grades you. Skip them entirely and your workshop is still complete.

Everything here honours the same two workshop rules as the core path:

- **Bring your own catalog.** Nothing here runs `CREATE CATALOG`. Objects land
  only in your existing catalog, in your per-participant `workshop_<you>` schema.
- **Per-participant namespacing.** Every workspace-scoped name (schema, Genie
  agent, app, Lakebase project, synced table, and the DAB below) is derived from
  your identity through `workshop.namespace(me, domain=...)`, so nothing you
  create here collides with a teammate's in the shared workspace.

| # | Module | Surface | Gated solution |
| - | ------ | ------- | -------------- |
| 1 | **Package your work as a DAB** | [`notebooks/stretch/package_as_dab.py`](../../notebooks/stretch/package_as_dab.py) | [`solutions/finance/stretch/package_as_dab.py`](../../solutions/finance/stretch/package_as_dab.py) + the example bundle in [`solutions/finance/stretch/package_as_dab_bundle/`](../../solutions/finance/stretch/package_as_dab_bundle/) |
| 2 | **Add your own metrics / Genie questions** | [`notebooks/stretch/add_your_own.py`](../../notebooks/stretch/add_your_own.py) | [`solutions/finance/stretch/add_your_own.py`](../../solutions/finance/stretch/add_your_own.py) |
| 3 | **From-scratch mode** | a convention on every build stage (below) | (documentation only) |

---

## 1. Package your work as a DAB

**The gap this closes.** Your team — Finance, Security, or ITSM — ships pipelines
and apps by hand. [Databricks Asset Bundles (DABs)](https://docs.databricks.com/aws/en/dev-tools/bundles/)
version your **built work** as source-controlled YAML, so it is reviewable,
re-runnable, and promotable between workspaces.

You package the built work as **two independently-deployable bundles**, not one
monolith; grouped by lifecycle / ownership / deploy cadence:

- **`pipeline`**: the medallion **Lakeflow Job** (bronze→gold→metadata→metrics).
- **`app`**: the **Databricks App**, shipping its own source.

**Packaging, not provisioning.** Your schema + UC Volume were created by
`00_setup` (the notebook path), so **neither bundle declares a schema/volume
resource**; they **target** your existing `catalog.schema` by variable. That is
what makes a first `bundle deploy` safe: it never collides with the UC objects
`00_setup` already created. (The maintainer bundle at the repo root *does* define
schema/volume+app; that one is for a reproducible *fresh* setup; the participant
stretch packages your built work and points at what you already provisioned.)

- **CREATE-CATALOG-free** and schema/volume-free: `catalog` names your existing
  catalog; the schema/volume come from `00_setup`. No catalog, schema, or volume
  resource in either bundle.
- **Namespace-aware.** `schema` (pipeline) and `app_name` (app) default to your
  identity-derived names, so a teammate can deploy their own copy without a clash.
- **Self-contained app.** The app bundle uses `sync.paths` to ship the repo's
  `app/` as its own source, rather than pointing at a pre-existing Workspace path.
- **Deterministic names.** No `mode: development`; dev-mode prefixing injects
  characters not legal in Unity Catalog identifiers and would drift from what
  your notebooks and the `07_app` checkpoint expect.

The metric views and Genie agent are **not** DAB resource types; the metric
views ride the pipeline job; the Genie agent is created via the SDK and wired to
the app by resource key.

> [!IMPORTANT]
> This module uses the Databricks CLI (`databricks bundle …`), which needs a
> terminal or a local machine. It is the one Tier-3 module that steps outside
> the pure Workspace-UI flow; deliberately, because a DAB *is* a
> source-control/CLI artifact. Validate offline with
> `databricks bundle validate --strict`; deploy only if you want to.

The gated solution ships the **complete, validated example bundle set** with a
README documenting the division rationale, cross-bundle references, and deploy
runbook: [`solutions/finance/stretch/package_as_dab_bundle/`](../../solutions/finance/stretch/package_as_dab_bundle/).

## 2. Add your own metrics / Genie questions

You built two Metric Views (`05_metric_views`) and a Genie agent (`06_genie`).
This module extends both **without touching the framework**; the checkpoints
already accept your own contract through `workshop.check` extras:

- **A third Metric View.** Author it in your schema exactly like the two you
  built, then validate it by passing a `metric_views={...}` contract to
  `workshop.check("05_metrics", ...)`. See the metrics-checkpoint contract
  (view name → `source_table`, `dimensions`, `measures`).
- **Your own Genie sources + benchmark questions.** Attach the new Metric View
  (or any gold asset) to your agent, then validate with
  `expected_sources=[...]` and `benchmark_questions=[...]` on
  `workshop.check("06_genie", ...)`. The `expected_sources` check is a
  **superset** test, so adding assets never breaks the default grade.

This is the same pattern the Security (#13) and ITSM (#14) domains use to reuse
the generic checkpoints, so it is worth understanding regardless of your domain.
The gated solution shows one concrete extra Metric View (`finance_discount_metrics`)
and two extra benchmark questions end to end.

## 3. From-scratch mode (documented once, applied on every stage)

Every graded **build** stage: `01_bronze_docs`, `01_bronze_txn`,
`02_silver_docs`, `03_gold`, `04_metadata`, `05_metric_views`, `06_genie`,
`07_app`; ships in **guided** mode: `# TODO` cells with collapsible **💡 Hint**
sections. A strong engineer can uniformly flip any stage to **from-scratch**
mode. `00_setup` is excluded; it provisions your environment with
`workshop.provision(...)` rather than teaching a build.

**How to flip a stage:**

1. Treat every `# TODO` cell in the stage as **blank** and keep each **💡 Hint**
   collapsed. Build the cell yourself.
2. Use the stage's **`workshop.check("<stage>", ...)` cell as your only spec.**
   It is byte-for-byte identical in guided and from-scratch mode and is the sole
   thing that grades you; the checkpoint reads your catalog, never your
   notebook.
3. Stuck? Re-open a hint (or ask Genie Code for a graded hint) to drop back to
   guided mode at any point. There is no penalty.

**Why it's a convention, not a setting.** The toggle is deliberately *not* a
widget or a code flag. Making it a setting would risk changing what runs and
what the checkpoint asserts; a convention cannot. Each build stage carries the
same short **"🚀 From-scratch mode (optional stretch)"** markdown cell, right
after its config cell, pointing back here; so the flip is uniform across stages
and provably harmless to the graded path.
