# app/

The **provided data app** participants wire to their own Genie agent. It's a
Python (FastAPI) app deployed and started from the Databricks Apps UI or a
notebook step — no web terminal required.

The app ships **complete except for exactly two gaps** each participant fills:

1. the **Genie agent connection** (via the Genie Conversation API), and
2. the **Lakebase read** (pointing at a gold table synced to Lakebase).

> Placeholder. The app is added by ticket #12 (provided FastAPI app + Lakebase
> synced table). Validated through `workshop.check()` like every other
> checkpoint.
