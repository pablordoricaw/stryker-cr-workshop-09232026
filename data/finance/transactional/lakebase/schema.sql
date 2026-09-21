-- Synthetic Lakebase/PostgreSQL source schema. Safe to rerun.
CREATE SCHEMA IF NOT EXISTS finance_seed;

CREATE TABLE IF NOT EXISTS finance_seed.sales_transactions (
transaction_id varchar(20) PRIMARY KEY,
    order_id varchar(20) NOT NULL,
    sale_date date NOT NULL,
    posting_timestamp timestamptz NOT NULL,
    customer_id varchar(20) NOT NULL,
    customer_name varchar(160) NOT NULL,
    customer_type varchar(50) NOT NULL,
    facility_state char(2) NOT NULL,
    sales_region varchar(40) NOT NULL,
    sales_rep_id varchar(20) NOT NULL,
    product_sku varchar(40) NOT NULL,
    product_family varchar(80) NOT NULL,
    procedure_category varchar(80) NOT NULL,
    units integer NOT NULL CHECK (units > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    gross_sales numeric(14,2) NOT NULL CHECK (gross_sales >= 0),
    discount_pct numeric(6,4) NOT NULL CHECK (discount_pct BETWEEN 0 AND 1),
    discount_amount numeric(14,2) NOT NULL CHECK (discount_amount >= 0),
    net_sales numeric(14,2) NOT NULL CHECK (net_sales >= 0),
    cost_of_goods numeric(14,2) NOT NULL CHECK (cost_of_goods >= 0),
    gross_margin numeric(14,2) NOT NULL,
    currency char(3) NOT NULL DEFAULT 'USD',
    sales_channel varchar(30) NOT NULL,
    contract_id varchar(40) NOT NULL,
    purchase_order_number varchar(40) NOT NULL,
    invoice_number varchar(40) NOT NULL UNIQUE,
    payment_status varchar(30) NOT NULL,
    source_updated_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS sales_transactions_sale_date_idx
    ON finance_seed.sales_transactions (sale_date);
CREATE INDEX IF NOT EXISTS sales_transactions_customer_idx
    ON finance_seed.sales_transactions (customer_id, sale_date);
CREATE INDEX IF NOT EXISTS sales_transactions_source_updated_idx
    ON finance_seed.sales_transactions (source_updated_at);
