\set ON_ERROR_STOP on
BEGIN;
TRUNCATE TABLE finance_seed.sales_transactions;
\copy finance_seed.sales_transactions (transaction_id, order_id, sale_date, posting_timestamp, customer_id, customer_name, customer_type, facility_state, sales_region, sales_rep_id, product_sku, product_family, procedure_category, units, unit_price, gross_sales, discount_pct, discount_amount, net_sales, cost_of_goods, gross_margin, currency, sales_channel, contract_id, purchase_order_number, invoice_number, payment_status, source_updated_at) FROM 'data/finance/transactional/lakebase/sales_transactions.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
COMMIT;
