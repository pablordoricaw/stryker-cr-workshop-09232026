#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["deltalake==1.2.1", "pyarrow==21.0.0", "reportlab==4.4.4"]
# ///
"""Generate the deterministic, synthetic ITSM workshop dataset."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
from deltalake import write_deltalake
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "itsm"
CLASSES = ("incident_report", "post_incident_review", "change_request", "kb_article_sop", "other")
ROWS = 3000

def _pdf(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter, invariant=1, pageCompression=1)
    pdf.setTitle(title); pdf.setAuthor("Synthetic Stryker Databricks Workshop")
    pdf.setFont("Helvetica-Bold", 17); pdf.drawString(48, 744, title)
    pdf.setFont("Helvetica", 10); y = 710
    for line in lines:
        pdf.drawString(48, y, line); y -= 22
    pdf.save()

def _document_lines(kind: str, n: int) -> list[str]:
    # The five incident-report documents deliberately reference a subset of the
    # ticket lifecycle's conformed incident IDs, enabling a real gold join.
    incident = f"INC-{202600000 + n - 1:07d}"
    if kind == "incident_report": return [f"Incident ID: {incident}", "Priority: P1", "Service: Patient Operations Portal", "Configuration Item: svc-patient-portal", "Opened: 2026-04-14T08:00:00Z", "Resolved: 2026-04-14T12:30:00Z", "Impact: Clinicians could not access scheduling."]
    if kind == "post_incident_review": return [f"Post-Incident Review: {incident}", "Root cause: expired OAuth signing certificate", "Severity: SEV-1", "Corrective action: automate certificate rotation", "Owner team: Digital Operations", "Review date: 2026-04-16"]
    if kind == "change_request": return [f"Change ID: CHG-{202600+n:07d}", "Service: Patient Operations Portal", "Risk: medium", "Implementation window: 2026-05-10T02:00:00Z", "Rollback plan: restore previous certificate", "Approval status: approved"]
    if kind == "kb_article_sop": return [f"KB Article: KB-{1000+n}", "Title: Rotate Patient Portal OAuth certificate", "Applies to: svc-patient-portal", "Step 1: generate and validate certificate", "Step 2: update secret and restart gateway", "Escalation: Digital Operations on-call"]
    return [f"Operations memo {n}", "Facilities maintenance notice", "Reference: OPS-MEMO", "This memo is not an incident, change, review, or knowledge article."]

def _rows() -> list[dict[str, object]]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc); rows=[]
    for i in range(ROWS):
        opened = start + timedelta(hours=i * 2)
        priority = ("P1", "P2", "P3", "P4")[i % 4]
        hours = (4.5 if priority == "P1" else 2.0 if priority == "P2" else 1.0) + (i % 7) / 10
        resolved = opened + timedelta(hours=hours)
        service = ("Patient Operations Portal", "Order Management", "Identity Gateway")[i % 3]
        ci = ("svc-patient-portal", "svc-order-mgmt", "svc-identity-gateway")[i % 3]
        ticket_id = f"INC-{202600000+i:07d}"
        rows.append({"ticket_id":ticket_id,"incident_id":ticket_id,"opened_at":opened.isoformat(),"resolved_at":resolved.isoformat(),"priority":priority,"status":"resolved","assignment_group":("Digital Operations" if i%3==0 else "Service Desk"),"service":service,"configuration_item":ci,"category":("authentication" if i%3==2 else "availability"),"resolution_hours":round(hours,2),"sla_breached":priority=="P1" and i%5==0,"root_cause_code":("certificate_expiry" if i%17==0 else "application_error"),"source_updated_at":resolved.isoformat()})
    return rows

def _write(target: Path) -> None:
    docs=target/"documents"; manifest=[]
    for kind in CLASSES:
        for n in range(1,6):
            name=f"{kind}_{n:02d}.pdf"; _pdf(docs/kind/name, kind.replace("_"," ").title(), _document_lines(kind,n)); manifest.append((name,kind,kind))
    with (docs/"document_manifest.csv").open("w",newline="") as f:
        w=csv.writer(f, lineterminator="\n"); w.writerow(["filename","source_class","document_subtype"]); w.writerows(manifest)
    rows=_rows(); txn=target/"transactional"; lake=txn/"lakebase"; lake.mkdir(parents=True,exist_ok=True)
    fields=list(rows[0]);
    with (lake/"service_tickets.csv").open("w",newline="") as f: w=csv.DictWriter(f,fields,lineterminator="\n"); w.writeheader(); w.writerows(rows)
    with (lake/"cmdb_configuration_items.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,["configuration_item","service","environment","owner_team","criticality"],lineterminator="\n"); w.writeheader(); w.writerows([{"configuration_item":"svc-patient-portal","service":"Patient Operations Portal","environment":"production","owner_team":"Digital Operations","criticality":"critical"},{"configuration_item":"svc-order-mgmt","service":"Order Management","environment":"production","owner_team":"Service Desk","criticality":"high"},{"configuration_item":"svc-identity-gateway","service":"Identity Gateway","environment":"production","owner_team":"Digital Operations","criticality":"critical"}])
    (lake/"schema.sql").write_text("CREATE SCHEMA IF NOT EXISTS itsm_seed;\nCREATE TABLE IF NOT EXISTS itsm_seed.service_tickets (ticket_id varchar(20) PRIMARY KEY, incident_id varchar(20) NOT NULL UNIQUE, opened_at timestamptz NOT NULL, resolved_at timestamptz NOT NULL, priority varchar(2) NOT NULL, status varchar(20) NOT NULL, assignment_group varchar(80) NOT NULL, service varchar(100) NOT NULL, configuration_item varchar(100) NOT NULL, category varchar(60) NOT NULL, resolution_hours numeric(8,2) NOT NULL, sla_breached boolean NOT NULL, root_cause_code varchar(80) NOT NULL, source_updated_at timestamptz NOT NULL);\nALTER TABLE itsm_seed.service_tickets REPLICA IDENTITY FULL;\n")
    (lake/"load.sql").write_text("\\set ON_ERROR_STOP on\nTRUNCATE itsm_seed.service_tickets;\n\\copy itsm_seed.service_tickets FROM 'data/itsm/transactional/lakebase/service_tickets.csv' WITH (FORMAT csv, HEADER true);\n")
    delta = txn / "delta" / "service_tickets"
    write_deltalake(str(delta), pa.Table.from_pylist(rows), mode="overwrite", configuration={"delta.enableChangeDataFeed":"true"})
    generated = next(delta.glob("*.parquet")); fixed = delta / "part-00000-itsm-tickets.c000.snappy.parquet"
    generated.rename(fixed)
    log = delta / "_delta_log" / "00000000000000000000.json"
    rewritten=[]
    for line in log.read_text().splitlines():
        entry=json.loads(line)
        if "add" in entry:
            entry = {"add": {"path": fixed.name, "partitionValues": {}, "size": fixed.stat().st_size, "modificationTime": 1775044800000, "dataChange": True}}
        if "metaData" in entry:
            entry["metaData"]["id"] = "00000000-0000-0000-0000-0000000014sm"
            entry["metaData"]["createdTime"] = 1775044800000
        if "commitInfo" in entry:
            entry = {"commitInfo": {"timestamp": 1775044800000, "operation": "WRITE", "operationParameters": {"mode": "Overwrite"}, "engineInfo": "itsm-generator"}}
        rewritten.append(json.dumps(entry, separators=(",", ":")))
    log.write_text("\n".join(rewritten)+"\n")
    hashes=[]
    for p in sorted(txn.rglob("*")):
        if p.is_file() and p.name != "checksums.sha256": hashes.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(txn)}")
    (txn/"checksums.sha256").write_text("\n".join(hashes)+"\n")

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--check-reproducible",action="store_true"); p.add_argument("--validate-only",action="store_true"); a=p.parse_args()
    if a.check_reproducible:
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            _write(Path(one)/"itsm"); _write(Path(two)/"itsm")
            first = {x.relative_to(Path(one)/"itsm"):x.read_bytes() for x in (Path(one)/"itsm").rglob("*") if x.is_file()}
            second = {x.relative_to(Path(two)/"itsm"):x.read_bytes() for x in (Path(two)/"itsm").rglob("*") if x.is_file()}
            different = [str(name) for name in first if first[name] != second[name]]
            assert not different, f"non-reproducible artifacts: {different}"
        return
    if not a.validate_only:
        # Keep hand-authored dataset documentation while replacing generated data.
        shutil.rmtree(OUT / "documents", ignore_errors=True)
        shutil.rmtree(OUT / "transactional", ignore_errors=True)
        _write(OUT)
    assert len(list((OUT/"documents").rglob("*.pdf"))) == 25
    assert len(list(csv.DictReader((OUT/"transactional/lakebase/service_tickets.csv").open()))) == ROWS
if __name__ == "__main__": main()
