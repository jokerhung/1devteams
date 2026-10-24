"""Persist ACP reasoning selection."""

import sqlalchemy as sa

from alembic import op

revision = "0004_agent_reasoning"
down_revision = "0003_chat_history"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("agents", sa.Column("reasoning_effort", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("agents", "reasoning_effort")
