"""Add verified_senders table

Revision ID: 003_add_verified_senders
Revises: 002_add_promo_codes
Create Date: 2025-01-14 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003_add_verified_senders'
down_revision = '002_add_promo_codes'
branch_labels = None
depends_on = None


def upgrade():
    # Create verified_senders table
    op.create_table(
        'verified_senders',
        sa.Column('chat_id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('first_name', sa.String(length=255), nullable=True),
        sa.Column('last_name', sa.String(length=255), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('last_message_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('message_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_blocked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('chat_id')
    )

    # Create indexes for verified_senders
    op.create_index('idx_verified_senders_verified_at', 'verified_senders', ['verified_at'])
    op.create_index('idx_verified_senders_last_message_at', 'verified_senders', ['last_message_at'])
    op.create_index('idx_verified_senders_username', 'verified_senders', ['username'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_verified_senders_username', 'verified_senders')
    op.drop_index('idx_verified_senders_last_message_at', 'verified_senders')
    op.drop_index('idx_verified_senders_verified_at', 'verified_senders')

    # Drop table
    op.drop_table('verified_senders')
