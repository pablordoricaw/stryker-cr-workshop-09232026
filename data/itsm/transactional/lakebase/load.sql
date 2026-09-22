\set ON_ERROR_STOP on
TRUNCATE itsm_seed.service_tickets;
\copy itsm_seed.service_tickets FROM 'data/itsm/transactional/lakebase/service_tickets.csv' WITH (FORMAT csv, HEADER true);
