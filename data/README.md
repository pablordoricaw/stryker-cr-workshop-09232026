# data/

Committed synthetic data, one subtree per domain. Everything here is generated
and fake — there is no real Stryker data anywhere in this repo.

```
data/
├── finance/    # Orthopedics finance: invoice / PO / sales contract / quarterly statement / Other
├── security/   # Infra security: vuln scan / CVE advisory / pentest / cloud-posture / Other
└── itsm/       # IT-Ops: incident / RCA / change request / KB article / Other
```

Each domain holds:

- `documents/` — ~20–25 synthetic PDFs (4–5 per class) that feed the document
  pipeline (`ai_classify` → `ai_parse_document` → `ai_extract`).
- `transactional/` — a pre-seeded transactional dataset (~2–5k rows) that lands
  in bronze. This is the **Delta fallback** for the Lakebase CDF path, so no
  participant is ever blocked by the one preview dependency.

The Finance seed is populated by issue #4. Security and ITSM remain placeholders
for their later offline generators (#13 and #14); their `.gitkeep` files retain
the intended directory structure until then.
