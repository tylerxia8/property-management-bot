from alembic import op

revision = "0019_maintenance_action_keys"
down_revision = "0018_maintenance_claim"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE public.maintenance_action_keys (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            actor_id uuid NOT NULL,
            ticket_id uuid NOT NULL,
            key text NOT NULL,
            request_hash text NOT NULL,
            response_status integer NOT NULL,
            response_body jsonb NOT NULL,
            UNIQUE (organization_id, actor_id, key),
            FOREIGN KEY (organization_id, actor_id) REFERENCES public.users(organization_id,id),
            FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets(organization_id,id)
        );
        ALTER TABLE public.maintenance_action_keys OWNER TO grok_owner;
        ALTER TABLE public.maintenance_action_keys ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_action_keys FORCE ROW LEVEL SECURITY;
        CREATE POLICY maintenance_actor ON public.maintenance_action_keys
        USING (
            organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
            AND actor_id=public.app_actor_id()
            AND EXISTS (SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id=maintenance_action_keys.organization_id AND t.id=maintenance_action_keys.ticket_id)
        );
        GRANT SELECT,INSERT ON public.maintenance_action_keys TO grok_app;
        CREATE TRIGGER maintenance_action_keys_immutable BEFORE UPDATE OR DELETE ON public.maintenance_action_keys FOR EACH ROW EXECUTE FUNCTION public.reject_mutation();
    """)


def downgrade():
    op.execute("DROP TABLE public.maintenance_action_keys")
