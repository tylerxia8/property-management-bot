ALTER TABLE public.receipts DROP CONSTRAINT receipts_method_check;
ALTER TABLE public.receipts ADD CONSTRAINT receipts_method_check CHECK
  (method IN ('CHECK', 'CASH', 'SECURITY_DEPOSIT_CHECK', 'SECURITY_DEPOSIT_CASH', 'ZELLE', 'VENMO', 'STRIPE_ACH'));
ALTER TABLE public.payee_destinations DROP CONSTRAINT payee_destinations_channel_check;
ALTER TABLE public.payee_destinations ADD CONSTRAINT payee_destinations_channel_check CHECK (channel IN ('ZELLE', 'VENMO', 'STRIPE_ACH'));
ALTER TABLE public.funding_lots ADD COLUMN receipt_id uuid;
ALTER TABLE public.funding_lots ADD FOREIGN KEY (organization_id, receipt_id) REFERENCES public.receipts (organization_id, id);
ALTER TABLE public.invoices DROP CONSTRAINT invoices_status_check;
ALTER TABLE public.invoices ADD CONSTRAINT invoices_status_check CHECK (status IN ('SUBMITTED', 'APPROVED', 'CREDITED', 'PAYMENT_PENDING', 'SETTLED'));

CREATE TABLE public.stripe_properties (
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  bank_account_id uuid NOT NULL,
  PRIMARY KEY (organization_id, property_id),
  FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);
CREATE TABLE public.stripe_recipients (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  party_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  account_id text UNIQUE,
  external_bank_id text,
  destination_id uuid,
  status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'READY')),
  first_attempt_at timestamptz,
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, party_id),
  FOREIGN KEY (organization_id, party_id) REFERENCES public.parties (organization_id, id),
  FOREIGN KEY (organization_id, actor_id) REFERENCES public.users (organization_id, id),
  FOREIGN KEY (organization_id, destination_id) REFERENCES public.payee_destinations (organization_id, id)
);
CREATE TABLE public.stripe_rents (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  lease_id uuid NOT NULL,
  payer_party_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  reference text NOT NULL,
  status text NOT NULL DEFAULT 'NEW' CHECK (status IN ('NEW', 'CHECKOUT', 'PROCESSING', 'AVAILABLE', 'FAILED', 'REVIEW')),
  checkout_id text UNIQUE,
  checkout_url text,
  payment_intent_id text UNIQUE,
  receipt_id uuid,
  fee_cents bigint NOT NULL DEFAULT 0 CHECK (fee_cents >= 0),
  fee_due_cents bigint NOT NULL DEFAULT 0 CHECK (fee_due_cents >= 0 AND fee_due_cents <= fee_cents),
  topup_id text UNIQUE,
  first_attempt_at timestamptz,
  posting_date date NOT NULL,
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, property_id, reference),
  FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  FOREIGN KEY (organization_id, lease_id) REFERENCES public.leases (organization_id, id),
  FOREIGN KEY (organization_id, payer_party_id) REFERENCES public.parties (organization_id, id),
  FOREIGN KEY (organization_id, actor_id) REFERENCES public.users (organization_id, id),
  FOREIGN KEY (organization_id, receipt_id) REFERENCES public.receipts (organization_id, id)
);
CREATE TABLE public.stripe_payout_jobs (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  item_id uuid NOT NULL,
  batch_id uuid NOT NULL,
  approval_id uuid NOT NULL,
  account_id text NOT NULL,
  external_bank_id text NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  posting_date date NOT NULL,
  status text NOT NULL DEFAULT 'QUEUED' CHECK (status IN
    ('QUEUED', 'TRANSFERRING', 'TRANSFERRED', 'PAYING', 'PENDING', 'SETTLED', 'FAILED', 'UNKNOWN', 'BLOCKED')),
  transfer_id text UNIQUE,
  payout_id text UNIQUE,
  transfer_attempt_at timestamptz,
  payout_attempt_at timestamptz,
  lease_until timestamptz,
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  attempt_count integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, item_id),
  FOREIGN KEY (organization_id, actor_id) REFERENCES public.users (organization_id, id),
  FOREIGN KEY (organization_id, item_id) REFERENCES public.distribution_items (organization_id, id),
  FOREIGN KEY (organization_id, batch_id) REFERENCES public.distribution_batches (organization_id, id),
  FOREIGN KEY (organization_id, approval_id) REFERENCES public.distribution_approvals (organization_id, id)
);
CREATE TABLE public.stripe_webhook_events (
  id text PRIMARY KEY,
  organization_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  object_id text NOT NULL,
  provider_object_id text NOT NULL,
  event_type text NOT NULL,
  processed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['stripe_properties', 'stripe_recipients', 'stripe_rents', 'stripe_payout_jobs', 'stripe_webhook_events'] LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO grok_owner', table_name);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON public.%I TO grok_app', table_name);
    EXECUTE format('CREATE POLICY tenant_isolation ON public.%I USING (organization_id = NULLIF(current_setting(''app.organization_id'', true), '''')::uuid) WITH CHECK (organization_id = NULLIF(current_setting(''app.organization_id'', true), '''')::uuid)', table_name);
    EXECUTE format('CREATE POLICY actor_scope ON public.%I AS RESTRICTIVE USING (public.app_actor_is_staff()) WITH CHECK (public.app_actor_is_staff())', table_name);
  END LOOP;
END $$;
CREATE INDEX stripe_payout_jobs_pending ON public.stripe_payout_jobs (available_at) WHERE status NOT IN ('SETTLED', 'FAILED', 'BLOCKED');

CREATE FUNCTION public.app_stripe_service_actor(p_organization_id uuid) RETURNS uuid
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT user_id FROM public.role_grants
  WHERE organization_id = p_organization_id AND role IN ('accounting_staff', 'property_manager')
    AND resource_type IS NULL AND active_from <= clock_timestamp()
    AND (active_until IS NULL OR active_until > clock_timestamp())
  ORDER BY CASE WHEN role = 'accounting_staff' THEN 0 ELSE 1 END, user_id LIMIT 1
$$;
ALTER FUNCTION public.app_stripe_service_actor(uuid) OWNER TO grok_auth;
REVOKE ALL ON FUNCTION public.app_stripe_service_actor(uuid) FROM PUBLIC;
GRANT SELECT ON public.role_grants TO grok_auth;
GRANT EXECUTE ON FUNCTION public.app_stripe_service_actor(uuid) TO grok_app, grok_auth;

CREATE FUNCTION public.app_stripe_worker_scopes() RETURNS TABLE (organization_id uuid, actor_id uuid)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
  SELECT s.organization_id, public.app_stripe_service_actor(s.organization_id) FROM (
    SELECT organization_id FROM public.stripe_payout_jobs WHERE status NOT IN ('SETTLED', 'FAILED', 'BLOCKED') AND available_at <= clock_timestamp()
    UNION SELECT organization_id FROM public.stripe_rents WHERE status IN ('CHECKOUT', 'PROCESSING') AND available_at <= clock_timestamp()
    UNION SELECT organization_id FROM public.stripe_webhook_events WHERE NOT processed
  ) AS s
  LIMIT 100
$$;
ALTER FUNCTION public.app_stripe_worker_scopes() OWNER TO grok_auth;
REVOKE ALL ON FUNCTION public.app_stripe_worker_scopes() FROM PUBLIC;
GRANT SELECT ON public.stripe_payout_jobs TO grok_auth;
GRANT SELECT ON public.stripe_rents, public.stripe_webhook_events TO grok_auth;
GRANT EXECUTE ON FUNCTION public.app_stripe_worker_scopes() TO grok_app;

CREATE FUNCTION public.app_ensure_stripe_chart(p_organization_id uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF p_organization_id IS DISTINCT FROM NULLIF(current_setting('app.organization_id', true), '')::uuid OR NOT public.app_actor_is_staff() THEN
    RAISE EXCEPTION 'staff tenant context required' USING ERRCODE = '42501';
  END IF;
  INSERT INTO public.ledger_accounts (id, organization_id, code, name, normal_balance)
  VALUES (gen_random_uuid(), p_organization_id, '1050', 'Due from management for processing fees', 'DEBIT')
  ON CONFLICT (organization_id, code) DO NOTHING;
END $$;
ALTER FUNCTION public.app_ensure_stripe_chart(uuid) OWNER TO grok_owner;
REVOKE ALL ON FUNCTION public.app_ensure_stripe_chart(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_ensure_stripe_chart(uuid) TO grok_app;
