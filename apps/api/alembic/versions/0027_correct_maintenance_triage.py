from alembic import op

revision = "0027_correct_maintenance_triage"
down_revision = "0026_manager_maintenance_review"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE public.maintenance_issues DROP CONSTRAINT maintenance_issues_status_check; ALTER TABLE public.maintenance_issues ADD CHECK (status IN ('OPEN','WAITING_PARTS','RESOLUTION_REPORTED','TENANT_CONFIRMED','ASSUMED_RESOLVED','DISMISSED')); ALTER TABLE public.escalations DROP CONSTRAINT escalations_state_check; ALTER TABLE public.escalations ADD CHECK (state IN ('OPEN','ACKNOWLEDGED','CANCELED'))")


def downgrade():
    op.execute("UPDATE public.maintenance_issues SET status='OPEN' WHERE status='DISMISSED'; ALTER TABLE public.maintenance_issues DROP CONSTRAINT maintenance_issues_status_check; ALTER TABLE public.maintenance_issues ADD CHECK (status IN ('OPEN','WAITING_PARTS','RESOLUTION_REPORTED','TENANT_CONFIRMED','ASSUMED_RESOLVED')); UPDATE public.escalations SET state='OPEN' WHERE state='CANCELED'; ALTER TABLE public.escalations DROP CONSTRAINT escalations_state_check; ALTER TABLE public.escalations ADD CHECK (state IN ('OPEN','ACKNOWLEDGED'))")
