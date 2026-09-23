# Package your work as a DAB: the example bundle **set** (gated solution)

This is the gated solution for the "package your work as a DAB" stretch. It is a
**set of two independently-deployable bundles**, not one monolith, and it packages
**the work you built** (the pipeline and the app) on top of the environment
`00_setup` already provisioned:

```
package_as_dab_bundle/
├── pipeline/       # medallion+metadata+metrics Lakeflow Job (data-engineering lifecycle)
│   ├── databricks.yml
│   └── resources/medallion.job.yml
└── app/            # Databricks App, bundle-local source          (product lifecycle)
    ├── databricks.yml          # sync.paths ships the repo's app/
    └── resources/data_app.app.yml
```

Each directory is its own bundle (its own `databricks.yml`) and validates and
deploys on its own:

```bash
cd pipeline && databricks bundle validate --strict   # then app/
```

Both pass `databricks bundle validate --strict` offline.

## Provisioning vs. packaging: why there is no schema/volume bundle

Your **schema and UC Volume are provisioned by `00_setup`** (the notebook path;
the workshop's required, Workspace-UI provisioning per decision Q20=B), **not by
these bundles.** So neither bundle declares a `schemas:` or `volumes:` resource:
if it did, the very first `bundle deploy` into your namespace would fail on the
UC schema/volume that `00_setup` already created. Instead, both bundles **target**
the existing `${var.catalog}.${var.schema}` by variable and manage only the
work you built:

- the **pipeline** packages the medallion **Lakeflow Job**, and
- the **app** packages the **Databricks App**.

(The maintainer-owned bundle at the repo root *does* define schema/volume+app;
that one is for a reproducible *fresh* setup. The participant stretch is
different: your schema already exists, so the stretch packages your built work
and points at it. Never `CREATE CATALOG` in either.)

## Why two bundles, not one

The strong instinct is to put everything into one bundle. **Don't.** A single
bundle couples resources with unrelated lifecycles under one
`deploy`/`destroy`, so an app redeploy re-plans the pipeline and an app teardown
can take the job with it. The division groups by **what changes together**,
**who owns it**, and **how often it deploys**:

| Bundle | Owns | Changes when… | Deploy cadence | Blast radius if it breaks |
| ------ | ---- | ------------- | -------------- | ------------------------- |
| **pipeline** | the medallion Lakeflow Job (bronze→silver→gold→metadata→metric views) | transforms/columns/metrics change | on the DE cadence; re-run to rebuild data | rebuilds tables; app keeps serving the last good gold |
| **app** | the Databricks App | UI/endpoint changes | many times a day | **smallest**: only the app; data is untouched |

Concretely, the monolith hurts and the split fixes:

1. **Deploy cadence.** The app iterates many times a day; the pipeline changes on
   the DE cadence. Splitting lets you redeploy the app all day without re-planning
   the job (and vice versa).
2. **Blast radius.** One bundle = one `destroy`/rollback unit. Coupling the app
   with the pipeline means an app teardown can drop the job. Independent bundles
   bound each failure to one lifecycle.
3. **Ownership (Conway's law).** Data engineering owns the pipeline; the app
   developer owns the app. Two owners want two bundles, each with its own
   permission set.

## How the bundles reference each other

DABs has **no first-class cross-bundle resource reference**: there is no
`${bundles.pipeline.resources...}` you can point at from the app bundle. That is
the point: the decoupling is deliberate. The bundles agree by **shared name**,
not by an in-bundle handle:

- The **pipeline** takes `catalog`, `schema`, `volume`, `domain`, and
  `notebooks_root`; its job writes gold into `${var.catalog}.${var.schema}`.
- The **app** takes `app_name` and `app_source_path`; it reads that same gold by
  name at runtime and reaches the Genie agent + Lakebase synced table through its
  app resources.
- Pass the **same** `--var catalog=`/`schema=` you gave `00_setup` to the
  pipeline, and your identity-derived `--var app_name=` to the app.
- The only ordering dependency (gold must exist before the app serves it) is
  enforced by **deploy order in the runbook below**, not by nesting resources.

Two components are **not** DAB resources at all, so they live outside the bundles
and are referenced by name:

- **UC Metric Views** are SQL DDL, not a bundle resource type; created by
  `05_metric_views` and run inside the **pipeline** job (the `metric_views` task).
- **The Genie agent** is not a bundle resource type; created via the SDK in
  `06_genie`; the app's `genie-space` resource points at it in the Apps UI.
- **The Lakebase synced table** is created via the CLI/SDK in `07_app` (the DAB
  synced-table resource is deprecated); the app reaches it via its `postgres`
  resource.

## The app bundle is self-contained

The app bundle ships its **own source**: `sync.paths` scopes its sync root to the
repo's `app/` directory, so `databricks bundle deploy` uploads exactly that app;
no dependency on a pre-existing Workspace checkout, and no second copy of the app
to drift. (The deep `../` in the paths is only because this example is stored
under `solutions/`; at your repo root, both `sync.paths` and `app_source_path`
are just `app`.)

## Deploy runbook (order matters: that's the cross-bundle "dependency")

```bash
# Values your notebooks printed (identity-derived; see 00_setup / 07_app):
CATALOG=your_existing_catalog          # provisioned by 00_setup; NOT created here
SCHEMA=workshop_you
APPNAME=stryker-finance-you-digest
PROFILE=your-profile                   # then pass --profile "$PROFILE"

# 1) Pipeline: deploy, then run to (re)build bronze->silver->gold->metadata->metric views.
cd pipeline
databricks bundle validate --strict --profile "$PROFILE"
databricks bundle deploy --var catalog="$CATALOG" --var schema="$SCHEMA" \
  --var notebooks_root=/Workspace/Users/you/stryker-cr-workshop/notebooks --profile "$PROFILE"
databricks bundle run medallion_build --profile "$PROFILE"

# (create the Genie agent [06] and Lakebase synced table [07] out-of-band if you
#  have not already; they are not bundle resources.)

# 2) App last: it reads the gold the pipeline produced and the Genie/Lakebase you wired.
cd ../app
databricks bundle validate --strict --profile "$PROFILE"
databricks bundle deploy --var app_name="$APPNAME" --profile "$PROFILE"
databricks apps start "$APPNAME" --profile "$PROFILE"
```

Because neither bundle declares the schema/volume that `00_setup` created, this
runbook deploys end to end without colliding with pre-existing UC objects.

## Bring-your-own-catalog & namespacing

- **No `catalogs:` resource anywhere**, and no `schemas:`/`volumes:` either;
  `catalog` names an existing catalog; the schema/volume come from `00_setup`.
- **Deterministic names**: no `mode: development`; dev-mode prefixing injects
  characters illegal in UC identifiers and would drift from what your notebooks
  and the `07_app` checkpoint expect.
- Pass the same identity-derived `--var` values you used in the notebooks so your
  bundle set never collides with a teammate's in the shared workspace.
