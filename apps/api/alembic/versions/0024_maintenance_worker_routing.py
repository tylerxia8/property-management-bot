from alembic import op

revision = "0024_maintenance_worker_routing"
down_revision = "0023_maintenance_worker_health"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE OR REPLACE FUNCTION public.app_can_claim_maintenance_ticket(ticket uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.maintenance_tickets t
                JOIN public.units u ON u.organization_id=t.organization_id AND u.id=t.unit_id
                WHERE t.id=ticket AND t.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
                AND t.verification='VERIFIED' AND NOT t.emergency AND t.active_assignment_id IS NULL
                AND t.status NOT IN ('COMPLETION_REVIEW','COMPLETED','CLOSED','CANCELED')
                AND NOT EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.ticket_id=t.id AND a.status='DECLINED' AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid)
                AND EXISTS (SELECT 1 FROM public.contractor_profiles c WHERE c.organization_id=t.organization_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND c.approved AND c.can_claim_unassigned AND c.accepting_work
                    AND (cardinality(c.service_property_ids)=0 OR u.property_id=ANY(c.service_property_ids))
                    AND (cardinality(c.service_categories)=0 OR t.category=ANY(c.service_categories))
                    AND (SELECT count(*) FROM public.assignments current_assignment JOIN public.maintenance_tickets current_ticket ON current_ticket.organization_id=current_assignment.organization_id AND current_ticket.active_assignment_id=current_assignment.id WHERE current_assignment.organization_id=c.organization_id AND current_assignment.contractor_profile_id=c.id AND current_assignment.status<>'DECLINED' AND current_ticket.status NOT IN ('COMPLETED','CLOSED','CANCELED'))<c.max_open_jobs)
                AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=t.organization_id AND g.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role='contractor' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp()))
            )
        $$;
CREATE OR REPLACE FUNCTION public.app_claim_maintenance_ticket(ticket uuid) RETURNS TABLE(assignment_id uuid,work_order_id uuid) LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
        DECLARE
            selected_ticket public.maintenance_tickets%ROWTYPE;
            selected_profile uuid;
        BEGIN
            SELECT * INTO selected_ticket FROM public.maintenance_tickets t WHERE t.id=ticket AND t.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid FOR UPDATE;
            IF NOT FOUND OR selected_ticket.active_assignment_id IS NOT NULL OR selected_ticket.verification <> 'VERIFIED' OR selected_ticket.unit_id IS NULL OR selected_ticket.emergency OR selected_ticket.status IN ('COMPLETION_REVIEW','COMPLETED','CLOSED','CANCELED') OR NOT public.app_can_claim_maintenance_ticket(ticket) THEN
                RETURN;
            END IF;
            SELECT c.id INTO selected_profile FROM public.contractor_profiles c WHERE c.organization_id=selected_ticket.organization_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND c.approved AND c.can_claim_unassigned AND c.accepting_work
                AND (cardinality(c.service_property_ids)=0 OR EXISTS (SELECT 1 FROM public.units u WHERE u.organization_id=c.organization_id AND u.id=selected_ticket.unit_id AND u.property_id=ANY(c.service_property_ids)))
                AND (cardinality(c.service_categories)=0 OR selected_ticket.category=ANY(c.service_categories))
                AND (SELECT count(*) FROM public.assignments a JOIN public.maintenance_tickets t ON t.organization_id=a.organization_id AND t.active_assignment_id=a.id WHERE a.organization_id=c.organization_id AND a.contractor_profile_id=c.id AND a.status<>'DECLINED' AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED'))<c.max_open_jobs ORDER BY c.created_at,c.id LIMIT 1;
            IF NOT FOUND THEN
                RETURN;
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended('maintenance-worker:'||selected_profile::text,0));
            IF NOT public.app_can_claim_maintenance_ticket(ticket) OR NOT EXISTS (SELECT 1 FROM public.contractor_profiles c WHERE c.id=selected_profile AND c.organization_id=selected_ticket.organization_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND c.approved AND c.can_claim_unassigned AND c.accepting_work
                AND (cardinality(c.service_property_ids)=0 OR EXISTS (SELECT 1 FROM public.units u WHERE u.organization_id=c.organization_id AND u.id=selected_ticket.unit_id AND u.property_id=ANY(c.service_property_ids)))
                AND (cardinality(c.service_categories)=0 OR selected_ticket.category=ANY(c.service_categories))
                AND (SELECT count(*) FROM public.assignments a JOIN public.maintenance_tickets t ON t.organization_id=a.organization_id AND t.active_assignment_id=a.id WHERE a.organization_id=c.organization_id AND a.contractor_profile_id=c.id AND a.status<>'DECLINED' AND t.status NOT IN ('COMPLETED','CLOSED','CANCELED'))<c.max_open_jobs) THEN
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
    """)


def downgrade():
    op.execute("""
CREATE OR REPLACE FUNCTION public.app_can_claim_maintenance_ticket(ticket uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
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
CREATE OR REPLACE FUNCTION public.app_claim_maintenance_ticket(ticket uuid) RETURNS TABLE(assignment_id uuid,work_order_id uuid) LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
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
    """)
