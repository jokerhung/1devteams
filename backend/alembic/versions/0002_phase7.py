"""Terminal, audit and explicit fallback configuration."""

import sqlalchemy as sa

from alembic import op

revision = "0002_phase7"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("fallback_runtime", sa.String(20), nullable=True))
    op.add_column("agents", sa.Column("fallback_agent_id", sa.Uuid(as_uuid=False), nullable=True))
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("ip", sa.String(100), nullable=True),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_table(
        "terminal_audit",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("project_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
    )
    op.create_index("ix_terminal_audit_user_id", "terminal_audit", ["user_id"])
    op.create_index("ix_terminal_audit_project_id", "terminal_audit", ["project_id"])


def downgrade():
    op.drop_table("terminal_audit")
    op.drop_table("audit_logs")
    op.drop_column("agents", "fallback_agent_id")
    op.drop_column("agents", "fallback_runtime")
