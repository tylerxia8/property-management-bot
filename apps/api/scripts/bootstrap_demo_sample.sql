-- Roles and the single demo database. Passwords come from psql variables.
-- This script creates grok_demo_sample and no other application database.
\set ON_ERROR_STOP on

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_owner') THEN
    CREATE ROLE grok_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_app') THEN
    CREATE ROLE grok_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_auth') THEN
    CREATE ROLE grok_auth NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_posting') THEN
    CREATE ROLE grok_posting NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grok_migrator') THEN
    CREATE ROLE grok_migrator NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
  END IF;
END
$$;

ALTER ROLE grok_owner NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
ALTER ROLE grok_app LOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT PASSWORD :'app_password';
ALTER ROLE grok_auth NOLOGIN NOSUPERUSER BYPASSRLS NOINHERIT;
ALTER ROLE grok_posting NOLOGIN NOSUPERUSER NOBYPASSRLS NOINHERIT;
ALTER ROLE grok_migrator LOGIN SUPERUSER PASSWORD :'migrator_password';

REVOKE grok_owner FROM grok_app;
REVOKE grok_auth FROM grok_app;
REVOKE grok_migrator FROM grok_app;
REVOKE grok_posting FROM grok_app;

SELECT format('CREATE DATABASE %I OWNER grok_owner', 'grok_demo_sample')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'grok_demo_sample')
\gexec

GRANT CONNECT ON DATABASE grok_demo_sample TO grok_app;
