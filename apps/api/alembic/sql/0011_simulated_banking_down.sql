DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM public.receipts WHERE method IN ('ZELLE', 'VENMO'))
    OR EXISTS (SELECT 1 FROM public.step_up_events WHERE method = 'SIMULATED_APPROVAL')
    OR EXISTS (SELECT 1 FROM public.simulated_bank_transactions) THEN
    RAISE EXCEPTION 'Simulation records must be preserved; restore a backup to roll back this migration';
  END IF;
END
$$;
DROP TABLE public.simulated_bank_transactions;
DROP TABLE public.simulated_bank_accounts;
ALTER TABLE public.payee_destinations DROP COLUMN channel;
ALTER TABLE public.step_up_events DROP CONSTRAINT step_up_events_method_check;
ALTER TABLE public.step_up_events ADD CONSTRAINT step_up_events_method_check CHECK (method = 'LOCAL_DEV_PASSWORD');
ALTER TABLE public.receipts DROP CONSTRAINT receipts_method_check;
ALTER TABLE public.receipts ADD CONSTRAINT receipts_method_check
  CHECK (method IN ('CHECK', 'CASH', 'SECURITY_DEPOSIT_CHECK', 'SECURITY_DEPOSIT_CASH'));
