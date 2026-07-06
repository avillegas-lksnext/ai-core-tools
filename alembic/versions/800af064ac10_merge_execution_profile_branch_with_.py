"""Merge execution profile branch with develop

Revision ID: 800af064ac10
Revises: merge001_userdel_platform_role, phase2_audit_001
Create Date: 2026-06-29 09:40:49.218496

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '800af064ac10'
down_revision = ('merge001_userdel_platform_role', 'phase2_audit_001')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
