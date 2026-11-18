from alembic import op

revision = "0022_maintenance_operations"
down_revision = "0021_maintenance_issues"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE public.contractor_profiles
          ADD COLUMN service_property_ids uuid[] NOT NULL DEFAULT '{}',
          ADD COLUMN service_categories text[] NOT NULL DEFAULT '{}',
          ADD COLUMN accepting_work boolean NOT NULL DEFAULT true,
          ADD COLUMN availability_note text NOT NULL DEFAULT '' CHECK (length(availability_note) <= 1000),
          ADD COLUMN max_open_jobs integer NOT NULL DEFAULT 10 CHECK (max_open_jobs BETWEEN 1 AND 50),
          ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0),
          ADD CONSTRAINT contractor_service_categories_valid CHECK (service_categories <@ ARRAY['leak','electrical','hvac','appliance','structural','pest_mold','lock','general']::text[]);
    """)


def downgrade():
    op.execute("""
        ALTER TABLE public.contractor_profiles DROP COLUMN service_property_ids,
          DROP COLUMN service_categories, DROP COLUMN accepting_work,
          DROP COLUMN availability_note, DROP COLUMN max_open_jobs, DROP COLUMN version;
    """)
