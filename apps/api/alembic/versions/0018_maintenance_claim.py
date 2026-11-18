from alembic import op

revision = "0018_maintenance_claim"
down_revision = "0017_demo_maintenance"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE public.contractor_profiles ADD COLUMN can_claim_unassigned boolean NOT NULL DEFAULT false;
        CREATE FUNCTION public.app_can_claim_maintenance_ticket(ticket uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.maintenance_tickets t
                JOIN public.units u ON u.organization_id=t.organization_id AND u.id=t.unit_id
                WHERE t.id=ticket AND t.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
                AND t.verification='VERIFIED' AND NOT t.emergency AND t.active_assignment_id IS NULL
                AND t.status NOT IN ('COMPLETION_REVIEW','COMPLETED','CLOSED','CANCELED')
                AND NOT EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.ticket_id=t.id AND a.status='DECLINED' AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid)
                AND EXISTS (SELECT 1 FROM public.contractor_profiles c WHERE c.organization_id=t.organization_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND c.approved AND c.can_claim_unassigned)
                AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=t.organization_id AND g.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role='contractor' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp()))
            )
        $$;
        ALTER FUNCTION public.app_can_claim_maintenance_ticket(uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_can_claim_maintenance_ticket(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_can_claim_maintenance_ticket(uuid) TO grok_app;
        GRANT INSERT ON public.assignments,public.work_orders TO grok_auth;
        CREATE FUNCTION public.app_claim_maintenance_ticket(ticket uuid) RETURNS TABLE(assignment_id uuid,work_order_id uuid) LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE
            selected_ticket public.maintenance_tickets%ROWTYPE;
            selected_profile uuid;
        BEGIN
            SELECT * INTO selected_ticket FROM public.maintenance_tickets t WHERE t.id=ticket AND t.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid FOR UPDATE;
            IF NOT FOUND OR selected_ticket.active_assignment_id IS NOT NULL OR selected_ticket.verification <> 'VERIFIED' OR selected_ticket.unit_id IS NULL OR selected_ticket.emergency OR selected_ticket.status IN ('COMPLETION_REVIEW','COMPLETED','CLOSED','CANCELED') OR NOT public.app_can_claim_maintenance_ticket(ticket) THEN
                RETURN;
            END IF;
            SELECT c.id INTO selected_profile FROM public.contractor_profiles c WHERE c.organization_id=selected_ticket.organization_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND c.approved AND c.can_claim_unassigned ORDER BY c.created_at,c.id LIMIT 1;
            IF NOT FOUND THEN
                RETURN;
            END IF;
            assignment_id := gen_random_uuid();
            work_order_id := gen_random_uuid();
            INSERT INTO public.assignments(id,organization_id,ticket_id,contractor_profile_id,status,scope) VALUES (assignment_id,selected_ticket.organization_id,ticket,selected_profile,'PENDING',selected_ticket.description);
            INSERT INTO public.work_orders(id,organization_id,ticket_id,assignment_id,workflow_managed) VALUES (work_order_id,selected_ticket.organization_id,ticket,assignment_id,true);
            UPDATE public.maintenance_tickets SET active_assignment_id=app_claim_maintenance_ticket.assignment_id WHERE id=ticket AND organization_id=selected_ticket.organization_id;
            RETURN NEXT;
        END
        $$;
        ALTER FUNCTION public.app_claim_maintenance_ticket(uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_claim_maintenance_ticket(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_claim_maintenance_ticket(uuid) TO grok_app;
        DROP POLICY actor_scope_tickets ON public.maintenance_tickets;
        CREATE POLICY actor_scope_tickets ON public.maintenance_tickets AS RESTRICTIVE FOR SELECT USING (
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
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
        AND c.user_id = public.app_actor_id()
    )
   OR public.app_can_claim_maintenance_ticket(id));
        CREATE POLICY actor_update_tickets ON public.maintenance_tickets AS RESTRICTIVE FOR UPDATE USING (
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
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
        AND c.user_id = public.app_actor_id()
    )
  ) WITH CHECK (
    (COALESCE(current_setting('app.access_mode', true), '') = 'unverified' AND verification = 'UNVERIFIED' AND reporter_user_id IS NULL)
    OR (public.app_actor_id() IS NULL AND id::text = NULLIF(current_setting('app.intake_ticket_id', true), ''))
    OR public.app_actor_is_staff()
    OR reporter_user_id = public.app_actor_id()
    OR EXISTS (
      SELECT 1 FROM public.assignments AS a
      JOIN public.contractor_profiles AS c
        ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id
      WHERE a.organization_id = maintenance_tickets.organization_id
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
        AND c.user_id = public.app_actor_id()
    )
  );
        CREATE POLICY actor_insert_tickets ON public.maintenance_tickets AS RESTRICTIVE FOR INSERT WITH CHECK (
    (COALESCE(current_setting('app.access_mode', true), '') = 'unverified' AND verification = 'UNVERIFIED' AND reporter_user_id IS NULL)
    OR (public.app_actor_id() IS NULL AND id::text = NULLIF(current_setting('app.intake_ticket_id', true), ''))
    OR public.app_actor_is_staff()
    OR reporter_user_id = public.app_actor_id()
    OR EXISTS (
      SELECT 1 FROM public.assignments AS a
      JOIN public.contractor_profiles AS c
        ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id
      WHERE a.organization_id = maintenance_tickets.organization_id
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
        AND c.user_id = public.app_actor_id()
    )
  );
        CREATE POLICY actor_delete_tickets ON public.maintenance_tickets AS RESTRICTIVE FOR DELETE USING (
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
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
        AND c.user_id = public.app_actor_id()
    )
  );
        CREATE OR REPLACE FUNCTION public.app_workflow_home(ticket uuid) RETURNS TABLE(property_name text,unit_label text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$ SELECT p.name::text,u.label::text FROM public.maintenance_tickets t JOIN public.units u ON u.organization_id = t.organization_id AND u.id = t.unit_id JOIN public.properties p ON p.organization_id = u.organization_id AND p.id = u.property_id WHERE t.id = ticket AND t.organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND (EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id = t.organization_id AND g.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role IN ('property_manager','organization_administrator') AND g.resource_type IS NULL AND g.active_from <= clock_timestamp() AND (g.active_until IS NULL OR g.active_until > clock_timestamp())) OR public.app_can_claim_maintenance_ticket(t.id) OR t.reporter_user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id WHERE a.organization_id = t.organization_id AND a.id = t.active_assignment_id AND c.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid)) $$;
    """)


def downgrade():
    op.execute("""
        DROP POLICY actor_scope_tickets ON public.maintenance_tickets;
        DROP POLICY actor_update_tickets ON public.maintenance_tickets;
        DROP POLICY actor_insert_tickets ON public.maintenance_tickets;
        DROP POLICY actor_delete_tickets ON public.maintenance_tickets;
        CREATE POLICY actor_scope_tickets ON public.maintenance_tickets AS RESTRICTIVE USING (
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
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
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
        AND a.ticket_id = maintenance_tickets.id AND a.id = maintenance_tickets.active_assignment_id
        AND c.user_id = public.app_actor_id()
    )
  );
        CREATE OR REPLACE FUNCTION public.app_workflow_home(ticket uuid) RETURNS TABLE(property_name text,unit_label text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$ SELECT p.name::text,u.label::text FROM public.maintenance_tickets t JOIN public.units u ON u.organization_id = t.organization_id AND u.id = t.unit_id JOIN public.properties p ON p.organization_id = u.organization_id AND p.id = u.property_id WHERE t.id = ticket AND t.organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND (EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id = t.organization_id AND g.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role IN ('property_manager','organization_administrator') AND g.resource_type IS NULL AND g.active_from <= clock_timestamp() AND (g.active_until IS NULL OR g.active_until > clock_timestamp())) OR t.reporter_user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id WHERE a.organization_id = t.organization_id AND a.id = t.active_assignment_id AND c.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid)) $$;
        DROP FUNCTION public.app_claim_maintenance_ticket(uuid);
        REVOKE INSERT ON public.assignments,public.work_orders FROM grok_auth;
        DROP FUNCTION public.app_can_claim_maintenance_ticket(uuid);
        ALTER TABLE public.contractor_profiles DROP COLUMN can_claim_unassigned;
    """)
