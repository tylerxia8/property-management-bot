DROP FUNCTION IF EXISTS public.app_outbox_progress(uuid, uuid, text, integer, timestamptz, text);

DROP POLICY IF EXISTS actor_scope_inbox ON public.inbox_events;
DROP POLICY IF EXISTS actor_scope_outbox ON public.outbox_events;

CREATE POLICY actor_scope_outbox ON public.outbox_events AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_id() IS NOT NULL OR current_user = 'grok_posting');

CREATE POLICY actor_required ON public.inbox_events AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR current_user = 'grok_posting')
  WITH CHECK (public.app_actor_is_staff() OR current_user = 'grok_posting');

ALTER TABLE public.outbox_events
  DROP COLUMN IF EXISTS last_error,
  DROP COLUMN IF EXISTS available_at,
  DROP COLUMN IF EXISTS attempt_count;
