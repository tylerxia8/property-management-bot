-- Local bootstrap for M0. Passwords here are development credentials, not production secrets.
-- grok_migrator is a superuser because Alembic must bypass RLS.
-- grok_app is the runtime role and must not be a superuser or BYPASSRLS.

\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_migrator') THEN
    CREATE ROLE grok_migrator LOGIN SUPERUSER PASSWORD 'grok_m0_migrator_local_only';
  ELSE
    ALTER ROLE grok_migrator LOGIN SUPERUSER PASSWORD 'grok_m0_migrator_local_only';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_owner') THEN
    CREATE ROLE grok_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  ELSE
    ALTER ROLE grok_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_app') THEN
    CREATE ROLE grok_app LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD 'grok_m0_app_local_only';
  ELSE
    ALTER ROLE grok_app LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD 'grok_m0_app_local_only';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_auth') THEN
    CREATE ROLE grok_auth NOLOGIN NOSUPERUSER BYPASSRLS NOINHERIT;
  ELSE
    ALTER ROLE grok_auth NOLOGIN NOSUPERUSER BYPASSRLS NOINHERIT;
  END IF;
END
$$;

REVOKE grok_owner FROM grok_app;
REVOKE grok_auth FROM grok_app;
REVOKE grok_migrator FROM grok_app;

SELECT format('CREATE DATABASE %I OWNER grok_owner', datname)
FROM (VALUES ('grok_m0_test'), ('grok_m0_migration'), ('grok_m0_e2e')) AS needed(datname)
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE pg_database.datname = needed.datname)
\gexec

GRANT CONNECT ON DATABASE grok_m0_test TO grok_app;
GRANT CONNECT ON DATABASE grok_m0_migration TO grok_app;
GRANT CONNECT ON DATABASE grok_m0_e2e TO grok_app;
