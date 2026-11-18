from alembic import op

revision = "0015_maintenance_routing"
down_revision = "0014_maintenance_phone"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE public.maintenance_tickets ADD COLUMN notification_status text CHECK (notification_status IN ('PENDING','SIMULATED','QUEUED','ACCEPTED','SENDING','SENT','DELIVERED','FAILED','UNDELIVERED','DELIVERY_UNKNOWN','BLOCKED','SUPPRESSED')), ADD COLUMN notification_event_id uuid REFERENCES public.maintenance_phone_events(id)")


def downgrade():
    op.execute("ALTER TABLE public.maintenance_tickets DROP COLUMN notification_event_id, DROP COLUMN notification_status")
