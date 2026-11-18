from alembic import op

revision = "0025_maintenance_visit_drafts"
down_revision = "0024_maintenance_worker_routing"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE public.work_orders ADD COLUMN visit_draft text CHECK (length(visit_draft)<=1000)")


def downgrade():
    op.execute("ALTER TABLE public.work_orders DROP COLUMN visit_draft")
