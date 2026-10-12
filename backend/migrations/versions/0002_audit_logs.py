"""Add append-only activity audit records."""

from alembic import op
import sqlalchemy as sa

from app.models import JSON_VALUE

revision = "0002_audit_logs"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("actor_profile_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("details", JSON_VALUE, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_profile_id", "audit_logs", ["actor_profile_id"])
    op.create_index("ix_audit_logs_document_id", "audit_logs", ["document_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_index("ix_audit_logs_document_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_actor_profile_id", table_name="audit_logs")
    op.drop_table("audit_logs")
