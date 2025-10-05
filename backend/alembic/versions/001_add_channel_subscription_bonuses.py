"""Add channel subscription bonuses table

Revision ID: 001_channel_bonuses
Revises: 
Create Date: 2025-01-15 12:00:00.000000

"""
import os
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_channel_bonuses'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create channel_subscription_bonuses table with full security constraints."""
    
    # Create the main table
    op.create_table(
        'channel_subscription_bonuses',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('channel_id', sa.String(255), nullable=False),
        sa.Column('bonus_amount', sa.DECIMAL(12, 2), nullable=False),
        sa.Column('subscription_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('bonus_claimed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('attempts_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        
        # 🔒 КРИТИЧЕСКАЯ ЗАЩИТА: один бонус на канал на пользователя НАВСЕГДА
        sa.UniqueConstraint('user_id', 'channel_id', name='uq_user_channel_bonus'),
        
        # 🔒 БИЗНЕС-ЛОГИКА: позитивный бонус
        sa.CheckConstraint('bonus_amount > 0', name='check_positive_bonus'),
        
        # 🔒 ЗАЩИТА ОТ СПАМА: лимит попыток
        sa.CheckConstraint('attempts_count <= 10 AND attempts_count > 0', name='check_attempts_limit')
    )
    
    # 🔒 Индексы для производительности и безопасности
    op.create_index('idx_channel_bonuses_user_channel', 'channel_subscription_bonuses', ['user_id', 'channel_id'])
    op.create_index('idx_channel_bonuses_claimed_at', 'channel_subscription_bonuses', ['bonus_claimed_at'])
    op.create_index('idx_channel_bonuses_user_id', 'channel_subscription_bonuses', ['user_id'])
    op.create_index('idx_channel_bonuses_channel_id', 'channel_subscription_bonuses', ['channel_id'])
    
    # Add channel bonus configuration to system_settings
    op.execute("""
        INSERT INTO system_settings (key, value, description) VALUES 
        ('channel_bonus_config', '{
            "enabled": true,
            "default_bonus_amount": 10.0,
            "channels": {
                "@your_channel": {
                    "bonus_amount": 10.0,
                    "enabled": true,
                    "description": "Main channel subscription bonus"
                }
            },
            "max_attempts_per_user": 10,
            "cooldown_minutes": 5
        }', 'Configuration for channel subscription bonuses')
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade() -> None:
    """Remove channel subscription bonuses functionality."""
    
    # Remove system settings
    op.execute("DELETE FROM system_settings WHERE key = 'channel_bonus_config';")
    
    # Drop indexes
    op.drop_index('idx_channel_bonuses_channel_id', 'channel_subscription_bonuses')
    op.drop_index('idx_channel_bonuses_user_id', 'channel_subscription_bonuses')
    op.drop_index('idx_channel_bonuses_claimed_at', 'channel_subscription_bonuses')
    op.drop_index('idx_channel_bonuses_user_channel', 'channel_subscription_bonuses')
    
    # Drop table
    op.drop_table('channel_subscription_bonuses')