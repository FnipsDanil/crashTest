"""
PromoCode Service with comprehensive security
Handles promo code validation and reward distribution
"""

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from models import User, PromoCode, PromoCodeUse, Transaction
from services.redis_service import RedisService
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class PromoCodeService:
    """Service for handling promo code validation and rewards with maximum security."""
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
        
        # Promo code validation patterns
        self.code_pattern = re.compile(r'^[A-Z0-9]{3,50}$')  # Only uppercase letters and numbers
    
    async def use_promo_code(
        self,
        user_id: int,
        promo_code: str,
        authenticated_user_id: int,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Validate and use promo code with full security.
        
        Args:
            user_id: Target user ID
            promo_code: Promo code to use
            authenticated_user_id: Actually authenticated user ID (for security)
            session: Database session
            
        Returns:
            Dict with success status, error message, and granted amount
        """
        
        # 🔒 SECURITY: Verify user ID matches authenticated user
        if user_id != authenticated_user_id:
            logger.warning(f"❌ User ID mismatch: {user_id} vs {authenticated_user_id}")
            return {"success": False, "error": "Authentication error"}
        
        # 🔒 SECURITY: Redis lock to prevent concurrent use
        lock_key = f"promo_code_use:{user_id}:{promo_code}"
        lock_acquired = await self.redis.acquire_lock(lock_key, timeout=30)
        
        if not lock_acquired:
            logger.warning(f"Rate limit: concurrent promo code request blocked for user {user_id}, code {promo_code}")
            return {"success": False, "error": "Request in progress, please wait"}
        
        try:
            return await self._process_promo_code_use(
                user_id, promo_code, session
            )
        finally:
            # 🔒 CRITICAL: Always release the lock
            try:
                await self.redis.release_lock(lock_key)
            except Exception as e:
                logger.error(f"Failed to release lock {lock_key}: {e}")
    
    async def _process_promo_code_use(
        self,
        user_id: int,
        promo_code: str,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Internal method to process promo code use with transaction safety."""
        
        try:
            # 🔒 VALIDATION: Input validation
            if not self._validate_promo_code_format(promo_code):
                return {"success": False, "error": "Invalid promo code format"}
            
            # 🔒 SECURITY: Get user with FOR UPDATE lock
            user_result = await session.execute(
                select(User)
                .where(User.telegram_id == user_id)
                .with_for_update()
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return {"success": False, "error": "User not found"}
            
            # 🔒 SECURITY: Get promo code with FOR UPDATE lock
            promo_result = await session.execute(
                select(PromoCode)
                .where(
                    and_(
                        PromoCode.code == promo_code.upper(),
                        PromoCode.is_active == True
                    )
                )
                .options(selectinload(PromoCode.uses))
                .with_for_update()
            )
            promo = promo_result.scalar_one_or_none()
            
            if not promo:
                return {"success": False, "error": "Promo code not found or inactive"}
            
            # 🔒 VALIDATION: Check if promo code is expired
            if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
                return {"success": False, "error": "Promo code has expired"}
            
            # 🔒 VALIDATION: Check if promo code has uses left
            if promo.current_uses >= promo.max_uses:
                return {"success": False, "error": "Promo code has no uses left"}
            
            # 🔒 VALIDATION: Check if user already used this promo code
            existing_use_result = await session.execute(
                select(PromoCodeUse)
                .where(
                    and_(
                        PromoCodeUse.promo_code_id == promo.id,
                        PromoCodeUse.user_id == user.id
                    )
                )
            )
            existing_use = existing_use_result.scalar_one_or_none()
            
            if existing_use:
                return {"success": False, "error": "Promo code already used"}
            
            # 🚀 GRANT REWARD: Update user balance
            old_balance = user.balance
            new_balance = old_balance + promo.balance_reward
            
            # Update user balance and withdrawal locked balance if needed
            user.balance = new_balance
            if promo.withdrawal_requirement:
                user.withdrawal_locked_balance += promo.balance_reward
            
            # 🚀 UPDATE: Increment promo code uses
            promo.current_uses += 1
            
            # 🚀 RECORD: Create promo code use record
            promo_use = PromoCodeUse(
                promo_code_id=promo.id,
                user_id=user.id,
                balance_granted=promo.balance_reward,
                withdrawal_requirement=promo.withdrawal_requirement
            )
            session.add(promo_use)
            
            # 🚀 AUDIT: Create transaction record
            transaction = Transaction(
                user_id=user.id,
                type='promo_code_bonus',
                amount=promo.balance_reward,
                balance_after=new_balance,
                status='completed',
                extra_data={
                    'promo_code': promo_code,
                    'promo_code_id': promo.id,
                    'withdrawal_requirement': str(promo.withdrawal_requirement) if promo.withdrawal_requirement else None
                },
                completed_at=datetime.now(timezone.utc)
            )
            session.add(transaction)
            
            # 🚀 COMMIT: Save all changes
            await session.commit()
            
            # 🚀 CACHE: Update Redis cache
            await self._update_balance_cache(user_id, new_balance)
            
            # Success logged in transaction table - no need for additional logging
            
            return {
                "success": True,
                "bonus_amount": str(promo.balance_reward),
                "new_balance": str(new_balance),
                "withdrawal_requirement": str(promo.withdrawal_requirement) if promo.withdrawal_requirement else None,
                "promo_code": promo_code
            }
            
        except IntegrityError as e:
            await session.rollback()
            logger.warning(f"❌ Integrity error using promo code {promo_code} for user {user_id}: {e}")
            return {"success": False, "error": "Promo code already used"}
        
        except Exception as e:
            await session.rollback()
            
            # Handle database trigger error for promo code validation
            error_message = str(e)
            if "Промокод неактивен, истек или исчерпан" in error_message:
                logger.warning(f"❌ Promo code validation failed (DB trigger): {promo_code} for user {user_id}")
                return {"success": False, "error": "Promo code is no longer available"}
            
            logger.error(f"❌ Error using promo code {promo_code} for user {user_id}: {e}")
            return {"success": False, "error": "Internal server error"}
    
    def _validate_promo_code_format(self, code: str) -> bool:
        """Validate promo code format."""
        if not code or len(code) < 3 or len(code) > 50:
            return False
        
        return bool(self.code_pattern.match(code.upper()))
    
    async def _update_balance_cache(self, user_id: int, balance: Decimal) -> None:
        """Update user balance in Redis cache."""
        try:
            if self.redis:
                await self.redis.set_user_balance(user_id, str(balance))
        except Exception as e:
            logger.warning(f"Failed to update balance cache for user {user_id}: {e}")
    
    async def get_user_promo_uses(
        self,
        user_id: int,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Get all promo codes used by user."""
        
        try:
            result = await session.execute(
                select(PromoCodeUse)
                .join(PromoCode)
                .where(PromoCodeUse.user_id == user_id)
                .options(selectinload(PromoCodeUse.promo_code))
                .order_by(PromoCodeUse.used_at.desc())
            )
            uses = result.scalars().all()
            
            promo_uses = []
            total_earned = Decimal('0')
            
            for use in uses:
                promo_uses.append({
                    "code": use.promo_code.code,
                    "balance_granted": str(use.balance_granted),
                    "withdrawal_requirement": str(use.withdrawal_requirement) if use.withdrawal_requirement else None,
                    "used_at": use.used_at.isoformat() if use.used_at else None
                })
                total_earned += use.balance_granted
            
            return {
                "promo_uses": promo_uses,
                "total_earned": str(total_earned),
                "count": len(promo_uses)
            }
        
        except Exception as e:
            logger.error(f"Failed to get promo uses for user {user_id}: {e}")
            return {
                "promo_uses": [],
                "total_earned": "0.00",
                "count": 0
            }
    
    async def check_withdrawal_eligibility(
        self,
        user_id: int,
        withdrawal_amount: Decimal,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Check if user can withdraw given amount considering promo code requirements."""
        
        try:
            # Get user data
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if not user:
                return {"eligible": False, "error": "User not found"}
            
            # Available balance for withdrawal = total balance - locked balance
            available_balance = user.balance - user.withdrawal_locked_balance
            
            if withdrawal_amount > available_balance:
                required_deposit = withdrawal_amount - available_balance
                return {
                    "eligible": False,
                    "error": "Insufficient available balance",
                    "available_balance": str(available_balance),
                    "locked_balance": str(user.withdrawal_locked_balance),
                    "required_deposit": str(required_deposit)
                }
            
            return {
                "eligible": True,
                "available_balance": str(available_balance),
                "locked_balance": str(user.withdrawal_locked_balance)
            }
        
        except Exception as e:
            logger.error(f"Failed to check withdrawal eligibility for user {user_id}: {e}")
            return {"eligible": False, "error": "Internal server error"}
    
    async def unlock_balance_on_deposit(
        self,
        user_id: int,
        deposit_amount: Decimal,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Unlock withdrawal locked balance when user makes a deposit."""
        
        try:
            # Get user with lock
            user_result = await session.execute(
                select(User)
                .where(User.telegram_id == user_id)
                .with_for_update()
            )
            user = user_result.scalar_one_or_none()
            
            if not user or user.withdrawal_locked_balance <= 0:
                return {"unlocked": "0.00"}
            
            # Unlock amount equal to deposit, but not more than locked balance
            unlock_amount = min(deposit_amount, user.withdrawal_locked_balance)
            user.withdrawal_locked_balance -= unlock_amount
            
            await session.commit()
            
            # Balance unlock completed successfully
            
            return {
                "unlocked": str(unlock_amount),
                "remaining_locked": str(user.withdrawal_locked_balance)
            }
        
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to unlock balance for user {user_id}: {e}")
            return {"unlocked": "0.00"}