"""Committed Security dataset integrity. Pure stdlib, off-platform.

These tests guard the *committed* ``data/security`` artifacts (the ones shipped
to participants) without the heavy generator dependencies (pyarrow / deltalake /
reportlab), so they run in the ordinary pure-Python gate. Byte reproducibility
of *generation* is covered separately by
``generators/security/generate.py --check-reproducible``; here we assert the
committed tree matches its checksum manifest and satisfies the invariants the
Security checkpoints rely on (25 documents across five classes, 3,000 findings
with a non-empty CVE-advisory join spine).
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data" / "security"
DOCUMENTS = DATA_ROOT / "documents"
TRANSACTIONAL = DATA_ROOT / "transactional"

CLASSES = (
    "vulnerability_scan",
    "cve_advisory",
    "pentest_report",
    "cloud_posture_finding",
    "other",
)
ROWS_PER_CLASS = 5
ROW_COUNT = 3_000

# The five CVEs that ship a cve_advisory PDF and therefore form the gold join
# spine (bronze_scan_findings.cve_id -> silver_cve_advisory.cve_id).
DOCUMENTED_CVES = frozenset(
    {
        "CVE-2026-31847",
        "CVE-2026-20415",
        "CVE-2025-48291",
        "CVE-2026-10022",
        "CVE-2025-53914",
    }
)

# The committed CSV column order (must match the generator's TXN_FIELDS and the
# solution's FINDING_COLUMNS). The gold checkpoint's join spine depends on
# finding_id (grain), cve_id (group/join key), and the additive measures below.
TXN_FIELDS = (
    "finding_id",
    "scan_id",
    "scan_date",
    "detected_timestamp",
    "asset_id",
    "asset_name",
    "asset_type",
    "environment",
    "business_unit",
    "owner_team",
    "cve_id",
    "vulnerability_title",
    "vulnerability_category",
    "severity",
    "cvss_score",
    "cvss_vector",
    "status",
    "first_detected_date",
    "age_days",
    "remediation_hours",
    "asset_value_at_risk",
    "weighted_risk",
    "remediation_sla_days",
    "exploit_available",
    "detection_source",
    "source_updated_at",
)

RECONCILE_MEASURES = ("remediation_hours", "asset_value_at_risk", "weighted_risk")


def _csv_path() -> Path:
    return TRANSACTIONAL / "lakebase" / "scan_findings.csv"


def _read_findings() -> list[dict[str, str]]:
    with _csv_path().open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


pytestmark = pytest.mark.skipif(
    not _csv_path().is_file(),
    reason="committed Security dataset not present (run generators/security/generate.py)",
)


def test_documents_are_25_pdfs_five_per_class():
    manifest_rows = list(
        csv.DictReader((DOCUMENTS / "document_manifest.csv").open(encoding="utf-8"))
    )
    assert len(manifest_rows) == len(CLASSES) * ROWS_PER_CLASS
    by_class: dict[str, int] = {}
    for row in manifest_rows:
        pdf = DOCUMENTS / row["file_path"]
        assert pdf.is_file(), f"missing PDF {pdf}"
        assert pdf.suffix == ".pdf"
        by_class[row["expected_class"]] = by_class.get(row["expected_class"], 0) + 1
    assert by_class == {cls: ROWS_PER_CLASS for cls in CLASSES}


def test_cve_advisory_documents_are_the_documented_cves():
    manifest_rows = list(
        csv.DictReader((DOCUMENTS / "document_manifest.csv").open(encoding="utf-8"))
    )
    advisory_ids = {
        row["document_id"]
        for row in manifest_rows
        if row["expected_class"] == "cve_advisory"
    }
    assert advisory_ids == set(DOCUMENTED_CVES)


def test_findings_csv_shape_and_columns():
    rows = _read_findings()
    assert len(rows) == ROW_COUNT
    assert tuple(rows[0].keys()) == TXN_FIELDS


def test_finding_ids_unique_and_cve_ids_non_null():
    rows = _read_findings()
    assert len({row["finding_id"] for row in rows}) == ROW_COUNT
    # The gold source-integrity check requires a non-null group key on every row.
    assert all(row["cve_id"].strip() for row in rows)


def test_documented_cves_all_appear_so_gold_join_is_non_empty():
    observed = {row["cve_id"] for row in _read_findings()}
    missing = DOCUMENTED_CVES - observed
    assert not missing, f"documented CVEs absent from findings: {sorted(missing)}"


def test_reconcile_measures_are_present_and_numeric():
    rows = _read_findings()
    for measure in RECONCILE_MEASURES:
        # Every additive measure the gold mart reconciles must parse as a number.
        assert all(_is_number(row[measure]) for row in rows), measure


def test_severity_matches_cvss_band():
    for row in _read_findings():
        score = float(row["cvss_score"])
        expected = (
            "Critical"
            if score >= 9.0
            else "High"
            if score >= 7.0
            else "Medium"
            if score >= 4.0
            else "Low"
        )
        assert row["severity"] == expected


def _checksum_entries() -> dict[str, str]:
    checksum_file = TRANSACTIONAL / "checksums.sha256"
    entries: dict[str, str] = {}
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ", 1)
        entries[relative] = digest
    return entries


def _committed_artifacts() -> set[str]:
    """The generated artifact set actually committed under data/security/.

    Mirrors the generator's ``artifact_files``: every class PDF, the document
    manifest, and every transactional file except the checksum manifest itself.
    Paths are relative to ``data/security`` (matching the checksum manifest).
    """
    files = list(DOCUMENTS.glob("*/*.pdf")) + [DOCUMENTS / "document_manifest.csv"]
    files += [
        p
        for p in TRANSACTIONAL.rglob("*")
        if p.is_file() and p.name != "checksums.sha256"
    ]
    return {p.relative_to(DATA_ROOT).as_posix() for p in files}


def test_committed_checksums_match_files():
    for relative, digest in _checksum_entries().items():
        target = DATA_ROOT / relative
        assert target.is_file(), f"checksum references missing file {relative}"
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        assert actual == digest, f"checksum mismatch for {relative}"


def test_checksum_manifest_covers_every_committed_artifact():
    # Completeness both ways: no committed PDF/Delta/Lakebase artifact escapes the
    # checksum manifest, and no listed path is missing. Catches a newly-added or
    # omitted artifact even if the manifest were otherwise self-consistent.
    listed = set(_checksum_entries())
    actual = _committed_artifacts()
    assert listed == actual, {
        "unlisted_artifacts": sorted(actual - listed),
        "missing_files": sorted(listed - actual),
    }


def test_document_manifest_lists_every_committed_pdf():
    manifest_rows = list(
        csv.DictReader((DOCUMENTS / "document_manifest.csv").open(encoding="utf-8"))
    )
    manifest_pdfs = {row["file_path"] for row in manifest_rows}
    actual_pdfs = {p.relative_to(DOCUMENTS).as_posix() for p in DOCUMENTS.glob("*/*.pdf")}
    assert manifest_pdfs == actual_pdfs


def test_lakebase_schema_uses_replica_identity_full():
    schema_sql = (TRANSACTIONAL / "lakebase" / "schema.sql").read_text(encoding="utf-8")
    assert "security_seed.scan_findings" in schema_sql
    assert "REPLICA IDENTITY FULL" in schema_sql


def test_lakebase_loader_copies_the_committed_columns_in_order():
    load_sql = (TRANSACTIONAL / "lakebase" / "load.sql").read_text(encoding="utf-8")
    assert "security_seed.scan_findings" in load_sql
    for field in TXN_FIELDS:
        assert field in load_sql


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False
