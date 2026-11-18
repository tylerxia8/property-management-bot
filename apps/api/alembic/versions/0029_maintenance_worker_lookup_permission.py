from alembic import op

revision = "0029_worker_lookup_permission"
down_revision = "0028_maintenance_worker_access"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("GRANT EXECUTE ON FUNCTION public.app_actor_is_manager() TO grok_auth")


def downgrade():
    op.execute("REVOKE EXECUTE ON FUNCTION public.app_actor_is_manager() FROM grok_auth")
