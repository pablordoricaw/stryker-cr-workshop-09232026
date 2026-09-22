# notebooks/

Participant-facing starter notebooks — one per workshop module — with `# TODO`
cells, collapsible hints, and "build from scratch" stretch toggles. Each module
ends with a `workshop.check("<checkpoint_id>")` validation cell.

The curriculum is **one shared spine** across all three domains (Finance,
Security, ITSM); only the dataset and pre-authored semantic content differ, so
notebooks are domain-agnostic and read your selected domain from the setup
notebook's config.

`00_setup.py` (added by #3) is the participant setup notebook: it creates a
schema and UC Volume inside your team's **existing catalog**, runs seed hooks,
and ends on the `00_setup` checkpoint. Start there.

`01_bronze_txn.py` is the Finance transactional-ingestion starter. It offers a
primary Lakebase CDF path (clearly marked as an admin-enabled Beta/Preview) and
a no-admin Delta fallback; both land `bronze_sales_transactions` and finish at
checkpoint `01_bronze_txn`.

> The remaining notebooks are added by later tickets: the rest of the medallion
> + AI-functions build spine (#5–#9), metric views (#10), the Genie agent (#11),
> and the app wiring (#12).
