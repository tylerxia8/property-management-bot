from alembic import op

revision = "0031_maintenance_bridge"
down_revision = "0030_worker_lookup_authorization"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE public.maintenance_property_links (
            organization_id uuid NOT NULL REFERENCES public.organizations(id),
            external_property_id uuid NOT NULL,
            unit_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (organization_id,external_property_id),
            UNIQUE (organization_id,unit_id),
            FOREIGN KEY (organization_id,unit_id) REFERENCES public.units(organization_id,id)
        );
        CREATE TABLE public.maintenance_source_requests (
            organization_id uuid NOT NULL REFERENCES public.organizations(id),
            source text NOT NULL CHECK (source='guest_recovery'),
            issue_id text NOT NULL CHECK (length(issue_id) BETWEEN 1 AND 200),
            external_property_id uuid NOT NULL,
            ticket_id uuid NOT NULL,
            reservation_id text NOT NULL CHECK (length(reservation_id) BETWEEN 1 AND 200),
            conversation_id text NOT NULL CHECK (length(conversation_id) BETWEEN 1 AND 200),
            source_fingerprint text NOT NULL CHECK (source_fingerprint ~ '^[a-f0-9]{64}$'),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (organization_id,source,issue_id),
            UNIQUE (organization_id,ticket_id),
            FOREIGN KEY (organization_id,external_property_id) REFERENCES public.maintenance_property_links(organization_id,external_property_id),
            FOREIGN KEY (organization_id,ticket_id) REFERENCES public.maintenance_tickets(organization_id,id)
        );
        CREATE TABLE public.maintenance_workspace_apps (
            organization_id uuid NOT NULL REFERENCES public.organizations(id),
            project text NOT NULL CHECK (project IN ('guest_recovery','cleaner_scheduler')),
            url text NOT NULL CHECK (length(url)<=500),
            PRIMARY KEY (organization_id,project)
        );
        ALTER TABLE public.maintenance_workspace_apps OWNER TO grok_owner;
        ALTER TABLE public.maintenance_workspace_apps ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_workspace_apps FORCE ROW LEVEL SECURITY;
        CREATE POLICY workspace_apps_manager ON public.maintenance_workspace_apps
            USING (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager())
            WITH CHECK (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager());
        GRANT SELECT,INSERT,UPDATE ON public.maintenance_workspace_apps TO grok_app;
        ALTER TABLE public.maintenance_property_links OWNER TO grok_owner;
        ALTER TABLE public.maintenance_source_requests OWNER TO grok_owner;
        ALTER TABLE public.maintenance_property_links ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_property_links FORCE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_source_requests ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_source_requests FORCE ROW LEVEL SECURITY;
        CREATE POLICY bridge_property_manager ON public.maintenance_property_links
            USING (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager())
            WITH CHECK (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager());
        CREATE POLICY bridge_request_manager ON public.maintenance_source_requests
            USING (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager())
            WITH CHECK (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager());
        GRANT SELECT,INSERT ON public.maintenance_property_links,public.maintenance_source_requests TO grok_app;
        GRANT DELETE ON public.maintenance_property_links TO grok_app;
    """)


def downgrade():
    op.execute("DROP TABLE public.maintenance_workspace_apps; DROP TABLE public.maintenance_source_requests; DROP TABLE public.maintenance_property_links")
