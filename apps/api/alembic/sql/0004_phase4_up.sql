-- Phase 4 prospects and tours. No consumer reports and no external calendar writes.

CREATE FUNCTION public.app_actor_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
  SELECT NULLIF(current_setting('app.actor_id', true), '')::uuid
$$;

CREATE FUNCTION public.app_actor_is_staff() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.role_grants
    WHERE organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND user_id = public.app_actor_id()
      AND role IN ('property_manager', 'organization_administrator', 'accounting_staff')
      AND resource_type IS NULL
      AND active_from <= clock_timestamp()
      AND (active_until IS NULL OR active_until > clock_timestamp())
  );
$$;

CREATE FUNCTION public.app_actor_is_manager() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.role_grants
    WHERE organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
      AND user_id = public.app_actor_id()
      AND role IN ('property_manager', 'organization_administrator')
      AND resource_type IS NULL
      AND active_from <= clock_timestamp()
      AND (active_until IS NULL OR active_until > clock_timestamp())
  );
$$;

REVOKE ALL ON FUNCTION public.app_actor_id() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_actor_is_staff() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.app_actor_is_manager() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_actor_id() TO grok_app, grok_posting;
GRANT EXECUTE ON FUNCTION public.app_actor_is_staff() TO grok_app, grok_posting;
GRANT EXECUTE ON FUNCTION public.app_actor_is_manager() TO grok_app;
GRANT SELECT ON public.role_grants TO grok_posting;

CREATE TABLE public.listings (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  unit_id uuid,
  external_source text NOT NULL,
  external_listing_id text NOT NULL,
  display_label text NOT NULL,
  asking_rent_cents bigint NOT NULL CHECK (asking_rent_cents >= 0),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT listings_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT listings_external_unique UNIQUE (organization_id, external_source, external_listing_id),
  CONSTRAINT listings_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT listings_unit_same_org_fkey
    FOREIGN KEY (organization_id, unit_id) REFERENCES public.units (organization_id, id)
);

CREATE TABLE public.prospects (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  user_id uuid,
  listing_id uuid,
  property_id uuid,
  unit_id uuid,
  state text NOT NULL,
  intake_version bigint NOT NULL DEFAULT 1 CHECK (intake_version > 0),
  unverified boolean NOT NULL DEFAULT true,
  disclosure_shown boolean NOT NULL DEFAULT true,
  booking_exception boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT prospects_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT prospects_state_known CHECK (state IN (
    'NEW', 'COLLECTING', 'NEEDS_INFORMATION', 'HUMAN_REVIEW', 'PRELIMINARILY_QUALIFIED',
    'TOUR_REQUESTED', 'TOUR_CONFIRMED', 'TOUR_COMPLETED', 'APPLICATION_INVITED',
    'WITHDRAWN', 'UNRESPONSIVE', 'TOUR_CANCELED', 'NO_SHOW'
  )),
  CONSTRAINT prospects_user_same_org_fkey
    FOREIGN KEY (organization_id, user_id) REFERENCES public.users (organization_id, id),
  CONSTRAINT prospects_listing_same_org_fkey
    FOREIGN KEY (organization_id, listing_id) REFERENCES public.listings (organization_id, id)
);

CREATE UNIQUE INDEX prospects_one_user ON public.prospects (organization_id, user_id) WHERE user_id IS NOT NULL;

CREATE TABLE public.inquiries (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  provider text NOT NULL,
  provider_message_id text NOT NULL,
  external_listing_id text,
  address_hint text,
  listing_id uuid,
  prospect_id uuid,
  ambiguous boolean NOT NULL DEFAULT false,
  clarification text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT inquiries_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT inquiries_provider_message UNIQUE (organization_id, provider, provider_message_id),
  CONSTRAINT inquiries_listing_same_org_fkey
    FOREIGN KEY (organization_id, listing_id) REFERENCES public.listings (organization_id, id),
  CONSTRAINT inquiries_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id)
);

CREATE TABLE public.prospect_intakes (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  move_in_date date,
  lease_months integer CHECK (lease_months IS NULL OR lease_months > 0),
  income_original_cents bigint CHECK (income_original_cents IS NULL OR income_original_cents >= 0),
  income_period text CHECK (income_period IS NULL OR income_period IN ('weekly', 'biweekly', 'monthly', 'annual')),
  income_monthly_cents bigint CHECK (income_monthly_cents IS NULL OR income_monthly_cents >= 0),
  income_unverified boolean NOT NULL DEFAULT true,
  occupant_count integer CHECK (occupant_count IS NULL OR occupant_count > 0),
  pets_declared boolean,
  assistance_animal_requested boolean NOT NULL DEFAULT false,
  rental_history text,
  income_source text,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT prospect_intakes_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT prospect_intakes_one UNIQUE (organization_id, prospect_id),
  CONSTRAINT prospect_intakes_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id)
);

CREATE TABLE public.screening_policies (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  status text NOT NULL CHECK (status = 'REVIEWED_ACTIVE'),
  fixture boolean NOT NULL DEFAULT false,
  legal_review_reference text NOT NULL,
  review_reason text NOT NULL,
  reviewed_by uuid NOT NULL,
  effective_at timestamptz NOT NULL,
  rules jsonb NOT NULL,
  missing_action text NOT NULL CHECK (missing_action IN ('NEEDS_INFORMATION', 'HUMAN_REVIEW')),
  accommodation_action text NOT NULL CHECK (accommodation_action = 'HUMAN_REVIEW'),
  automatic_final_denial boolean NOT NULL CHECK (automatic_final_denial = false),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT screening_policies_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT screening_policies_version_unique UNIQUE (organization_id, property_id, version),
  CONSTRAINT screening_policies_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT screening_policies_fixture_label CHECK (fixture = false OR legal_review_reference LIKE 'fixture:%')
);

CREATE TABLE public.policy_evaluations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  intake_version bigint NOT NULL,
  policy_id uuid,
  policy_version integer,
  input_hash text NOT NULL,
  result text NOT NULL CHECK (result IN ('PRELIMINARILY_QUALIFIED', 'NEEDS_INFORMATION', 'HUMAN_REVIEW')),
  missing_fields jsonb NOT NULL,
  rule_results jsonb NOT NULL,
  formal_screening_permitted boolean NOT NULL CHECK (formal_screening_permitted = false),
  configuration_code text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT policy_evaluations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT policy_evaluations_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id),
  CONSTRAINT policy_evaluations_policy_same_org_fkey
    FOREIGN KEY (organization_id, policy_id) REFERENCES public.screening_policies (organization_id, id)
);

CREATE TABLE public.human_reviews (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  evaluation_id uuid,
  property_id uuid,
  reason text NOT NULL,
  rule_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  state text NOT NULL CHECK (state IN ('OPEN', 'RESOLVED')),
  resolution text,
  exception_granted boolean NOT NULL DEFAULT false,
  exception_reason text,
  reviewer_id uuid,
  opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  resolved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT human_reviews_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT human_reviews_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id),
  CONSTRAINT human_reviews_evaluation_same_org_fkey
    FOREIGN KEY (organization_id, evaluation_id) REFERENCES public.policy_evaluations (organization_id, id)
);

CREATE TABLE public.accommodation_cases (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  subject_user_id uuid,
  ciphertext bytea NOT NULL,
  nonce bytea NOT NULL,
  key_version integer NOT NULL,
  state text NOT NULL CHECK (state = 'OPEN'),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT accommodation_cases_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT accommodation_cases_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id)
);

CREATE TABLE public.schedule_configs (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  duration_minutes integer NOT NULL CHECK (duration_minutes > 0),
  buffer_minutes integer NOT NULL CHECK (buffer_minutes >= 0),
  hold_minutes integer NOT NULL CHECK (hold_minutes > 0),
  min_notice_minutes integer NOT NULL CHECK (min_notice_minutes >= 0),
  day_start time NOT NULL,
  day_end time NOT NULL,
  open_weekdays integer[] NOT NULL,
  timezone text NOT NULL,
  fixture boolean NOT NULL DEFAULT false,
  label text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT schedule_configs_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT schedule_configs_property_unique UNIQUE (organization_id, property_id),
  CONSTRAINT schedule_configs_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT schedule_configs_hours CHECK (day_end > day_start),
  CONSTRAINT schedule_configs_fixture_label CHECK (fixture = false OR label LIKE 'fixture:%')
);

CREATE TABLE public.scheduling_resources (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  property_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind = 'AGENT'),
  display_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT scheduling_resources_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT scheduling_resources_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id)
);

CREATE TABLE public.tour_appointments (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  property_id uuid NOT NULL,
  unit_id uuid,
  resource_id uuid NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  blocked_starts_at timestamptz NOT NULL,
  blocked_ends_at timestamptz NOT NULL,
  timezone text NOT NULL,
  status text NOT NULL CHECK (status IN (
    'HELD', 'EXPIRED', 'CONFIRMATION_PENDING', 'MANAGER_CONFIRMED', 'CANCELED', 'COMPLETED', 'NO_SHOW'
  )),
  expires_at timestamptz,
  external_event_key text,
  external_event_created boolean NOT NULL DEFAULT false CHECK (external_event_created = false),
  access_evidence text,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT tour_appointments_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT tour_appointments_time CHECK (ends_at > starts_at AND blocked_ends_at > blocked_starts_at),
  CONSTRAINT tour_appointments_event_key UNIQUE (organization_id, external_event_key),
  CONSTRAINT tour_appointments_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id),
  CONSTRAINT tour_appointments_property_same_org_fkey
    FOREIGN KEY (organization_id, property_id) REFERENCES public.properties (organization_id, id),
  CONSTRAINT tour_appointments_unit_same_org_fkey
    FOREIGN KEY (organization_id, unit_id) REFERENCES public.units (organization_id, id),
  CONSTRAINT tour_appointments_resource_same_org_fkey
    FOREIGN KEY (organization_id, resource_id) REFERENCES public.scheduling_resources (organization_id, id),
  CONSTRAINT tour_appointments_no_overlap EXCLUDE USING gist (
    organization_id WITH =,
    resource_id WITH =,
    tstzrange(blocked_starts_at, blocked_ends_at, '[)') WITH &&
  ) WHERE (status IN ('HELD', 'CONFIRMATION_PENDING', 'MANAGER_CONFIRMED'))
);

CREATE TABLE public.prospect_consents (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  channel text NOT NULL CHECK (channel IN ('email', 'sms')),
  allowed boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT prospect_consents_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT prospect_consents_one UNIQUE (organization_id, prospect_id, channel),
  CONSTRAINT prospect_consents_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id)
);

CREATE TABLE public.reminder_jobs (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  appointment_id uuid NOT NULL,
  appointment_version bigint NOT NULL,
  offset_minutes integer NOT NULL,
  channel text NOT NULL CHECK (channel IN ('email', 'sms')),
  status text NOT NULL CHECK (status IN ('SCHEDULED', 'SUPPRESSED', 'OPTED_OUT')),
  delivered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT reminder_jobs_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT reminder_jobs_one UNIQUE (organization_id, appointment_id, appointment_version, offset_minutes, channel),
  CONSTRAINT reminder_jobs_not_delivered CHECK (delivered_at IS NULL),
  CONSTRAINT reminder_jobs_appointment_same_org_fkey
    FOREIGN KEY (organization_id, appointment_id) REFERENCES public.tour_appointments (organization_id, id)
);

CREATE TABLE public.application_invitations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  appointment_id uuid NOT NULL,
  invited_by uuid NOT NULL,
  external_reference text,
  status text NOT NULL CHECK (status = 'INVITED'),
  report_ordered boolean NOT NULL DEFAULT false CHECK (report_ordered = false),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT application_invitations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT application_invitations_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id),
  CONSTRAINT application_invitations_tour_same_org_fkey
    FOREIGN KEY (organization_id, appointment_id) REFERENCES public.tour_appointments (organization_id, id)
);

CREATE TABLE public.housing_dispositions (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  prospect_id uuid NOT NULL,
  decision_note text NOT NULL,
  reason text NOT NULL,
  decided_by uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT housing_dispositions_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT housing_dispositions_prospect_same_org_fkey
    FOREIGN KEY (organization_id, prospect_id) REFERENCES public.prospects (organization_id, id)
);

REVOKE UPDATE, DELETE ON public.policy_evaluations FROM grok_app;
REVOKE UPDATE, DELETE ON public.housing_dispositions FROM grok_app;

CREATE FUNCTION public.prevent_evaluation_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'policy evaluations are immutable';
END;
$$;

CREATE TRIGGER trg_policy_evaluations_immutable
  BEFORE UPDATE OR DELETE ON public.policy_evaluations
  FOR EACH ROW EXECUTE FUNCTION public.prevent_evaluation_mutation();

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'listings', 'prospects', 'inquiries', 'prospect_intakes', 'screening_policies',
    'policy_evaluations', 'human_reviews', 'accommodation_cases', 'schedule_configs',
    'scheduling_resources', 'tour_appointments', 'prospect_consents', 'reminder_jobs',
    'application_invitations', 'housing_dispositions'
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
    IF table_name = 'policy_evaluations' OR table_name = 'housing_dispositions' THEN
      EXECUTE format('GRANT SELECT, INSERT ON public.%I TO grok_app', table_name);
    ELSE
      EXECUTE format('GRANT SELECT, INSERT, UPDATE ON public.%I TO grok_app', table_name);
    END IF;
  END LOOP;
END
$$;

CREATE POLICY actor_scope_prospects ON public.prospects AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_manager() OR user_id = public.app_actor_id())
  WITH CHECK (public.app_actor_id() IS NULL OR public.app_actor_is_manager() OR user_id = public.app_actor_id());

CREATE POLICY actor_scope_intakes ON public.prospect_intakes AS RESTRICTIVE
  USING (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = prospect_intakes.organization_id
        AND p.id = prospect_intakes.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = prospect_intakes.organization_id
        AND p.id = prospect_intakes.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_accommodation_cases ON public.accommodation_cases AS RESTRICTIVE
  USING (
    public.app_actor_is_manager()
    OR subject_user_id = public.app_actor_id()
  )
  WITH CHECK (
    public.app_actor_is_manager()
    OR subject_user_id = public.app_actor_id()
  );

CREATE POLICY actor_scope_evaluations ON public.policy_evaluations AS RESTRICTIVE
  USING (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = policy_evaluations.organization_id
        AND p.id = policy_evaluations.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = policy_evaluations.organization_id
        AND p.id = policy_evaluations.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_reviews ON public.human_reviews AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_manager())
  WITH CHECK (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = human_reviews.organization_id
        AND p.id = human_reviews.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_policies ON public.screening_policies AS RESTRICTIVE
  USING (
    public.app_actor_id() IS NULL
    OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.role_grants
      WHERE organization_id = screening_policies.organization_id
        AND user_id = public.app_actor_id()
        AND role = 'prospect'
        AND resource_type IS NULL
        AND active_from <= clock_timestamp()
        AND (active_until IS NULL OR active_until > clock_timestamp())
    )
  )
  WITH CHECK (public.app_actor_is_manager());

CREATE POLICY actor_scope_tours ON public.tour_appointments AS RESTRICTIVE
  USING (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = tour_appointments.organization_id
        AND p.id = tour_appointments.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  )
  WITH CHECK (
    public.app_actor_id() IS NULL OR public.app_actor_is_manager()
    OR EXISTS (
      SELECT 1 FROM public.prospects AS p
      WHERE p.organization_id = tour_appointments.organization_id
        AND p.id = tour_appointments.prospect_id
        AND p.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_properties ON public.properties AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_staff());

CREATE POLICY actor_scope_units ON public.units AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_staff());

CREATE POLICY actor_scope_leases ON public.leases AS RESTRICTIVE
  USING (
    public.app_actor_id() IS NULL OR public.app_actor_is_staff()
    OR EXISTS (
      SELECT 1 FROM public.lease_parties AS lp
      WHERE lp.organization_id = leases.organization_id
        AND lp.lease_id = leases.id
        AND lp.user_id = public.app_actor_id()
    )
  );

CREATE POLICY actor_scope_lease_parties ON public.lease_parties AS RESTRICTIVE
  USING (
    public.app_actor_id() IS NULL OR public.app_actor_is_staff()
    OR user_id = public.app_actor_id()
  );

CREATE POLICY actor_scope_tickets ON public.maintenance_tickets AS RESTRICTIVE
  USING (
    (public.app_actor_id() IS NULL AND NULLIF(current_setting('app.intake_ticket_id', true), '') IS NULL AND COALESCE(current_setting('app.access_mode', true), '') = '')
    OR (public.app_actor_id() IS NULL AND id::text = NULLIF(current_setting('app.intake_ticket_id', true), ''))
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
    (public.app_actor_id() IS NULL AND COALESCE(current_setting('app.access_mode', true), '') = 'unverified' AND verification = 'UNVERIFIED')
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

CREATE POLICY actor_scope_entry_secrets ON public.entry_secrets AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_accommodation_notes ON public.accommodation_notes AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_staff())
  WITH CHECK (public.app_actor_is_staff());

CREATE POLICY actor_scope_journals ON public.journal_entries AS RESTRICTIVE
  USING (
    current_user = 'grok_posting'
    OR public.app_actor_id() IS NULL
    OR public.app_actor_is_staff()
  )
  WITH CHECK (
    current_user = 'grok_posting'
    OR public.app_actor_is_staff()
  );

CREATE POLICY actor_scope_journal_lines ON public.journal_lines AS RESTRICTIVE
  USING (
    current_user = 'grok_posting'
    OR public.app_actor_id() IS NULL
    OR public.app_actor_is_staff()
  )
  WITH CHECK (
    current_user = 'grok_posting'
    OR public.app_actor_is_staff()
  );

CREATE POLICY actor_scope_receipts ON public.receipts AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_staff());

CREATE POLICY actor_scope_invoices ON public.invoices AS RESTRICTIVE
  USING (public.app_actor_id() IS NULL OR public.app_actor_is_staff())
  WITH CHECK (public.app_actor_id() IS NULL OR public.app_actor_is_staff());
