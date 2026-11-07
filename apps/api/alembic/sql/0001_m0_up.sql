-- M0 foundation. No ledger, payment, screening, or maintenance tables.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'grok_app' AND rolsuper = false AND rolbypassrls = false
  ) THEN
    RAISE EXCEPTION 'grok_app must exist as NOSUPERUSER NOBYPASSRLS before this migration';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'grok_owner' AND rolsuper = false AND rolbypassrls = false
  ) THEN
    RAISE EXCEPTION 'grok_owner must exist as NOSUPERUSER NOBYPASSRLS before this migration';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'grok_auth' AND rolsuper = false AND rolbypassrls = true AND rolcanlogin = false
  ) THEN
    RAISE EXCEPTION 'grok_auth must exist as NOLOGIN BYPASSRLS before this migration';
  END IF;
END
$$;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.reject_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'append-only table % cannot be updated or deleted', TG_TABLE_NAME
    USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION public.redact_jsonb(input jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  key text;
  value jsonb;
  element jsonb;
  result jsonb;
  sensitive constant text[] := ARRAY[
    'password', 'secret', 'token', 'access_token', 'refresh_token', 'authorization',
    'api_key', 'account_number', 'routing_number', 'door_code', 'signed_url', 'ssn',
    'email', 'phone', 'contact_value', 'ciphertext', 'dev_password_hash', 'cookie',
    'set-cookie', 'session_secret', 'encryption_key'
  ];
BEGIN
  IF input IS NULL THEN
    RETURN NULL;
  END IF;
  IF jsonb_typeof(input) = 'object' THEN
    result := '{}'::jsonb;
    FOR key, value IN SELECT * FROM jsonb_each(input)
    LOOP
      IF lower(key) = ANY (sensitive) THEN
        result := result || jsonb_build_object(key, '[REDACTED]'::text);
      ELSE
        result := result || jsonb_build_object(key, public.redact_jsonb(value));
      END IF;
    END LOOP;
    RETURN result;
  ELSIF jsonb_typeof(input) = 'array' THEN
    result := '[]'::jsonb;
    FOR element IN SELECT jsonb_array_elements(input)
    LOOP
      result := result || jsonb_build_array(public.redact_jsonb(element));
    END LOOP;
    RETURN result;
  ELSE
    RETURN input;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.redact_audit_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.before_state := public.redact_jsonb(NEW.before_state);
  NEW.after_state := public.redact_jsonb(NEW.after_state);
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.redact_outbox_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.payload := public.redact_jsonb(NEW.payload);
  RETURN NEW;
END;
$$;

CREATE TABLE public.organizations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  name text NOT NULL,
  settings jsonb NOT NULL DEFAULT '{}'::jsonb,
  default_timezone text,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT organizations_id_matches_tenant CHECK (organization_id = id),
  CONSTRAINT organizations_settings_object CHECK (jsonb_typeof(settings) = 'object'),
  CONSTRAINT organizations_org_id_unique UNIQUE (organization_id, id)
);

CREATE TABLE public.users (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  issuer text NOT NULL,
  subject text NOT NULL,
  display_name text NOT NULL,
  dev_password_hash text,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT users_issuer_subject_present CHECK (length(issuer) > 0 AND length(subject) > 0),
  CONSTRAINT users_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT users_issuer_subject_unique UNIQUE (organization_id, issuer, subject),
  CONSTRAINT users_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

COMMENT ON COLUMN public.users.dev_password_hash IS
  'Dev/test scrypt-compatible pgcrypto hash. A stored hash does not enable production login.';

CREATE TABLE public.role_grants (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  role text NOT NULL,
  resource_type text,
  resource_id uuid,
  active_from timestamptz NOT NULL,
  active_until timestamptz,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT role_grants_role_known CHECK (role IN (
    'organization_administrator', 'property_manager', 'accounting_staff', 'owner',
    'tenant', 'prospect', 'contractor', 'ai_service', 'worker'
  )),
  CONSTRAINT role_grants_scope_pair CHECK (
    (resource_type IS NULL AND resource_id IS NULL)
    OR (resource_type IS NOT NULL AND resource_id IS NOT NULL)
  ),
  CONSTRAINT role_grants_active_window CHECK (active_until IS NULL OR active_until > active_from),
  CONSTRAINT role_grants_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT role_grants_user_same_org_fkey
    FOREIGN KEY (organization_id, user_id) REFERENCES public.users (organization_id, id)
);

CREATE TABLE public.parties (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  display_name text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('person', 'company')),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT parties_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT parties_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

CREATE TABLE public.contacts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  party_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('email', 'phone', 'other')),
  ciphertext bytea NOT NULL,
  nonce bytea NOT NULL,
  key_version integer NOT NULL CHECK (key_version > 0),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT contacts_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT contacts_party_same_org_fkey
    FOREIGN KEY (organization_id, party_id) REFERENCES public.parties (organization_id, id)
);

CREATE TABLE public.properties (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  address_line1 text NOT NULL,
  address_line2 text,
  city text NOT NULL,
  region text NOT NULL,
  postal_code text NOT NULL,
  country_code char(2) NOT NULL CHECK (country_code ~ '^[A-Z]{2}$'),
  timezone text NOT NULL CHECK (length(timezone) > 0),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_by uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT properties_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT properties_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id),
  CONSTRAINT properties_created_by_same_org_fkey
    FOREIGN KEY (organization_id, created_by) REFERENCES public.users (organization_id, id)
);

CREATE TABLE public.units (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  label text NOT NULL CHECK (length(label) BETWEEN 1 AND 80),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT units_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT units_label_per_property UNIQUE (organization_id, property_id, label),
  CONSTRAINT units_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

CREATE TABLE public.audit_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  actor_id uuid,
  actor_type text NOT NULL CHECK (actor_type IN ('user', 'system')),
  action text NOT NULL,
  target_type text NOT NULL,
  target_id uuid,
  target_version bigint,
  reason text,
  request_id text,
  before_state jsonb,
  after_state jsonb,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT audit_events_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT audit_events_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id),
  CONSTRAINT audit_events_actor_same_org_fkey
    FOREIGN KEY (organization_id, actor_id) REFERENCES public.users (organization_id, id)
);

CREATE TABLE public.outbox_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  dedup_key text NOT NULL,
  property_id uuid,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DISPATCHED', 'FAILED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT outbox_events_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT outbox_events_dedup UNIQUE (organization_id, dedup_key),
  CONSTRAINT outbox_events_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id),
  CONSTRAINT outbox_events_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

CREATE TABLE public.inbox_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  provider text NOT NULL,
  provider_event_id text NOT NULL,
  payload_ciphertext bytea NOT NULL,
  payload_nonce bytea NOT NULL,
  key_version integer NOT NULL CHECK (key_version > 0),
  received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT inbox_events_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT inbox_events_provider_event UNIQUE (organization_id, provider, provider_event_id),
  CONSTRAINT inbox_events_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

CREATE TABLE public.idempotency_records (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  key text NOT NULL CHECK (length(key) BETWEEN 1 AND 200),
  request_hash text NOT NULL,
  response_status integer NOT NULL CHECK (response_status BETWEEN 100 AND 599),
  response_body jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT idempotency_records_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT idempotency_org_key UNIQUE (organization_id, key),
  CONSTRAINT idempotency_records_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

CREATE INDEX properties_org_created_idx ON public.properties (organization_id, created_at, id);
CREATE INDEX units_org_property_created_idx ON public.units (organization_id, property_id, created_at, id);
CREATE INDEX users_issuer_subject_idx ON public.users (issuer, subject);
CREATE INDEX audit_events_org_created_idx ON public.audit_events (organization_id, created_at);
CREATE INDEX outbox_events_org_status_idx ON public.outbox_events (organization_id, status, created_at);

CREATE TRIGGER trg_organizations_updated BEFORE UPDATE ON public.organizations
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON public.users
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_role_grants_updated BEFORE UPDATE ON public.role_grants
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_parties_updated BEFORE UPDATE ON public.parties
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_contacts_updated BEFORE UPDATE ON public.contacts
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_properties_updated BEFORE UPDATE ON public.properties
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_units_updated BEFORE UPDATE ON public.units
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_outbox_updated BEFORE UPDATE ON public.outbox_events
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_audit_redact BEFORE INSERT ON public.audit_events
  FOR EACH ROW EXECUTE FUNCTION public.redact_audit_row();
CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON public.audit_events
  FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();
CREATE TRIGGER trg_outbox_redact BEFORE INSERT OR UPDATE ON public.outbox_events
  FOR EACH ROW EXECUTE FUNCTION public.redact_outbox_row();
CREATE TRIGGER trg_inbox_append_only BEFORE UPDATE OR DELETE ON public.inbox_events
  FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();
CREATE TRIGGER trg_idempotency_append_only BEFORE UPDATE OR DELETE ON public.idempotency_records
  FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

CREATE OR REPLACE FUNCTION public.app_local_login(p_issuer text, p_subject text, p_password text)
RETURNS TABLE (
  user_id uuid,
  organization_id uuid,
  display_name text,
  role text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT u.id, u.organization_id, u.display_name, g.role
  FROM public.users AS u
  JOIN public.role_grants AS g
    ON g.organization_id = u.organization_id
   AND g.user_id = u.id
  WHERE u.issuer = p_issuer
    AND u.subject = p_subject
    AND u.dev_password_hash IS NOT NULL
    AND u.dev_password_hash = public.crypt(p_password, u.dev_password_hash)
    AND g.resource_type IS NULL
    AND g.resource_id IS NULL
    AND g.active_from <= clock_timestamp()
    AND (g.active_until IS NULL OR g.active_until > clock_timestamp());
$$;

REVOKE ALL ON FUNCTION public.app_local_login(text, text, text) FROM PUBLIC;
ALTER FUNCTION public.app_local_login(text, text, text) OWNER TO grok_auth;
GRANT EXECUTE ON FUNCTION public.app_local_login(text, text, text) TO grok_app;
GRANT SELECT ON public.users, public.role_grants TO grok_auth;

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'organizations', 'users', 'role_grants', 'parties', 'contacts', 'properties',
    'units', 'audit_events', 'outbox_events', 'inbox_events', 'idempotency_records'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO grok_owner', table_name);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON public.%I', table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON public.%I '
      'USING (organization_id = NULLIF(current_setting(''app.organization_id'', true), '''')::uuid) '
      'WITH CHECK (organization_id = NULLIF(current_setting(''app.organization_id'', true), '''')::uuid)',
      table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
  END LOOP;
END
$$;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO grok_app;

GRANT SELECT ON public.organizations TO grok_app;
GRANT SELECT (
  id, organization_id, issuer, subject, display_name, version, created_at, updated_at
) ON public.users TO grok_app;
GRANT SELECT ON public.role_grants TO grok_app;
GRANT SELECT, INSERT ON public.parties TO grok_app;
GRANT SELECT, INSERT ON public.contacts TO grok_app;
GRANT SELECT, INSERT, UPDATE ON public.properties TO grok_app;
GRANT SELECT, INSERT, UPDATE ON public.units TO grok_app;
GRANT SELECT, INSERT ON public.audit_events TO grok_app;
GRANT SELECT, INSERT ON public.outbox_events TO grok_app;
GRANT SELECT, INSERT ON public.inbox_events TO grok_app;
GRANT SELECT, INSERT ON public.idempotency_records TO grok_app;
