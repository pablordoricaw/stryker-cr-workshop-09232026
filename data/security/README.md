# Security reference data

This entirely synthetic dataset gives the infrastructure-security workshop 25
security PDFs and 3,000 vulnerability-scan findings. No real company, customer,
system, or personal data is present. Fixed seed `20260923` makes every generated
byte reproducible.

## Contents

- `documents/` has five two-page PDFs in each ground-truth class directory and
  `document_manifest.csv` records the expected class and subtype. The classes are
  `vulnerability_scan`, `cve_advisory`, `pentest_report`,
  `cloud_posture_finding`, and `other`. Layouts and labels vary; the `other`
  examples (security policy, IR runbook, risk-acceptance memo, change notice,
  awareness bulletin) deliberately mention CVEs, scans, and remediation so
  classification cannot rely on one keyword.
- `transactional/delta/scan_findings/` is a readable Delta v0 fallback table with
  Change Data Feed enabled in its table properties.
- `transactional/lakebase/` has the same 3,000 rows as CSV, PostgreSQL DDL in
  `schema.sql`, and an idempotent psql loader in `load.sql`.
- `transactional/checksums.sha256` covers every generated artifact.

The findings span October 2025 through mid-September 2026. Asset, CVE, and
severity mix are intentionally skewed, and Production assets receive a heavier
share of **Open** critical findings during a January–March 2026 remediation
backlog. This gives later exercises a traceable "production critical backlog"
story rather than flat random data.

Each finding carries a `cve_id`. Fifty distinct CVEs appear; five of them
(`CVE-2026-31847`, `CVE-2026-20415`, `CVE-2025-48291`, `CVE-2026-10022`,
`CVE-2025-53914`) ship a `cve_advisory` PDF, so
`scan_findings.cve_id` joins the extracted `silver_cve_advisory.cve_id` in the
gold layer exactly the way Finance's `contract_id` joins `agreement_id`. Every
documented CVE is guaranteed to appear in the findings, so the gold
document-enrichment join is never empty.

## Re-run and validate

Run from the repository root. `uv` reads the maintainer-only script metadata and
creates an isolated environment; no Databricks workspace or database is used.

```bash
uv run --script generators/security/generate.py
uv run --script generators/security/generate.py --validate-only
uv run --script generators/security/generate.py --check-reproducible
```

The last command generates into two temporary directories, reads every PDF and
Delta table, parses the PostgreSQL DDL, checks the CVE/severity/weighted-risk
arithmetic, confirms every documented CVE appears in the findings, and requires
byte-identical SHA-256 hashes.

## Loading either transactional path

Delta fallback (after copying the committed directory to a workspace-accessible
location):

```python
findings = spark.read.format("delta").load("<path>/scan_findings")
```

Lakebase/PostgreSQL, from the repository root using a regular PostgreSQL URL:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f data/security/transactional/lakebase/schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f data/security/transactional/lakebase/load.sql
```

`schema.sql` also sets `REPLICA IDENTITY FULL`, which Lakebase Lakehouse Sync /
CDF requires to capture complete update and delete row images. The CDF path is
a Beta/Preview dependency: a workspace admin must enable it in **Previews**, use
a Lakebase Autoscaling Postgres 17 project, and configure the `security_seed`
schema to sync into the participant's existing Unity Catalog catalog/schema.
Participants without that setup should use the committed Delta fallback.

For Lakebase OAuth connectivity, the same files can be passed through the
Databricks psql wrapper (choose the project and CLI profile explicitly):

```bash
databricks psql --project <PROJECT_ID> --profile <PROFILE> -- \
  -f data/security/transactional/lakebase/schema.sql
databricks psql --project <PROJECT_ID> --profile <PROFILE> -- \
  -f data/security/transactional/lakebase/load.sql
```

`load.sql` truncates and reloads `security_seed.scan_findings`, so it is safe to
repeat for workshop setup. Configure the later Lakebase CDF ingestion before
loading when the initial insert events themselves must be captured.

## Extraction-field contract for issue #6

After `ai_parse_document` and `ai_classify`, issue #6 routes each class to an
`ai_extract` schema with these target fields:

| Expected class | Target fields |
| --- | --- |
| `vulnerability_scan` | `scan_id`, `scanner_name`, `scan_date`, `target_scope`, `authenticated`, `total_findings`, `critical_count`, `high_count`, `medium_count`, `low_count`, `highest_cvss`, `top_findings` (`cve_id`, `asset`, `category`, `cvss`, `status`) |
| `cve_advisory` | `cve_id`, `title`, `published_date`, `last_updated`, `severity`, `cvss_score`, `cvss_vector`, `exploit_observed`, `affected_products`, `recommended_remediation`, `references` |
| `pentest_report` | `engagement_id`, `test_type`, `start_date`, `end_date`, `tester_name`, `overall_risk`, `findings_count`, `exploited_paths` (`attack_path`, `impact`, `related_cve`), `recommendations` |
| `cloud_posture_finding` | `finding_id`, `cloud_provider`, `service`, `control_id`, `benchmark`, `severity`, `region`, `status`, `resource_id`, `first_detected_date`, `remediation_guidance` |
| `other` | `document_subtype`, `document_number`, `document_date`, `owner_or_preparer`, `subject`, `classification`, `referenced_documents` |

Dates use ISO `YYYY-MM-DD`, CVSS scores are numeric (0–10), and CVE identifiers
are copied verbatim as `CVE-YYYY-NNNNN`. The `cve_advisory` class's `cve_id` is
the gold join key, so it must be extracted cleanly and be unique across the five
advisories. Missing fields should remain null, not be inferred from a different
document class.
