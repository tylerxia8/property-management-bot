DROP TABLE IF EXISTS public.alert_events;

DROP POLICY IF EXISTS actor_scope_properties ON public.properties;
CREATE POLICY actor_scope_properties ON public.properties AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_units ON public.units;
CREATE POLICY actor_scope_units ON public.units AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_receipts ON public.receipts;
CREATE POLICY actor_scope_receipts ON public.receipts AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_invoices ON public.invoices;
CREATE POLICY actor_scope_invoices ON public.invoices AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_journal_lines ON public.journal_lines;
CREATE POLICY actor_scope_journal_lines ON public.journal_lines AS RESTRICTIVE
  USING (current_user = 'grok_posting' OR public.app_actor_is_staff())
  WITH CHECK (current_user = 'grok_posting' OR public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_journals ON public.journal_entries;
CREATE POLICY actor_scope_journals ON public.journal_entries AS RESTRICTIVE
  USING (current_user = 'grok_posting' OR public.app_actor_is_staff())
  WITH CHECK (current_user = 'grok_posting' OR public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_distribution_batches ON public.distribution_batches;
CREATE POLICY actor_required ON public.distribution_batches AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR current_user = 'grok_posting')
  WITH CHECK (public.app_actor_is_staff() OR current_user = 'grok_posting');

ALTER TABLE public.payment_events DROP CONSTRAINT IF EXISTS payment_events_simulator_kind;
ALTER TABLE public.payment_events
  ADD CONSTRAINT payment_events_simulator_check CHECK (simulator = true);
DROP FUNCTION IF EXISTS public.app_set_outbound(uuid, jsonb);
DROP FUNCTION IF EXISTS public.app_actor_can_access_property(uuid);
