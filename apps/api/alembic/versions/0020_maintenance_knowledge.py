from alembic import op

revision = "0020_maintenance_knowledge"
down_revision = "0019_maintenance_action_keys"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE public.maintenance_knowledge (
            id uuid PRIMARY KEY,
            organization_id uuid NOT NULL,
            property_id uuid NOT NULL,
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
            problem_key text NOT NULL CHECK (problem_key ~ '^[a-z][a-z0-9_]{0,79}$'),
            model text NOT NULL DEFAULT '' CHECK (length(model)<=120),
            part_details text NOT NULL DEFAULT '' CHECK (length(part_details)<=300),
            instructions text NOT NULL CHECK (length(instructions) BETWEEN 1 AND 1000),
            reference_media_ids uuid[] NOT NULL DEFAULT '{}'::uuid[] CHECK (cardinality(reference_media_ids)<=6 AND array_position(reference_media_ids,NULL) IS NULL),
            verified boolean NOT NULL DEFAULT false,
            verified_at timestamptz,
            verified_by uuid,
            version integer NOT NULL DEFAULT 1 CHECK (version>0),
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL,
            FOREIGN KEY (organization_id,property_id) REFERENCES public.properties(organization_id,id),
            FOREIGN KEY (organization_id,verified_by) REFERENCES public.users(organization_id,id),
            CHECK ((verified AND verified_at IS NOT NULL AND verified_by IS NOT NULL) OR (NOT verified AND verified_at IS NULL AND verified_by IS NULL))
        );
        ALTER TABLE public.maintenance_knowledge OWNER TO grok_owner;
        ALTER TABLE public.maintenance_knowledge ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.maintenance_knowledge FORCE ROW LEVEL SECURITY;
        CREATE POLICY knowledge_manager ON public.maintenance_knowledge
        USING (organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid AND EXISTS (
            SELECT 1 FROM public.role_grants g WHERE g.organization_id=maintenance_knowledge.organization_id
            AND g.user_id=public.app_actor_id() AND g.role='property_manager' AND g.resource_type IS NULL
            AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp())
        ));
        GRANT SELECT,INSERT,UPDATE ON public.maintenance_knowledge TO grok_app;
        GRANT SELECT ON public.maintenance_knowledge,public.lease_parties,public.media_objects TO grok_auth;
        CREATE INDEX maintenance_knowledge_lookup ON public.maintenance_knowledge(organization_id,property_id,problem_key) WHERE active AND verified;
        CREATE FUNCTION public.app_verified_maintenance_knowledge(ticket uuid,problem_keys text[])
        RETURNS TABLE(id uuid,title text,problem_key text,model text,part_details text,instructions text,reference_media_ids uuid[],version integer,verified_at timestamptz)
        LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
            SELECT k.id,k.title,k.problem_key,k.model,k.part_details,k.instructions,
                ARRAY(SELECT m.id FROM public.media_objects m JOIN public.maintenance_tickets mt ON mt.organization_id=m.organization_id AND mt.id=m.ticket_id JOIN public.units mu ON mu.organization_id=mt.organization_id AND mu.id=mt.unit_id WHERE m.organization_id=k.organization_id AND mu.property_id=k.property_id AND m.id=ANY(k.reference_media_ids) AND m.status='READY' AND m.detected_type IN ('image/jpeg','image/png','image/heic','image/heif') AND m.derivative_key IS NOT NULL ORDER BY array_position(k.reference_media_ids,m.id)),
                k.version,k.verified_at
            FROM public.maintenance_tickets t
            JOIN public.units u ON u.organization_id=t.organization_id AND u.id=t.unit_id
            JOIN public.maintenance_knowledge k ON k.organization_id=u.organization_id AND k.property_id=u.property_id
            WHERE t.id=ticket AND t.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
            AND k.active AND k.verified AND k.problem_key=ANY(problem_keys)
            AND (t.reporter_user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid
                OR EXISTS (SELECT 1 FROM public.lease_parties lp WHERE lp.organization_id=t.organization_id AND lp.lease_id=t.lease_id AND lp.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid)
                OR EXISTS (SELECT 1 FROM public.role_grants g WHERE g.organization_id=t.organization_id AND g.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid AND g.role='property_manager' AND g.resource_type IS NULL AND g.active_from<=clock_timestamp() AND (g.active_until IS NULL OR g.active_until>clock_timestamp()))
                OR EXISTS (SELECT 1 FROM public.assignments a JOIN public.contractor_profiles c ON c.organization_id=a.organization_id AND c.id=a.contractor_profile_id WHERE a.organization_id=t.organization_id AND a.id=t.active_assignment_id AND c.user_id=NULLIF(current_setting('app.actor_id',true),'')::uuid))
            ORDER BY k.title,k.id LIMIT 20
        $$;
        ALTER FUNCTION public.app_verified_maintenance_knowledge(uuid,text[]) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_verified_maintenance_knowledge(uuid,text[]) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_verified_maintenance_knowledge(uuid,text[]) TO grok_app;
        CREATE FUNCTION public.app_verified_maintenance_reference_media(ticket uuid,problem_keys text[])
        RETURNS TABLE(derivative_key text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
            SELECT DISTINCT m.derivative_key FROM public.app_verified_maintenance_knowledge(ticket,problem_keys) k
            CROSS JOIN LATERAL unnest(k.reference_media_ids) r(id)
            JOIN public.media_objects m ON m.id=r.id AND m.organization_id=NULLIF(current_setting('app.organization_id',true),'')::uuid
            WHERE m.status='READY' AND m.detected_type IN ('image/jpeg','image/png','image/heic','image/heif') AND m.derivative_key IS NOT NULL
            ORDER BY m.derivative_key LIMIT 3
        $$;
        ALTER FUNCTION public.app_verified_maintenance_reference_media(uuid,text[]) OWNER TO grok_auth;
        REVOKE ALL ON FUNCTION public.app_verified_maintenance_reference_media(uuid,text[]) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.app_verified_maintenance_reference_media(uuid,text[]) TO grok_app;
    """)


def downgrade():
    op.execute("DROP FUNCTION public.app_verified_maintenance_reference_media(uuid,text[]); DROP FUNCTION public.app_verified_maintenance_knowledge(uuid,text[]); DROP TABLE public.maintenance_knowledge")
