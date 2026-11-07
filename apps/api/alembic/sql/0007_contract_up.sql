CREATE FUNCTION public.app_actor_can_access_property(p_property_id uuid) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.role_grants AS g
      WHERE g.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
        AND g.user_id = public.app_actor_id()
        AND g.resource_type = 'property'
        AND g.resource_id = p_property_id
        AND g.role IN ('property_manager', 'accounting_staff', 'organization_administrator')
        AND g.active_from <= clock_timestamp()
        AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
    );
$$;

REVOKE ALL ON FUNCTION public.app_actor_can_access_property(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_actor_can_access_property(uuid) TO grok_app, grok_posting;

CREATE OR REPLACE FUNCTION public.app_local_login(p_issuer text, p_subject text, p_password text)
RETURNS TABLE (
  user_id uuid,
  organization_id uuid,
  display_name text,
  role text
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
  SELECT u.id, u.organization_id, u.display_name, g.role
  FROM public.users AS u
  JOIN public.role_grants AS g
    ON g.organization_id = u.organization_id
   AND g.user_id = u.id
  WHERE u.issuer = p_issuer
    AND u.subject = p_subject
    AND u.dev_password_hash IS NOT NULL
    AND u.dev_password_hash = public.crypt(p_password, u.dev_password_hash)
    AND g.active_from <= clock_timestamp()
    AND (g.active_until IS NULL OR g.active_until > clock_timestamp());
$$;
GRANT EXECUTE ON FUNCTION public.app_actor_is_manager() TO grok_owner;

CREATE FUNCTION public.app_set_outbound(p_organization_id uuid, p_value jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
  IF NULLIF(current_setting('app.organization_id', true), '')::uuid IS DISTINCT FROM p_organization_id THEN
    RAISE EXCEPTION 'tenant context mismatch' USING ERRCODE = '42501';
  END IF;
  IF NOT public.app_actor_is_manager() THEN
    RAISE EXCEPTION 'manager required' USING ERRCODE = '42501';
  END IF;
  UPDATE public.organizations
  SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), '{outbound}', p_value, true)
  WHERE id = p_organization_id;
END;
$$;

REVOKE ALL ON FUNCTION public.app_set_outbound(uuid, jsonb) FROM PUBLIC;
ALTER FUNCTION public.app_set_outbound(uuid, jsonb) OWNER TO grok_owner;
GRANT EXECUTE ON FUNCTION public.app_set_outbound(uuid, jsonb) TO grok_app;

DROP POLICY IF EXISTS actor_scope_properties ON public.properties;
CREATE POLICY actor_scope_properties ON public.properties AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR public.app_actor_can_access_property(id))
  WITH CHECK (public.app_actor_is_staff() OR public.app_actor_can_access_property(id));

DROP POLICY IF EXISTS actor_scope_units ON public.units;
CREATE POLICY actor_scope_units ON public.units AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id))
  WITH CHECK (public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_scope_receipts ON public.receipts;
CREATE POLICY actor_scope_receipts ON public.receipts AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id))
  WITH CHECK (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id));

DROP POLICY IF EXISTS actor_scope_invoices ON public.invoices;
CREATE POLICY actor_scope_invoices ON public.invoices AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id))
  WITH CHECK (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id));

DROP POLICY IF EXISTS actor_scope_journal_lines ON public.journal_lines;
CREATE POLICY actor_scope_journal_lines ON public.journal_lines AS RESTRICTIVE
  USING (
    current_user = 'grok_posting'
    OR public.app_actor_is_staff()
    OR (property_id IS NOT NULL AND public.app_actor_can_access_property(property_id))
  )
  WITH CHECK (
    current_user = 'grok_posting'
    OR public.app_actor_is_staff()
    OR (property_id IS NOT NULL AND public.app_actor_can_access_property(property_id))
  );

DROP POLICY IF EXISTS actor_scope_journals ON public.journal_entries;
CREATE POLICY actor_scope_journals ON public.journal_entries AS RESTRICTIVE
  USING (
    current_user = 'grok_posting'
    OR public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.journal_lines AS l
      WHERE l.organization_id = journal_entries.organization_id
        AND l.journal_id = journal_entries.id
        AND l.property_id IS NOT NULL
        AND public.app_actor_can_access_property(l.property_id)
    )
  )
  WITH CHECK (current_user = 'grok_posting' OR public.app_actor_is_staff());

DROP POLICY IF EXISTS actor_required ON public.distribution_batches;
CREATE POLICY actor_scope_distribution_batches ON public.distribution_batches AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id))
  WITH CHECK (public.app_actor_is_staff() OR public.app_actor_can_access_property(property_id));

DO $$
DECLARE name text;
BEGIN
  FOR name IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'public.payment_events'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%simulator%'
  LOOP
    EXECUTE format('ALTER TABLE public.payment_events DROP CONSTRAINT %I', name);
  END LOOP;
END $$;

ALTER TABLE public.payment_events
  ADD CONSTRAINT payment_events_simulator_kind CHECK (
    simulator = true OR kind IN ('MANUAL_SUBMISSION', 'MANUAL_SETTLEMENT')
  );

CREATE TABLE public.alert_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  kind text NOT NULL,
  payload jsonb NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING', 'FAILED', 'SUPPRESSED')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  delivered_at timestamptz,
  fallback_of uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT alert_events_undelivered CHECK (delivered_at IS NULL),
  CONSTRAINT alert_events_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT alert_events_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

ALTER TABLE public.alert_events OWNER TO grok_owner;
ALTER TABLE public.alert_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alert_events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.alert_events
  USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid)
  WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid);
CREATE POLICY actor_scope_alerts ON public.alert_events AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());
GRANT SELECT, INSERT, UPDATE ON public.alert_events TO grok_app;
