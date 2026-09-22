# Databricks notebook source
# ruff: noqa: F821, I001
# MAGIC %md
# MAGIC # 03 · Gold medallion layer — SOLUTION (ITSM)
# MAGIC `gold_incidents` preserves ticket grain; `gold_service_performance` is the MTTR/SLA serving mart. No catalog is created.

# COMMAND ----------
import os, sys
_root=os.path.abspath(os.getcwd())
while not os.path.isfile(os.path.join(_root,"workshop","__init__.py")): _root=os.path.dirname(_root)
if _root not in sys.path: sys.path.insert(0,_root)
import workshop
from pyspark.sql import functions as F
dbutils.widgets.text("catalog", "", "Catalog (your existing catalog — required)")
dbutils.widgets.dropdown("domain", "itsm", ["itsm"], "Domain")
dbutils.widgets.text("schema", "", "Schema (blank = your workshop_<you> schema)")
me=spark.sql("SELECT current_user()").collect()[0][0]
config=workshop.resolve_config(catalog=dbutils.widgets.get("catalog") or None,domain="itsm",schema=dbutils.widgets.get("schema") or None,identity=me)
bronze=workshop.fully_qualified(config.catalog,config.schema,"bronze_service_tickets")
silver=workshop.fully_qualified(config.catalog,config.schema,"silver_incident_report")
detail=workshop.fully_qualified(config.catalog,config.schema,"gold_incidents")
mart=workshop.fully_qualified(config.catalog,config.schema,"gold_service_performance")

# COMMAND ----------
reports=spark.table(silver).select(F.col("incident_id").alias("report_incident_id"),F.col("path").alias("incident_document_path"),F.col("impact").alias("documented_impact"))
(spark.table(bronze).alias("ticket").join(reports.alias("report"),F.col("ticket.ticket_id")==F.col("report.report_incident_id"),"left").select("ticket.*","report.report_incident_id","report.incident_document_path","report.documented_impact").write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable(detail))
(spark.table(detail).groupBy("service","priority","assignment_group").agg(F.count("ticket_id").alias("incident_count"),F.avg("resolution_hours").alias("mttr_hours"),F.sum(F.when(F.col("sla_breached"),1).otherwise(0)).alias("sla_breach_count"),F.countDistinct("configuration_item").alias("affected_ci_count")).write.format("delta").mode("overwrite").option("overwriteSchema","true").saveAsTable(mart))
spark.sql(f"COMMENT ON TABLE {detail} IS 'ITSM incident fact at ticket grain'")
spark.sql(f"COMMENT ON TABLE {mart} IS 'ITSM service performance mart with MTTR and SLA breaches'")

# COMMAND ----------
result=workshop.check("03_gold",spark=spark,catalog=config.catalog,schema=config.schema,source_table="bronze_service_tickets",document_table="silver_incident_report",detail_table="gold_incidents",mart_table="gold_service_performance",source_key="ticket_id",detail_key="ticket_id",source_group_key="service",document_key="incident_id",detail_document_key="report_incident_id",detail_document_match="incident_document_path",mart_key="service",reconcile_measures=False)
print(result); assert result.passed, result.message
