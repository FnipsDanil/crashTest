"""Complete Database service - merged implementation"""

import math
import logging
import secrets
import string
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from sqlalchemy import select, insert, update, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from models import User, UserStats, GameHistory, Transaction, Gift, GiftPurchase, PaymentRequest, Referral, SystemSettings
from database import get_db

# Setup logging
logger = logging.getLogger(__name__)

class DatabaseService:
    """Complete modular database service - merged from db_service.py"""
    
    def __init__(self, redis_service=None):
        """Initialize with optional Redis service for balance sync"""
        self.redis_service = redis_service
    
    @staticmethod
    async def check_health(session: AsyncSession) -> bool:
        """Check database health"""
        try:
            await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
    
    # === CORE DATABASE METHODS (from db_service.py) ===
    
    @staticmethod
    async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID"""
        # 🔒 CRITICAL FIX: Ensure telegram_id is always an integer to prevent type mismatch
        telegram_id = int(telegram_id) if telegram_id else 0
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def create_user(session: AsyncSession, telegram_id: int, username: str = None, 
                         first_name: str = None, last_name: str = None, language_code: str = None) -> User:
        """Create new user"""
        # Generate unique referral code
        referral_code = await DatabaseService._generate_referral_code(session)
        
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            referral_code=referral_code,
            language_code=language_code or 'en'  # Default to 'en' if not provided
        )
        session.add(user)
        await session.flush()  # Get the ID
        
        # Create user stats
        stats = UserStats(user_id=user.id)
        session.add(stats)
        
        await session.commit()
        return user
    
    @staticmethod
    async def get_or_create_user(session: AsyncSession, telegram_id: int, 
                                username: str = None, first_name: str = None, 
                                last_name: str = None, language_code: str = None) -> User:
        """Get existing user or create new one"""
        user = await DatabaseService.get_user_by_telegram_id(session, telegram_id)
        if user:
            # Update user info if provided
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            if last_name and user.last_name != last_name:
                user.last_name = last_name
            if language_code and user.language_code != language_code:
                user.language_code = language_code
            await session.commit()
            return user
        else:
            return await DatabaseService.create_user(session, telegram_id, username, first_name, last_name, language_code)
    
    @staticmethod
    async def update_balance(session: AsyncSession, user_id: int, amount, 
                           transaction_type: str, extra_data: Dict = None, game_id: int = None, allow_promo_balance: bool = False):
        """Update user balance and create transaction record - ATOMIC with row lock"""
        # ✅ ATOMIC: Get user with row-level lock to prevent race conditions
        result = await session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")
        
        # Ensure amount is Decimal for proper arithmetic
        amount = Decimal(str(amount))
        
        # Ensure user.balance is also Decimal for proper arithmetic
        current_balance = Decimal(str(user.balance))
        
        # Calculate new balance
        new_balance = current_balance + amount
        if new_balance < 0:
            raise ValueError("Insufficient balance")
        
        # 🔓 PROMO CODE: Dynamic withdrawal locked balance - no need to update field
        # withdrawal_locked_balance is now calculated dynamically when needed
        
        # 🔒 PROMO CODE: Обнуляем stored withdrawal_locked_balance для gift_purchase если нужно
        if amount < 0 and transaction_type == "gift_purchase":  # Gift purchase operation
            # Проверка withdrawal_locked_balance уже выполнена в migration_service.py
            # Здесь только обнуляем stored значение если баланс разблокирован
            actual_locked_balance = await DatabaseService.calculate_withdrawal_locked_balance(session, user.id)
            if actual_locked_balance == 0 and user.withdrawal_locked_balance > 0:
                user.withdrawal_locked_balance = Decimal('0.00')
        
        # Update user balance
        user.balance = new_balance
        
        # Create transaction record
        transaction = Transaction(
            user_id=user_id,
            game_id=game_id,  # Add game_id to transaction
            type=transaction_type,
            amount=amount,
            balance_after=new_balance,
            status='completed',
            extra_data=extra_data,
            completed_at=func.now()
        )
        session.add(transaction)
        
        await session.commit()
        return new_balance
    
    # === HIGH-LEVEL METHODS WITH REDIS SYNC ===
    
    async def get_user_balance(self, user_id: int):
        """Get user balance in stars with Redis sync"""
        try:
            async for session in get_db():
                user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                if user and user.balance is not None:
                    balance = user.balance
                    # Sync with Redis if available
                    if self.redis_service:
                        await self.redis_service.set_user_balance(user_id, str(balance))
                    return balance
                break
        except Exception as e:
            logger.warning(f"⚠️ Failed to get balance from PostgreSQL: {e}")
        
        # Fallback to Redis
        if self.redis_service:
            balance = await self.redis_service.get_user_balance(user_id)
            return Decimal(str(balance)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        
        return Decimal('0.00')  # Default balance
    
    async def update_user_balance(self, user_id: int, amount, transaction_type: str = "game_operation", extra_data: Dict = None, game_id: int = None):
        """Update user balance and return new balance in stars"""
        try:
            async for session in get_db():
                user = await DatabaseService.get_or_create_user(session, user_id)
                new_balance = await DatabaseService.update_balance(
                    session, user.id, amount, transaction_type, extra_data, game_id
                )
                # Sync with Redis
                if self.redis_service:
                    await self.redis_service.set_user_balance(user_id, str(new_balance))
                
                return new_balance
        except Exception as e:
            logger.warning(f"⚠️ Failed to update balance in PostgreSQL: {e}")
        
        # Fallback to Redis only
        if self.redis_service:
            current_balance = await self.redis_service.get_user_balance(user_id)
            current_balance_decimal = Decimal(str(current_balance))  # Убеждаемся, что это Decimal
            amount_decimal = Decimal(str(amount))
            
            # 🔒 SECURITY: Prevent balance overflow/underflow
            MAX_BALANCE = Decimal('999999999.99')  # Maximum allowed balance
            MIN_BALANCE = Decimal('0.00')           # Minimum allowed balance
            
            new_balance = current_balance_decimal + amount_decimal
            
            # Check for overflow
            if new_balance > MAX_BALANCE:
                logger.error(f"🚨 Balance overflow prevented for user {user_id}: {new_balance} > {MAX_BALANCE}")
                
                # 🔒 SECURITY: Log balance overflow attempt
                try:
                    import asyncio
                    from security_monitor import get_security_monitor
                    security_monitor = get_security_monitor(self.redis_service.get_client())
                    # Run async function in background
                    asyncio.create_task(security_monitor.log_balance_overflow_attempt(
                        user_id,
                        new_balance,
                        MAX_BALANCE,
                        "unknown_ip"  # TODO: Pass real IP from request
                    ))
                except Exception as e:
                    logger.error(f"Failed to log security event: {e}")
                
                new_balance = MAX_BALANCE
                
            # Check for underflow (already handled by max(), but explicit check for logging)
            if new_balance < MIN_BALANCE:
                logger.warning(f"⚠️ Balance underflow prevented for user {user_id}: {new_balance} -> {MIN_BALANCE}")
                new_balance = MIN_BALANCE
            
            # Округляем до копеек
            new_balance = new_balance.quantize(Decimal('0.01'))
            await self.redis_service.set_user_balance(user_id, str(new_balance))
            return new_balance
        
        return Decimal('0.00')  # Default balance
    
    async def update_user_balance_safe(self, user_id: int, amount, transaction_type: str = "deposit", extra_data: Dict = None, game_id: int = None):
        """🔒 RACE CONDITION SAFE balance update with Redis mutex"""
        lock_key = f"balance_lock:{user_id}"
        lock_timeout = 10  # 10 seconds timeout
        
        # Try to acquire lock
        lock_acquired = False
        if self.redis_service:
            try:
                # SET with NX (only if not exists) and EX (expire)
                lock_acquired = await self.redis_service.get_client().set(
                    lock_key, "1", nx=True, ex=lock_timeout
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to acquire balance lock for user {user_id}: {e}")
        
        if not lock_acquired:
            # If Redis is unavailable or lock failed, use regular method (better than failing)
            logger.warning(f"⚠️ Using fallback balance update for user {user_id} (no lock)")
            return await self.update_user_balance(user_id, amount, transaction_type, extra_data, game_id)
        
        try:
            # Protected balance update under mutex
            return await self.update_user_balance(user_id, amount, transaction_type, extra_data, game_id)
        finally:
            # Always release lock
            if self.redis_service:
                try:
                    await self.redis_service.get_client().delete(lock_key)
                except Exception as e:
                    logger.error(f"❌ Failed to release balance lock for user {user_id}: {e}")
    
    @staticmethod
    async def create_game_round(session: AsyncSession, crash_point: Decimal) -> int:
        """Create new game round record and return game_id"""
        game_round = GameHistory(
            crash_point=crash_point,
            total_bet=Decimal('0.00'),
            total_payout=Decimal('0.00'), 
            house_profit=Decimal('0.00'),
            player_count=0
        )
        session.add(game_round)
        await session.flush()  # Get ID without committing
        return game_round.id
    
    @staticmethod
    async def create_game_round_without_crash(session: AsyncSession) -> int:
        """Create new game round record without crash_point and return game_id"""
        game_round = GameHistory(
            crash_point=Decimal('1.00'),  # Minimum valid value, will be updated when round starts
            total_bet=Decimal('0.00'),
            total_payout=Decimal('0.00'), 
            house_profit=Decimal('0.00'),
            player_count=0
        )
        session.add(game_round)
        await session.flush()  # Get ID without committing
        return game_round.id
    
    @staticmethod
    async def update_game_round_crash_point(session: AsyncSession, game_id: int, crash_point: Decimal) -> None:
        """Update crash_point for existing game round"""
        await session.execute(
            update(GameHistory)
            .where(GameHistory.id == game_id)
            .values(crash_point=crash_point)
        )
    
    @staticmethod
    async def record_player_bet(session: AsyncSession, user_id: int, game_id: int, 
                               bet_amount: Decimal, balance_after: Decimal) -> None:
        """Record player bet as game_loss transaction"""
        # Create bet transaction
        transaction = Transaction(
            user_id=user_id,
            game_id=game_id,
            type='game_loss',
            amount=-bet_amount,  # 🔒 CRITICAL FIX: Negative amount for losses (constraint updated)
            balance_after=balance_after,
            multiplier=None
        )
        session.add(transaction)
        
        # Update game round totals
        await session.execute(
            update(GameHistory)
            .where(GameHistory.id == game_id)
            .values(
                total_bet=GameHistory.total_bet + bet_amount,
                player_count=GameHistory.player_count + 1
            )
        )
    
    @staticmethod 
    async def record_player_win(session: AsyncSession, user_id: int, game_id: int,
                               win_amount: Decimal, multiplier: Decimal, balance_after: Decimal = None) -> None:
        """Record player win as game_win transaction"""
        # Get current balance if not provided
        if balance_after is None:
            user = await DatabaseService.get_user_by_telegram_id(session, user_id)
            balance_after = user.balance if user else Decimal('0.00')
        
        # Create win transaction
        transaction = Transaction(
            user_id=user_id,
            game_id=game_id,
            type='game_win',
            amount=win_amount,
            balance_after=balance_after,
            multiplier=multiplier
        )
        session.add(transaction)
        
        # Update game round totals
        await session.execute(
            update(GameHistory)
            .where(GameHistory.id == game_id)
            .values(total_payout=GameHistory.total_payout + win_amount)
        )
    
    @staticmethod
    async def finalize_game_round(session: AsyncSession, game_id: int) -> None:
        """Calculate and set house profit for completed game round"""
        await session.execute(
            update(GameHistory)
            .where(GameHistory.id == game_id)
            .values(house_profit=GameHistory.total_bet - GameHistory.total_payout)
        )
    
    @staticmethod
    async def complete_previous_round(session: AsyncSession) -> None:
        """Mark previous round as completed when new round starts"""
        # Найти последний незавершенный раунд и пометить как завершенный
        await session.execute(
            update(GameHistory)
            .where(GameHistory.is_completed == False)
            .values(is_completed=True)
        )
    
    async def record_game_result(self, user_id: int, bet_amount, multiplier = None, 
                                win_amount = 0, crash_point = None, 
                                cashed_out_at = None) -> bool:
        """Record game result and update user stats"""
        try:
            async for session in get_db():
                user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                if user:
                    await DatabaseService.record_game(
                        session, user.id, bet_amount, multiplier, win_amount, 
                        crash_point, cashed_out_at
                    )
                    return True
                break
        except Exception as e:
            logger.warning(f"⚠️ Failed to record game result: {e}")
        
        return False
    
    @staticmethod
    async def _get_user_stats_entity(session: AsyncSession, user_id: int) -> Optional[UserStats]:
        """Get user statistics entity (internal use)"""
        result = await session.execute(
            select(UserStats).where(UserStats.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    
    async def get_user_stats(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user statistics"""
        try:
            async for session in get_db():
                user = await DatabaseService.get_user_by_telegram_id(session, user_id)
                if user:
                    stats = await DatabaseService._get_user_stats_entity(session, user.id)
                    if stats:
                        final_avg = str(stats.avg_multiplier) if stats.games_won > 0 else "1.0"
                        
                        return {
                            "user_id": user_id,
                            "total_games": stats.total_games,
                            "games_won": stats.games_won,
                            "games_lost": stats.games_lost,
                            "total_wagered": str(stats.total_wagered),
                            "total_won": str(stats.total_won),
                            "wagered_balance": str(stats.wagered_balance),
                            "best_multiplier": str(stats.best_multiplier) if stats.games_won > 0 else "0.0",
                            "avg_multiplier": final_avg
                        }
                break
        except Exception as e:
            logger.warning(f"⚠️ Failed to get user stats: {e}")
        
        return {
            "user_id": user_id,
            "total_games": 0,
            "games_won": 0,
            "games_lost": 0,
            "total_wagered": "0.00",
            "total_won": "0.00",
            "wagered_balance": "0.00",
            "best_multiplier": "0.00",
            "avg_multiplier": "1.00"
        }
    
    # === ADDITIONAL METHODS FROM DB_SERVICE.PY ===
    
    @staticmethod
    async def get_gifts(session: AsyncSession, active_only: bool = True) -> List[Gift]:
        """Get available gifts"""
        query = select(Gift).order_by(Gift.sort_order, Gift.name)
        if active_only:
            query = query.where(Gift.is_active == True)
        
        result = await session.execute(query)
        return result.scalars().all()
    
    @staticmethod
    async def get_gift_by_id(session: AsyncSession, gift_id: str) -> Optional[Gift]:
        """Get gift by ID"""
        result = await session.execute(
            select(Gift).where(Gift.id == gift_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def purchase_gift(session: AsyncSession, user_id: int, gift_id: str, actual_price: Decimal = None) -> GiftPurchase:
        """Record gift purchase with actual price paid"""
        gift = await DatabaseService.get_gift_by_id(session, gift_id)
        if not gift:
            raise ValueError("Gift not found")
        
        # Use actual_price if provided, otherwise fall back to gift.price
        purchase_price = actual_price if actual_price is not None else Decimal(str(gift.price)) if gift.price else None
        if purchase_price is None:
            raise ValueError(f"No price available for gift {gift_id}")
        
        purchase = GiftPurchase(
            user_id=user_id,
            gift_id=gift_id,
            price=purchase_price,
            telegram_gift_id=gift.telegram_gift_id,
            status='pending'
        )
        session.add(purchase)
        await session.commit()
        return purchase
    
    @staticmethod
    async def update_gift_purchase_status(session: AsyncSession, purchase_id: int, 
                                        status: str, error_message: str = None) -> None:
        """Update gift purchase status"""
        purchase = await session.get(GiftPurchase, purchase_id)
        if purchase:
            purchase.status = status
            if error_message:
                purchase.error_message = error_message
            if status == 'sent':
                purchase.sent_at = func.now()
            await session.commit()

    @staticmethod
    async def create_payment_request(session: AsyncSession, user_id: int, gift_id: str, price_stars: Decimal = None) -> PaymentRequest:
        """Create payment request for unique gift"""
        gift = await DatabaseService.get_gift_by_id(session, gift_id)
        if not gift:
            raise ValueError("Gift not found")
        
        # Для уникальных подарков цена в payment_request должна быть в TON
        price_for_request = gift.ton_price if gift.is_unique and gift.ton_price else gift.price
        
        # Если price_stars не передан, используем price_for_request как fallback
        if price_stars is None:
            price_stars = price_for_request
        
        payment_request = PaymentRequest(
            user_id=user_id,
            gift_id=gift_id,
            gift_name=gift.name,
            price=price_for_request,  # Для unique подарков - цена в TON
            price_stars=price_stars,  # Фактически списанная цена в звездах
            status='pending'
        )
        session.add(payment_request)
        await session.commit()
        await session.refresh(payment_request)
        return payment_request
    
    @staticmethod
    async def reduce_wagered_balance(session: AsyncSession, user_id: int, amount: Decimal) -> bool:
        """Reduce user's wagered balance for gift purchase - ATOMIC operation"""
        try:
            # Ensure amount is Decimal with proper precision
            amount = Decimal(str(amount)).quantize(Decimal('0.01'))
            
            # Use atomic UPDATE with WHERE condition to prevent race conditions
            result = await session.execute(
                update(UserStats)
                .where(
                    UserStats.user_id == user_id,
                    UserStats.wagered_balance >= amount  # Only update if sufficient balance
                )
                .values(
                    wagered_balance=UserStats.wagered_balance - amount,
                    updated_at=func.now()
                )
            )
            
            # Check if any row was updated
            if result.rowcount == 0:
                # Either user doesn't exist or insufficient wagered balance
                # Check if user exists
                stats_result = await session.execute(
                    select(UserStats).where(UserStats.user_id == user_id)
                )
                stats = stats_result.scalar_one_or_none()
                
                if not stats:
                    # Create stats with zero wagered balance
                    stats = UserStats(user_id=user_id, wagered_balance=Decimal('0.0'))
                    session.add(stats)
                    await session.flush()
                
                logger.warning(f"❌ Insufficient wagered balance for user {user_id}: requested {amount}, available {stats.wagered_balance if stats else 0}")
                return False
            
            # Don't commit here - let the parent transaction handle it
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to reduce wagered balance: {e}")
            return False

    @staticmethod
    async def get_pending_payment_requests(session: AsyncSession) -> List[PaymentRequest]:
        """Get all pending payment requests"""
        result = await session.execute(
            select(PaymentRequest).where(PaymentRequest.status == 'pending')
            .options(selectinload(PaymentRequest.user), selectinload(PaymentRequest.gift))
            .order_by(PaymentRequest.created_at)
        )
        return result.scalars().all()

    @staticmethod
    async def update_payment_request_status(session: AsyncSession, request_id: int, status: str) -> None:
        """Update payment request status"""
        payment_request = await session.get(PaymentRequest, request_id)
        if payment_request:
            payment_request.status = status
            if status == 'approved':
                payment_request.approved_at = func.now()
            elif status == 'completed':
                payment_request.completed_at = func.now()
            await session.commit()

    @staticmethod
    async def get_user_payment_requests(session: AsyncSession, telegram_user_id: int) -> List[PaymentRequest]:
        """Get user's payment requests by telegram_id"""
        # First get the internal user_id from telegram_id
        user = await DatabaseService.get_user_by_telegram_id(session, telegram_user_id)
        if not user:
            return []
        
        result = await session.execute(
            select(PaymentRequest).where(PaymentRequest.user_id == user.id)
            .options(selectinload(PaymentRequest.gift))
            .order_by(PaymentRequest.created_at.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_user_transactions(session: AsyncSession, user_id: int, 
                                  limit: int = 50, offset: int = 0) -> List[Transaction]:
        """Get user transaction history"""
        result = await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(desc(Transaction.created_at))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_system_setting(session: AsyncSession, key: str) -> Optional[Dict]:
        """Get system setting"""
        result = await session.execute(
            select(SystemSettings.value).where(SystemSettings.key == key)
        )
        value = result.scalar_one_or_none()
        return value if value else None
    
    @staticmethod
    async def set_system_setting(session: AsyncSession, key: str, value: Dict, 
                               description: str = None) -> None:
        """Set system setting using PostgreSQL UPSERT"""
        from sqlalchemy.dialects.postgresql import insert
        
        stmt = insert(SystemSettings).values(
            key=key,
            value=value,
            description=description
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=['key'],
            set_=dict(
                value=stmt.excluded.value,
                updated_at=func.now()
            )
        )
        await session.execute(stmt)
        await session.commit()
    
    @staticmethod
    async def get_available_gifts(session: AsyncSession) -> List[Gift]:
        """Get all available gifts"""
        result = await session.execute(
            select(Gift).where(Gift.is_active == True).order_by(Gift.sort_order)
        )
        return result.scalars().all()
    
    @staticmethod
    async def _generate_referral_code(session: AsyncSession) -> str:
        """Generate unique referral code"""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            # Check if code already exists
            result = await session.execute(
                select(User.id).where(User.referral_code == code)
            )
            if not result.scalar_one_or_none():
                return code
    
    @staticmethod
    async def create_referral(session: AsyncSession, referrer_id: int, referred_id: int, 
                            bonus_amount: int = 0) -> Referral:
        """Create referral relationship"""
        referral = Referral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            bonus_amount=bonus_amount
        )
        session.add(referral)
        await session.commit()
        return referral
    
    @staticmethod
    async def calculate_withdrawal_locked_balance(session: AsyncSession, user_db_id: int) -> Decimal:
        """Calculate actual withdrawal locked balance dynamically based on promo codes and deposits"""
        from models import PromoCodeUse, Transaction
        
        # Find all promo code uses with withdrawal requirements
        promo_uses_result = await session.execute(
            select(PromoCodeUse)
            .where(
                PromoCodeUse.user_id == user_db_id,
                PromoCodeUse.withdrawal_requirement > 0
            )
            .order_by(PromoCodeUse.used_at.desc())
        )
        promo_uses = promo_uses_result.scalars().all()
        
        if not promo_uses:
            return Decimal('0.00')
        
        # Get the EARLIEST promo code activation date (not latest!)
        earliest_promo_date = promo_uses[-1].used_at  # Last in desc order = earliest
        
        # Calculate TOTAL deposits after the EARLIEST promo activation
        deposits_result = await session.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0))
            .where(
                Transaction.user_id == user_db_id,
                Transaction.type == 'deposit',
                Transaction.completed_at > earliest_promo_date,
                Transaction.amount > 0
            )
        )
        total_deposits = Decimal(str(deposits_result.scalar() or 0))
        
        # Calculate TOTAL withdrawal requirements for ALL promo codes
        total_required = sum(Decimal(str(use.withdrawal_requirement)) for use in promo_uses)
        
        # Return remaining locked amount
        if total_deposits >= total_required:
            return Decimal('0.00')
        else:
            return total_required - total_deposits
    
    @staticmethod
    async def get_leaderboard(session: AsyncSession, limit: int = 100, current_user_telegram_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get leaderboard sorted by total_won with is_current_user flag for privacy"""
        result = await session.execute(
            select(
                User.telegram_id,
                User.first_name,
                User.last_name,
                User.username,
                UserStats.total_won,
                UserStats.total_games,
                UserStats.games_won,
                UserStats.best_multiplier,
                UserStats.avg_multiplier
            )
            .join(UserStats, User.id == UserStats.user_id)
            .where(UserStats.total_games > 0)
            .order_by(desc(UserStats.total_won))
            .limit(limit)
        )
        
        leaderboard = []
        for rank, row in enumerate(result.fetchall(), 1):
            # 🔒 SECURITY: Only add is_current_user flag, remove telegram_id from response
            leaderboard.append({
                "rank": rank,
                "is_current_user": current_user_telegram_id is not None and row.telegram_id == current_user_telegram_id,
                "first_name": row.first_name,
                "last_name": row.last_name,
                "username": row.username,
                "total_won": str(row.total_won),
                "total_games": row.total_games,
                "games_won": row.games_won,
                "best_multiplier": str(row.best_multiplier) if row.games_won > 0 else "0.0",
                "avg_multiplier": str(row.avg_multiplier) if row.games_won > 0 else "1.0"
            })
        
        return leaderboard
    
    @staticmethod
    async def get_user_rank(session: AsyncSession, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user's rank on leaderboard by telegram_id"""
        # Get total number of players
        total_players_result = await session.execute(
            select(func.count(UserStats.user_id)).where(UserStats.total_games > 0)
        )
        total_players = total_players_result.scalar() or 0
        
        # First find user by telegram_id
        user = await DatabaseService.get_user_by_telegram_id(session, telegram_id)
        if not user:
            return {"rank": None, "total_players": total_players}
        
        # Get user's stats by internal user_id
        user_stats = await DatabaseService._get_user_stats_entity(session, user.id)
        if not user_stats or user_stats.total_games == 0:
            return {"rank": None, "total_players": total_players}
        
        rank_result = await session.execute(
            select(func.count(UserStats.user_id))
            .where(UserStats.total_won > user_stats.total_won)
            .where(UserStats.total_games > 0)
        )
        rank = (rank_result.scalar() or 0) + 1
        
        return {"rank": rank, "total_players": total_players}
    
    @staticmethod
    async def get_recent_crashes(session: AsyncSession, limit: int = 20) -> List[GameHistory]:
        """Get recent crash coefficients from completed games only"""
        result = await session.execute(
            select(GameHistory)
            .where(GameHistory.crash_point.isnot(None))
            .where(GameHistory.crash_point > 1.0)
            .where(GameHistory.is_completed == True)  # Только завершенные игры
            .order_by(desc(GameHistory.played_at))
            .limit(limit)
        )
        return result.scalars().all()
    
    @staticmethod
    async def count_gifts_purchased_today(session: AsyncSession, user_id: int) -> int:
        """Count total gifts purchased by user today (both regular and unique)"""
        from datetime import datetime, timezone
        from sqlalchemy import func, select
        
        # Calculate start of current day in UTC
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # 🔧 FIX: Count only from gift_purchases as it contains both regular and unique gifts
        # Previously was double counting unique gifts (from both gift_purchases and payment_requests)
        gifts_query = select(func.count(GiftPurchase.id)).where(
            GiftPurchase.user_id == user_id,
            GiftPurchase.purchased_at >= today_start
        )
        
        result = await session.execute(gifts_query)
        return result.scalar() or 0