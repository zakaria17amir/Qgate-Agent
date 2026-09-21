-- migrate:up
CREATE SCHEMA IF NOT EXISTS qgate;

-- migrate:down
DROP SCHEMA IF EXISTS qgate;
