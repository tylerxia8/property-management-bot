from alembic import op

revision = "0021_maintenance_issues"
down_revision = "0020_maintenance_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE public.maintenance_issues (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            ticket_id uuid NOT NULL,
            key text NOT NULL CHECK (length(key) BETWEEN 1 AND 100),
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
            status text NOT NULL CHECK (status IN ('OPEN','WAITING_PARTS','RESOLUTION_REPORTED','TENANT_CONFIRMED','ASSUMED_RESOLVED')),
            evidence text NOT NULL CHECK (length(evidence) <= 5000),
            version integer NOT NULL DEFAULT 1 CHECK (version > 0),
            confirmed_by uuid,
            confirmed_at timestamptz,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            UNIQUE (organization_id,ticket_id,key),
            UNIQUE (organization_id,ticket_id,id),
            CHECK ((status = 'TENANT_CONFIRMED') = (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)),
            CHECK (status = 'TENANT_CONFIRMED' OR (confirmed_by IS NULL AND confirmed_at IS NULL)),
            FOREIGN KEY (organization_id,ticket_id) REFERENCES public.maintenance_tickets(organization_id,id),
            FOREIGN KEY (organization_id,confirmed_by) REFERENCES public.users(organization_id,id)
        );
        CREATE TABLE public.maintenance_issue_events (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            ticket_id uuid NOT NULL,
            issue_id uuid NOT NULL,
            actor_id uuid,
            version integer NOT NULL,
            before_status text,
            status text NOT NULL,
            source text NOT NULL CHECK (source IN ('observation','update','ticket_outcome')),
            note text NOT NULL CHECK (length(note) <= 5000),
            created_at timestamptz NOT NULL,
            UNIQUE (issue_id,version),
            FOREIGN KEY (organization_id,ticket_id,issue_id) REFERENCES public.maintenance_issues(organization_id,ticket_id,id),
            FOREIGN KEY (organization_id,actor_id) REFERENCES public.users(organization_id,id)
        );
        CREATE INDEX maintenance_issue_events_ticket ON public.maintenance_issue_events(organization_id,ticket_id,created_at);
        ALTER TABLE public.maintenance_issues OWNER TO grok_owner;
        ALTER TABLE public.maintenance_issue_events OWNER TO grok_owner;
        ALTER TABLE public.maintenance_issues ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_issues FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_issue_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_issue_events FORCE ROW LEVEL SECURITY;
        GRANT SELECT,INSERT,UPDATE ON public.maintenance_issues TO grok_app;
        GRANT SELECT,INSERT ON public.maintenance_issue_events TO grok_app;
        CREATE TRIGGER maintenance_issue_events_immutable BEFORE UPDATE OR DELETE ON public.maintenance_issue_events FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();
    """)
    for table in ("maintenance_issues", "maintenance_issue_events"):
        op.execute(f"""
            CREATE POLICY issue_read ON public.{table} FOR SELECT USING (
                organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
                AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id={table}.organization_id AND t.id={table}.ticket_id)
            );
            CREATE POLICY issue_insert ON public.{table} FOR INSERT WITH CHECK (
                organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
                AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id={table}.organization_id AND t.id={table}.ticket_id AND (
                    public.app_actor_is_staff() OR t.reporter_user_id=public.app_actor_id()
                    OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.id=t.active_assignment_id AND a.status IN ('PENDING','ACCEPTED') AND c.user_id=public.app_actor_id())
                ))
            );
        """)
    op.execute("""
        CREATE POLICY issue_update ON public.maintenance_issues FOR UPDATE USING (
            organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
            AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id=maintenance_issues.organization_id AND t.id=maintenance_issues.ticket_id AND (
                public.app_actor_is_staff() OR t.reporter_user_id=public.app_actor_id()
                OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.id=t.active_assignment_id AND a.status IN ('PENDING','ACCEPTED') AND c.user_id=public.app_actor_id())
            ))
        );
    """)


def downgrade():
    op.execute("DROP TABLE public.maintenance_issue_events; DROP TABLE public.maintenance_issues")
