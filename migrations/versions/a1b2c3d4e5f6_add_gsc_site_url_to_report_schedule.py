"""Add gsc_site_url to report_schedules

Revision ID: a1b2c3d4e5f6
Revises: 3de4ed13f3f8
Create Date: 2026-03-05 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '3de4ed13f3f8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'report_schedules',
        sa.Column('gsc_site_url', sa.String(500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('report_schedules', 'gsc_site_url')
