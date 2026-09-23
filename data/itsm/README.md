# ITSM reference data

Synthetic, deterministic ITSM/IT-Ops data: 25 PDFs (five each of incident
reports, post-incident reviews, change requests, KB/SOP articles, and Other),
plus 3,000 service-desk ticket lifecycle records and a CMDB configuration-item
seed. The ticket key is `ticket_id`; `bronze_service_tickets` is the domain
bronze table.

Run `uv run --script generators/itsm/generate.py --check-reproducible` to prove
byte reproducibility. Delta fallback is `transactional/delta/service_tickets`;
Postgres/Lakebase seeds are in `transactional/lakebase/`.

The ITSM semantic story is certificate-expiry P1 incidents affecting the
Patient Operations Portal, suitable for MTTR, priority-volume, and SLA-breach
analysis. All records are synthetic.
