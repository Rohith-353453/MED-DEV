"""Initial Carefolio schema."""

from alembic import op

from app.db import Base
from app import models  # noqa: F401

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the original baseline stable as later revisions own newly added tables.
    tables = [table for table in Base.metadata.sorted_tables if table.name != "audit_logs"]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables)


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
