"""Materialized chat messages; raw events remain the replay source."""

import sqlalchemy as sa

from alembic import op

revision = "0003_chat_history"
down_revision = "0002_phase7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_history_entries",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ticket_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_key", sa.String(100), nullable=False),
        sa.Column("first_seq", sa.BigInteger(), nullable=False),
        sa.Column("last_seq", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("ticket_id", "entry_key"),
    )
    op.create_index("ix_chat_history_ticket_seq", "chat_history_entries", ["ticket_id", "first_seq"])
    op.create_index("ix_message_ticket_run_seq", "ticket_messages", ["ticket_id", "run_id", "seq"])


def downgrade():
    op.drop_index("ix_message_ticket_run_seq", table_name="ticket_messages")
    op.drop_table("chat_history_entries")
