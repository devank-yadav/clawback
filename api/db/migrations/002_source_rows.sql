-- Where each seeded row came from in data/: its file, and its row number there (1 is the row after the header).
-- Postgres keeps no row order, and the app reads these tables back in the files' order (api/db/reads.py), so a run
-- on the database sends the agents exactly what a run on the files does. Charges also find their month by file.
-- Safe to run again; on a database seeded before this file, the next `make seed` fills the columns in.

ALTER TABLE charges        ADD COLUMN IF NOT EXISTS source_file text, ADD COLUMN IF NOT EXISTS source_row integer;
ALTER TABLE prior_payments ADD COLUMN IF NOT EXISTS source_file text, ADD COLUMN IF NOT EXISTS source_row integer;
ALTER TABLE store_sales    ADD COLUMN IF NOT EXISTS source_file text, ADD COLUMN IF NOT EXISTS source_row integer;
ALTER TABLE promo_plan     ADD COLUMN IF NOT EXISTS source_file text, ADD COLUMN IF NOT EXISTS source_row integer;
