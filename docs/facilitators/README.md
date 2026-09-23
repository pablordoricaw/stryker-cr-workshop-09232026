# Facilitator pre-workshop checklist

Operational prep for whoever runs the Stryker hands-on workshop. Work through this
before the session and resolve every unchecked item (or confirm its fallback). This
file is maintainer-only: it lives on `dev` and the release promotion strips
`docs/facilitators/` from the participant `main` branch, so it may reference internal
and event-specific details.

The workshop runs across two kinds of environment:

- **Stryker team workspaces**: shared workspaces where features are guaranteed on.
- **Databricks Free Edition**: per-participant self-signup accounts, used where no team
  workspace seat is available.

> [!NOTE]
> **Feature lifecycle as of 2026-09-23** (verified with Databricks Genie against current
> docs; see [Sources](#sources)). Most of what the workshop needs is Generally Available
> and on by default, so the checks below are mostly "confirm", not "enable":
>
> | Feature | Lifecycle | Default on a new workspace |
> |---|---|---|
> | Lakebase (managed Postgres) and synced tables | GA | On, where **serverless compute** is enabled |
> | Lakebase project creation by non-admins | GA | On (all users get `CAN CREATE`) |
> | Lakebase Change Data Feed (Postgres to Delta) | Public Preview | Off, admin enables on the Previews page |
> | Genie Code (in-product assistant) | GA | On, including Free Edition |
> | Genie Agents / Spaces (Chat mode) | GA | On (needs a pro or serverless SQL warehouse) |
> | Partner-powered AI features | GA setting | On, **except** compliance-security-profile (CSP) workspaces |
> | Databricks Apps | GA | On, in serverless-supported regions |
> | Foundation Model API `databricks-claude-sonnet-4-6` | GA | Preconfigured (pay-per-token) in US and EU regions |
>
> All of these require the workspace region to support **serverless compute**. Confirm that first.

---

## Capacity and quotas

- [ ] **Confirm the final roster and per-workspace headcount.** ~30 participants total across
  the Finance, Security, and ITSM tracks plus the IT AI LATAM team. Count heads per team
  workspace so no single shared workspace is overloaded, and record the numbers.
  - **Fallback:** if the roster is not final, chase the organizer before day-of; plan with
    ~10 participants per team workspace as a placeholder.

- [ ] **Decide where the IT AI LATAM team runs.** Either join a Stryker team workspace (fine
  when that workspace's total stays roughly at or below 15 heads) or use Free Edition
  self-signup (see [Participant access and onboarding](#participant-access-and-onboarding)).
  - **Fallback:** Free Edition is always available and needs no seat allocation.

> [!NOTE]
> Each participant gets a deterministic per-participant schema (`workshop_<identity-digest>`)
> inside the shared catalog, so ~30 participants in one workspace means ~30 `workshop_`-prefixed
> schemas in one catalog with no name collisions. This is bring-your-own-catalog: neither
> participants nor the bundle create catalogs.

- [ ] **Confirm one shared serverless SQL warehouse per team workspace.** It powers Genie
  Agents (`06_genie`) and AI-function queries (`02_silver_docs`, `04_metadata`). One
  auto-scaling warehouse serves everyone in that workspace.
  - **How (UI):** SQL Warehouses, confirm at least one Serverless warehouse that is running
    or has auto-start on.
  - **How (CLI):** `databricks warehouses list --profile <PROFILE>`, confirm a serverless
    warehouse with auto-start enabled.
  - **Fallback:** create one (SQL Warehouses, Create, Serverless, auto-start on). If
    participants hit query queuing on the day, raise the warehouse's max scaling.

- [ ] **Confirm the Databricks Apps quota covers every participant's app.** Each participant
  deploys one Streamlit app in `07_app`.
  - **Team workspaces:** no practical per-workspace app cap; deploy freely.
  - **Free Edition:** hard limit of **3 apps per account**, and each app auto-stops 24 hours
    after it is started, updated, or redeployed.
  - **Fallback:** on Free Edition, participants delete an unused app or restart a stopped one;
    do not pre-deploy Free Edition apps more than a day early.

- [ ] **Confirm Lakebase project capacity.** Each participant may create one Lakebase project
  for the app's synced table. Non-admin users can create projects by default (all workspace
  users hold `CAN CREATE`), and team workspaces allow far more projects than the headcount.
  Free Edition includes one project per account.
  - **Fallback:** the shared-project fallback in
    [Participant access and onboarding](#participant-access-and-onboarding).

- [ ] **Confirm Foundation Model access for the head count.** Metadata generation
  (`04_metadata`, dbxmetagen) and AI functions call `databricks-claude-sonnet-4-6`, which is a
  preconfigured pay-per-token endpoint in US and EU regions.
  - **How (UI):** Serving, Foundation Models, confirm `databricks-claude-sonnet-4-6` is listed.
  - **How (CLI):** `databricks serving-endpoints list --profile <PROFILE>`.
  - **Note:** Claude endpoints are pay-per-token only; **provisioned throughput is not
    available for Anthropic models**, so you cannot pre-provision capacity. If concurrent runs
    throttle (HTTP 429), stagger cohorts (for example Finance runs `04_metadata` first, then
    Security, then ITSM) rather than trying to raise a throughput limit.
  - **Fallback:** if `databricks-claude-sonnet-4-6` is absent (region, or a Free Edition model
    restriction), pick another available endpoint and have participants set it via the
    `model_endpoint` widget in `04_metadata`; `04_metadata` also ships a no-PyPI manual
    documentation fallback that still passes the checkpoint.

### Open questions for the maintainer

- Confirm the IT AI LATAM team assignment (dedicated workspace vs Free Edition) and final head count.
- On Free Edition specifically, confirm `databricks-claude-sonnet-4-6` appears in the Serving
  endpoints list (the docs note "certain models not available" on Free Edition without
  enumerating them). If absent, choose the alternative endpoint ahead of time.

---

## Platform toggles and preview features

- [ ] **Confirm the workspace region supports serverless compute.** Lakebase, Databricks Apps,
  and the Foundation Model APIs all run on serverless. Everything below assumes this holds.
  - **Fallback:** if a target workspace is not in a serverless-supported region, move that
    cohort to a workspace that is (or to Free Edition).

- [ ] **Confirm Partner-powered AI features are enabled.** This setting lets Genie use
  partner-hosted models (Anthropic on Databricks and others). It is **on by default except on
  compliance-security-profile (CSP) workspaces**. Genie Agent modes (used in `06_genie`)
  require it; core Genie Code falls back to Databricks-hosted models if it is off.
  - **How (UI):** Settings, then the Partner-powered AI features setting (account or workspace
    level). Confirm it is on.
  - **Fallback:** if off (for example a CSP workspace), a workspace or account admin enables it.

> [!WARNING]
> The Partner-powered AI features **toggle is being removed on 2026-11-01**. Before that date a
> workspace where it is off can still turn it on; after that date the value is frozen and
> changes require the Databricks account team. Verify it is on well ahead of the workshop.

- [ ] **Confirm Genie Code is available for participants (including Free Edition).** Genie Code
  is GA and is an explicit Free Edition capability; it delivers the workshop's graded hint
  ladder.
  - **How:** open Genie Code in a notebook in each environment and confirm it responds.
  - **Fallback:** the hint ladder degrades gracefully. Participants open the solution file
    directly at `solutions/<domain>/<module>.py`; `workshop.check()` grading is identical
    either way.

- [ ] **Confirm the synced table sync mode and its Change Data Feed needs.** `07_app` creates
  the Lakebase synced table in **Snapshot mode by default, which needs no CDF**. Only the
  Tier-3 stretch that switches the sync to Triggered or Continuous needs a change feed on the
  source gold table.
  - **How (if using Triggered/Continuous):** enable write-time CDF on the gold table
    (`ALTER TABLE <gold> SET TBLPROPERTIES ('delta.enableChangeDataFeed' = true)`) or rely on
    automatic CDF; the Lakebase UI prints the exact command if it is missing.
  - **Fallback:** stay on Snapshot mode (the recommended default), which requires no CDF and no
    preview toggle.

> [!NOTE]
> The issue's phrase "Lakebase CDF admin/preview toggle" refers to the separate **Lakebase
> Change Data Feed (Postgres to Delta)** feature, which is Public Preview and admin-enabled on
> the Previews page. The workshop's synced table (Delta to Postgres) in Snapshot mode does not
> use it, so this preview is not on the critical path.

- [ ] **Confirm the dbxmetagen Foundation Model endpoint.** See the Foundation Model item under
  [Capacity and quotas](#capacity-and-quotas); confirm `databricks-claude-sonnet-4-6` is present
  or select an alternative and communicate the `model_endpoint` value.

> [!WARNING]
> **App-start gotcha (the most common `07_app` blocker).** The app checkpoint fails RED unless
> both of these hold:
>
> 1. **The synced table is ONLINE.** Synced-table provisioning is asynchronous; the app cannot
>    read rows until it finishes. Confirm the table shows online before deploying the app
>    (Lakebase project, Synced tables, green online indicator; or check the provisioning state
>    via the CLI). If it is stuck, check the sync pipeline logs (common causes: source table
>    missing, zero rows, or a CDF misconfiguration on a Triggered/Continuous table).
> 2. **The app is STARTED, not just deployed.** Deploying does not start the app; a
>    deployed-but-stopped app answers nothing. After deploy, explicitly start it
>    (`databricks apps start <app_name>` or Apps UI, Start) and wait for RUNNING.
>
> Call both out at kickoff; "deployed" does not mean "running".

### Open questions for the maintainer

- Confirm the exact current UI path for the Partner-powered AI setting in the workshop
  workspaces (menu labels shift between releases).
- If any cohort uses the Triggered/Continuous stretch, pre-enable CDF on that domain's gold
  table so the stretch is not blocked mid-session.

---

## Participant access and onboarding

- [ ] **Confirm Free Edition self-signup for participants who need it.** Signup is at
  <https://www.databricks.com/learn/free-edition>: one personal account per participant, one
  workspace each.
  - **Fallback:** if a participant's signup is blocked (for example a corporate-email
    restriction), add them to a Stryker team workspace instead.

> [!NOTE]
> Free Edition constraints to communicate up front: one Lakebase project, up to 3 apps with a
> 24-hour auto-stop, throttled (non-provisioned) Foundation Model calls, and a single small SQL
> warehouse. Genie Code is available. None of these block the workshop, but participants should
> expect throttling under load.

- [ ] **Confirm the GitHub-to-Databricks path for the fork and Git folder.** Participants fork
  <https://github.com/pablordoricaw/stryker-cr-workshop-09232026> and clone the fork into a
  workspace Git folder. The **Databricks GitHub App** is the recommended link method
  ([docs](https://learn.microsoft.com/en-us/azure/databricks/repos/get-access-tokens-from-git-provider#databricks-github-app-recommended));
  a personal access token also works.
  - **How:** confirm one participant can complete fork, then Workspace, Create, Git folder,
    paste the fork URL, and see `notebooks/00_setup.py` in the clone.
  - **Fallback (no GitHub link):** download the repo ZIP (Code, Download ZIP), then in the
    workspace use Workspace, Import to upload the unzipped folder. Test this import once before
    the workshop.

> [!WARNING]
> Any participant who cannot or will not link GitHub must use the ZIP-upload fallback. State
> both paths clearly at kickoff: "pick one, GitHub fork or ZIP upload."

- [ ] **Confirm non-admin Lakebase project creation.** By default all workspace users hold
  `CAN CREATE`, so a non-admin can create the project the app's synced table needs (done inside
  `07_app`, not pre-workshop). Verify this default has not been restricted in the team
  workspaces.
  - **How:** as a non-admin test identity, confirm Compute, Lakebase projects, Create project
    is available.
  - **Fallback (shared project):** if creation is restricted, pre-create one shared Lakebase
    project, tell participants its name at kickoff, and have them target it in `07_app` instead
    of creating their own.

- [ ] **Send the kickoff materials 48 hours ahead.** Share `docs/humans/kickoff-deck.html` with
  the environment choice (team workspace or Free Edition), the code-access choice (GitHub fork
  or ZIP upload), and the Free Edition constraints above. Note that all work happens in the
  workspace UI; there is no local terminal.

### Open questions for the maintainer

- Confirm the current Free Edition signup URL and the exact "Git folder" and "Import" UI labels
  in the workshop workspace release (labels drift between versions).
- Decide and document whether team-workspace participants each create their own Lakebase project
  or share one, and pre-create the shared project if you choose that path.

---

## Day-of quick reference

| If this fails | Fallback |
|---|---|
| Genie Code unavailable | Open `solutions/<domain>/<module>.py` directly; grading is unchanged |
| Foundation Model throttling (HTTP 429) | Stagger cohorts through `04_metadata`; Claude is pay-per-token only, so there is no throughput to raise |
| `databricks-claude-sonnet-4-6` absent | Set another endpoint via the `04_metadata` `model_endpoint` widget, or use the no-PyPI manual fallback |
| Synced table will not come online | Check sync pipeline logs; recreate the table; confirm the gold table has rows |
| App returns nothing | Start the app (`databricks apps start <app_name>`) and confirm the synced table is online |
| Non-admin cannot create a Lakebase project | Target the pre-created shared project |
| Participant cannot link GitHub | ZIP download and Workspace Import |
| Partner-powered AI is off (CSP workspace) | Admin enables it before 2026-11-01; core Genie Code still works via Databricks-hosted models |

---

## Sources

Feature lifecycle and default-enablement facts above were verified with Databricks Genie
against current documentation on 2026-09-23:

- Lakebase, synced tables, and project permissions: Databricks docs, Lakebase (`oltp`) section.
- Lakebase Change Data Feed (Public Preview) and Previews management: Databricks docs, admin
  workspace settings.
- Partner-powered AI features (default-on, CSP exception, 2026-11-01 sunset): Databricks docs,
  Databricks AI assistive features.
- Genie Code and Genie Agents lifecycle and Free Edition availability: Databricks docs, Genie
  Code / Genie Agents and Free Edition pages.
- Databricks Apps and Free Edition limits: Databricks docs, Databricks Apps and Free Edition
  limitations.
- `databricks-claude-sonnet-4-6` availability: Databricks docs, Foundation Model APIs supported
  models.
