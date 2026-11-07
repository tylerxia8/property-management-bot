-- Phase 3 maintenance. No external messaging and no production malware scanner.

CREATE TABLE public.lease_parties (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  lease_id uuid NOT NULL,
  user_id uuid,
  party_id uuid,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT lease_parties_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT lease_parties_lease_same_org_fkey
    FOREIGN KEY (organization_id, lease_id) REFERENCES public.leases (organization_id, id),
  CONSTRAINT lease_parties_user_same_org_fkey
    FOREIGN KEY (organization_id, user_id) REFERENCES public.users (organization_id, id),
  CONSTRAINT lease_parties_party_same_org_fkey
    FOREIGN KEY (organization_id, party_id) REFERENCES public.parties (organization_id, id)
);

CREATE TABLE public.ticket_counters (
  organization_id uuid PRIMARY KEY REFERENCES public.organizations (id),
  last_number bigint NOT NULL CHECK (last_number >= 0),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE public.maintenance_tickets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_number bigint NOT NULL,
  unit_id uuid,
  lease_id uuid,
  reporter_user_id uuid,
  verification text NOT NULL CHECK (verification IN ('VERIFIED', 'UNVERIFIED')),
  status text NOT NULL,
  category text NOT NULL DEFAULT 'general',
  emergency boolean NOT NULL DEFAULT false,
  urgent_triage boolean NOT NULL DEFAULT false,
  deescalated_by uuid,
  deescalation_reason text,
  clarification_attempts integer NOT NULL DEFAULT 0,
  handoff boolean NOT NULL DEFAULT false,
  asked_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  description text NOT NULL DEFAULT '',
  safety_context text NOT NULL DEFAULT '',
  duplicate_of_id uuid,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT maintenance_tickets_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT maintenance_tickets_number_unique UNIQUE (organization_id, ticket_number),
  CONSTRAINT maintenance_tickets_unit_same_org_fkey
    FOREIGN KEY (organization_id, unit_id) REFERENCES public.units (organization_id, id),
  CONSTRAINT maintenance_tickets_lease_same_org_fkey
    FOREIGN KEY (organization_id, lease_id) REFERENCES public.leases (organization_id, id),
  CONSTRAINT maintenance_tickets_category_known CHECK (category IN (
    'leak', 'hvac', 'electrical', 'appliance', 'structural', 'pest_mold', 'lock', 'general'
  )),
  CONSTRAINT maintenance_tickets_status_known CHECK (status IN (
    'INTAKE_OPEN', 'TRIAGE_PENDING', 'MANAGER_REVIEW', 'ASSIGNMENT_PENDING', 'ASSIGNED',
    'SCHEDULING', 'SCHEDULED', 'IN_PROGRESS', 'COMPLETION_REVIEW', 'COMPLETED', 'CLOSED',
    'WAITING_TENANT', 'WAITING_PARTS', 'WAITING_APPROVAL', 'CANCELED', 'REOPENED'
  ))
);

CREATE TABLE public.intake_fields (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  field_key text NOT NULL,
  status text NOT NULL CHECK (status IN ('PROVIDED', 'UNKNOWN', 'DECLINED', 'NOT_PRACTICAL')),
  value_text text,
  reason text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT intake_fields_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT intake_fields_one UNIQUE (organization_id, ticket_id, field_key),
  CONSTRAINT intake_fields_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id),
  CONSTRAINT intake_fields_key_known CHECK (field_key IN (
    'identity_property', 'description', 'exact_location', 'onset_frequency',
    'media', 'contact', 'access_windows', 'entry_safety'
  ))
);

CREATE TABLE public.ticket_messages (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  body text NOT NULL,
  classifier_result text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT ticket_messages_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT ticket_messages_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id)
);

CREATE TABLE public.media_objects (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('UPLOAD_REQUESTED', 'QUARANTINED', 'SCANNING', 'READY', 'REJECTED')),
  declared_content_type text NOT NULL,
  detected_type text,
  size_bytes bigint,
  sha256 text,
  storage_key text NOT NULL,
  derivative_key text,
  scanner_name text,
  scan_code text,
  rejection_reason text,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT media_objects_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT media_objects_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id)
);

CREATE TABLE public.contractor_profiles (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  party_id uuid NOT NULL,
  user_id uuid,
  approved boolean NOT NULL DEFAULT false,
  trades text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT contractor_profiles_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT contractor_profiles_party_same_org_fkey
    FOREIGN KEY (organization_id, party_id) REFERENCES public.parties (organization_id, id),
  CONSTRAINT contractor_profiles_user_same_org_fkey
    FOREIGN KEY (organization_id, user_id) REFERENCES public.users (organization_id, id)
);

CREATE TABLE public.assignments (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  contractor_profile_id uuid NOT NULL,
  status text NOT NULL CHECK (status IN ('PENDING', 'ACCEPTED', 'DECLINED')),
  scope text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT assignments_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT assignments_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id),
  CONSTRAINT assignments_contractor_same_org_fkey
    FOREIGN KEY (organization_id, contractor_profile_id) REFERENCES public.contractor_profiles (organization_id, id)
);

CREATE TABLE public.work_orders (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  assignment_id uuid NOT NULL,
  estimate_cents bigint CHECK (estimate_cents IS NULL OR estimate_cents >= 0),
  authorization_state text NOT NULL DEFAULT 'NONE' CHECK (authorization_state IN ('NONE', 'WAITING_APPROVAL')),
  completion_notes text,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT work_orders_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT work_orders_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id),
  CONSTRAINT work_orders_assignment_same_org_fkey
    FOREIGN KEY (organization_id, assignment_id) REFERENCES public.assignments (organization_id, id)
);

CREATE TABLE public.maintenance_invoice_links (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  work_order_id uuid NOT NULL,
  invoice_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT maintenance_invoice_links_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT maintenance_invoice_links_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id),
  CONSTRAINT maintenance_invoice_links_work_same_org_fkey
    FOREIGN KEY (organization_id, work_order_id) REFERENCES public.work_orders (organization_id, id),
  CONSTRAINT maintenance_invoice_links_invoice_same_org_fkey
    FOREIGN KEY (organization_id, invoice_id) REFERENCES public.invoices (organization_id, id)
);

CREATE TABLE public.escalation_destinations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  role text NOT NULL CHECK (role IN ('primary', 'alternate')),
  label text NOT NULL,
  fail_next boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT escalation_destinations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT escalation_destinations_organization_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations (id)
);

CREATE TABLE public.escalations (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  state text NOT NULL CHECK (state IN ('OPEN', 'ACKNOWLEDGED')),
  acknowledged_by uuid,
  acknowledged_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT escalations_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT escalations_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id)
);

CREATE TABLE public.notification_jobs (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  escalation_id uuid NOT NULL,
  kind text NOT NULL CHECK (kind IN ('primary', 'fallback', 'repeat')),
  status text NOT NULL CHECK (status IN ('RECORDED', 'DESTINATION_UNCONFIGURED')),
  destination_label text,
  scheduled_for timestamptz NOT NULL,
  delivered_at timestamptz,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT notification_jobs_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT notification_jobs_not_delivered CHECK (delivered_at IS NULL),
  CONSTRAINT notification_jobs_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id),
  CONSTRAINT notification_jobs_escalation_same_org_fkey
    FOREIGN KEY (organization_id, escalation_id) REFERENCES public.escalations (organization_id, id)
);

CREATE TABLE public.entry_secrets (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  ciphertext bytea NOT NULL,
  nonce bytea NOT NULL,
  key_version integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT entry_secrets_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT entry_secrets_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id)
);

CREATE TABLE public.accommodation_notes (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  ciphertext bytea NOT NULL,
  nonce bytea NOT NULL,
  key_version integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT accommodation_notes_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT accommodation_notes_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id)
);

CREATE TABLE public.maintenance_appointments (
  id uuid PRIMARY KEY,
  organization_id uuid NOT NULL,
  ticket_id uuid NOT NULL,
  unit_id uuid,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  timezone text NOT NULL,
  status text NOT NULL CHECK (status IN ('REQUESTED', 'CONFIRMED', 'CANCELED')),
  entry_permission text NOT NULL DEFAULT 'NOT_YET_GRANTED',
  notice_evidence text,
  contractor_accepted boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CONSTRAINT maintenance_appointments_time CHECK (ends_at > starts_at),
  CONSTRAINT maintenance_appointments_org_id_unique UNIQUE (organization_id, id),
  CONSTRAINT maintenance_appointments_ticket_same_org_fkey
    FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets (organization_id, id),
  CONSTRAINT maintenance_appointments_unit_same_org_fkey
    FOREIGN KEY (organization_id, unit_id) REFERENCES public.units (organization_id, id),
  CONSTRAINT maintenance_appointments_no_overlap EXCLUDE USING gist (
    organization_id WITH =,
    unit_id WITH =,
    tstzrange(starts_at, ends_at, '[)') WITH &&
  ) WHERE (status = 'CONFIRMED' AND unit_id IS NOT NULL)
);

DO $$
DECLARE
  table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'lease_parties', 'ticket_counters', 'maintenance_tickets', 'intake_fields', 'ticket_messages',
    'media_objects', 'contractor_profiles', 'assignments', 'work_orders', 'maintenance_invoice_links',
    'escalation_destinations', 'escalations', 'notification_jobs', 'entry_secrets',
    'accommodation_notes', 'maintenance_appointments'
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
    EXECUTE format('GRANT SELECT, INSERT, UPDATE ON public.%I TO grok_app', table_name);
  END LOOP;
END
$$;
