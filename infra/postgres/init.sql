-- Amakuru Phase 0: database roles for RLS.
-- The application connects as amakuru_app, which cannot bypass Row Level Security.
-- Migrations run as the superuser (POSTGRES_USER) during setup.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'amakuru_app') THEN
    CREATE ROLE amakuru_app LOGIN PASSWORD 'change-me-app';
  END IF;
END
$$;

-- Application role must never bypass RLS.
ALTER ROLE amakuru_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

GRANT CONNECT ON DATABASE amakuru TO amakuru_app;
GRANT USAGE ON SCHEMA public TO amakuru_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO amakuru_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO amakuru_app;
