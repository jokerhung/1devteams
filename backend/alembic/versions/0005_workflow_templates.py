"""Store editable workflow template instructions."""

import sqlalchemy as sa

from alembic import op

revision = "0005_workflow_templates"
down_revision = "0004_agent_reasoning"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String(60), nullable=False, unique=True),
        sa.Column("instructions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("workflow_templates")
