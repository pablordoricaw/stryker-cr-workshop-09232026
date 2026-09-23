\set ON_ERROR_STOP on
BEGIN;
TRUNCATE TABLE security_seed.scan_findings;
\copy security_seed.scan_findings (finding_id, scan_id, scan_date, detected_timestamp, asset_id, asset_name, asset_type, environment, business_unit, owner_team, cve_id, vulnerability_title, vulnerability_category, severity, cvss_score, cvss_vector, status, first_detected_date, age_days, remediation_hours, asset_value_at_risk, weighted_risk, remediation_sla_days, exploit_available, detection_source, source_updated_at) FROM 'data/security/transactional/lakebase/scan_findings.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
COMMIT;
