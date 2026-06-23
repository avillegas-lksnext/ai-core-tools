"""Add config audit logging table for Phase 2

Revision ID: phase2_audit_001
Revises: e105f60137f5
Create Date: 2026-06-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'phase2_audit_001'
down_revision = 'e105f60137f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing enum if it exists (from previous failed attempts)
    op.execute("DROP TYPE IF EXISTS changetype CASCADE")
    
    # Create config_audit_log table
    # The ENUM column definition will create the type automatically
    op.create_table(
        'config_audit_log',
        sa.Column('audit_id', sa.Integer(), nullable=False),
        sa.Column('config_id', sa.Integer(), nullable=False),
        sa.Column('agent_id', sa.Integer(), nullable=False),
        sa.Column('app_id', sa.Integer(), nullable=False),
        sa.Column('change_type', postgresql.ENUM(
            'create', 'update', 'restore', 'prompt_update', 'skill_change', 'tool_change', 'mcp_change',
            name='changetype'
        ), nullable=False),
        sa.Column('changed_by_user_id', sa.Integer(), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=False),
        sa.Column('field_name', sa.String(255), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('change_reason', sa.String(1024), nullable=True),
        sa.Column('related_config_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['config_id'], ['AgentConfigVersion.config_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['agent_id'], ['Agent.agent_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['app_id'], ['App.app_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['User.user_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('audit_id')
    )
    op.create_index(op.f('ix_config_audit_log_agent_id'), 'config_audit_log', ['agent_id'])
    op.create_index(op.f('ix_config_audit_log_app_id'), 'config_audit_log', ['app_id'])
    op.create_index(op.f('ix_config_audit_log_changed_at'), 'config_audit_log', ['changed_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_config_audit_log_changed_at'), table_name='config_audit_log')
    op.drop_index(op.f('ix_config_audit_log_app_id'), table_name='config_audit_log')
    op.drop_index(op.f('ix_config_audit_log_agent_id'), table_name='config_audit_log')
    op.drop_table('config_audit_log')
    sa.Enum(name='changetype').drop(op.get_bind(), checkfirst=True)