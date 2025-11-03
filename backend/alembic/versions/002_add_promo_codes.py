"""Add promo code system

Revision ID: 002_add_promo_codes
Revises: 001_add_channel_subscription_bonuses
Create Date: 2025-01-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_add_promo_codes'
down_revision = '001_channel_bonuses'
branch_labels = None
depends_on = None


def upgrade():
    # Add withdrawal_locked_balance column to users table
    op.add_column('users', sa.Column('withdrawal_locked_balance', sa.DECIMAL(12, 2), nullable=False, server_default='0.00'))
    
    # Create promo_codes table
    op.create_table(
        'promo_codes',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('balance_reward', sa.DECIMAL(12, 2), nullable=False),
        sa.Column('withdrawal_requirement', sa.DECIMAL(12, 2), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=False),
        sa.Column('current_uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for promo_codes
    op.create_index('ix_promo_codes_code', 'promo_codes', ['code'], unique=True)
    
    # Create promo_code_uses table
    op.create_table(
        'promo_code_uses',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('promo_code_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('balance_granted', sa.DECIMAL(12, 2), nullable=False),
        sa.Column('withdrawal_requirement', sa.DECIMAL(12, 2), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['promo_code_id'], ['promo_codes.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for promo_code_uses
    op.create_index('ix_promo_code_uses_promo_code_id', 'promo_code_uses', ['promo_code_id'])
    op.create_index('ix_promo_code_uses_user_id', 'promo_code_uses', ['user_id'])
    op.create_index('idx_promo_code_uses_unique', 'promo_code_uses', ['promo_code_id', 'user_id'], unique=True)
    
    # Add constraints for promo_codes
    op.create_check_constraint(
        'check_balance_reward_positive',
        'promo_codes',
        'balance_reward > 0'
    )
    
    op.create_check_constraint(
        'check_max_uses_positive',
        'promo_codes',
        'max_uses > 0'
    )
    
    op.create_check_constraint(
        'check_current_uses_non_negative',
        'promo_codes',
        'current_uses >= 0'
    )
    
    # Add constraints for promo_code_uses
    op.create_check_constraint(
        'check_balance_granted_positive',
        'promo_code_uses',
        'balance_granted > 0'
    )
    
    # Add constraint for users withdrawal_locked_balance
    op.create_check_constraint(
        'check_withdrawal_locked_balance_non_negative',
        'users',
        'withdrawal_locked_balance >= 0'
    )
    
    # Update transaction type constraint to include promo_code_bonus
    # Drop the existing constraint
    op.drop_constraint('check_valid_transaction_amounts', 'transactions', type_='check')
    
    # Recreate with promo_code_bonus included
    op.create_check_constraint(
        'check_valid_transaction_amounts',
        'transactions',
        """(type IN ('game_win', 'deposit', 'referral_bonus', 'withdrawal', 'refund', 'promo_code_bonus') AND amount > 0.00) OR
           (type IN ('game_loss', 'gift_purchase') AND amount < 0.00) OR
           (type NOT IN ('game_win', 'deposit', 'referral_bonus', 'game_loss', 'withdrawal', 'gift_purchase', 'refund', 'promo_code_bonus'))"""
    )
    

def downgrade():
    # Restore original transaction constraint (remove promo_code_bonus)
    op.drop_constraint('check_valid_transaction_amounts', 'transactions', type_='check')
    op.create_check_constraint(
        'check_valid_transaction_amounts',
        'transactions',
        """(type IN ('game_win', 'deposit', 'referral_bonus', 'withdrawal', 'refund') AND amount > 0.00) OR
           (type IN ('game_loss', 'gift_purchase') AND amount < 0.00) OR
           (type NOT IN ('game_win', 'deposit', 'referral_bonus', 'game_loss', 'withdrawal', 'gift_purchase', 'refund'))"""
    )
    
    # Drop constraints
    op.drop_constraint('check_withdrawal_locked_balance_non_negative', 'users', type_='check')
    op.drop_constraint('check_balance_granted_positive', 'promo_code_uses', type_='check')
    op.drop_constraint('check_current_uses_non_negative', 'promo_codes', type_='check')
    op.drop_constraint('check_max_uses_positive', 'promo_codes', type_='check')
    op.drop_constraint('check_balance_reward_positive', 'promo_codes', type_='check')
    
    # Drop indexes
    op.drop_index('idx_promo_code_uses_unique', 'promo_code_uses')
    op.drop_index('ix_promo_code_uses_user_id', 'promo_code_uses')
    op.drop_index('ix_promo_code_uses_promo_code_id', 'promo_code_uses')
    op.drop_index('ix_promo_codes_code', 'promo_codes')
    
    # Drop tables
    op.drop_table('promo_code_uses')
    op.drop_table('promo_codes')
    
    # Remove column from users
    op.drop_column('users', 'withdrawal_locked_balance')