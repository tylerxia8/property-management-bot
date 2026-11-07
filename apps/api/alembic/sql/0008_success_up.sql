CREATE UNIQUE INDEX payment_events_manual_once
  ON public.payment_events (organization_id, item_id, kind)
  WHERE kind IN ('MANUAL_SUBMISSION', 'MANUAL_SETTLEMENT');
