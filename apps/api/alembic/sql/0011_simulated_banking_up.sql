ALTER TABLE public.receipts DROP CONSTRAINT receipts_method_check;
ALTER TABLE public.receipts ADD CONSTRAINT receipts_method_check
  CHECK (method IN ('CHECK', 'CASH', 'SECURITY_DEPOSIT_CHECK', 'SECURITY_DEPOSIT_CASH', 'ZELLE', 'VENMO'));
ALTER TABLE public.payee_destinations ADD COLUMN channel text NOT NULL DEFAULT 'ZELLE'
  CHECK (channel IN ('ZELLE', 'VENMO'));
ALTER TABLE public.step_up_events DROP CONSTRAINT step_up_events_method_check;
ALTER TABLE public.step_up_events ADD CONSTRAINT step_up_events_method_check
  CHECK (method IN ('LOCAL_DEV_PASSWORD', 'SIMULATED_APPROVAL'));

CREATE TABLE public.simulated_bank_accounts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  next_outcome text NOT NULL DEFAULT 'settle' CHECK (next_outcome IN ('settle', 'timeout', 'fail')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, property_id),
  FOREIGN KEY (organization_id, id) REFERENCES public.bank_accounts (organization_id, id),
  FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

CREATE TABLE public.simulated_bank_transactions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  account_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('RECEIPT', 'PAYOUT')),
  channel text NOT NULL CHECK (channel IN ('ZELLE', 'VENMO')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  status text NOT NULL CHECK (status IN ('SETTLED', 'FAILED')),
  reference text NOT NULL,
  item_id uuid,
  receipt_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  UNIQUE (organization_id, id),
  UNIQUE (organization_id, item_id),
  UNIQUE (organization_id, receipt_id),
  UNIQUE (organization_id, account_id, kind, reference),
  CHECK ((kind = 'RECEIPT' AND receipt_id IS NOT NULL AND item_id IS NULL)
    OR (kind = 'PAYOUT' AND item_id IS NOT NULL AND receipt_id IS NULL)),
  FOREIGN KEY (organization_id, account_id) REFERENCES public.simulated_bank_accounts (organization_id, id),
  FOREIGN KEY (organization_id, item_id) REFERENCES public.distribution_items (organization_id, id),
  FOREIGN KEY (organization_id, receipt_id) REFERENCES public.receipts (organization_id, id)
);

ALTER TABLE public.simulated_bank_accounts OWNER TO grok_owner;
ALTER TABLE public.simulated_bank_transactions OWNER TO grok_owner;
ALTER TABLE public.simulated_bank_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.simulated_bank_accounts FORCE ROW LEVEL SECURITY;
ALTER TABLE public.simulated_bank_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.simulated_bank_transactions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.simulated_bank_accounts
  USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY tenant_isolation ON public.simulated_bank_transactions
  USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY actor_scope ON public.simulated_bank_accounts AS RESTRICTIVE
  USING (public.app_actor_is_staff()) WITH CHECK (public.app_actor_is_staff());
CREATE POLICY actor_scope ON public.simulated_bank_transactions AS RESTRICTIVE
  USING (public.app_actor_is_staff()) WITH CHECK (public.app_actor_is_staff());
REVOKE ALL ON public.simulated_bank_accounts, public.simulated_bank_transactions FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON public.simulated_bank_accounts TO grok_app;
GRANT SELECT, INSERT ON public.simulated_bank_transactions TO grok_app;
