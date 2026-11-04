CREATE SCHEMA IF NOT EXISTS iceberg.smoke;
DROP TABLE IF EXISTS iceberg.smoke.t;
CREATE TABLE iceberg.smoke.t (id BIGINT, v VARCHAR, dt DATE) WITH (partitioning = ARRAY['dt']);
INSERT INTO iceberg.smoke.t VALUES (1, 'a', DATE '2026-11-01'), (2, 'b', DATE '2026-11-01');
MERGE INTO iceberg.smoke.t t
USING (VALUES (BIGINT '2', 'b2', DATE '2026-11-02'), (BIGINT '3', 'c', DATE '2026-11-02')) AS s (id, v, dt)
  ON t.id = s.id
WHEN MATCHED THEN UPDATE SET v = s.v, dt = s.dt
WHEN NOT MATCHED THEN INSERT (id, v, dt) VALUES (s.id, s.v, s.dt);
SELECT id, v, dt FROM iceberg.smoke.t ORDER BY id;
SELECT count(*) FROM shop.public.orders;
DROP TABLE iceberg.smoke.t;
DROP SCHEMA iceberg.smoke;
