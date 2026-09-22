# Package your work as a DAB — the example bundle **set** (gated solution)

This is the gated solution for the "package your work as a DAB" stretch. It is a
**set of three independently-deployable bundles**, not one monolith:

```
package_as_dab_bundle/
├── foundation/     # schema + UC Volume            (platform lifecycle)
│   ├── databricks.yml
│   └── resources/{schema.schema.yml, volume.volume.yml}
├── pipeline/       # medallion+metadata+metrics job (data-engineering lifecycle)
│   ├── databricks.yml
│   └── resources/medallion.job.yml
└── app/            # Databricks App                 (product lifecycle)
    ├── databricks.yml
    └── resources/data_app.app.yml
```

Each directory is its own bundle (its own `databricks.yml`) and validates and
deploys on its own:

```bash
cd foundation && databricks bundle validate --strict   # then pipeline/, then app/
```

All three pass `databricks bundle validate --strict` offline.

## Why three bundles, not one

The strong instinct is to put every component you built — the medallion, the
metric views, the Genie agent, the app + Lakebase — into one big bundle. **Don't.**
A single bundle couples resources that have nothing to do with each other's
lifecycle, and `databricks bundle deploy` / `destroy` then acts on *all* of them
at once. The division below groups resources by **what changes together**,
**who owns it**, and **how often it deploys**, and decouples everything else.

| Bundle | Owns | Changes when… | Deploy cadence | Blast radius if it breaks |
| ------ | ---- | ------------- | -------------- | ------------------------- |
| **foundation** | schema, UC Volume | governance/layout changes (rare) | once, up front | **widest** — everything reads this schema |
| **pipeline** | the medallion Lakeflow Job (bronze→silver→gold→metadata→metric views) | transforms/columns/metrics change | on the DE cadence; re-run to rebuild data | rebuilds tables; app keeps serving the last good gold |
| **app** | the Databricks App | UI/endpoint changes | many times a day | **smallest** — only the app; data is untouched |

Concretely, the monolith hurts in four ways the split fixes:

1. **Deploy cadence.** The app iterates many times a day; the foundation schema
   almost never changes. In one bundle, every app redeploy re-plans the schema
   and volume, and a `bundle destroy` to tear down an app would try to drop your
   **schema** with it. Splitting lets you `deploy` the app alone, all day, with
   zero risk to the substrate.
2. **Blast radius.** One bundle = one `destroy`/rollback unit. Coupling the
   foundation with the pipeline means a pipeline rollback can take your schema
   and gold data with it. Independent bundles bound each failure to one
   lifecycle.
3. **Ownership (Conway's law).** Platform/governance owns the schema; data
   engineering owns the pipeline; the app developer owns the app. One bundle
   carries one owner and one permission set — three owners want three bundles.
4. **Independent iteration.** You can ship a new gold transform (redeploy +
   run the pipeline) without redeploying or restarting the app, and ship a new
   app build without re-running the pipeline.

## How the bundles reference each other

DABs has **no first-class cross-bundle resource reference** — there is no
`${bundles.foundation.resources.schemas...}` you can point at from another
bundle. That is a feature here, not a limitation: the decoupling is the point.
The bundles agree by **shared name**, not by an in-bundle handle:

- Every bundle takes the same `catalog` and `schema` **variables** (your existing
  catalog + your `workshop_<you>` schema). The pipeline job writes into
  `${var.catalog}.${var.schema}`; the app reads gold from the same place. Pass
  identical `--var` values to all three.
- Where an ordering dependency is unavoidable (schema must exist before the
  pipeline writes to it; gold must exist before the app serves it), it is
  enforced by **deploy order in a runbook**, not by nesting resources in one
  bundle. See below.

Two components are **not** DAB resources at all, so they deliberately live
outside the bundles and are referenced by name:

- **UC Metric Views** are SQL DDL, not a bundle resource type — they are created
  by `05_metric_views` and ride inside the **pipeline** job (the `metric_views`
  task), not a bundle of their own.
- **The Genie agent** is not a bundle resource type — it is created via the SDK
  in `06_genie`. The app's `genie-space` resource points at it by id/key in the
  Apps UI.
- **The Lakebase synced table** is created via the CLI/SDK in `07_app` (the DAB
  synced-table resource is deprecated). The app reaches it through its `postgres`
  app resource.

## Deploy runbook (order matters — that's the cross-bundle "dependency")

```bash
# Values your notebooks printed (identity-derived; see 00_setup / 06_genie / 07_app):
CATALOG=<your_existing_catalog>
SCHEMA=workshop_<you>
APPNAME=stryker-finance-<you>-<digest>
P=--profile <your-profile>

# 1) Foundation first — the schema + volume everything else references.
cd foundation
databricks bundle validate --strict
databricks bundle deploy --var catalog=$CATALOG --var schema=$SCHEMA $P

# 2) Pipeline — deploy, then run to (re)build bronze->silver->gold->metadata->metric views.
cd ../pipeline
databricks bundle validate --strict
databricks bundle deploy --var catalog=$CATALOG --var schema=$SCHEMA \
  --var notebooks_root=/Workspace/Users/<you>/stryker-cr-workshop/notebooks $P
databricks bundle run medallion_build $P

# (create the Genie agent [06] and Lakebase synced table [07] out-of-band if you
#  have not already — they are not bundle resources.)

# 3) App last — it reads the gold the pipeline produced and the Genie/Lakebase you wired.
cd ../app
databricks bundle validate --strict
databricks bundle deploy --var app_name=$APPNAME \
  --var app_source_path=/Workspace/Users/<you>/stryker-cr-workshop/app $P
databricks apps start $APPNAME $P
```

## Bring-your-own-catalog & namespacing (unchanged from the core path)

- **No `catalogs:` resource anywhere.** `catalog` names an existing catalog.
- **Deterministic names** — no `mode: development`; dev-mode prefixing injects
  characters illegal in UC identifiers and would drift from what your notebooks
  and the checkpoints expect.
- Pass the same identity-derived `--var schema=` (and `--var app_name=`) to every
  bundle so your set never collides with a teammate's in the shared workspace.
