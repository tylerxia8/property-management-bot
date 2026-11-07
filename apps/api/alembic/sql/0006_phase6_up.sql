-- Restores relationship policies that a 0005 downgrade drops and does not recreate.
DROP POLICY IF EXISTS actor_required ON public.intake_fields;
DROP POLICY IF EXISTS actor_scope_intake_fields ON public.intake_fields;
CREATE POLICY actor_scope_intake_fields ON public.intake_fields AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = intake_fields.organization_id AND t.id = intake_fields.ticket_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = intake_fields.organization_id AND t.id = intake_fields.ticket_id
    )
  );

DROP POLICY IF EXISTS actor_required ON public.ticket_messages;
DROP POLICY IF EXISTS actor_scope_ticket_messages ON public.ticket_messages;
CREATE POLICY actor_scope_ticket_messages ON public.ticket_messages AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = ticket_messages.organization_id AND t.id = ticket_messages.ticket_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = ticket_messages.organization_id AND t.id = ticket_messages.ticket_id
    )
  );

DROP POLICY IF EXISTS actor_required ON public.media_objects;
DROP POLICY IF EXISTS actor_scope_media ON public.media_objects;
CREATE POLICY actor_scope_media ON public.media_objects AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = media_objects.organization_id AND t.id = media_objects.ticket_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = media_objects.organization_id AND t.id = media_objects.ticket_id
    )
  );

DROP POLICY IF EXISTS actor_required ON public.accommodation_cases;
DROP POLICY IF EXISTS actor_scope_accommodation_cases ON public.accommodation_cases;
CREATE POLICY actor_scope_accommodation_cases ON public.accommodation_cases AS RESTRICTIVE
  USING (public.app_actor_is_manager() OR subject_user_id = public.app_actor_id())
  WITH CHECK (public.app_actor_is_manager() OR subject_user_id = public.app_actor_id());

ALTER TABLE public.outbox_events
  ADD COLUMN attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  ADD COLUMN available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  ADD COLUMN last_error text;

DROP POLICY IF EXISTS actor_required ON public.inbox_events;
DROP POLICY IF EXISTS actor_scope_inbox ON public.inbox_events;

CREATE POLICY actor_scope_inbox ON public.inbox_events AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (
    public.app_actor_is_staff()
    OR COALESCE(current_setting('app.access_mode', true), '') = 'webhook'
  );

DROP POLICY IF EXISTS actor_scope_outbox ON public.outbox_events;

CREATE POLICY actor_scope_outbox ON public.outbox_events AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (
    public.app_actor_id() IS NOT NULL
    OR current_user = 'grok_posting'
    OR COALESCE(current_setting('app.access_mode', true), '') = 'webhook'
  );

CREATE FUNCTION public.app_outbox_progress(
  p_organization_id uuid,
  p_event_id uuid,
  p_status text,
  p_attempt_count integer,
  p_available_at timestamptz,
  p_last_error text
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NULLIF(current_setting('app.organization_id', true), '')::uuid IS DISTINCT FROM p_organization_id THEN
    RAISE EXCEPTION 'tenant context mismatch' USING ERRCODE = '42501';
  END IF;
  IF NOT public.app_actor_is_staff() THEN
    RAISE EXCEPTION 'staff actor required' USING ERRCODE = '42501';
  END IF;
  IF p_status NOT IN ('PENDING', 'DISPATCHED', 'FAILED') THEN
    RAISE EXCEPTION 'invalid outbox status';
  END IF;
  UPDATE public.outbox_events
  SET status = p_status,
      attempt_count = p_attempt_count,
      available_at = p_available_at,
      last_error = p_last_error
  WHERE organization_id = p_organization_id
    AND id = p_event_id
    AND status = 'PENDING';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'outbox event is not pending';
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION public.app_actor_id() TO grok_owner;
GRANT EXECUTE ON FUNCTION public.app_actor_is_staff() TO grok_owner;

REVOKE ALL ON FUNCTION public.app_outbox_progress(uuid, uuid, text, integer, timestamptz, text) FROM PUBLIC;
ALTER FUNCTION public.app_outbox_progress(uuid, uuid, text, integer, timestamptz, text) OWNER TO grok_owner;
GRANT EXECUTE ON FUNCTION public.app_outbox_progress(uuid, uuid, text, integer, timestamptz, text) TO grok_app;
