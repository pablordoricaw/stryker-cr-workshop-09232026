# solutions/

Gated reference solutions for all three domains — the top rung of the hint
ladder and the ground truth maintainer CI runs end-to-end.

**Participants:** reach for these only through Genie Code's graded hints. Peeking
here skips the learning; try the nudge → skeleton → checkpoint-solution ladder
first.

Layout (one subtree per domain; filled in as build-spine tickets land):

```
solutions/
├── finance/
│   ├── 01_bronze_docs.py   # #5 — land PDFs + register the bronze docs table
│   ├── 01_bronze_txn.py    # #7 — Lakebase CDF + Delta fallback to bronze txn
│   ├── 02_silver_docs.py   # #6 — ai_parse_document/classify/extract to silver
│   ├── 03_gold.py          # #8 — document-enriched sales + contract mart
│   ├── 04_metadata.py      # #9 — dbxmetagen comment/pi/domain on the gold tables
│   ├── 05_metric_views.py  # #10 — governed UC Metric Views over the gold tables
│   └── 06_genie.py         # #11 — per-participant Genie agent over gold + metrics
├── security/
└── itsm/
```

The Finance solutions for `01_bronze_docs`, `01_bronze_txn`, and `02_silver_docs`
are authored. `01_bronze_txn` implements both the admin-enabled Lakebase CDF path
and the no-admin Delta fallback; `02_silver_docs` builds the document-intelligence
silver layer with AI Functions (`ai_parse_document` → `ai_classify` →
`ai_extract`), landing `silver_docs` plus one `silver_<class>` table per class.
`03_gold` joins sales to extracted commercial agreements without changing
transaction grain and builds a reconciled contract-performance mart. `04_metadata`
runs dbxmetagen (pinned `v0.10.68`) in `comment`, `pi`, and `domain` modes,
staging metadata with `apply_ddl=false` and then applying comments, PI
classification tags, and domain tags to the gold tables. Later solution notebooks
are authored alongside each build-spine ticket and validated by maintainer CI
(#17). This directory ships on both `dev` and the participant release.

`05_metric_views` defines the Finance sales revenue/margin and contract-
performance semantic layers as UC Metric Views in the participant's existing
resolved schema. It also demonstrates the `MEASURE()` query syntax and documents
the optional custom-metric stretch.

`06_genie` creates (idempotently, create-or-update) a per-participant Genie agent
over the two gold tables and two Metric Views, with an identity-derived name,
pre-authored sample questions, short text instructions, and benchmark Q&A. It
uses the Databricks SDK (`WorkspaceClient().genie`), asks a sample question to
show the generated SQL, and ends on the `06_genie` checkpoint, which validates
the agent by observable Genie state only.
