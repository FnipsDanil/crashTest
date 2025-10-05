from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from services.database_service import DatabaseService
from services.redis_service import _serialize_decimals
from models import User, Gift as GiftModel, UserStats
import redis.asyncio as redis
import json
import os
import logging
from typing import Optional, List, Dict, Any

# Setup logging
logger = logging.getLogger(__name__)

class MigrationService:
    """Service to gradually migrate data from Redis to PostgreSQL"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        
    async def get_user_balance_hybrid(self, session: AsyncSession, user_id: int):
        """Get user balance with fallback to Redis"""
        try:
            # Try PostgreSQL first
            user = await DatabaseService.get_user_by_telegram_id(session, user_id)
            if user:
                return user.balance
        except Exception as e:
            logger.warning(f"PostgreSQL balance lookup failed: {e}")
        
        # Fallback to Redis
        balance = await self.redis_client.hget("user_balances", str(user_id))
        return Decimal(str(balance)).quantize(Decimal('0.01')) if balance else Decimal('0.00')
    
    async def update_user_balance_hybrid(self, session: AsyncSession, user_id: int, 
                                       amount, transaction_type: str = "manual", 
                                       extra_data: Dict = None, user_data: Dict = None) -> Decimal:
        """Update user balance in both PostgreSQL and Redis"""
        try:
            # Try to get or create user in PostgreSQL with user data if available
            if user_data:
                user = await DatabaseService.get_or_create_user(
                    session, user_id,
                    username=user_data.get("username"),
                    first_name=user_data.get("first_name"),
                    last_name=user_data.get("last_name"),
                    language_code=user_data.get("language_code")
                )
            else:
                user = await DatabaseService.get_or_create_user(session, user_id)
            new_balance = await DatabaseService.update_balance(
                session, user.id, amount, transaction_type
            )
            
            # Also update Redis for backward compatibility
            await self.redis_client.hset("user_balances", str(user_id), str(new_balance))
            return new_balance
            
        except Exception as e:
            logger.warning(f"PostgreSQL balance update failed: {e}")
            # Fallback to Redis only
            current_balance = await self.get_user_balance_hybrid(session, user_id)
            new_balance = max(Decimal('0'), current_balance + amount)
            await self.redis_client.hset("user_balances", str(user_id), str(new_balance))
            return new_balance
    
    async def get_gifts_hybrid(self, session: AsyncSession) -> List[Dict]:
        """Get gifts with PostgreSQL priority, Redis fallback"""
        try:
            # Try PostgreSQL first
            gifts = await DatabaseService.get_gifts(session)
            if gifts:
                return [
                    {
                        "id": gift.id,
                        "name": gift.name,
                        "description": gift.description,
                        "price": gift.price,
                        "telegram_gift_id": gift.telegram_gift_id,
                        "emoji": gift.emoji,
                        "image_url": gift.image_url
                    }
                    for gift in gifts
                ]
        except Exception as e:
            logger.warning(f"PostgreSQL gifts lookup failed: {e}")
        
        # Fallback to Redis
        gifts_raw = await self.redis_client.get("available_gifts")
        if gifts_raw:
            return json.loads(gifts_raw)
        return []
    
    async def migrate_user_to_postgres(self, session: AsyncSession, telegram_id: int) -> Optional[User]:
        """Migrate single user from Redis to PostgreSQL"""
        try:
            # Check if user already exists in PostgreSQL
            user = await DatabaseService.get_user_by_telegram_id(session, telegram_id)
            if user:
                return user
            
            # Get balance from Redis
            balance = await self.redis_client.hget("user_balances", str(telegram_id))
            balance = Decimal(str(balance)).quantize(Decimal('0.01')) if balance else Decimal('0.00')
            
            # Get stats from Redis if available
            stats_raw = await self.redis_client.hget("user_stats", str(telegram_id))
            stats = json.loads(stats_raw) if stats_raw else {}
            
            # Create user in PostgreSQL
            user = await DatabaseService.create_user(session, telegram_id)
            user.balance = balance
            
            # Update with any additional info from stats
            if stats:
                user.total_deposited = stats.get("total_deposited", 0)
                user.total_withdrawn = stats.get("total_withdrawn", 0)
            
            await session.commit()
            # User migrated successfully
            return user
            
        except Exception as e:
            logger.error(f"❌ Failed to migrate user {telegram_id}: {e}")
            return None
    
    async def sync_gifts_to_postgres(self, session: AsyncSession) -> bool:
        """Sync gifts from Redis to PostgreSQL"""
        try:
            # Get gifts from Redis
            gifts_raw = await self.redis_client.get("available_gifts")
            if not gifts_raw:
                return False
            
            redis_gifts = json.loads(gifts_raw)
            
            # Sync each gift to PostgreSQL
            for gift_data in redis_gifts:
                # Check if gift exists
                existing_gift = await DatabaseService.get_gift_by_id(session, gift_data["id"])
                
                if not existing_gift:
                    # Create new gift
                    gift = GiftModel(
                        id=gift_data["id"],
                        name=gift_data["name"],
                        description=gift_data["description"],
                        price=gift_data["price"],
                        telegram_gift_id=gift_data["telegram_gift_id"],
                        emoji=gift_data["emoji"],
                        image_url=gift_data.get("image_url")
                    )
                    session.add(gift)
                else:
                    # Update existing gift
                    existing_gift.name = gift_data["name"]
                    existing_gift.description = gift_data["description"]
                    existing_gift.price = gift_data["price"]
                    existing_gift.telegram_gift_id = gift_data["telegram_gift_id"]
                    existing_gift.emoji = gift_data["emoji"]
                    existing_gift.image_url = gift_data.get("image_url")
            
            await session.commit()
            # Gifts synced successfully
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to sync gifts: {e}")
            return False
    
    async def record_player_transaction(self, session: AsyncSession, user_id: int, 
                                      game_id: int, transaction_type: str,
                                      amount: Decimal, multiplier: Decimal = None) -> bool:
        """Record player transaction (bet or win) in new schema"""
        try:
            # First ensure user exists in PostgreSQL
            user = await self.migrate_user_to_postgres(session, user_id)
            if not user:
                return False
            
            # Get current balance
            current_balance = await self.get_user_balance_hybrid(session, user_id)
            
            if transaction_type == 'game_loss':
                # Record bet - update balance and record transaction
                # Recording game loss
                await self.update_user_balance_hybrid(session, user_id, -amount, transaction_type)
                # Get new balance after deduction
                new_balance = current_balance - amount
                await DatabaseService.record_player_bet(
                    session, user.id, game_id, amount, new_balance
                )
                # Game loss recorded
            elif transaction_type == 'game_win':
                # 🔒 FIXED: Single transaction approach to prevent double statistics
                # Recording game win
                
                # 1. Update user balance manually (no transaction created yet)
                user_obj = await DatabaseService.get_user_by_telegram_id(session, user_id)
                if not user_obj:
                    logger.error(f"❌ User {user_id} not found during win recording")
                    return False
                
                user_obj.balance = Decimal(str(user_obj.balance)) + Decimal(str(amount))
                new_balance = user_obj.balance
                
                # 2. Record single transaction for statistics
                await DatabaseService.record_player_win(
                    session, user_obj.id, game_id, amount, multiplier, new_balance
                )
                
                # 3. Sync with Redis
                await self.redis_client.hset("user_balances", str(user_id), str(new_balance))
                
                # Game win recorded
            
            # 🔒 FIXED: Balance is already updated above, no double crediting
            
            # Also update Redis stats for backward compatibility
            if transaction_type == 'game_win':
                # amount теперь содержит total_payout, нужно вычесть ставку
                from sqlalchemy import select
                bet_query = await session.execute(
                    select(Transaction.amount)
                    .where(Transaction.user_id == user.id, Transaction.game_id == game_id, Transaction.type == 'game_bet')
                )
                bet_transaction = bet_query.scalar()
                bet_amount_actual = abs(bet_transaction) if bet_transaction else Decimal('0.00')
                win_amount = amount - bet_amount_actual  # Чистый выигрыш
                bet_amount = Decimal('0.00')
            else:
                win_amount = Decimal('0.00')
                bet_amount = amount if transaction_type == 'game_loss' else Decimal('0.00')
            await self._update_redis_stats(user_id, bet_amount, win_amount, multiplier)
            return True
            
        except Exception as e:
            logger.error(f"Failed to record player transaction: {e}")
            # 🔒 CRITICAL FIX: Rollback session to prevent "transaction has been rolled back" error
            try:
                await session.rollback()
                # Session rolled back due to error
            except Exception as rollback_error:
                logger.error(f"❌ Failed to rollback session: {rollback_error}")
            
            # Fallback to Redis only
            # NOTE: В fallback режиме не можем правильно рассчитать win_amount для game_win
            # так как нет доступа к game_id для поиска соответствующей ставки
            if transaction_type == 'game_win':
                logger.warning(f"Fallback mode: cannot calculate correct win_amount for user {user_id}")
                # Пропускаем обновление Redis stats в fallback для game_win
                win_amount = Decimal('0.00')
                bet_amount = Decimal('0.00')
            else:
                win_amount = Decimal('0.00')
                bet_amount = amount if transaction_type == 'game_loss' else Decimal('0.00')
            
            if not (transaction_type == 'game_win'):  # Обновляем Redis только если не game_win
                await self._update_redis_stats(user_id, bet_amount, win_amount, multiplier)
            return False
    
    # Deprecated - use record_player_transaction instead
    async def record_game_hybrid(self, session: AsyncSession, user_id: int, 
                               bet_amount, multiplier = None, 
                               win_amount = 0.0, crash_point = None, 
                               cashed_out_at = None) -> bool:
        """DEPRECATED: Record game in both PostgreSQL and Redis stats"""
        # Convert to new schema calls
        try:
            success = True
            if bet_amount > 0:
                success = await self.record_player_transaction(
                    session, user_id, None, 'game_loss', Decimal(str(bet_amount))
                )
            if win_amount > 0 and success:
                success = await self.record_player_transaction(
                    session, user_id, None, 'game_win', Decimal(str(win_amount)), 
                    Decimal(str(multiplier)) if multiplier else None
                )
            return success
        except Exception as e:
            logger.error(f"Failed in record_game_hybrid: {e}")
            return False
    
    async def _update_redis_stats(self, user_id: int, bet_amount, 
                                win_amount, multiplier = None):
        """Update Redis stats for backward compatibility"""
        try:
            stats_key = f"user_stats"
            stats_raw = await self.redis_client.hget(stats_key, str(user_id))
            
            if stats_raw:
                stats = json.loads(stats_raw)
            else:
                stats = {
                    "total_games": 0,
                    "games_won": 0,
                    "games_lost": 0,
                    "total_wagered": "0.00",
                    "total_won": "0.00",
                    "wagered_balance": "0.00",  # 🔒 FIXED: Added wagered_balance to Redis stats
                    "best_multiplier": 0.0,
                    "total_deposited": "0.00",
                    "total_withdrawn": "0.00"
                }
            
            # Update stats - convert to Decimal for consistency
            from decimal import Decimal
            stats["total_games"] += 1
            
            # Calculate new values
            total_wagered = Decimal(str(stats["total_wagered"])) + Decimal(str(bet_amount))
            total_won = Decimal(str(stats["total_won"])) + Decimal(str(win_amount))
            
            # 🔒 FIXED: Don't update wagered_balance in Redis - PostgreSQL trigger handles it automatically
            # This prevents double wagered_balance addition (PostgreSQL trigger + Redis update)
            current_wagered_balance = Decimal(str(stats.get("wagered_balance", "0.00")))
            # new_wagered_balance = current_wagered_balance + Decimal(str(win_amount))  # REMOVED: PostgreSQL trigger does this
            
            if Decimal(str(win_amount)) > Decimal('0'):
                stats["games_won"] += 1
            else:
                stats["games_lost"] += 1
            
            if multiplier and Decimal(str(multiplier)) > Decimal(str(stats["best_multiplier"])):
                stats["best_multiplier"] = str(multiplier)
            
            # Update stats object
            stats["total_wagered"] = total_wagered
            stats["total_won"] = total_won
            # stats["wagered_balance"] = new_wagered_balance  # REMOVED: Keep existing wagered_balance in Redis
            
            # Use the serializer to convert Decimals to strings
            stats_for_json = _serialize_decimals(stats)
            
            await self.redis_client.hset(stats_key, str(user_id), json.dumps(stats_for_json))
            
        except Exception as e:
            logger.error(f"Failed to update Redis stats: {e}")
    
    async def purchase_gift_hybrid(self, session: AsyncSession, user_id: int, 
                                 gift_id: str, user_data: Dict = None) -> Optional[Dict]:
        """Purchase gift with PostgreSQL priority"""
        try:
            # Ensure user exists in PostgreSQL with updated data
            if user_data:
                user = await DatabaseService.get_or_create_user(
                    session, user_id,
                    username=user_data.get("username"),
                    first_name=user_data.get("first_name"),
                    last_name=user_data.get("last_name"),
                    language_code=user_data.get("language_code")
                )
            else:
                user = await self.migrate_user_to_postgres(session, user_id)
            if not user:
                raise ValueError("Could not create/find user")
            
            # 🔒 CRITICAL FIX: Lock user row to prevent race conditions in balance operations
            # Re-fetch user with lock to ensure atomicity (necessary for race condition prevention)
            result = await session.execute(
                select(User).where(User.id == user.id).with_for_update()
            )
            user = result.scalar_one()
            
            # Lock user_stats to prevent concurrent wagered_balance operations
            await session.execute(
                select(UserStats).where(UserStats.user_id == user.id).with_for_update()
            )
            
            # Get gift info
            gift = await DatabaseService.get_gift_by_id(session, gift_id)
            if not gift:
                raise ValueError("Gift not found")
            
            # 🎯 CRITICAL FIX: Calculate actual price for unique gifts using TON conversion
            actual_price = Decimal(str(gift.price)) if gift.price else Decimal('0')  # Default to regular price, handle NULL
            
            if gift.is_unique and gift.ton_price:
                # For unique gifts, calculate price in stars from TON price
                from services.ton_price_service import ton_price_service
                calculated_stars_price = await ton_price_service.get_stars_price_for_ton(gift.ton_price)
                if calculated_stars_price:
                    actual_price = Decimal(str(calculated_stars_price))
                else:
                    logger.error(f"❌ Failed to calculate stars price for unique gift {gift.id}")
                    raise ValueError("Failed to calculate gift price")
            
            # 🔒 NOTE: Promo code withdrawal restriction is checked in DatabaseService.update_balance
            # This ensures atomicity - the check happens within the same transaction as balance update
            
            # 🎯 NEW: Check wagered balance requirement  
            # 🔒 FIXED: Use database_service instance method, not session-based static method
            from services.database_service import DatabaseService as db_service
            db_instance = db_service()
            user_stats = await db_instance.get_user_stats(user_id)
            wagered_balance = Decimal(str(user_stats.get("wagered_balance", "0.0")))
            required_wagered = (actual_price / Decimal('2')).quantize(Decimal('0.01'))  # Need to wager 50% of gift price
            
            if wagered_balance < required_wagered:
                missing_amount = required_wagered - wagered_balance
                raise ValueError(f"Вам нужно отыграть баланс, выиграв без учёта проигрышей {missing_amount:.0f} звёзд")
            
            # 🎁 NEW: Check daily gift purchase limit
            daily_gift_limit_setting = await DatabaseService.get_system_setting(session, "daily_gift_limit")
            daily_limit = daily_gift_limit_setting.get("limit", 5) if daily_gift_limit_setting else 5
            
            gifts_purchased_today = await DatabaseService.count_gifts_purchased_today(session, user.id)
            if gifts_purchased_today >= daily_limit:
                raise ValueError(f"Превышен дневной лимит покупки подарков ({daily_limit} шт.). Временное ограничение до 5 подарков в день.")
            
            # 🔒 FIRST: Check withdrawal_locked_balance BEFORE any operations
            current_balance = Decimal(str(user.balance))
            withdrawal_locked_balance = await DatabaseService.calculate_withdrawal_locked_balance(session, user.id)
            
            if withdrawal_locked_balance > 0:
                # 🔒 CRITICAL: ANY locked balance blocks ALL withdrawals/purchases until deposit
                required_deposit = withdrawal_locked_balance
                raise ValueError(
                    f"promo_balance_locked|0|{withdrawal_locked_balance}|{required_deposit}"
                )
            
            # 🎯 SECOND: Reduce wagered balance AFTER withdrawal check passed
            wagered_balance_reduction = (actual_price / Decimal('2')).quantize(Decimal('0.01'))
            wagered_balance_reduced = await DatabaseService.reduce_wagered_balance(session, user.id, wagered_balance_reduction)
            if not wagered_balance_reduced:
                logger.error(f"❌ Failed to reduce wagered_balance for user {user_id}: reduction {wagered_balance_reduction}, available {wagered_balance}")
                raise ValueError("Failed to reduce wagered balance - insufficient funds")
            
            # Record purchase with actual calculated price
            purchase = await DatabaseService.purchase_gift(session, user.id, gift_id, actual_price)
            
            # Update balance using the actual calculated price (withdrawal_locked_balance already checked above)
            new_balance = await DatabaseService.update_balance(
                session, user.id, -actual_price, "gift_purchase"
            )
            
            # Update Redis balance for compatibility - use returned balance for consistency
            await self.redis_client.hset("user_balances", str(user_id), str(new_balance))
            
            return {
                "purchase_id": purchase.id,
                "user_id": user.id,  # 🔧 FIX: Add internal database user ID for payment_requests
                "gift": {
                    "id": gift.id,
                    "name": gift.name,
                    "description": gift.description,
                    "price": str(actual_price),  # 🎯 FIX: Return actual calculated price, not database price
                    "telegram_gift_id": gift.telegram_gift_id,
                    "business_gift_id": gift.business_gift_id,
                    "emoji": gift.emoji,
                    "image_url": gift.image_url,
                    "is_unique": gift.is_unique
                },
                "new_balance": str(new_balance)
            }
            
        except Exception as e:
            # 🔒 CRITICAL: Rollback all database changes on any error
            try:
                await session.rollback()
                # Gift purchase transaction rolled back
            except Exception as rollback_error:
                logger.error(f"❌ CRITICAL: Failed to rollback gift purchase transaction: {rollback_error}")
            
            # Don't log daily limit as error - it's normal business logic  
            if "дневной лимит" not in str(e) and "daily limit" not in str(e) and "promo_balance_locked" not in str(e):
                logger.error(f"Gift purchase failed: {e}")
            raise e