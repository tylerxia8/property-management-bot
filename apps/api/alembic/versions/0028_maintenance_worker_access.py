from alembic import op

revision = "0028_maintenance_worker_access"
down_revision = "0027_correct_maintenance_triage"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE FUNCTION public.app_maintenance_worker_active(profile uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.contractor_profiles c
                WHERE c.id=profile AND c.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
                AND (public.app_actor_is_manager() OR c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid)
                AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=c.organization_id AND g.user_id=c.user_id AND g.role='contractor' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp()))
            )
        $$;
        ALTER FUNCTION public.app_maintenance_worker_active(uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_maintenance_worker_active(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_maintenance_worker_active(uuid) TO grok_app;
    """)


def downgrade():
    op.execute("DROP FUNCTION public.app_maintenance_worker_active(uuid)")
