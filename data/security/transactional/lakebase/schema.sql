-- Synthetic Lakebase/PostgreSQL source schema. Safe to rerun.
CREATE SCHEMA IF NOT EXISTS security_seed;

CREATE TABLE IF NOT EXISTS security_seed.scan_findings (
finding_id varchar(20) PRIMARY KEY,
    scan_id varchar(40) NOT NULL,
    scan_date date NOT NULL,
    detected_timestamp timestamptz NOT NULL,
    asset_id varchar(20) NOT NULL,
    asset_name varchar(80) NOT NULL,
    asset_type varchar(40) NOT NULL,
    environment varchar(30) NOT NULL,
    business_unit varchar(60) NOT NULL,
    owner_team varchar(60) NOT NULL,
    cve_id varchar(24) NOT NULL,
    vulnerability_title varchar(200) NOT NULL,
    vulnerability_category varchar(60) NOT NULL,
    severity varchar(12) NOT NULL,
    cvss_score numeric(3,1) NOT NULL CHECK (cvss_score BETWEEN 0 AND 10),
    cvss_vector varchar(60) NOT NULL,
    status varchar(20) NOT NULL,
    first_detected_date date NOT NULL,
    age_days integer NOT NULL CHECK (age_days >= 0),
    remediation_hours numeric(8,2) NOT NULL CHECK (remediation_hours >= 0),
    asset_value_at_risk numeric(14,2) NOT NULL CHECK (asset_value_at_risk >= 0),
    weighted_risk numeric(10,2) NOT NULL CHECK (weighted_risk >= 0),
    remediation_sla_days integer NOT NULL CHECK (remediation_sla_days > 0),
    exploit_available boolean NOT NULL,
    detection_source varchar(40) NOT NULL,
    source_updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS scan_findings_scan_date_idx
    ON security_seed.scan_findings (scan_date);
CREATE INDEX IF NOT EXISTS scan_findings_cve_idx
    ON security_seed.scan_findings (cve_id, severity);
CREATE INDEX IF NOT EXISTS scan_findings_source_updated_idx
    ON security_seed.scan_findings (source_updated_at);

-- Required by Lakebase Lakehouse Sync / CDF so updates and deletes carry the
-- complete row image into the Unity Catalog history table.
ALTER TABLE security_seed.scan_findings REPLICA IDENTITY FULL;
