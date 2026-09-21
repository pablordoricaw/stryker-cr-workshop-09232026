"""Tests for workshop.provision — schema + volume only, off-platform.

A recording fake Spark captures the SQL so we can assert exactly what runs
(idempotent, backtick-safe, and never CREATE CATALOG).
"""

from __future__ import annotations

from workshop import ProvisionReport, provision, resolve_config


class RecordingSpark:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def sql(self, query: str):
        self.executed.append(query)
        return None


def test_provisions_schema_then_volume():
    spark = RecordingSpark()
    cfg = resolve_config(catalog="my_catalog", domain="finance", volume="landing")

    report = provision(cfg, spark)

    assert isinstance(report, ProvisionReport)
    assert spark.executed == [
        "CREATE SCHEMA IF NOT EXISTS `my_catalog`.`finance`",
        "CREATE VOLUME IF NOT EXISTS `my_catalog`.`finance`.`landing`",
    ]
    assert report.statements == spark.executed


def test_never_creates_a_catalog():
    spark = RecordingSpark()
    provision(resolve_config(catalog="c", schema="s", volume="v"), spark)
    assert not any("CREATE CATALOG" in stmt for stmt in spark.executed)


def test_statements_are_idempotent_and_backtick_safe():
    spark = RecordingSpark()
    cfg = resolve_config(catalog="stryker-finance", schema="select", volume="my vol")
    provision(cfg, spark)

    for stmt in spark.executed:
        assert "IF NOT EXISTS" in stmt
    # Names with hyphens / reserved words / spaces are backtick-quoted.
    assert "`stryker-finance`.`select`" in spark.executed[0]
    assert "`stryker-finance`.`select`.`my vol`" in spark.executed[1]
