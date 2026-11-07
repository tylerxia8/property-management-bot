DROP TABLE IF EXISTS public.period_closes;
DROP TABLE IF EXISTS public.reconciliations;
DROP TABLE IF EXISTS public.owner_declarations;
DROP TABLE IF EXISTS public.credit_notes;
DROP TABLE IF EXISTS public.invoice_lines;
DROP TABLE IF EXISTS public.invoices;
DROP TABLE IF EXISTS public.charge_allocations;
DROP TABLE IF EXISTS public.rent_charges;
DROP TABLE IF EXISTS public.funding_lots;
DROP TABLE IF EXISTS public.journal_lines;
DROP TABLE IF EXISTS public.journal_entries;
DROP TABLE IF EXISTS public.bank_matches;
DROP TABLE IF EXISTS public.bank_transactions;
DROP TABLE IF EXISTS public.deposit_items;
DROP TABLE IF EXISTS public.deposit_batches;
DROP TABLE IF EXISTS public.receipts;
DROP TABLE IF EXISTS public.receipt_counters;
DROP TABLE IF EXISTS public.reserve_rules;
DROP TABLE IF EXISTS public.fee_rules;
DROP TABLE IF EXISTS public.agreements;
DROP TABLE IF EXISTS public.ownership_shares;
DROP TABLE IF EXISTS public.ownership_periods;
DROP TABLE IF EXISTS public.leases;
DROP TABLE IF EXISTS public.bank_accounts;
DROP TABLE IF EXISTS public.ledger_accounts;

ALTER TABLE public.properties DROP COLUMN IF EXISTS disbursements_frozen;

DROP FUNCTION IF EXISTS public.app_post_journal(uuid, text, uuid, date, jsonb, text, uuid);
DROP FUNCTION IF EXISTS public.app_ensure_proposed_chart(uuid);
DROP FUNCTION IF EXISTS public.reject_posted_journal_change();
DROP FUNCTION IF EXISTS public.reject_journal_line_mutation();
DROP FUNCTION IF EXISTS public.reject_line_on_posted_journal();
DROP FUNCTION IF EXISTS public.assert_journal_balanced();
DROP FUNCTION IF EXISTS public.assert_ownership_weight_sum();

DROP EXTENSION IF EXISTS btree_gist;
