-- Local dev only. Source system "shop" + the database backing the Iceberg JDBC catalog.
CREATE DATABASE shop;
CREATE DATABASE iceberg_catalog;

-- Trino 483 does not create the Iceberg JDBC catalog tables itself (V1 schema).
\connect iceberg_catalog

CREATE TABLE iceberg_tables (
    catalog_name               VARCHAR(255)  NOT NULL,
    table_namespace            VARCHAR(255)  NOT NULL,
    table_name                 VARCHAR(255)  NOT NULL,
    metadata_location          VARCHAR(1000),
    previous_metadata_location VARCHAR(1000),
    iceberg_type               VARCHAR(5),
    PRIMARY KEY (catalog_name, table_namespace, table_name)
);

CREATE TABLE iceberg_namespace_properties (
    catalog_name   VARCHAR(255)  NOT NULL,
    namespace      VARCHAR(255)  NOT NULL,
    property_key   VARCHAR(255)  NOT NULL,
    property_value VARCHAR(1000),
    PRIMARY KEY (catalog_name, namespace, property_key)
);

\connect shop

CREATE TABLE public.customers (
    customer_id   BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    city          TEXT,
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

INSERT INTO public.customers VALUES
    (101, 'An',   'Hanoi',       '2026-10-01 08:00:00', '2026-10-01 08:00:00'),
    (102, 'Binh', 'Ho Chi Minh', '2026-10-05 09:00:00', '2026-11-02 10:00:00'),
    (103, 'Chi',  'Da Nang',     '2026-10-09 10:00:00', '2026-10-09 10:00:00');

CREATE TABLE public.orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL REFERENCES public.customers (customer_id),
    order_status TEXT NOT NULL,
    total_amount NUMERIC(18, 2) NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    updated_at   TIMESTAMP NOT NULL
);

-- updated_at per day: 2026-11-01 -> 1 row, 2026-11-02 -> 2 rows, 2026-11-03 -> 3 rows.
INSERT INTO public.orders VALUES
    (1, 101, 'paid',      120000.00, '2026-11-01 09:00:00', '2026-11-01 09:30:00'),
    (2, 102, 'shipped',    80000.00, '2026-11-01 11:00:00', '2026-11-02 08:00:00'),
    (3, 103, 'paid',      250000.00, '2026-11-02 14:00:00', '2026-11-02 14:05:00'),
    (4, 101, 'cancelled',  40000.00, '2026-11-02 20:00:00', '2026-11-03 07:00:00'),
    (5, 102, 'paid',       99000.00, '2026-11-03 10:00:00', '2026-11-03 10:01:00'),
    (6, 103, 'created',    15000.00, '2026-11-03 23:00:00', '2026-11-03 23:59:59');
