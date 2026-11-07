-- Phase 2 accounting core. No live bank submission.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname = 'grok_posting' AND rolsuper = false AND rolbypassrls = false AND rolcanlogin = false
  ) THEN
    RAISE EXCEPTION 'grok_posting must exist as NOLOGIN NOSUPERUSER NOBYPASSRLS';
  END IF;
END
$$;

CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE public.properties
  ADD COLUMN disbursements_frozen boolean NOT NULL DEFAULT false;

CREATE TABLE public.ledger_accounts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  code text NOT NULL,
  name text NOT NULL,
  normal_balance text NOT NULL CHECK (normal_balance IN ('DEBIT', 'CREDIT')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ledger_accounts_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT ledger_accounts_code_unique UNIQUE (organization_id, code),
  CONSTRAINT ledger_accounts_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

CREATE TABLE public.bank_accounts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  display_name text NOT NULL,
  masked_label text NOT NULL,
  currency char(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT bank_accounts_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT bank_accounts_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

CREATE TABLE public.leases (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  unit_id uuid NOT NULL,
  start_date date NOT NULL,
  end_date date NOT NULL,
  occupancy_period daterange GENERATED ALWAYS AS (daterange(start_date, end_date, '[)')) STORED,
  agreed_rent_cents bigint NOT NULL CHECK (agreed_rent_cents >= 0),
  currency char(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT leases_dates CHECK (end_date > start_date),
  CONSTRAINT leases_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT leases_unit_same_org_fkey FOREIGN KEY (organization_id, unit_id) REFERENCES public.units (organization_id, id),
  CONSTRAINT leases_no_overlap EXCLUDE USING gist (
    organization_id WITH =,
    unit_id WITH =,
    occupancy_period WITH &&
  )
);

CREATE TABLE public.ownership_periods (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  start_date date NOT NULL,
  end_date date NOT NULL,
  effective_period daterange GENERATED ALWAYS AS (daterange(start_date, end_date, '[)')) STORED,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ownership_periods_dates CHECK (end_date > start_date),
  CONSTRAINT ownership_periods_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT ownership_periods_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT ownership_periods_no_overlap EXCLUDE USING gist (
    organization_id WITH =,
    property_id WITH =,
    effective_period WITH &&
  )
);

CREATE TABLE public.ownership_shares (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  period_id uuid NOT NULL,
  owner_party_id uuid NOT NULL,
  weight integer NOT NULL CHECK (weight > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ownership_shares_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT ownership_shares_owner_once UNIQUE (organization_id, period_id, owner_party_id),
  CONSTRAINT ownership_shares_period_same_org_fkey
    FOREIGN KEY (organization_id, period_id) REFERENCES public.ownership_periods (organization_id, id),
  CONSTRAINT ownership_shares_owner_same_org_fkey
    FOREIGN KEY (organization_id, owner_party_id) REFERENCES public.parties (organization_id, id)
);

CREATE TABLE public.agreements (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  start_date date NOT NULL,
  end_date date NOT NULL,
  effective_period daterange GENERATED ALWAYS AS (daterange(start_date, end_date, '[)')) STORED,
  responsibility_mode text NOT NULL DEFAULT 'OWNERSHIP_WEIGHTS' CHECK (responsibility_mode = 'OWNERSHIP_WEIGHTS'),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT agreements_dates CHECK (end_date > start_date),
  CONSTRAINT agreements_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT agreements_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

CREATE TABLE public.fee_rules (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  agreement_id uuid NOT NULL,
  fee_base text NOT NULL CHECK (fee_base = 'ALLOCATED_RENT'),
  rate_numerator integer NOT NULL CHECK (rate_numerator >= 0),
  rate_denominator integer NOT NULL CHECK (rate_denominator > 0),
  fixed_cents bigint NOT NULL DEFAULT 0 CHECK (fixed_cents >= 0),
  cap_cents bigint CHECK (cap_cents IS NULL OR cap_cents >= 0),
  minimum_cents bigint CHECK (minimum_cents IS NULL OR minimum_cents >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fee_rules_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT fee_rules_one_per_agreement UNIQUE (organization_id, agreement_id),
  CONSTRAINT fee_rules_agreement_same_org_fkey
    FOREIGN KEY (organization_id, agreement_id) REFERENCES public.agreements (organization_id, id)
);

CREATE TABLE public.reserve_rules (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  agreement_id uuid NOT NULL,
  target_total_cents bigint NOT NULL CHECK (target_total_cents >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT reserve_rules_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT reserve_rules_one_per_agreement UNIQUE (organization_id, agreement_id),
  CONSTRAINT reserve_rules_agreement_same_org_fkey
    FOREIGN KEY (organization_id, agreement_id) REFERENCES public.agreements (organization_id, id)
);

CREATE TABLE public.receipt_counters (
  organization_id uuid PRIMARY KEY REFERENCES public.organizations (id),
  last_number bigint NOT NULL CHECK (last_number >= 0),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE public.receipts (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  unit_id uuid NOT NULL,
  lease_id uuid NOT NULL,
  payer_party_id uuid NOT NULL,
  method text NOT NULL CHECK (method IN ('CHECK', 'CASH', 'SECURITY_DEPOSIT_CHECK', 'SECURITY_DEPOSIT_CASH')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  currency char(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  received_at timestamptz NOT NULL,
  posting_date date NOT NULL,
  reference_masked text NOT NULL,
  receipt_number bigint NOT NULL,
  service_period text,
  status text NOT NULL CHECK (status IN (
    'RECORDED', 'DEPOSITED', 'BANK_VERIFIED', 'AVAILABLE', 'ALLOCATED', 'VOIDED', 'RETURNED'
  )),
  deposited_cents bigint NOT NULL DEFAULT 0,
  verified_cents bigint NOT NULL DEFAULT 0,
  available_cents bigint NOT NULL DEFAULT 0,
  allocated_cents bigint NOT NULL DEFAULT 0,
  returned_cents bigint NOT NULL DEFAULT 0,
  available_at timestamptz,
  bank_account_id uuid,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT receipts_counters CHECK (
    deposited_cents BETWEEN 0 AND amount_cents
    AND verified_cents BETWEEN 0 AND deposited_cents
    AND available_cents BETWEEN 0 AND verified_cents
    AND allocated_cents BETWEEN 0 AND available_cents
    AND returned_cents BETWEEN 0 AND amount_cents
  ),
  CONSTRAINT receipts_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT receipts_number_unique UNIQUE (organization_id, receipt_number),
  CONSTRAINT receipts_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT receipts_unit_same_org_fkey
    FOREIGN KEY (organization_id, unit_id) REFERENCES public.units (organization_id, id),
  CONSTRAINT receipts_lease_same_org_fkey
    FOREIGN KEY (organization_id, lease_id) REFERENCES public.leases (organization_id, id),
  CONSTRAINT receipts_payer_same_org_fkey
    FOREIGN KEY (organization_id, payer_party_id) REFERENCES public.parties (organization_id, id),
  CONSTRAINT receipts_bank_same_org_fkey
    FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);

CREATE TABLE public.deposit_batches (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  bank_account_id uuid NOT NULL,
  slip_reference text NOT NULL,
  deposited_on date NOT NULL,
  total_cents bigint NOT NULL CHECK (total_cents > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT deposit_batches_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT deposit_batches_bank_same_org_fkey
    FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);

CREATE TABLE public.deposit_items (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  batch_id uuid NOT NULL,
  receipt_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT deposit_items_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT deposit_items_batch_same_org_fkey
    FOREIGN KEY (organization_id, batch_id) REFERENCES public.deposit_batches (organization_id, id),
  CONSTRAINT deposit_items_receipt_same_org_fkey
    FOREIGN KEY (organization_id, receipt_id) REFERENCES public.receipts (organization_id, id)
);

CREATE TABLE public.bank_transactions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  bank_account_id uuid NOT NULL,
  external_id text NOT NULL,
  amount_cents bigint NOT NULL,
  posted_on date NOT NULL,
  import_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT bank_transactions_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT bank_transactions_external_unique UNIQUE (organization_id, bank_account_id, external_id),
  CONSTRAINT bank_transactions_bank_same_org_fkey
    FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);

CREATE TABLE public.bank_matches (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  bank_transaction_id uuid NOT NULL,
  deposit_batch_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT bank_matches_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT bank_matches_transaction_same_org_fkey
    FOREIGN KEY (organization_id, bank_transaction_id) REFERENCES public.bank_transactions (organization_id, id),
  CONSTRAINT bank_matches_batch_same_org_fkey
    FOREIGN KEY (organization_id, deposit_batch_id) REFERENCES public.deposit_batches (organization_id, id)
);

CREATE TABLE public.journal_entries (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  source_type text NOT NULL,
  source_id uuid NOT NULL,
  posting_date date NOT NULL,
  currency char(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  status text NOT NULL CHECK (status IN ('DRAFT', 'POSTED')),
  lines_hash text NOT NULL,
  reversal_of_id uuid,
  posted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT journal_entries_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT journal_entries_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id),
  CONSTRAINT journal_entries_reversal_same_org_fkey
    FOREIGN KEY (organization_id, reversal_of_id) REFERENCES public.journal_entries (organization_id, id)
);

CREATE UNIQUE INDEX journal_entries_source_once
  ON public.journal_entries (organization_id, source_type, source_id)
  WHERE status = 'POSTED';

CREATE TABLE public.journal_lines (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  journal_id uuid NOT NULL,
  account_id uuid NOT NULL,
  side text NOT NULL CHECK (side IN ('DEBIT', 'CREDIT')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  currency char(3) NOT NULL CHECK (currency = 'USD'),
  property_id uuid,
  owner_party_id uuid,
  lease_id uuid,
  bank_account_id uuid,
  purpose text CHECK (purpose IS NULL OR purpose IN ('RENT', 'SECURITY_DEPOSIT', 'RESERVE')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT journal_lines_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT journal_lines_journal_same_org_fkey
    FOREIGN KEY (organization_id, journal_id) REFERENCES public.journal_entries (organization_id, id),
  CONSTRAINT journal_lines_account_same_org_fkey
    FOREIGN KEY (organization_id, account_id) REFERENCES public.ledger_accounts (organization_id, id),
  CONSTRAINT journal_lines_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT journal_lines_owner_same_org_fkey
    FOREIGN KEY (organization_id, owner_party_id) REFERENCES public.parties (organization_id, id),
  CONSTRAINT journal_lines_lease_same_org_fkey
    FOREIGN KEY (organization_id, lease_id) REFERENCES public.leases (organization_id, id),
  CONSTRAINT journal_lines_bank_same_org_fkey
    FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);

CREATE TABLE public.funding_lots (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  bank_account_id uuid NOT NULL,
  purpose text NOT NULL CHECK (purpose IN ('RENT', 'SECURITY_DEPOSIT', 'RESERVE')),
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  consumed_cents bigint NOT NULL DEFAULT 0 CHECK (consumed_cents >= 0 AND consumed_cents <= amount_cents),
  source_type text NOT NULL,
  source_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT funding_lots_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT funding_lots_source_unique UNIQUE (organization_id, source_type, source_id),
  CONSTRAINT funding_lots_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT funding_lots_bank_same_org_fkey
    FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);

CREATE TABLE public.rent_charges (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  lease_id uuid NOT NULL,
  due_on date NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  currency char(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  description text NOT NULL,
  allocated_cents bigint NOT NULL DEFAULT 0 CHECK (allocated_cents >= 0 AND allocated_cents <= amount_cents),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT rent_charges_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT rent_charges_lease_same_org_fkey
    FOREIGN KEY (organization_id, lease_id) REFERENCES public.leases (organization_id, id)
);

CREATE TABLE public.charge_allocations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  rent_charge_id uuid NOT NULL,
  receipt_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT charge_allocations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT charge_allocations_charge_same_org_fkey
    FOREIGN KEY (organization_id, rent_charge_id) REFERENCES public.rent_charges (organization_id, id),
  CONSTRAINT charge_allocations_receipt_same_org_fkey
    FOREIGN KEY (organization_id, receipt_id) REFERENCES public.receipts (organization_id, id)
);

CREATE TABLE public.invoices (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  contractor_party_id uuid NOT NULL,
  invoice_number text NOT NULL,
  normalized_invoice_number text NOT NULL,
  status text NOT NULL CHECK (status IN ('SUBMITTED', 'APPROVED', 'CREDITED', 'SETTLED')),
  currency char(3) NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
  tax_cents bigint NOT NULL CHECK (tax_cents >= 0),
  total_cents bigint NOT NULL CHECK (total_cents > 0),
  credited_cents bigint NOT NULL DEFAULT 0 CHECK (credited_cents >= 0),
  settled_cents bigint NOT NULL DEFAULT 0 CHECK (settled_cents >= 0),
  ownership_period_id uuid,
  payable_journal_id uuid,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT invoices_credit_settled CHECK (credited_cents + settled_cents <= total_cents),
  CONSTRAINT invoices_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT invoices_number_unique UNIQUE (organization_id, contractor_party_id, normalized_invoice_number),
  CONSTRAINT invoices_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT invoices_contractor_same_org_fkey
    FOREIGN KEY (organization_id, contractor_party_id) REFERENCES public.parties (organization_id, id),
  CONSTRAINT invoices_period_same_org_fkey
    FOREIGN KEY (organization_id, ownership_period_id) REFERENCES public.ownership_periods (organization_id, id),
  CONSTRAINT invoices_journal_same_org_fkey
    FOREIGN KEY (organization_id, payable_journal_id) REFERENCES public.journal_entries (organization_id, id)
);

CREATE TABLE public.invoice_lines (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  description text NOT NULL,
  quantity integer NOT NULL CHECK (quantity > 0),
  unit_price_cents bigint NOT NULL CHECK (unit_price_cents >= 0),
  line_total_cents bigint NOT NULL CHECK (line_total_cents >= 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT invoice_lines_math CHECK (line_total_cents = quantity * unit_price_cents),
  CONSTRAINT invoice_lines_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT invoice_lines_invoice_same_org_fkey
    FOREIGN KEY (organization_id, invoice_id) REFERENCES public.invoices (organization_id, id)
);

CREATE TABLE public.credit_notes (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  journal_id uuid NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT credit_notes_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT credit_notes_invoice_same_org_fkey
    FOREIGN KEY (organization_id, invoice_id) REFERENCES public.invoices (organization_id, id),
  CONSTRAINT credit_notes_journal_same_org_fkey
    FOREIGN KEY (organization_id, journal_id) REFERENCES public.journal_entries (organization_id, id)
);

CREATE TABLE public.owner_declarations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  owner_party_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  journal_id uuid NOT NULL,
  settled_cents bigint NOT NULL DEFAULT 0 CHECK (settled_cents >= 0 AND settled_cents <= amount_cents),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT owner_declarations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT owner_declarations_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT owner_declarations_owner_same_org_fkey
    FOREIGN KEY (organization_id, owner_party_id) REFERENCES public.parties (organization_id, id),
  CONSTRAINT owner_declarations_journal_same_org_fkey
    FOREIGN KEY (organization_id, journal_id) REFERENCES public.journal_entries (organization_id, id)
);

CREATE TABLE public.reconciliations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  bank_account_id uuid NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  statement_opening_cents bigint NOT NULL,
  statement_closing_cents bigint NOT NULL,
  ledger_cash_cents bigint NOT NULL,
  obligation_cents bigint NOT NULL,
  timing_item_cents bigint NOT NULL DEFAULT 0,
  difference_cents bigint NOT NULL,
  status text NOT NULL CHECK (status IN ('DRAFT', 'CLOSED')),
  evidence_hash text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT reconciliations_dates CHECK (period_end >= period_start),
  CONSTRAINT reconciliations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT reconciliations_bank_same_org_fkey
    FOREIGN KEY (organization_id, bank_account_id) REFERENCES public.bank_accounts (organization_id, id)
);

CREATE TABLE public.period_closes (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL CHECK (status = 'CLOSED'),
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT period_closes_dates CHECK (period_end >= period_start),
  CONSTRAINT period_closes_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT period_closes_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id),
  CONSTRAINT period_closes_no_overlap EXCLUDE USING gist (
    organization_id WITH =,
    daterange(period_start, period_end, '[]') WITH &&
  )
);

CREATE OR REPLACE FUNCTION public.app_ensure_proposed_chart(p_organization_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NULLIF(current_setting('app.organization_id', true), '')::uuid IS DISTINCT FROM p_organization_id THEN
    RAISE EXCEPTION 'tenant context mismatch' USING ERRCODE = '42501';
  END IF;
  INSERT INTO public.ledger_accounts (id, organization_id, code, name, normal_balance)
  SELECT gen_random_uuid(), p_organization_id, code, name, normal_balance
  FROM (VALUES
    ('1010', 'Cash/checks in custody', 'DEBIT'),
    ('1020', 'Bank pending/unavailable', 'DEBIT'),
    ('1030', 'Bank available', 'DEBIT'),
    ('1040', 'Due from owner / returned-funds recovery', 'DEBIT'),
    ('2010', 'Unapplied receipts', 'CREDIT'),
    ('2020', 'Owner funds, unrestricted', 'CREDIT'),
    ('2030', 'Owner reserves, restricted', 'CREDIT'),
    ('2040', 'Approved contractor payable', 'CREDIT'),
    ('2050', 'Management company payable', 'CREDIT'),
    ('2060', 'Declared owner distributions payable', 'CREDIT'),
    ('2070', 'Security deposits, restricted', 'CREDIT')
  ) AS proposed(code, name, normal_balance)
  ON CONFLICT (organization_id, code) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION public.app_post_journal(
  p_organization_id uuid,
  p_source_type text,
  p_source_id uuid,
  p_posting_date date,
  p_lines jsonb,
  p_lines_hash text,
  p_reversal_of uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
  v_existing uuid;
  v_existing_hash text;
  v_journal uuid;
  v_line jsonb;
  v_account uuid;
  v_count integer := 0;
BEGIN
  IF NULLIF(current_setting('app.organization_id', true), '')::uuid IS DISTINCT FROM p_organization_id THEN
    RAISE EXCEPTION 'tenant context mismatch' USING ERRCODE = '42501';
  END IF;
  IF EXISTS (
    SELECT 1 FROM public.period_closes AS close_row
    WHERE close_row.organization_id = p_organization_id
      AND close_row.status = 'CLOSED'
      AND p_posting_date >= close_row.period_start
      AND p_posting_date <= close_row.period_end
  ) THEN
    RAISE EXCEPTION 'closed posting period' USING ERRCODE = '23514';
  END IF;
  SELECT id, lines_hash INTO v_existing, v_existing_hash
  FROM public.journal_entries
  WHERE organization_id = p_organization_id
    AND source_type = p_source_type
    AND source_id = p_source_id
    AND status = 'POSTED';
  IF v_existing IS NOT NULL THEN
    IF v_existing_hash IS DISTINCT FROM p_lines_hash THEN
      RAISE EXCEPTION 'posted source already has different lines' USING ERRCODE = '23505';
    END IF;
    RETURN v_existing;
  END IF;
  PERFORM public.app_ensure_proposed_chart(p_organization_id);
  v_journal := gen_random_uuid();
  INSERT INTO public.journal_entries (
    id, organization_id, source_type, source_id, posting_date, currency, status, lines_hash, reversal_of_id
  ) VALUES (
    v_journal, p_organization_id, p_source_type, p_source_id, p_posting_date, 'USD', 'DRAFT', p_lines_hash, p_reversal_of
  );
  FOR v_line IN SELECT value FROM jsonb_array_elements(p_lines)
  LOOP
    SELECT id INTO v_account
    FROM public.ledger_accounts
    WHERE organization_id = p_organization_id AND code = v_line->>'account_code';
    IF v_account IS NULL THEN
      RAISE EXCEPTION 'unknown account code' USING ERRCODE = '23514';
    END IF;
    INSERT INTO public.journal_lines (
      id, organization_id, journal_id, account_id, side, amount_cents, currency,
      property_id, owner_party_id, lease_id, bank_account_id, purpose
    ) VALUES (
      gen_random_uuid(),
      p_organization_id,
      v_journal,
      v_account,
      v_line->>'side',
      (v_line->>'amount_cents')::bigint,
      'USD',
      NULLIF(v_line->>'property_id', '')::uuid,
      NULLIF(v_line->>'owner_party_id', '')::uuid,
      NULLIF(v_line->>'lease_id', '')::uuid,
      NULLIF(v_line->>'bank_account_id', '')::uuid,
      NULLIF(v_line->>'purpose', '')
    );
    v_count := v_count + 1;
  END LOOP;
  IF v_count < 2 THEN
    RAISE EXCEPTION 'journal needs at least two lines' USING ERRCODE = '23514';
  END IF;
  UPDATE public.journal_entries
  SET status = 'POSTED', posted_at = clock_timestamp()
  WHERE id = v_journal AND organization_id = p_organization_id;
  RETURN v_journal;
END;
$$;

CREATE OR REPLACE FUNCTION public.reject_posted_journal_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'posted journals cannot be deleted' USING ERRCODE = '55000';
  END IF;
  IF OLD.status = 'POSTED' THEN
    RAISE EXCEPTION 'posted journals are immutable' USING ERRCODE = '55000';
  END IF;
  IF NOT (OLD.status = 'DRAFT' AND NEW.status = 'POSTED') THEN
    RAISE EXCEPTION 'invalid journal transition' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.reject_journal_line_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'journal lines are append-only' USING ERRCODE = '55000';
END;
$$;

CREATE OR REPLACE FUNCTION public.reject_line_on_posted_journal()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_status text;
BEGIN
  SELECT status INTO v_status
  FROM public.journal_entries
  WHERE id = NEW.journal_id AND organization_id = NEW.organization_id;
  IF v_status IS DISTINCT FROM 'DRAFT' THEN
    RAISE EXCEPTION 'cannot add lines unless the journal is draft' USING ERRCODE = '55000';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.assert_journal_balanced()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_count integer;
  v_debit bigint;
  v_credit bigint;
  v_currencies integer;
BEGIN
  IF NEW.status <> 'POSTED' THEN
    RETURN NEW;
  END IF;
  SELECT count(*),
         coalesce(sum(amount_cents) FILTER (WHERE side = 'DEBIT'), 0),
         coalesce(sum(amount_cents) FILTER (WHERE side = 'CREDIT'), 0),
         count(DISTINCT currency)
    INTO v_count, v_debit, v_credit, v_currencies
  FROM public.journal_lines
  WHERE journal_id = NEW.id AND organization_id = NEW.organization_id;
  IF v_count < 2 OR v_debit <> v_credit OR v_debit <= 0 OR v_currencies <> 1 THEN
    RAISE EXCEPTION 'unbalanced journal' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION public.assert_ownership_weight_sum()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_period uuid;
  v_sum integer;
BEGIN
  v_period := COALESCE(NEW.period_id, OLD.period_id);
  SELECT coalesce(sum(weight), 0) INTO v_sum
  FROM public.ownership_shares
  WHERE organization_id = COALESCE(NEW.organization_id, OLD.organization_id)
    AND period_id = v_period;
  IF v_sum <> 1000000 THEN
    RAISE EXCEPTION 'ownership weights must total 1000000' USING ERRCODE = '23514';
  END IF;
  RETURN NULL;
END;
$$;

CREATE TRIGGER trg_journal_entries_immutable
  BEFORE UPDATE OR DELETE ON public.journal_entries
  FOR EACH ROW EXECUTE FUNCTION public.reject_posted_journal_change();
CREATE TRIGGER trg_journal_lines_append_only
  BEFORE UPDATE OR DELETE ON public.journal_lines
  FOR EACH ROW EXECUTE FUNCTION public.reject_journal_line_mutation();
CREATE TRIGGER trg_journal_lines_draft_only
  BEFORE INSERT ON public.journal_lines
  FOR EACH ROW EXECUTE FUNCTION public.reject_line_on_posted_journal();
CREATE CONSTRAINT TRIGGER trg_journal_balanced
  AFTER INSERT OR UPDATE ON public.journal_entries
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.assert_journal_balanced();
CREATE CONSTRAINT TRIGGER trg_ownership_weight_sum
  AFTER INSERT OR UPDATE OR DELETE ON public.ownership_shares
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION public.assert_ownership_weight_sum();
CREATE TRIGGER trg_bank_transactions_append_only
  BEFORE UPDATE OR DELETE ON public.bank_transactions
  FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();

REVOKE ALL ON FUNCTION public.app_ensure_proposed_chart(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_post_journal(uuid, text, uuid, date, jsonb, text, uuid) FROM PUBLIC;
ALTER FUNCTION public.app_ensure_proposed_chart(uuid) OWNER TO grok_posting;
ALTER FUNCTION public.app_post_journal(uuid, text, uuid, date, jsonb, text, uuid) OWNER TO grok_posting;
GRANT EXECUTE ON FUNCTION public.app_ensure_proposed_chart(uuid) TO grok_app;
GRANT EXECUTE ON FUNCTION public.app_post_journal(uuid, text, uuid, date, jsonb, text, uuid) TO grok_app;
GRANT SELECT ON public.period_closes TO grok_posting;
GRANT SELECT, INSERT ON public.ledger_accounts TO grok_posting;
GRANT SELECT, INSERT, UPDATE ON public.journal_entries TO grok_posting;
GRANT SELECT, INSERT ON public.journal_lines TO grok_posting;

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'ledger_accounts', 'bank_accounts', 'leases', 'ownership_periods', 'ownership_shares',
    'agreements', 'fee_rules', 'reserve_rules', 'receipt_counters', 'receipts',
    'deposit_batches', 'deposit_items', 'bank_transactions', 'bank_matches',
    'journal_entries', 'journal_lines', 'funding_lots', 'rent_charges', 'charge_allocations',
    'invoices', 'invoice_lines', 'credit_notes', 'owner_declarations', 'reconciliations',
    'period_closes'
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

GRANT SELECT ON public.ledger_accounts, public.journal_entries, public.journal_lines TO grok_app;
GRANT SELECT, INSERT, UPDATE ON
  public.bank_accounts, public.leases, public.ownership_periods, public.ownership_shares,
  public.agreements, public.fee_rules, public.reserve_rules, public.receipts,
  public.deposit_batches, public.deposit_items, public.bank_matches, public.funding_lots,
  public.rent_charges, public.charge_allocations, public.invoices, public.invoice_lines,
  public.credit_notes, public.owner_declarations, public.reconciliations, public.period_closes,
  public.properties
  TO grok_app;
GRANT SELECT, INSERT, UPDATE ON public.receipt_counters TO grok_app;
GRANT SELECT, INSERT ON public.bank_transactions TO grok_app;
GRANT SELECT, INSERT ON public.parties TO grok_app;
