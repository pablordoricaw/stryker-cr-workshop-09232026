# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Governed Metric Views — SOLUTION (Security)
# MAGIC
# MAGIC This solution creates two Unity Catalog Metric Views in the participant's
# MAGIC existing resolved schema. They are semantic definitions over the #8 gold
# MAGIC tables, not copies of data: `security_findings_metrics` provides exposure
# MAGIC and remediation slices by asset, environment, severity, category, and date;
# MAGIC and `security_cve_metrics` provides per-CVE exposure KPIs. No catalog or
# MAGIC additional schema is created.
# MAGIC
# MAGIC **Compute requirement:** `WITH METRICS ... version: 1.1` needs DBR 17.2+
# MAGIC and `DESCRIBE ... AS JSON` needs DBR 16.2+, so use DBR 17.2+ overall.

# COMMAND ----------

# --- Workshop bootstrap: run this first in every notebook ---
import os, sys
_root = os.path.abspath(os.getcwd())
while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        raise RuntimeError("workshop repo root not found; open this notebook inside the cloned workshop Git folder.")
    _root = _parent
if _root not in sys.path:
    sys.path.insert(0, _root)

import workshop

# COMMAND ----------

dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "security", ["security"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
dbutils.widgets.text("volume", "landing", "UC Volume")

# COMMAND ----------

# Your identity resolves the SAME per-participant workshop_<you> schema 00_setup
# created in the shared team catalog. Leave the schema blank to use it.
me = spark.sql("SELECT current_user()").collect()[0][0]

config = workshop.resolve_config(
    catalog=dbutils.widgets.get("catalog") or None,
    domain=dbutils.widgets.get("domain"),
    schema=dbutils.widgets.get("schema") or None,
    volume=dbutils.widgets.get("volume") or None,
    identity=me,
)
gold_findings = workshop.fully_qualified(config.catalog, config.schema, "gold_findings")
gold_cve_exposure = workshop.fully_qualified(
    config.catalog, config.schema, "gold_cve_exposure"
)
findings_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "security_findings_metrics"
)
cve_metrics = workshop.fully_qualified(
    config.catalog, config.schema, "security_cve_metrics"
)

print(f"Catalog (existing): {config.catalog}")
print(f"Schema: {config.schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Finding-level exposure and remediation metrics

# COMMAND ----------

spark.sql(
    f'''CREATE OR REPLACE VIEW {findings_metrics}
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: "{gold_findings}"
comment: "Governed Security exposure and remediation metrics by asset and severity"
dimensions:
  - name: Scan Date
    expr: scan_date
  - name: Asset Type
    expr: asset_type
  - name: Environment
    expr: environment
  - name: Severity
    expr: severity
  - name: Vulnerability Category
    expr: vulnerability_category
measures:
  - name: Finding Count
    expr: COUNT(1)
  - name: Scan Count
    expr: COUNT(DISTINCT scan_id)
  - name: Affected Assets
    expr: COUNT(DISTINCT asset_id)
  - name: Open Findings
    expr: SUM(CASE WHEN status = 'Open' THEN 1 ELSE 0 END)
  - name: Critical Findings
    expr: SUM(CASE WHEN severity = 'Critical' THEN 1 ELSE 0 END)
  - name: Remediation Hours
    expr: SUM(remediation_hours)
  - name: Value at Risk
    expr: SUM(asset_value_at_risk)
  - name: Average CVSS
    expr: AVG(cvss_score)
$$'''
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. CVE-level exposure metrics

# COMMAND ----------

spark.sql(
    f'''CREATE OR REPLACE VIEW {cve_metrics}
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: "{gold_cve_exposure}"
comment: "Governed Security per-CVE exposure metrics"
dimensions:
  - name: CVE ID
    expr: cve_id
  - name: Severity
    expr: severity
  - name: Vulnerability Category
    expr: vulnerability_category
measures:
  - name: Finding Count
    expr: SUM(finding_count)
  - name: Open Findings
    expr: SUM(open_findings)
  - name: Critical Findings
    expr: SUM(critical_findings)
  - name: Affected Assets
    expr: SUM(affected_assets)
  - name: Remediation Hours
    expr: SUM(remediation_hours)
  - name: Value at Risk
    expr: SUM(asset_value_at_risk)
  - name: Weighted Risk
    expr: SUM(weighted_risk)
$$'''
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Query the metric layer

# COMMAND ----------

display(
    spark.sql(
        f'''SELECT
              `Severity`,
              MEASURE(`Finding Count`) AS finding_count,
              MEASURE(`Open Findings`) AS open_findings,
              MEASURE(`Value at Risk`) AS value_at_risk
            FROM {findings_metrics}
            GROUP BY ALL
            ORDER BY value_at_risk DESC'''
    )
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Checkpoint: `05_metrics`
# MAGIC
# MAGIC The domain-generic check validates each required Metric View by observable
# MAGIC state only. The Security view contracts (source table, dimensions, and
# MAGIC measures) are passed through the `metric_views` extra.

# COMMAND ----------

result = workshop.check(
    "05_metrics",
    spark=spark,
    catalog=config.catalog,
    schema=config.schema,
    metric_views={
        "security_findings_metrics": {
            "source_table": "gold_findings",
            "dimensions": [
                "Scan Date",
                "Asset Type",
                "Environment",
                "Severity",
                "Vulnerability Category",
            ],
            "measures": [
                "Finding Count",
                "Scan Count",
                "Affected Assets",
                "Open Findings",
                "Critical Findings",
                "Remediation Hours",
                "Value at Risk",
                "Average CVSS",
            ],
        },
        "security_cve_metrics": {
            "source_table": "gold_cve_exposure",
            "dimensions": ["CVE ID", "Severity", "Vulnerability Category"],
            "measures": [
                "Finding Count",
                "Open Findings",
                "Critical Findings",
                "Affected Assets",
                "Remediation Hours",
                "Value at Risk",
                "Weighted Risk",
            ],
        },
    },
)
print(result)
assert result.passed, result.message

# COMMAND ----------

# MAGIC %md
# MAGIC ## Stretch — add your own governed metric
# MAGIC
# MAGIC Create another Metric View in this same schema, for example a
# MAGIC business-unit or owner-team exposure metric. Keep the YAML source pointed
# MAGIC at a gold table, choose useful dimensions, and use `MEASURE()` for composed
# MAGIC ratios. Query it with `GROUP BY ALL`; if you want the generic checkpoint to
# MAGIC validate it, pass a matching `metric_views` contract (view name, source
# MAGIC table, dimensions, and measures) to `workshop.check`.
