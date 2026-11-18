from alembic import op

revision = "0030_worker_lookup_authorization"
down_revision = "0029_worker_lookup_permission"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION public.app_maintenance_worker_active(profile uuid) RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
            SELECT EXISTS (
                SELECT 1 FROM public.contractor_profiles c
                WHERE c.id=profile AND c.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
                AND (EXISTS (SELECT 1 FROM public.role_grants manager_grant WHERE manager_grant.organization_id=c.organization_id AND manager_grant.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND manager_grant.role IN ('property_manager','organization_administrator') AND manager_grant.resource_type IS NULL AND manager_grant.active_from<=clock_timestamp() AND (manager_grant.active_until IS NULL OR manager_grant.active_until>clock_timestamp())) OR c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid)
                AND EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=c.organization_id AND g.user_id=c.user_id AND g.role='contractor' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp()))
            )
        $$;
        ALTER FUNCTION public.app_maintenance_worker_active(uuid) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_maintenance_worker_active(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_maintenance_worker_active(uuid) TO grok_app;

        REVOKE EXECUTE ON FUNCTION public.app_actor_is_manager() FROM grok_auth;
    """)


def downgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION public.app_maintenance_worker_active(profile uuid) RETURNS boolean
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

        GRANT EXECUTE ON FUNCTION public.app_actor_is_manager() TO grok_auth;
    """)
