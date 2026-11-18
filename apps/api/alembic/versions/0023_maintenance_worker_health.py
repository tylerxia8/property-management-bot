from alembic import op

revision = "0023_maintenance_worker_health"
down_revision = "0022_maintenance_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE public.maintenance_worker_health (
            organization_id uuid NOT NULL REFERENCES public.organizations(id),
            worker_key text NOT NULL CHECK (worker_key='maintenance_phone'),
            heartbeat_at timestamptz NOT NULL,
            last_success_at timestamptz,
            last_error_type text CHECK (last_error_type ~ '^[A-Za-z]{1,80}$'),
            failure_count bigint NOT NULL DEFAULT 0 CHECK (failure_count>=0),
            PRIMARY KEY (organization_id,worker_key)
        );
        ALTER TABLE public.maintenance_worker_health OWNER TO grok_owner;
        ALTER TABLE public.maintenance_worker_health ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_worker_health FORCE ROW LEVEL SECURITY;
        CREATE POLICY maintenance_worker_manager ON public.maintenance_worker_health
        USING (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND public.app_actor_is_manager());
        GRANT SELECT,INSERT,UPDATE ON public.maintenance_worker_health TO grok_app;
    """)


def downgrade():
    op.execute("DROP TABLE public.maintenance_worker_health")
