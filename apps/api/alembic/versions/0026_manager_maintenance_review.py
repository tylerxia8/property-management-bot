from alembic import op

revision = "0026_manager_maintenance_review"
down_revision = "0025_maintenance_visit_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE OR REPLACE FUNCTION public.app_can_claim_maintenance_ticket(ticket uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$ SELECT false $$")


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
                AND EXISTS (SELECT 1 FROM public.contractor_profiles c WHERE c.organization_id=t.organization_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND c.approved AND c.can_claim_unassigned AND c.accepting_work
                    AND (cardinality(c.service_property_ids)=0 OR u.property_id=ANY(c.service_property_ids))
                    AND (cardinality(c.service_categories)=0 OR t.category=ANY(c.service_categories))
                    AND (SELECT count(*) FROM public.assignments current_assignment JOIN public.maintenance_tickets current_ticket ON current_ticket.organization_id=current_assignment.organization_id AND current_ticket.active_assignment_id=current_assignment.id WHERE current_assignment.organization_id=c.organization_id AND current_assignment.contractor_profile_id=c.id AND current_assignment.status<>'DECLINED' AND current_ticket.status NOT IN ('COMPLETED','CLOSED','CANCELED'))<c.max_open_jobs)
                AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=t.organization_id AND g.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role='contractor' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp()))
            )
        $$;
    """)
