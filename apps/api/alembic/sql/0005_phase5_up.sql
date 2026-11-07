-- Phase 5: fail-closed actor policies, distribution approval, and statements.
-- grok_migrator bypasses RLS because it is a superuser. grok_app does not.

DROP POLICY IF EXISTS actor_scope_prospects ON public.prospects;
DROP POLICY IF EXISTS actor_scope_intakes ON public.prospect_intakes;
DROP POLICY IF EXISTS actor_scope_evaluations ON public.policy_evaluations;
DROP POLICY IF EXISTS actor_scope_reviews ON public.human_reviews;
DROP POLICY IF EXISTS actor_scope_policies ON public.screening_policies;
DROP POLICY IF EXISTS actor_scope_tours ON public.tour_appointments;
DROP POLICY IF EXISTS actor_scope_properties ON public.properties;
DROP POLICY IF EXISTS actor_scope_units ON public.units;
DROP POLICY IF EXISTS actor_scope_leases ON public.leases;
DROP POLICY IF EXISTS actor_scope_lease_parties ON public.lease_parties;
DROP POLICY IF EXISTS actor_scope_tickets ON public.maintenance_tickets;
DROP POLICY IF EXISTS actor_scope_entry_secrets ON public.entry_secrets;
DROP POLICY IF EXISTS actor_scope_accommodation_notes ON public.accommodation_notes;
DROP POLICY IF EXISTS actor_scope_journals ON public.journal_entries;
DROP POLICY IF EXISTS actor_scope_journal_lines ON public.journal_lines;
DROP POLICY IF EXISTS actor_scope_receipts ON public.receipts;
DROP POLICY IF EXISTS actor_scope_invoices ON public.invoices;

CREATE POLICY actor_scope_organizations ON public.organizations AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.role_grants AS g
      WHERE g.organization_id = organizations.id
        AND g.user_id = public.app_actor_id()
        AND g.resource_type IS NULL
        AND g.active_from <= clock_timestamp()
        AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
    )
  );

CREATE POLICY actor_scope_users ON public.users AS RESTRICTIVE
  USING (id = public.app_actor_id() OR public.app_actor_is_staff())
  WITH CHECK (id = public.app_actor_id() OR public.app_actor_is_staff());

CREATE POLICY actor_scope_role_grants ON public.role_grants AS RESTRICTIVE
  USING (user_id = public.app_actor_id())
  WITH CHECK (user_id = public.app_actor_id() OR public.app_actor_is_staff());

CREATE POLICY actor_scope_properties ON public.properties AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_units ON public.units AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_leases ON public.leases AS RESTRICTIVE
  USING (
    public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.lease_parties AS lp
      WHERE lp.organization_id = leases.organization_id
        AND lp.lease_id = leases.id
        AND lp.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_lease_parties ON public.lease_parties AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR user_id = public.app_actor_id())
  WITH CHECK (public.app_actor_is_staff() OR user_id = public.app_actor_id());

CREATE POLICY actor_scope_tickets ON public.maintenance_tickets AS RESTRICTIVE
  USING (
    (public.app_actor_id() IS NULL AND id::text = NULLIF(current_setting('app.intake_ticket_id', true), ''))
    OR (COALESCE(current_setting('app.access_mode', true), '') = 'unverified' AND verification = 'UNVERIFIED' AND reporter_user_id IS NULL AND id::text = NULLIF(current_setting('app.intake_ticket_id', true), ''))
    OR public.app_actor_is_staff()
    OR reporter_user_id = public.app_actor_id()
    OR EXISTS (
      SELECT 1 FROM public.lease_parties AS lp
      WHERE lp.organization_id = maintenance_tickets.organization_id
        AND lp.lease_id = maintenance_tickets.lease_id
        AND lp.user_id = public.app_actor_id()
    )
    OR EXISTS (
      SELECT 1 FROM public.assignments AS a
      JOIN public.contractor_profiles AS c
        ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id
      WHERE a.organization_id = maintenance_tickets.organization_id
        AND a.ticket_id = maintenance_tickets.id
        AND c.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    (COALESCE(current_setting('app.access_mode', true), '') = 'unverified' AND verification = 'UNVERIFIED' AND reporter_user_id IS NULL)
    OR (public.app_actor_id() IS NULL AND id::text = NULLIF(current_setting('app.intake_ticket_id', true), ''))
    OR public.app_actor_is_staff()
    OR reporter_user_id = public.app_actor_id()
    OR EXISTS (
      SELECT 1 FROM public.assignments AS a
      JOIN public.contractor_profiles AS c
        ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id
      WHERE a.organization_id = maintenance_tickets.organization_id
        AND a.ticket_id = maintenance_tickets.id
        AND c.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_entry_secrets ON public.entry_secrets AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_accommodation_notes ON public.accommodation_notes AS RESTRICTIVE
  USING (public.app_actor_is_manager())
  WITH CHECK (public.app_actor_is_manager());

CREATE POLICY actor_scope_journals ON public.journal_entries AS RESTRICTIVE
  USING (current_user = 'grok_posting' OR public.app_actor_is_staff())
  WITH CHECK (current_user = 'grok_posting' OR public.app_actor_is_staff());

CREATE POLICY actor_scope_journal_lines ON public.journal_lines AS RESTRICTIVE
  USING (current_user = 'grok_posting' OR public.app_actor_is_staff())
  WITH CHECK (current_user = 'grok_posting' OR public.app_actor_is_staff());

CREATE POLICY actor_scope_receipts ON public.receipts AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_invoices ON public.invoices AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_prospects ON public.prospects AS RESTRICTIVE
  USING (public.app_actor_is_manager() OR user_id = public.app_actor_id())
  WITH CHECK (public.app_actor_is_manager() OR user_id = public.app_actor_id());

CREATE POLICY actor_scope_intakes ON public.prospect_intakes AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = prospect_intakes.organization_id
        AND p.id = prospect_intakes.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = prospect_intakes.organization_id
        AND p.id = prospect_intakes.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_evaluations ON public.policy_evaluations AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = policy_evaluations.organization_id
        AND p.id = policy_evaluations.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = policy_evaluations.organization_id
        AND p.id = policy_evaluations.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_reviews ON public.human_reviews AS RESTRICTIVE
  USING (public.app_actor_is_manager())
  WITH CHECK (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = human_reviews.organization_id
        AND p.id = human_reviews.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_policies ON public.screening_policies AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.role_grants AS g
      WHERE g.organization_id = screening_policies.organization_id
        AND g.user_id = public.app_actor_id()
        AND g.role = 'prospect'
        AND g.resource_type IS NULL
        AND g.active_from <= clock_timestamp()
        AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
    )
  )
  WITH CHECK (public.app_actor_is_manager());

CREATE POLICY actor_scope_tours ON public.tour_appointments AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = tour_appointments.organization_id
        AND p.id = tour_appointments.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = tour_appointments.organization_id
        AND p.id = tour_appointments.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_audit ON public.audit_events AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR actor_id = public.app_actor_id())
  WITH CHECK (
    public.app_actor_id() IS NOT NULL
    OR COALESCE(current_setting('app.access_mode', true), '') IN ('unverified', 'intake')
  );

CREATE POLICY actor_scope_outbox ON public.outbox_events AS RESTRICTIVE
  USING (public.app_actor_is_staff())
  WITH CHECK (public.app_actor_id() IS NOT NULL OR current_user = 'grok_posting');

CREATE TABLE public.step_up_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  occurred_at timestamptz NOT NULL,
  method text NOT NULL CHECK (method = 'LOCAL_DEV_PASSWORD'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT step_up_events_org_id_unique UNIQUE (organization_id, id)
);

CREATE TABLE public.payee_destinations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  party_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  masked_label text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT payee_destinations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT payee_destinations_version_unique UNIQUE (organization_id, party_id, version),
  CONSTRAINT payee_destinations_party_same_org_fkey
    FOREIGN KEY (organization_id, party_id) REFERENCES public.parties (organization_id, id)
);

CREATE TABLE public.distribution_batches (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  as_of date NOT NULL,
  status text NOT NULL,
  snapshot_hash text,
  approval_ttl_hours integer,
  approved_at timestamptz,
  expires_at timestamptz,
  total_cents bigint NOT NULL DEFAULT 0,
  retained_reserves_cents bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT distribution_batches_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT distribution_batches_status_known CHECK (status IN (
    'DRAFT', 'VALIDATED', 'AWAITING_APPROVAL', 'APPROVED', 'SUBMISSION_PENDING',
    'PARTIALLY_SETTLED', 'SETTLED', 'REJECTED', 'EXPIRED', 'CANCELED', 'FAILED', 'UNKNOWN'
  )),
  CONSTRAINT distribution_batches_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

CREATE TABLE public.distribution_items (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  batch_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('OWNER', 'CONTRACTOR', 'MANAGEMENT')),
  recipient_party_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  destination_id uuid,
  destination_version integer,
  liability_id uuid,
  status text NOT NULL,
  provider_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT distribution_items_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT distribution_items_key_unique UNIQUE (organization_id, provider_key),
  CONSTRAINT distribution_items_status_known CHECK (status IN (
    'DRAFT', 'RESERVED', 'APPROVED', 'UNKNOWN', 'SETTLED', 'FAILED', 'CANCELED', 'RETURNED'
  )),
  CONSTRAINT distribution_items_batch_same_org_fkey
    FOREIGN KEY (organization_id, batch_id) REFERENCES public.distribution_batches (organization_id, id)
);

CREATE TABLE public.fund_reservations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  item_id uuid NOT NULL,
  funding_lot_id uuid NOT NULL,
  property_id uuid NOT NULL,
  amount_cents bigint NOT NULL CHECK (amount_cents > 0),
  status text NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED', 'CONSUMED')),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT fund_reservations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT fund_reservations_item_same_org_fkey
    FOREIGN KEY (organization_id, item_id) REFERENCES public.distribution_items (organization_id, id),
  CONSTRAINT fund_reservations_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

ALTER TABLE public.funding_lots
  ADD COLUMN reserved_cents bigint NOT NULL DEFAULT 0 CHECK (reserved_cents >= 0 AND reserved_cents <= amount_cents);

CREATE TABLE public.distribution_approvals (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  batch_id uuid NOT NULL,
  actor_id uuid NOT NULL,
  snapshot_hash text NOT NULL,
  step_up_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT distribution_approvals_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT distribution_approvals_batch_same_org_fkey
    FOREIGN KEY (organization_id, batch_id) REFERENCES public.distribution_batches (organization_id, id)
);

CREATE TABLE public.distribution_exports (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  batch_id uuid NOT NULL,
  artifact_hash text NOT NULL,
  duplicate_download boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT distribution_exports_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT distribution_exports_batch_same_org_fkey
    FOREIGN KEY (organization_id, batch_id) REFERENCES public.distribution_batches (organization_id, id)
);

CREATE TABLE public.payment_events (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  item_id uuid NOT NULL,
  provider_key text NOT NULL,
  kind text NOT NULL,
  simulator boolean NOT NULL CHECK (simulator = true),
  evidence text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT payment_events_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT payment_events_item_same_org_fkey
    FOREIGN KEY (organization_id, item_id) REFERENCES public.distribution_items (organization_id, id)
);

CREATE TABLE public.owner_links (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  party_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT owner_links_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT owner_links_one UNIQUE (organization_id, user_id, party_id),
  CONSTRAINT owner_links_user_same_org_fkey
    FOREIGN KEY (organization_id, user_id) REFERENCES public.users (organization_id, id),
  CONSTRAINT owner_links_party_same_org_fkey
    FOREIGN KEY (organization_id, party_id) REFERENCES public.parties (organization_id, id)
);

CREATE TABLE public.owner_statements (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  owner_party_id uuid NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  snapshot_hash text NOT NULL,
  snapshot jsonb NOT NULL,
  superseded_by uuid,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT owner_statements_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT owner_statements_version_unique UNIQUE (organization_id, property_id, owner_party_id, period_start, period_end, version),
  CONSTRAINT owner_statements_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

REVOKE UPDATE, DELETE ON public.distribution_approvals FROM grok_app;
REVOKE UPDATE, DELETE ON public.owner_statements FROM grok_app;
REVOKE UPDATE, DELETE ON public.payment_events FROM grok_app;

CREATE FUNCTION public.prevent_statement_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'owner statements are immutable';
END;
$$;

CREATE TRIGGER trg_owner_statements_immutable
  BEFORE UPDATE OR DELETE ON public.owner_statements
  FOR EACH ROW EXECUTE FUNCTION public.prevent_statement_mutation();

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'step_up_events', 'payee_destinations', 'distribution_batches', 'distribution_items',
    'fund_reservations', 'distribution_approvals', 'distribution_exports', 'payment_events',
    'owner_links', 'owner_statements'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO grok_owner', table_name);
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON public.%I '
      'USING (organization_id = NULLIF(current_setting(''app.organization_id'', true), '''')::uuid) '
      'WITH CHECK (organization_id = NULLIF(current_setting(''app.organization_id'', true), '''')::uuid)',
      table_name
    );
    EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC', table_name);
    IF table_name IN ('distribution_approvals', 'owner_statements', 'payment_events') THEN
      EXECUTE format('GRANT SELECT, INSERT ON public.%I TO grok_app', table_name);
    ELSE
      EXECUTE format('GRANT SELECT, INSERT, UPDATE ON public.%I TO grok_app', table_name);
    END IF;
  END LOOP;
END
$$;

CREATE POLICY actor_scope_statements ON public.owner_statements AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.owner_links AS link
      WHERE link.organization_id = owner_statements.organization_id
        AND link.party_id = owner_statements.owner_party_id
        AND link.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_owner_links ON public.owner_links AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR user_id = public.app_actor_id())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_listings ON public.listings AS RESTRICTIVE
  USING (
    public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.role_grants AS g
      WHERE g.organization_id = listings.organization_id
        AND g.user_id = public.app_actor_id()
        AND g.role = 'prospect'
        AND g.resource_type IS NULL
        AND g.active_from <= clock_timestamp()
        AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
    )
  )
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_schedules ON public.schedule_configs AS RESTRICTIVE
  USING (
    public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.role_grants AS g
      WHERE g.organization_id = schedule_configs.organization_id
        AND g.user_id = public.app_actor_id()
        AND g.role = 'prospect'
        AND g.resource_type IS NULL
        AND g.active_from <= clock_timestamp()
        AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
    )
  )
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_resources ON public.scheduling_resources AS RESTRICTIVE
  USING (
    public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.role_grants AS g
      WHERE g.organization_id = scheduling_resources.organization_id
        AND g.user_id = public.app_actor_id()
        AND g.role = 'prospect'
        AND g.resource_type IS NULL
        AND g.active_from <= clock_timestamp()
        AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
    )
  )
  WITH CHECK (public.app_actor_is_staff());

DO $$
DECLARE
  rel record;
BEGIN
  FOR rel IN
    SELECT c.relname
    FROM pg_class AS c
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relkind = 'r'
      AND c.relrowsecurity
      AND NOT EXISTS (
        SELECT 1 FROM pg_policy AS p
        WHERE p.polrelid = c.oid AND NOT p.polpermissive
      )
  LOOP
    EXECUTE format(
      'CREATE POLICY actor_required ON public.%I AS RESTRICTIVE '
      'USING (public.app_actor_is_staff() OR current_user = ''grok_posting'') '
      'WITH CHECK (public.app_actor_is_staff() OR current_user = ''grok_posting'')',
      rel.relname
    );
  END LOOP;
END
$$;

CREATE FUNCTION public.app_actor_has_any_role() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.role_grants
    WHERE organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND user_id = public.app_actor_id()
      AND resource_type IS NULL
      AND active_from <= clock_timestamp()
      AND (active_until IS NULL OR active_until > clock_timestamp())
  );
$$;

REVOKE ALL ON FUNCTION public.app_actor_has_any_role() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_actor_has_any_role() TO grok_app;

DROP POLICY IF EXISTS actor_required ON public.ticket_counters;
DROP POLICY IF EXISTS actor_required ON public.escalations;
DROP POLICY IF EXISTS actor_required ON public.notification_jobs;
DROP POLICY IF EXISTS actor_required ON public.prospect_consents;
DROP POLICY IF EXISTS actor_required ON public.maintenance_appointments;
DROP POLICY IF EXISTS actor_required ON public.assignments;
DROP POLICY IF EXISTS actor_required ON public.work_orders;
DROP POLICY IF EXISTS actor_required ON public.contractor_profiles;
DROP POLICY IF EXISTS actor_required ON public.escalation_destinations;

CREATE POLICY actor_scope_escalation_destinations ON public.escalation_destinations AS RESTRICTIVE
  USING (public.app_actor_has_any_role() OR COALESCE(current_setting('app.access_mode', true), '') IN ('unverified', 'intake'))
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_contractor_profiles ON public.contractor_profiles AS RESTRICTIVE
  USING (public.app_actor_is_staff() OR user_id = public.app_actor_id())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_ticket_counters ON public.ticket_counters AS RESTRICTIVE
  USING (
    public.app_actor_has_any_role()
    OR COALESCE(current_setting('app.access_mode', true), '') IN ('unverified', 'intake')
  )
  WITH CHECK (
    public.app_actor_has_any_role()
    OR COALESCE(current_setting('app.access_mode', true), '') IN ('unverified', 'intake')
  );

CREATE POLICY actor_scope_escalations ON public.escalations AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = escalations.organization_id AND t.id = escalations.ticket_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = escalations.organization_id AND t.id = escalations.ticket_id
    )
  );

CREATE POLICY actor_scope_notification_jobs ON public.notification_jobs AS RESTRICTIVE
  USING (
    public.app_actor_has_any_role()
    OR COALESCE(current_setting('app.access_mode', true), '') IN ('unverified', 'intake')
  )
  WITH CHECK (
    public.app_actor_has_any_role()
    OR COALESCE(current_setting('app.access_mode', true), '') IN ('unverified', 'intake')
  );

CREATE POLICY actor_scope_appointments ON public.maintenance_appointments AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = maintenance_appointments.organization_id
        AND t.id = maintenance_appointments.ticket_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.maintenance_tickets AS t
      WHERE t.organization_id = maintenance_appointments.organization_id
        AND t.id = maintenance_appointments.ticket_id
    )
  );

CREATE POLICY actor_scope_assignments ON public.assignments AS RESTRICTIVE
  USING (
    public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.contractor_profiles AS c
      WHERE c.organization_id = assignments.organization_id
        AND c.id = assignments.contractor_profile_id
        AND c.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.contractor_profiles AS c
      WHERE c.organization_id = assignments.organization_id
        AND c.id = assignments.contractor_profile_id
        AND c.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_work_orders ON public.work_orders AS RESTRICTIVE
  USING (
    EXISTS (
      SELECT 1 FROM public.assignments AS a
      WHERE a.organization_id = work_orders.organization_id AND a.id = work_orders.assignment_id
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.assignments AS a
      WHERE a.organization_id = work_orders.organization_id AND a.id = work_orders.assignment_id
    )
  );

CREATE POLICY actor_scope_consents ON public.prospect_consents AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = prospect_consents.organization_id
        AND p.id = prospect_consents.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = prospect_consents.organization_id
        AND p.id = prospect_consents.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );
