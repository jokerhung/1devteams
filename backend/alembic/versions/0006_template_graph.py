"""Persist complete editable template graphs."""

import sqlalchemy as sa

from alembic import op

revision = "0006_template_graph"
down_revision = "0005_workflow_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_templates", sa.Column("graph", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("workflow_templates", "graph")
