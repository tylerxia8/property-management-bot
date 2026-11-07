CREATE FUNCTION public.app_maintenance_homes()
RETURNS TABLE (lease_id uuid, unit_id uuid, unit_label text, property_name text)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
 SELECT l.id, u.id, u.label::text, p.name::text
 FROM public.leases l
 JOIN public.units u ON u.id = l.unit_id AND u.organization_id = l.organization_id
 JOIN public.properties p ON p.id = u.property_id AND p.organization_id = u.organization_id
 WHERE l.organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
 AND (EXISTS (SELECT 1 FROM public.role_grants g
   WHERE g.organization_id = l.organization_id
   AND g.user_id = NULLIF(current_setting('app.actor_id', true), '')::uuid
   AND g.role IN ('property_manager','organization_administrator') AND g.resource_type IS NULL
   AND g.active_from <= clock_timestamp() AND (g.active_until IS NULL OR g.active_until > clock_timestamp())) OR EXISTS (
   SELECT 1 FROM public.lease_parties lp WHERE lp.organization_id = l.organization_id
   AND lp.lease_id = l.id AND lp.user_id = NULLIF(current_setting('app.actor_id', true), '')::uuid
 ))
$$;
ALTER FUNCTION public.app_maintenance_homes() OWNER TO grok_auth;
REVOKE ALL ON FUNCTION public.app_maintenance_homes() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_maintenance_homes() TO grok_app;

CREATE TABLE public.maintenance_report_keys (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL,
 actor_id uuid NOT NULL,
 key text NOT NULL,
 request_hash text NOT NULL,
 ticket_id uuid NOT NULL,
 UNIQUE (organization_id, actor_id, key),
 FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets(organization_id,id),
 FOREIGN KEY (organization_id, actor_id) REFERENCES public.users(organization_id,id)
);
ALTER TABLE public.maintenance_report_keys OWNER TO grok_owner;
ALTER TABLE public.maintenance_report_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_report_keys FORCE ROW LEVEL SECURITY;
CREATE POLICY report_key_scope ON public.maintenance_report_keys
 USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND actor_id = public.app_actor_id())
 WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND actor_id = public.app_actor_id());
GRANT SELECT, INSERT ON public.maintenance_report_keys TO grok_app;

CREATE TABLE public.maintenance_status_updates (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL,
 ticket_id uuid NOT NULL,
 status text NOT NULL,
 reason text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets(organization_id,id)
);
ALTER TABLE public.maintenance_status_updates OWNER TO grok_owner;
ALTER TABLE public.maintenance_status_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_status_updates FORCE ROW LEVEL SECURITY;
CREATE POLICY maintenance_update_scope ON public.maintenance_status_updates
 USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND EXISTS (
 SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id = maintenance_status_updates.organization_id
 AND t.id = maintenance_status_updates.ticket_id AND (public.app_actor_is_manager() OR t.reporter_user_id = public.app_actor_id())
 ))
 WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND public.app_actor_is_manager());
GRANT SELECT, INSERT ON public.maintenance_status_updates TO grok_app;
CREATE INDEX maintenance_updates_ticket_idx ON public.maintenance_status_updates(organization_id,ticket_id,created_at);
GRANT SELECT ON public.leases, public.units, public.properties, public.lease_parties TO grok_auth;
