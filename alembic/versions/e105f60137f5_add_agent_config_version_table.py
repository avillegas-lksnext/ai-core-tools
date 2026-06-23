"""add_agent_config_version_table

Revision ID: e105f60137f5
Revises: ragcfg001
Create Date: 2026-06-23 08:01:23.480931

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e105f60137f5"
down_revision = "ragcfg001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "AgentConfigVersion",
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("persona", sa.String(length=500), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("tone", sa.String(length=255), nullable=True),
        sa.Column("constraints", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("allowed_tools", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False),
        sa.Column("memory_scope", sa.String(length=20), server_default="none", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["agent_id"], ["Agent.agent_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["User.user_id"]),
        sa.PrimaryKeyConstraint("config_id"),
        sa.UniqueConstraint("agent_id", "version_number", name="uq_agent_config_version"),
    )
    op.create_index(
        op.f("ix_AgentConfigVersion_agent_id"),
        "AgentConfigVersion",
        ["agent_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_AgentConfigVersion_agent_id"), table_name="AgentConfigVersion")
    op.drop_table("AgentConfigVersion")