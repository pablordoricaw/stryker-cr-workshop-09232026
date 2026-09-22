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
│   └── 02_silver_docs.py   # #6 — ai_parse_document/classify/extract to silver
├── security/
└── itsm/
```

The Finance solutions for `01_bronze_docs`, `01_bronze_txn`, and `02_silver_docs`
are authored. `01_bronze_txn` implements both the admin-enabled Lakebase CDF path
and the no-admin Delta fallback; `02_silver_docs` builds the document-intelligence
silver layer with AI Functions (`ai_parse_document` → `ai_classify` →
`ai_extract`), landing `silver_docs` plus one `silver_<class>` table per class.
Later solution notebooks are authored alongside each build-spine ticket and
validated by maintainer CI (#17). This directory ships on both `dev` and the
participant release.
