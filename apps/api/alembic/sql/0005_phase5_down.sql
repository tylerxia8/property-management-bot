DO $$
DECLARE
  rel record;
BEGIN
  FOR rel IN
    SELECT c.relname, p.polname
    FROM pg_policy AS p
    JOIN pg_class AS c ON c.oid = p.polrelid
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND p.polname LIKE 'actor_%'
  LOOP
    EXECUTE format('DROP POLICY %I ON public.%I', rel.polname, rel.relname);
  END LOOP;
END
$$;

DROP FUNCTION IF EXISTS public.app_actor_has_any_role();

DROP TABLE IF EXISTS public.owner_statements;
DROP TABLE IF EXISTS public.owner_links;
DROP TABLE IF EXISTS public.payment_events;
DROP TABLE IF EXISTS public.distribution_exports;
DROP TABLE IF EXISTS public.distribution_approvals;
DROP TABLE IF EXISTS public.fund_reservations;
DROP TABLE IF EXISTS public.distribution_items;
DROP TABLE IF EXISTS public.distribution_batches;
DROP TABLE IF EXISTS public.payee_destinations;
DROP TABLE IF EXISTS public.step_up_events;
ALTER TABLE public.funding_lots DROP COLUMN IF EXISTS reserved_cents;
DROP FUNCTION IF EXISTS public.prevent_statement_mutation();

DROP POLICY IF EXISTS actor_scope_organizations ON public.organizations;
DROP POLICY IF EXISTS actor_scope_users ON public.users;
DROP POLICY IF EXISTS actor_scope_role_grants ON public.role_grants;
DROP POLICY IF EXISTS actor_scope_audit ON public.audit_events;
DROP POLICY IF EXISTS actor_scope_outbox ON public.outbox_events;

DO $$
DECLARE
  rel record;
BEGIN
  FOR rel IN
    SELECT n.nspname, c.relname, p.polname
    FROM pg_policy AS p
    JOIN pg_class AS c ON c.oid = p.polrelid
    JOIN pg_namespace AS n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND p.polname = 'actor_required'
  LOOP
    EXECUTE format('DROP POLICY actor_required ON public.%I', rel.relname);
  END LOOP;
END
$$;
