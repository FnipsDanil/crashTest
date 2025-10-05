"""
Channel Subscription Service with comprehensive security
Handles Telegram channel subscription verification and bonus distribution
"""

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from models import User, ChannelSubscriptionBonus, Transaction
from services.redis_service import RedisService
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)


class ChannelSubscriptionService:
    """Service for handling channel subscription bonuses with maximum security."""
    
    def __init__(self, bot_token: str, redis_service: RedisService):
        self.bot_token = bot_token
        self.redis = redis_service
        self.timeout = 10.0  # HTTP timeout for Telegram API
        self.max_retries = 3
        self.rate_limit_delay = 2  # seconds between retries on 429
        
        # Channel ID validation patterns
        self.username_pattern = re.compile(r'^@[a-zA-Z0-9_]{5,32}$')
        self.channel_id_pattern = re.compile(r'^-100\d{10,}$')
    
    async def check_and_grant_bonus(
        self,
        user_id: int,
        channel_id: str,
        authenticated_user_id: int,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Check channel subscription and grant bonus with full security.
        
        Returns:
            - success: bool
            - error: str (if not successful)
            - bonus_amount: float (if successful)
            - new_balance: float (if successful)
        """
        
        # 🔒 SECURITY: Verify user identity matches authentication
        if user_id != authenticated_user_id:
            logger.warning(f"Security violation: user_id {user_id} != authenticated {authenticated_user_id}")
            return {"success": False, "error": "Access denied"}
        
        # 🔒 RATE LIMITING: Redis lock to prevent concurrent requests
        lock_key = f"channel_bonus_lock:{user_id}:{channel_id}"
        lock_acquired = await self.redis.acquire_lock(lock_key, timeout=30)
        
        if not lock_acquired:
            logger.warning(f"Rate limit: concurrent request blocked for user {user_id}, channel {channel_id}")
            return {"success": False, "error": "Request in progress, please wait"}
        
        try:
            # 1. Validate channel ID format
            if not self._is_valid_channel_id(channel_id):
                logger.warning(f"Invalid channel ID format: {channel_id}")
                return {"success": False, "error": "Invalid channel ID format"}
            
            # 2. Get user first to check if bonus already claimed
            result = await session.execute(select(User).where(User.telegram_id == user_id))
            user = result.scalar_one_or_none()
            if not user:
                return {"success": False, "error": "User not found"}
            
            # Check if user already received bonus for this channel
            existing_bonus = await session.execute(
                select(ChannelSubscriptionBonus)
                .where(ChannelSubscriptionBonus.user_id == user.id)  # Use database user.id
                .where(ChannelSubscriptionBonus.channel_id == channel_id)
            )
            existing_bonus = existing_bonus.scalar_one_or_none()
            
            if existing_bonus and existing_bonus.subscription_verified_at is not None:
                return {"success": False, "error": "Bonus already claimed for this channel"}
            
            # 3. Check subscription with full error handling
            try:
                subscription_result = await self._check_subscription_with_retry(user_id, channel_id)
                is_subscribed, error_reason = subscription_result
                
                if not is_subscribed:
                    # Don't create any database records for failed attempts
                    return {"success": False, "error": f"Not subscribed to channel: {error_reason}"}
                
            except Exception as e:
                logger.error(f"Telegram API error for user {user_id}, channel {channel_id}: {e}")
                return {"success": False, "error": "Unable to verify subscription, please try again later"}
            
            # 4. Grant bonus in atomic transaction
            try:
                # Get bonus amount from system settings
                bonus_setting = await DatabaseService.get_system_setting(session, 'channel_subscription_bonus')
                bonus_amount = Decimal(str(bonus_setting)) if bonus_setting else Decimal('5.0')  # Default 5.0 if not configured
                
                # 4a. Update user balance (user already retrieved above)
                
                old_balance = user.balance
                user.balance += bonus_amount
                
                # 4b. Create bonus record
                bonus_record = ChannelSubscriptionBonus(
                    user_id=user.id,  # Use database user.id, not telegram_id
                    channel_id=channel_id,
                    bonus_amount=bonus_amount,
                    subscription_verified_at=datetime.now(timezone.utc),
                    attempts_count=1
                )
                session.add(bonus_record)
                
                # 4c. Create transaction record
                transaction = Transaction(
                    user_id=user.id,  # Use database user.id, not telegram_id
                    type='channel_bonus',
                    amount=bonus_amount,
                    balance_after=user.balance,
                    status='completed',
                    extra_data={
                        'channel_id': channel_id,
                        'bonus_type': 'subscription',
                        'verified_at': datetime.now(timezone.utc).isoformat()
                    }
                )
                session.add(transaction)
                
                # 4d. Commit all changes atomically
                await session.commit()
                
                # 5. Update Redis cache
                if self.redis:
                    try:
                        await self.redis.set_user_balance(user_id, str(user.balance))
                    except Exception as e:
                        logger.warning(f"Failed to update Redis balance: {e}")
                
                
                return {
                    "success": True,
                    "bonus_amount": float(bonus_amount),
                    "new_balance": float(user.balance),
                    "channel_id": channel_id
                }
                
            except IntegrityError as e:
                await session.rollback()
                logger.warning(f"Integrity error (likely duplicate): {e}")
                return {"success": False, "error": "Bonus already claimed"}
            
            except Exception as e:
                await session.rollback()
                logger.error(f"Database error during bonus grant: {e}")
                return {"success": False, "error": "Failed to process bonus"}
        
        finally:
            # 🔒 CRITICAL: Always release the lock
            try:
                await self.redis.release_lock(lock_key)
            except Exception as e:
                logger.error(f"Failed to release lock {lock_key}: {e}")
    
    async def _check_subscription_with_retry(
        self, 
        user_id: int, 
        channel_id: str
    ) -> Tuple[bool, str]:
        """
        Check subscription with comprehensive error handling and retries.
        
        Returns:
            Tuple[is_subscribed: bool, error_reason: str]
        """
        last_error = "Unknown error"
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(
                        f"https://api.telegram.org/bot{self.bot_token}/getChatMember",
                        params={
                            "chat_id": channel_id,
                            "user_id": user_id
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        
                        if data.get("ok"):
                            status = data["result"]["status"]
                            # Valid subscription statuses
                            if status in ["member", "administrator", "creator", "owner"]:
                                return True, "subscribed"
                            elif status in ["left", "kicked", "banned"]:
                                return False, "not_subscribed"
                            else:
                                return False, f"status_{status}"
                        else:
                            # API returned error
                            error_desc = data.get("description", "Unknown API error")
                            
                            if "user not found" in error_desc.lower():
                                return False, "user_not_found"
                            elif "chat not found" in error_desc.lower():
                                raise ValueError(f"Invalid channel ID: {channel_id}")
                            elif "bot was blocked" in error_desc.lower():
                                return False, "bot_blocked"
                            else:
                                last_error = error_desc
                    
                    elif response.status_code == 429:
                        # Rate limited - wait and retry
                        retry_after = int(response.headers.get("Retry-After", self.rate_limit_delay))
                        logger.warning(f"Rate limited, waiting {retry_after}s (attempt {attempt + 1})")
                        
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            last_error = "rate_limited"
                    
                    elif response.status_code in [400, 403]:
                        # Bad request or forbidden - likely not subscribed
                        return False, "api_error_400_403"
                    
                    else:
                        last_error = f"http_{response.status_code}"
                        
            except httpx.TimeoutException:
                last_error = "timeout"
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                    
            except httpx.ConnectError:
                last_error = "connection_error"
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                    
            except Exception as e:
                last_error = f"unexpected_error: {str(e)}"
                logger.error(f"Unexpected error in subscription check: {e}")
        
        # All retries exhausted
        raise Exception(f"Failed to check subscription after {self.max_retries} attempts: {last_error}")
    
    async def _record_failed_attempt(
        self,
        session: AsyncSession,
        telegram_user_id: int,
        channel_id: str,
        error_reason: str
    ):
        """Record failed subscription attempt for analytics."""
        try:
            # Get user by telegram_id first
            result = await session.execute(select(User).where(User.telegram_id == telegram_user_id))
            user = result.scalar_one_or_none()
            if not user:
                logger.warning(f"Cannot record failed attempt - user with telegram_id {telegram_user_id} not found")
                return
            
            # Check if there's already a failed attempt record
            existing = await session.execute(
                select(ChannelSubscriptionBonus)
                .where(ChannelSubscriptionBonus.user_id == user.id)  # Use database user.id
                .where(ChannelSubscriptionBonus.channel_id == channel_id)
            )
            existing = existing.scalar_one_or_none()
            
            if existing:
                # Update attempt count
                existing.attempts_count += 1
                existing.last_attempt_at = datetime.now(timezone.utc)
            else:
                # Create new failed attempt record (no bonus granted)
                failed_attempt = ChannelSubscriptionBonus(
                    user_id=user.id,  # Use database user.id, not telegram_id
                    channel_id=channel_id,
                    bonus_amount=Decimal('0.0'),  # No bonus granted
                    subscription_verified_at=None,  # Not verified
                    bonus_claimed_at=None,  # No bonus claimed
                    attempts_count=1
                )
                session.add(failed_attempt)
            
            await session.commit()
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to record attempt: {e}")
    
    def _is_valid_channel_id(self, channel_id: str) -> bool:
        """
        Validate channel ID format.
        
        Valid formats:
        - @username (5-32 chars, alphanumeric + underscore)
        - -1001234567890 (channel chat ID)
        """
        if not channel_id or not isinstance(channel_id, str):
            return False
        
        # Username format: @channel_name
        if channel_id.startswith('@'):
            return bool(self.username_pattern.match(channel_id))
        
        # Channel ID format: -1001234567890
        elif channel_id.startswith('-100'):
            return bool(self.channel_id_pattern.match(channel_id))
        
        return False
    
    async def get_user_channel_bonuses(
        self,
        telegram_user_id: int,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """Get all channel bonuses for a user."""
        try:
            # Get user by telegram_id first
            result = await session.execute(select(User).where(User.telegram_id == telegram_user_id))
            user = result.scalar_one_or_none()
            if not user:
                logger.warning(f"User with telegram_id {telegram_user_id} not found")
                return {"bonuses": [], "total_earned": 0.0, "channels_count": 0}
            
            bonuses = await session.execute(
                select(ChannelSubscriptionBonus)
                .where(ChannelSubscriptionBonus.user_id == user.id)  # Use database user.id
                .order_by(ChannelSubscriptionBonus.created_at.desc())
            )
            bonuses = bonuses.scalars().all()
            
            result = {
                "bonuses": [],
                "total_earned": 0.0,
                "channels_count": 0
            }
            
            for bonus in bonuses:
                if bonus.subscription_verified_at:  # Only count successful bonuses
                    result["bonuses"].append({
                        "channel_id": bonus.channel_id,
                        "bonus_amount": float(bonus.bonus_amount),
                        "claimed_at": bonus.bonus_claimed_at.isoformat() if bonus.bonus_claimed_at else None,
                        "verified_at": bonus.subscription_verified_at.isoformat()
                    })
                    result["total_earned"] += float(bonus.bonus_amount)
                    result["channels_count"] += 1
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get user channel bonuses: {e}")
            return {"bonuses": [], "total_earned": 0.0, "channels_count": 0}