CREATE OR REPLACE FUNCTION public.app_demo_sample_session(p_role text)
RETURNS TABLE (user_id uuid, organization_id uuid, display_name text)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT u.id, u.organization_id, u.display_name
  FROM public.users AS u
  JOIN public.role_grants AS g
    ON g.organization_id = u.organization_id AND g.user_id = u.id
  WHERE current_database() = 'grok_demo_sample'
    AND p_role IN ('property_manager', 'accounting_staff', 'tenant', 'prospect', 'owner')
    AND g.role = p_role
    AND g.resource_type IS NULL
    AND g.active_from <= clock_timestamp()
    AND (g.active_until IS NULL OR g.active_until > clock_timestamp())
  ORDER BY u.display_name
  LIMIT 1;
$$;

ALTER FUNCTION public.app_demo_sample_session(text) OWNER TO grok_auth;
REVOKE ALL ON FUNCTION public.app_demo_sample_session(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.app_demo_sample_session(text) TO grok_app;
