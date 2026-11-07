DROP TABLE IF EXISTS public.idempotency_records;
DROP TABLE IF EXISTS public.inbox_events;
DROP TABLE IF EXISTS public.outbox_events;
DROP TABLE IF EXISTS public.audit_events;
DROP TABLE IF EXISTS public.contacts;
DROP TABLE IF EXISTS public.units;
DROP TABLE IF EXISTS public.properties;
DROP TABLE IF EXISTS public.role_grants;
DROP TABLE IF EXISTS public.parties;
DROP TABLE IF EXISTS public.users;
DROP TABLE IF EXISTS public.organizations;

DROP FUNCTION IF EXISTS public.app_local_login(text, text, text);
DROP FUNCTION IF EXISTS public.redact_outbox_row();
DROP FUNCTION IF EXISTS public.redact_audit_row();
DROP FUNCTION IF EXISTS public.redact_jsonb(jsonb);
DROP FUNCTION IF EXISTS public.reject_mutation();
DROP FUNCTION IF EXISTS public.set_updated_at();

DROP EXTENSION IF EXISTS pgcrypto;
