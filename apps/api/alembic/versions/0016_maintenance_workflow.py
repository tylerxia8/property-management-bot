from alembic import op

revision = "0016_maintenance_workflow"
down_revision = "0015_maintenance_routing"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TRIGGER workflow_assignments_updated BEFORE UPDATE ON public.assignments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER workflow_work_orders_updated BEFORE UPDATE ON public.work_orders FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        CREATE TRIGGER workflow_appointments_updated BEFORE UPDATE ON public.maintenance_appointments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
        ALTER TABLE public.maintenance_tickets ADD COLUMN availability_windows jsonb NOT NULL DEFAULT '[]'::jsonb, ADD COLUMN active_assignment_id uuid, ADD FOREIGN KEY (organization_id,active_assignment_id) REFERENCES public.assignments(organization_id,id);
        UPDATE public.maintenance_tickets t SET active_assignment_id = (SELECT a.id FROM public.assignments a WHERE a.organization_id = t.organization_id AND a.ticket_id = t.id ORDER BY a.created_at DESC,a.id DESC LIMIT 1);
        ALTER TABLE public.ticket_messages ADD COLUMN author_id uuid, ADD COLUMN author_role text NOT NULL DEFAULT 'tenant' CHECK (author_role IN ('tenant','manager','contractor','system')), ADD COLUMN sender_label text NOT NULL DEFAULT 'Resident', ADD COLUMN media_ids jsonb NOT NULL DEFAULT '[]'::jsonb, ADD FOREIGN KEY (organization_id,author_id) REFERENCES public.users(organization_id,id);
        UPDATE public.ticket_messages SET author_role = 'system',sender_label = 'System' WHERE body LIKE 'Simulated SMS reply: %' OR body LIKE 'SMS reply queued: %';
        ALTER TABLE public.work_orders DROP CONSTRAINT work_orders_authorization_state_check;
        ALTER TABLE public.work_orders ADD CONSTRAINT work_orders_authorization_state_check CHECK (authorization_state IN ('NONE','WAITING_APPROVAL','APPROVED','REJECTED'));
        ALTER TABLE public.work_orders ADD COLUMN workflow_managed boolean NOT NULL DEFAULT false, ADD COLUMN estimate_version integer NOT NULL DEFAULT 0, ADD COLUMN estimate_scope text, ADD COLUMN approved_version integer, ADD COLUMN spending_limit_cents bigint CHECK (spending_limit_cents >= 0), ADD COLUMN approved_by uuid, ADD COLUMN approved_at timestamptz, ADD COLUMN started_at timestamptz, ADD COLUMN completion_media_ids jsonb NOT NULL DEFAULT '[]'::jsonb, ADD COLUMN confirmed_at timestamptz, ADD FOREIGN KEY (organization_id,approved_by) REFERENCES public.users(organization_id,id);
        ALTER TABLE public.maintenance_appointments ADD COLUMN assignment_id uuid, ADD COLUMN entry_granted_by uuid, ADD FOREIGN KEY (organization_id,assignment_id) REFERENCES public.assignments(organization_id,id), ADD FOREIGN KEY (organization_id,entry_granted_by) REFERENCES public.users(organization_id,id);
        ALTER TABLE public.work_orders ADD CONSTRAINT work_order_current_approval CHECK (authorization_state <> 'APPROVED' OR (estimate_cents IS NOT NULL AND approved_version IS NOT NULL AND approved_version=estimate_version AND approved_by IS NOT NULL AND approved_at IS NOT NULL AND spending_limit_cents IS NOT NULL AND spending_limit_cents>=estimate_cents));
        CREATE FUNCTION public.app_workflow_contractors() RETURNS TABLE(id uuid,name text,trades text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$ SELECT c.id,u.display_name::text,c.trades::text FROM public.contractor_profiles c JOIN public.users u ON u.organization_id=c.organization_id AND u.id=c.user_id WHERE c.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND c.approved AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=c.organization_id AND g.user_id=u.id AND g.role='contractor' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp())) AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=c.organization_id AND g.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role IN ('property_manager','organization_administrator') AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp())) ORDER BY c.created_at $$;
        ALTER FUNCTION public.app_workflow_contractors() OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_workflow_contractors() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_workflow_contractors() TO grok_app;
        GRANT UPDATE(active_assignment_id) ON public.maintenance_tickets TO grok_auth;
        CREATE FUNCTION public.app_workflow_release_assignment(ticket uuid,assignment uuid) RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$ UPDATE public.maintenance_tickets t SET active_assignment_id=NULL WHERE t.id=ticket AND t.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND t.active_assignment_id=assignment AND EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.id=assignment AND a.status='DECLINED' AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid) RETURNING true $$;
        ALTER FUNCTION public.app_workflow_release_assignment(uuid,uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_workflow_release_assignment(uuid,uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_workflow_release_assignment(uuid,uuid) TO grok_app;
        CREATE FUNCTION public.app_workflow_reporter(ticket uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$ SELECT EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.id = ticket AND t.organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND t.reporter_user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid) $$;
        GRANT SELECT ON public.maintenance_tickets TO grok_auth;
        ALTER FUNCTION public.app_workflow_reporter(uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_workflow_reporter(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_workflow_reporter(uuid) TO grok_app;
        CREATE FUNCTION public.app_workflow_home(ticket uuid) RETURNS TABLE(property_name text,unit_label text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$ SELECT p.name::text,u.label::text FROM public.maintenance_tickets t JOIN public.units u ON u.organization_id = t.organization_id AND u.id = t.unit_id JOIN public.properties p ON p.organization_id = u.organization_id AND p.id = u.property_id WHERE t.id = ticket AND t.organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND (EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id = t.organization_id AND g.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role IN ('property_manager','organization_administrator') AND g.resource_type IS NULL AND g.active_from <= clock_timestamp() AND (g.active_until IS NULL OR g.active_until > clock_timestamp())) OR t.reporter_user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id WHERE a.organization_id = t.organization_id AND a.id = t.active_assignment_id AND c.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid)) $$;
        GRANT SELECT ON public.assignments,public.contractor_profiles,public.units,public.properties TO grok_auth;
        ALTER FUNCTION public.app_workflow_home(uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_workflow_home(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_workflow_home(uuid) TO grok_app;
        ALTER POLICY actor_scope_tickets ON public.maintenance_tickets USING (
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
        ALTER POLICY actor_scope_assignments ON public.assignments USING (public.app_actor_is_staff() OR public.app_workflow_reporter(ticket_id) OR EXISTS (SELECT 1 FROM public.contractor_profiles c WHERE c.organization_id = assignments.organization_id AND c.id = assignments.contractor_profile_id AND c.user_id = public.app_actor_id()));
        ALTER POLICY actor_scope_work_orders ON public.work_orders WITH CHECK (public.app_actor_is_manager() OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id = a.organization_id AND c.id = a.contractor_profile_id WHERE a.organization_id = work_orders.organization_id AND a.id = work_orders.assignment_id AND c.user_id = public.app_actor_id()) OR public.app_workflow_reporter(ticket_id));
        ALTER POLICY maintenance_update_scope ON public.maintenance_status_updates USING (organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id = maintenance_status_updates.organization_id AND t.id = maintenance_status_updates.ticket_id)) WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id = maintenance_status_updates.organization_id AND t.id = maintenance_status_updates.ticket_id));
    """)


def downgrade():
    op.execute("""
        DROP FUNCTION public.app_workflow_contractors();
        DROP FUNCTION public.app_workflow_release_assignment(uuid,uuid);
        ALTER TABLE public.work_orders DROP CONSTRAINT work_order_current_approval;
        DROP TRIGGER workflow_assignments_updated ON public.assignments;
        DROP TRIGGER workflow_work_orders_updated ON public.work_orders;
        DROP TRIGGER workflow_appointments_updated ON public.maintenance_appointments;
        ALTER POLICY actor_scope_tickets ON public.maintenance_tickets USING (
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
        ALTER POLICY actor_scope_assignments ON public.assignments USING (public.app_actor_is_staff() OR EXISTS (SELECT 1 FROM public.contractor_profiles c WHERE c.organization_id = assignments.organization_id AND c.id = assignments.contractor_profile_id AND c.user_id = public.app_actor_id()));
        ALTER POLICY actor_scope_work_orders ON public.work_orders WITH CHECK (EXISTS (SELECT 1 FROM public.assignments a WHERE a.organization_id = work_orders.organization_id AND a.id = work_orders.assignment_id));
        ALTER POLICY maintenance_update_scope ON public.maintenance_status_updates USING (organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id = maintenance_status_updates.organization_id AND t.id = maintenance_status_updates.ticket_id AND (EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id = t.organization_id AND g.user_id = NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role IN ('property_manager','organization_administrator') AND g.resource_type IS NULL AND g.active_from <= clock_timestamp() AND (g.active_until IS NULL OR g.active_until > clock_timestamp())) OR t.reporter_user_id = public.app_actor_id()))) WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager());
        DROP FUNCTION public.app_workflow_reporter(uuid);
        DROP FUNCTION public.app_workflow_home(uuid);
        ALTER TABLE public.maintenance_appointments DROP COLUMN assignment_id, DROP COLUMN entry_granted_by;
        ALTER TABLE public.work_orders DROP CONSTRAINT work_orders_authorization_state_check;
        UPDATE public.work_orders SET authorization_state = 'WAITING_APPROVAL' WHERE authorization_state IN ('APPROVED','REJECTED');
        ALTER TABLE public.work_orders ADD CONSTRAINT work_orders_authorization_state_check CHECK (authorization_state IN ('NONE','WAITING_APPROVAL'));
        ALTER TABLE public.work_orders DROP COLUMN workflow_managed, DROP COLUMN estimate_version, DROP COLUMN estimate_scope, DROP COLUMN approved_version, DROP COLUMN spending_limit_cents, DROP COLUMN approved_by, DROP COLUMN approved_at, DROP COLUMN started_at, DROP COLUMN completion_media_ids, DROP COLUMN confirmed_at;
        ALTER TABLE public.ticket_messages DROP COLUMN author_id, DROP COLUMN author_role, DROP COLUMN sender_label, DROP COLUMN media_ids;
        ALTER TABLE public.maintenance_tickets DROP COLUMN availability_windows, DROP COLUMN active_assignment_id;
    """)
