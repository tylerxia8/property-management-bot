DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM public.stripe_rents) OR EXISTS (SELECT 1 FROM public.stripe_recipients)
    OR EXISTS (SELECT 1 FROM public.stripe_payout_jobs) THEN
    RAISE EXCEPTION 'Stripe records must be preserved; restore a backup for rollback';
  END IF;
END $$;
DROP FUNCTION public.app_stripe_worker_scopes();
DROP FUNCTION public.app_stripe_service_actor(uuid);
DROP FUNCTION public.app_ensure_stripe_chart(uuid);
DROP TABLE public.stripe_webhook_events, public.stripe_payout_jobs, public.stripe_rents, public.stripe_recipients, public.stripe_properties;
ALTER TABLE public.funding_lots DROP COLUMN receipt_id;
ALTER TABLE public.invoices DROP CONSTRAINT invoices_status_check;
ALTER TABLE public.invoices ADD CONSTRAINT invoices_status_check CHECK (status IN ('SUBMITTED', 'APPROVED', 'CREDITED', 'SETTLED'));
ALTER TABLE public.receipts DROP CONSTRAINT receipts_method_check;
ALTER TABLE public.receipts ADD CONSTRAINT receipts_method_check CHECK
  (method IN ('CHECK', 'CASH', 'SECURITY_DEPOSIT_CHECK', 'SECURITY_DEPOSIT_CASH', 'ZELLE', 'VENMO'));
ALTER TABLE public.payee_destinations DROP CONSTRAINT payee_destinations_channel_check;
ALTER TABLE public.payee_destinations ADD CONSTRAINT payee_destinations_channel_check CHECK (channel IN ('ZELLE', 'VENMO'));
