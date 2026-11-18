CREATE TABLE public.maintenance_analyses (
 id uuid PRIMARY KEY,
 organization_id uuid NOT NULL,
 ticket_id uuid NOT NULL,
 actor_id uuid NOT NULL,
 idempotency_key text NOT NULL,
 input_hash text NOT NULL,
 result jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE (organization_id, actor_id, idempotency_key),
 FOREIGN KEY (organization_id, ticket_id) REFERENCES public.maintenance_tickets(organization_id,id),
 FOREIGN KEY (organization_id, actor_id) REFERENCES public.users(organization_id,id)
);
ALTER TABLE public.maintenance_analyses OWNER TO grok_owner;
ALTER TABLE public.maintenance_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_analyses FORCE ROW LEVEL SECURITY;
CREATE POLICY maintenance_analysis_scope ON public.maintenance_analyses
 USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND EXISTS (
 SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id = maintenance_analyses.organization_id AND t.id = maintenance_analyses.ticket_id
 ))
 WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid AND actor_id = public.app_actor_id() AND EXISTS (
 SELECT 1 FROM public.maintenance_tickets t WHERE t.organization_id = maintenance_analyses.organization_id AND t.id = maintenance_analyses.ticket_id
 AND (public.app_actor_is_manager() OR t.reporter_user_id = public.app_actor_id())
 ));
GRANT SELECT, INSERT ON public.maintenance_analyses TO grok_app;
CREATE INDEX maintenance_analysis_ticket_idx ON public.maintenance_analyses(organization_id,ticket_id,created_at);
CREATE INDEX maintenance_analysis_actor_idx ON public.maintenance_analyses(organization_id,actor_id,created_at);
