# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Governed Metric Views · SOLUTION (ITSM)
# MAGIC
# MAGIC This solution creates two Unity Catalog Metric Views in the participant's
# MAGIC existing resolved schema. They are semantic definitions over the #8 gold
# MAGIC tables, not copies of data: `itsm_incident_metrics` provides incident
# MAGIC volume, MTTR, and SLA-breach slices by priority, service, and assignment
# MAGIC group; and `itsm_service_metrics` provides per-service performance KPIs.
# MAGIC No catalog or additional schema is created.
# MAGIC
# MAGIC **Compute requirement:** `WITH METRICS ... version: 1.1` needs DBR 17.2+
# MAGIC and `DESCRIBE ... AS JSON` needs DBR 16.2+, so use DBR 17.2+ overall.

# COMMAND ----------

import os
import sys

_root = os.path.abspath(os.getcwd())
while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        raise RuntimeError("workshop repo root not found; open this notebook inside the cloned workshop Git folder.")
    _root = _parent
if _root not in sys.path:
    sys.path.insert(0, _root)
import workshop
dbutils.widgets.text("catalog","","Catalog (your existing catalog, required)")
dbutils.widgets.text("schema","","Schema (blank = your workshop_<you> schema)")

# COMMAND ----------

me=spark.sql("SELECT current_user()").collect()[0][0]
config=workshop.resolve_config(catalog=dbutils.widgets.get("catalog") or None,domain="itsm",schema=dbutils.widgets.get("schema") or None,identity=me)
incidents=workshop.fully_qualified(config.catalog,config.schema,"gold_incidents")
services=workshop.fully_qualified(config.catalog,config.schema,"gold_service_performance")
incident_metrics=workshop.fully_qualified(config.catalog,config.schema,"itsm_incident_metrics")
service_metrics=workshop.fully_qualified(config.catalog,config.schema,"itsm_service_metrics")
spark.sql(f'''CREATE OR REPLACE VIEW {incident_metrics} WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: "{incidents}"
comment: "ITSM incident volume, SLA and MTTR metrics"
dimensions:
  - name: Priority
    expr: priority
  - name: Service
    expr: service
  - name: Assignment Group
    expr: assignment_group
measures:
  - name: Incident Volume
    expr: COUNT(1)
  - name: MTTR Hours
    expr: AVG(resolution_hours)
  - name: SLA Breach Count
    expr: SUM(CASE WHEN sla_breached THEN 1 ELSE 0 END)
$$''')
spark.sql(f'''CREATE OR REPLACE VIEW {service_metrics} WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: "{services}"
comment: "ITSM service performance metrics"
dimensions:
  - name: Service
    expr: service
  - name: Priority
    expr: priority
measures:
  - name: Incident Volume
    expr: SUM(incident_count)
  - name: MTTR Hours
    expr: AVG(mttr_hours)
  - name: SLA Breach Count
    expr: SUM(sla_breach_count)
$$''')
result=workshop.check("05_metrics",spark=spark,catalog=config.catalog,schema=config.schema,metric_views={"itsm_incident_metrics":{"source_table":"gold_incidents","dimensions":["Priority","Service","Assignment Group"],"measures":["Incident Volume","MTTR Hours","SLA Breach Count"]},"itsm_service_metrics":{"source_table":"gold_service_performance","dimensions":["Service","Priority"],"measures":["Incident Volume","MTTR Hours","SLA Breach Count"]}})
print(result); assert result.passed,result.message
