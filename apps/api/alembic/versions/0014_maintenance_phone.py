from alembic import op

revision = "0014_maintenance_phone"
down_revision = "0013_maintenance_analysis"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE public.maintenance_phone_events (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            actor_id uuid NOT NULL,
            ticket_id uuid NOT NULL,
            channel text NOT NULL CHECK (channel IN ('SMS','VOICEMAIL')),
            direction text NOT NULL CHECK (direction IN ('INBOUND','OUTBOUND')),
            from_number text NOT NULL,
            to_number text NOT NULL,
            body text NOT NULL,
            status text NOT NULL,
            provider_key text NOT NULL,
            recording_sid text,
            provider_sid text,
            processing_at timestamptz,
            media_jobs jsonb NOT NULL DEFAULT '[]'::jsonb,
            transcript_received boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (organization_id, provider_key),
            FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets(organization_id,id),
            FOREIGN KEY (organization_id, actor_id) REFERENCES public.users(organization_id,id)
        );
        ALTER TABLE public.maintenance_phone_events OWNER TO grok_owner;
        ALTER TABLE public.maintenance_phone_events ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_phone_events FORCE ROW LEVEL SECURITY;
        CREATE POLICY maintenance_phone_scope ON public.maintenance_phone_events
            USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND public.app_actor_is_manager())
            WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND public.app_actor_is_manager());
        GRANT SELECT, INSERT, UPDATE ON public.maintenance_phone_events TO grok_app;
        CREATE INDEX maintenance_phone_recent_idx ON public.maintenance_phone_events(organization_id,created_at);
    """)


def downgrade():
    op.execute("DROP TABLE public.maintenance_phone_events")
