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

> Placeholder. Domain datasets are produced by offline generators in later
> tickets (Finance seed #4; Security #13; ITSM #14). The `.gitkeep` files hold
> the directory structure until then.
