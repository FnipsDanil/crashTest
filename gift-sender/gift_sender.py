"""
Automatic Gift Sender Script
Processes approved payment requests and sends gifts via aiogram
Features:
- Auto-detects gifts available on business account
- Auto-matches gifts from collections to payment requests by name
- Requires manual confirmation before sending
"""

import os
import sys
import asyncio
import logging
import random
from decimal import Decimal
from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.types import Gift
from aiogram.exceptions import TelegramAPIError

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('gift_sender.log')
    ]
)

logger = logging.getLogger(__name__)

class GiftSenderService:
    """Service for processing approved payment requests and sending gifts"""
    
    def __init__(self, business_connection_id: Optional[str] = None):
        # Get configuration from environment
        self.bot_token = os.getenv('TG_BOT_SENDER_TOKEN')
        self.business_connection_id = business_connection_id or os.getenv('BUSINESS_CONNECTION_ID')
        self.gift_transfer_star_cost = int(os.getenv('GIFT_TRANSFER_STAR_COST', '25'))  # Default 25 stars
        self.user_interaction_hours = int(os.getenv('USER_INTERACTION_HOURS', '48'))  # Default 48 hours
        
        # Telethon configuration for checking message history
        self.api_id             = os.getenv('TELEGRAM_SENDER_API_ID')
        self.api_hash           = os.getenv('TELEGRAM_SENDER_API_HASH')
        self.phone_number       = os.getenv('TELEGRAM_SENDER_PHONE_NUMBER')
        self.telegram_client    = None
        
        # Build database URL from components (same as main project)
        # В Docker network используем hostname 'postgres'
        db_host = os.getenv('POSTGRES_HOST', 'postgres')
        db_port = os.getenv('POSTGRES_PORT', '5432')
        db_name = os.getenv('POSTGRES_DB', 'crash_stars_db')
        db_user = os.getenv('POSTGRES_USER', 'crash_stars_user')
        db_password = os.getenv('POSTGRES_PASSWORD', '')
        
        # Allow override with full DATABASE_URL
        self.db_url = os.getenv('DATABASE_URL') or f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        
        if not self.bot_token:
            raise ValueError("TG_BOT_SENDER_TOKEN environment variable is required")
        
        if not self.db_url:
            raise ValueError("Database configuration is required")
        
        # Initialize bot
        self.bot = Bot(token=self.bot_token)
        
        # Initialize database
        self.engine = create_async_engine(self.db_url)
        self.Session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        
        logger.info(f"✅ Gift sender service initialized")
        logger.info(f"🤖 Bot token: ...{self.bot_token[-10:]}")
        logger.info(f"⭐ Gift transfer cost: {self.gift_transfer_star_cost} stars")
        logger.info(f"🕐 User interaction check: {self.user_interaction_hours} hours")
        
        if self.api_id and self.api_hash:
            logger.info(f"📱 Telethon client will be used for message history checking")
            logger.info(f"📱 API ID: {self.api_id}, Phone: {self.phone_number}")
        else:
            logger.warning("⚠️ Telethon credentials not provided - message checking disabled")
            logger.warning(f"⚠️ API ID: {self.api_id}, API Hash: {'set' if self.api_hash else 'not set'}, Phone: {self.phone_number}")
        
        if self.business_connection_id:
            logger.info(f"🏢 Business connection: {self.business_connection_id}")
        else:
            logger.warning("⚠️ Business connection ID not provided - will need to get it from updates")
    
    def stars_to_usd(self, stars: Decimal) -> Decimal:
        """Convert stars to USD using the price from ton_price_service"""
        # Same conversion as ton_price_service.py: 1 star = $0.015
        return stars
    
    async def check_business_connections(self) -> Optional[str]:
        """Check for active business connections and return the first available connection ID"""
        try:
            logger.info("🔍 Проверяем активные бизнес-подключения...")
            
            # Note: There's no direct "list business connections" method in Bot API
            # Business connection ID is typically received via business_connection updates
            # For now, we'll prompt the user to provide it manually
            
            if not self.business_connection_id:
                print("\n" + "⚠️" * 50)
                print("❌ BUSINESS CONNECTION ID НЕ НАЙДЕН!")
                print("⚠️" * 50)
                print("\n📝 Чтобы получить Business Connection ID:")
                print("1. 📱 Откройте Telegram и зайдите в свой бизнес-аккаунт")
                print("2. ⚙️ Откройте настройки бизнес-аккаунта")
                print("3. 🤖 Подключите этого бота к своему бизнес-аккаунту")
                print("4. 📨 Когда бот получит business_connection update, он покажет connection ID")
                print("\n🔧 Альтернативно:")
                print("- Добавьте BUSINESS_CONNECTION_ID в .env файл")
                print("- Или передайте его как аргумент скрипта")
                
                manual_id = input("\n❓ Введите Business Connection ID вручную (или Enter для выхода): ").strip()
                
                if manual_id:
                    self.business_connection_id = manual_id
                    logger.info(f"✅ Business connection ID установлен: {manual_id}")
                    return manual_id
                else:
                    return None
            
            return self.business_connection_id
            
        except Exception as e:
            logger.error(f"❌ Error checking business connections: {e}")
            return None
    
    async def get_available_business_gifts(self) -> List[Dict[str, Any]]:
        """Get all gifts available on business account using pagination"""
        try:
            logger.info("📦 Получаем подарки с бизнес-аккаунта...")
            all_gifts = []
            offset = None
            
            while True:
                # Use aiogram's get_business_account_gifts method
                params = {
                    'business_connection_id': self.business_connection_id
                }
                if offset:
                    params['offset'] = offset
                
                result = await self.bot.get_business_account_gifts(**params)
                
                batch = result.gifts if result.gifts else []
                all_gifts.extend(batch)
                
                logger.info(f"📦 Получено {len(batch)} подарков в батче")
                
                # Check if there are more gifts
                if not hasattr(result, 'next_offset') or not result.next_offset:
                    break
                    
                offset = result.next_offset
            
            logger.info(f"📦 Всего получено подарков: {len(all_gifts)}")
            
            # Convert to dict format for easier processing
            gifts_data = []
            for owned_gift in all_gifts:
                # Check if it's OwnedGiftUnique (only these can be transferred)
                if hasattr(owned_gift, 'can_be_transferred') and owned_gift.can_be_transferred:
                    gift_data = {
                        'type': 'unique',
                        'can_be_transferred': True,
                        'business_gift_id': getattr(owned_gift, 'owned_gift_id', None),  # 🔧 CORRECT: Use owned_gift_id for transferGift
                        'gift_name': None
                    }
                    
                    # Get the Gift object from OwnedGiftUnique
                    if hasattr(owned_gift, 'gift') and owned_gift.gift:
                        gift_obj = owned_gift.gift
                        # Get name from Gift object
                        gift_data['gift_name'] = getattr(gift_obj, 'base_name', None)
                    
                    gifts_data.append(gift_data)
            
            return gifts_data
            
        except TelegramAPIError as e:
            logger.error(f"❌ Telegram API error getting business gifts: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error getting business gifts: {e}")
            return []
    
    async def init_telegram_client(self) -> bool:
        """Initialize Telethon client for message history checking"""
        try:
            if not self.api_id or not self.api_hash:
                logger.error("❌ TELEGRAM_SENDER_API_ID and TELEGRAM_SENDER_API_HASH are required for message history checking")
                return False
            
            # Create Telethon client with persistent session
            session_dir = 'telethon_sessions'
            os.makedirs(session_dir, exist_ok=True)
            session_path = os.path.join(session_dir, 'gift_sender_session')
            self.telegram_client = TelegramClient(session_path, self.api_id, self.api_hash)
            await self.telegram_client.start(phone=self.phone_number)
            
            if await self.telegram_client.is_user_authorized():
                logger.info("✅ Telethon client authorized successfully")
                return True
            else:
                logger.error("❌ Telethon client authorization failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to initialize Telethon client: {e}")
            return False
    
    async def check_user_recent_messages_telethon(self, user_id: int) -> tuple[bool, str]:
        """Check if user has sent messages to MY account (business connection owner) using Telethon"""
        try:
            if not self.telegram_client:
                if not await self.init_telegram_client():
                    return False, "Telethon client not available"
            
            # Calculate cutoff time
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.user_interaction_hours)
            
            logger.info(f"🔍 Checking if user {user_id} sent messages to MY account since {cutoff_time}")
            
            # Get user entity (recipient of the gift)
            user_entity = None
            try:
                user_entity = await self.telegram_client.get_entity(user_id)
                logger.info(f"📱 Found user: {user_entity.first_name} (@{user_entity.username or 'no_username'})")
            except Exception as e:
                logger.warning(f"⚠️ Could not find user {user_id} in session: {e}")
                logger.info(f"🔄 Trying to check dialogs directly without get_entity...")
                # Продолжаем проверку без entity - возможно пользователь есть в диалогах
            
            # Check if there's a chat with this user
            try:
                # Get dialogs (chats) to see if we have a chat with this user
                dialogs = await self.telegram_client.get_dialogs(limit=None)
                user_dialog = None
                
                for dialog in dialogs:
                    if dialog.entity.id == user_id:
                        user_dialog = dialog
                        break
                
                if not user_dialog:
                    logger.warning(f"⚠️ No chat found with user {user_id} - never messaged or blocked bot")
                    return False, "No chat exists - user never messaged or blocked bot"
                
                logger.info(f"💬 Found chat with user {user_id}")
                
                # Get messages from this user in our chat
                messages = []
                user_messages = []
                message_count = 0
                
                logger.info(f"🔍 Getting messages from chat with user {user_id}")
                # Use user_dialog.entity if user_entity is not available
                chat_entity = user_entity if user_entity else user_dialog.entity
                async for message in self.telegram_client.iter_messages(
                    chat_entity,
                    limit=50  # Check last 50 messages
                ):
                    message_count += 1
                    messages.append(message)
                    
                    # Debug: log message info
                    from_user = "me" if message.out else f"user_{message.from_id.user_id if message.from_id else 'unknown'}"
                    logger.info(f"📝 Message {message_count}: from={from_user}, out={message.out}, date={message.date}, text={message.text[:50] if message.text else 'no_text'}")
                    
                    # Only check messages FROM the user TO me (not my messages to them)
                    # In a private chat: message.out = False means message is FROM the other user TO me
                    if not message.out:  # This means the message is FROM the user TO me
                        user_messages.append(message)
                        logger.info(f"✅ Found message from user: {message.date}, text: {message.text[:50] if message.text else 'no_text'}")
                    
                    # Stop if message is too old
                    if message.date < cutoff_time:
                        logger.debug(f"🛑 Stopping - message too old: {message.date}")
                        break
                
                logger.info(f"📊 Found {message_count} total messages, {len(user_messages)} from user {user_id}")
                
                # Check if any message from user is recent
                recent_user_messages = [msg for msg in user_messages if msg.date >= cutoff_time]
                
                if recent_user_messages:
                    latest_msg = recent_user_messages[0]
                    hours_ago = (datetime.now(timezone.utc) - latest_msg.date).total_seconds() / 3600
                    logger.info(f"✅ User {user_id} sent message at {latest_msg.date} ({hours_ago:.1f}h ago)")
                    return True, f"Last message: {hours_ago:.1f}h ago"
                else:
                    if user_messages:
                        latest_msg = user_messages[0]
                        hours_ago = (datetime.now(timezone.utc) - latest_msg.date).total_seconds() / 3600
                        logger.warning(f"⚠️ User {user_id} last message at {latest_msg.date} ({hours_ago:.1f}h ago) - TOO OLD")
                        return False, f"Last message: {hours_ago:.1f}h ago (over {self.user_interaction_hours}h limit)"
                    else:
                        logger.warning(f"⚠️ User {user_id} has never sent messages to me")
                        return False, "No messages from user found"
                        
            except Exception as e:
                logger.error(f"❌ Error checking chat with user {user_id}: {e}")
                return False, f"Chat check failed: {str(e)}"
                    
        except Exception as e:
            logger.error(f"❌ Error checking user messages with Telethon: {e}")
            return False, f"Check failed: {str(e)}"
    
    async def check_user_recent_messages(self, user_id: int) -> bool:
        """Check if user has sent messages to bot in the last N hours via Telegram API"""
        try:
            # Calculate cutoff timestamp (48 hours ago by default)
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.user_interaction_hours)
            cutoff_timestamp = int(cutoff_time.timestamp())
            
            logger.info(f"🔍 Checking if user {user_id} sent messages after {cutoff_time}")
            
            # Get recent updates from Telegram
            # Note: getUpdates only shows recent messages, may need to use getChatHistory if available
            try:
                # Try to get chat history (this might not work for all bot types)
                # Alternative: check if we can get recent messages from the chat
                updates = await self.bot.get_updates(limit=100, timeout=1)
                
                for update in updates:
                    if (update.message and 
                        update.message.from_user and 
                        update.message.from_user.id == user_id and
                        update.message.date.timestamp() >= cutoff_timestamp):
                        
                        logger.info(f"✅ User {user_id} sent message at {update.message.date} (within {self.user_interaction_hours}h)")
                        return True
                
                logger.warning(f"⚠️ User {user_id} has NOT sent messages within {self.user_interaction_hours} hours")
                return False
                
            except Exception as api_error:
                logger.error(f"❌ Failed to check Telegram messages for user {user_id}: {api_error}")
                
                # Fallback: try to send a test message to see if chat exists and is recent
                try:
                    # Send a typing action to check if we can interact with user
                    await self.bot.send_chat_action(chat_id=user_id, action="typing")
                    logger.warning(f"⚠️ Could not verify message history, but chat is accessible for user {user_id}")
                    # If we can send typing, assume interaction is recent enough
                    return True
                except Exception as chat_error:
                    logger.error(f"❌ Cannot interact with user {user_id}: {chat_error}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error checking user messages for {user_id}: {e}")
            # По умолчанию запрещаем отправку если проверка не удалась
            logger.warning(f"⚠️ Blocking gift transfer due to message check failure for user {user_id}")
            return False
    
    def find_gift_by_collection_name(self, available_gifts: List[Dict], collection_name: str) -> Optional[Dict]:
        """Find a transferable unique gift by collection name (startsWith match)"""
        
        # Filter transferable unique gifts
        transferable_gifts = [
            g for g in available_gifts 
            if g.get('type') == 'unique' 
            and g.get('can_be_transferred', False)
            and g.get('gift_name')
            and g.get('business_gift_id')
        ]
        
        # Find gift that starts with collection name
        matching_gifts = [
            g for g in transferable_gifts
            if g['gift_name'].startswith(collection_name)
        ]
        
        if matching_gifts:
            # Return random gift from matching collection
            selected_gift = random.choice(matching_gifts)
            logger.info(f"🎯 Найден подарок для коллекции '{collection_name}': {selected_gift['gift_name']}")
            return selected_gift
        else:
            logger.warning(f"❌ Подарок коллекции '{collection_name}' не найден")
            logger.info(f"📜 Доступные подарки: {[g['gift_name'] for g in transferable_gifts]}")
            return None
    
    def group_gifts_by_collection(self, available_gifts: List[Dict]) -> Dict[str, List[Dict]]:
        """Group available gifts by their collection names"""
        collections = defaultdict(list)
        
        for gift in available_gifts:
            if (gift.get('type') == 'unique' 
                and gift.get('can_be_transferred', False)
                and gift.get('gift_name')
                and gift.get('business_gift_id')):
                
                # Extract collection name (assuming it's the first word or part before space)
                gift_name = gift['gift_name']
                # You might need to adjust this logic based on actual gift naming patterns
                collection_name = gift_name
                collections[collection_name].append(gift)
        
        return dict(collections)
    
    async def get_approved_payment_requests(self) -> List[Dict[str, Any]]:
        """Get all approved payment requests from database"""
        async with self.Session() as session:
            query = text("""
                SELECT 
                    pr.id,
                    pr.user_id,
                    u.telegram_id,
                    pr.gift_id,
                    pr.gift_name,
                    pr.price,
                    g.name as gift_collection_name,
                    u.username,
                    u.first_name,
                    u.last_name
                FROM payment_requests pr
                JOIN gifts g ON pr.gift_id = g.id
                JOIN users u ON pr.user_id = u.id
                WHERE pr.status = 'approved'
                ORDER BY pr.approved_at ASC
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            return [
                {
                    'request_id': row.id,
                    'user_id': row.user_id,
                    'telegram_id': row.telegram_id,
                    'gift_id': row.gift_id,
                    'gift_name': row.gift_name,
                    'gift_collection_name': row.gift_collection_name,  # 🔧 FIX: Add missing field
                    'price': row.price,
                    'business_gift_id': None,  # Will be assigned later
                    'username': row.username,
                    'first_name': row.first_name,
                    'last_name': row.last_name
                }
                for row in rows
            ]
    
    async def auto_assign_business_gift_ids(self, payment_requests: List[Dict], available_gifts: List[Dict]) -> List[Dict]:
        """Automatically assign business_gift_ids to payment requests by matching collection names"""
        logger.info("🔄 Начинаем автоматическое сопоставление подарков...")
        
        assigned_requests = []
        successful_assignments = 0
        failed_assignments = 0
        
        for request in payment_requests:
            collection_name = request['gift_name']
            
            # Find matching gift from available gifts
            matched_gift = self.find_gift_by_collection_name(available_gifts, collection_name)
            
            if matched_gift:
                request['business_gift_id'] = matched_gift['business_gift_id']
                request['matched_gift_name'] = matched_gift['gift_name']
                assigned_requests.append(request)
                successful_assignments += 1
                logger.info(f"✅ Запрос {request['request_id']}: '{collection_name}' → '{matched_gift['gift_name']}'")
            else:
                logger.error(f"❌ Запрос {request['request_id']}: коллекция '{collection_name}' не найдена")
                failed_assignments += 1
        
        logger.info(f"📊 Сопоставление завершено: {successful_assignments} успешно, {failed_assignments} неудачно")
        return assigned_requests
    
    async def close_telegram_client(self):
        """Close Telethon client"""
        if self.telegram_client:
            await self.telegram_client.disconnect()
            logger.info("📱 Telethon client disconnected")
    
    async def display_assignment_summary(self, assigned_requests: List[Dict], available_collections: Dict[str, List[Dict]]):
        """Display summary of gift assignments for manual confirmation"""
        print("\n" + "="*80)
        print("🎁 СВОДКА АВТОМАТИЧЕСКОГО СОПОСТАВЛЕНИЯ ПОДАРКОВ")
        print("="*80)
        
        logger.info("🔍 display_assignment_summary started")
        logger.info(f"🔍 Telethon credentials available: API_ID={bool(self.api_id)}, API_HASH={bool(self.api_hash)}")
        
        if not assigned_requests:
            print("❌ Нет запросов для обработки!")
            return False
        
        print(f"\n📋 Найдено {len(assigned_requests)} запросов для отправки:")
        
        # Check if Telethon is available for message checking
        if not self.api_id or not self.api_hash:
            print("⚠️ Telethon credentials not provided - SKIPPING message history check!")
            logger.warning("⚠️ Message history check skipped - no Telethon credentials")
            # Skip message checking and proceed with all requests
            valid_requests = assigned_requests
            blocked_requests = []
        else:
            print("🔍 Проверяем историю сообщений для каждого пользователя...\n")
            
            # 🔒 SECURITY: Check message history for each user before showing summary
            valid_requests = []
            blocked_requests = []
            
            for i, request in enumerate(assigned_requests, 1):
                user_name = request['first_name'] or request['username'] or f"ID{request['telegram_id']}"
                user_id = request['telegram_id']
                
                print(f"{i:2d}. 👤 {user_name} (ID: {user_id})")
                
                # Check message history
                try:
                    has_recent_messages, message_info = await self.check_user_recent_messages_telethon(user_id)
                except Exception as e:
                    logger.error(f"❌ Error checking messages for user {user_id}: {e}")
                    has_recent_messages = False
                    message_info = f"Check failed: {str(e)}"
                
                if has_recent_messages:
                    price_usd = self.stars_to_usd(Decimal(str(request['price'])))
                    print(f"    ✅ Сообщения: {message_info}")
                    print(f"    🎁 Коллекция: {request['gift_collection_name']}")
                    print(f"    🎯 Подарок: {request['matched_gift_name']}")
                    print(f"    💰 Цена: {request['price']} ⭐ (${price_usd:.2f})")
                    print(f"    🔑 Business ID: {request['business_gift_id']}")
                    valid_requests.append(request)
                else:
                    print(f"    ❌ Сообщения: {message_info}")
                    print(f"    🚫 ПОДАРОК НЕ БУДЕТ ОТПРАВЛЕН - нет недавних сообщений")
                    print(f"    📝 Отменяем заявку с причиной: no_message")
                    
                    # Cancel the payment request with reason
                    try:
                        await self.update_payment_request_status(request['request_id'], 'canceled', 'no_message')
                        print(f"    ✅ Заявка {request['request_id']} отменена в базе данных")
                    except Exception as e:
                        logger.error(f"❌ Failed to cancel request {request['request_id']}: {e}")
                        print(f"    ❌ Ошибка отмены заявки: {e}")
                    
                    blocked_requests.append(request)
                print()
        
        print(f"📊 Результат проверки:")
        print(f"   ✅ Разрешено к отправке: {len(valid_requests)}")
        print(f"   ❌ Заблокировано: {len(blocked_requests)}")
        
        if blocked_requests:
            print(f"\n🚫 Заблокированные запросы:")
            for req in blocked_requests:
                user_name = req['first_name'] or req['username'] or f"ID{req['telegram_id']}"
                print(f"   - {user_name} (ID: {req['telegram_id']})")
        
        if not valid_requests:
            print("\n❌ Нет запросов для отправки после проверки сообщений!")
            return False
        
        # Count available gifts by collection name
        available_gift_counts = defaultdict(int)
        for collection_name, gifts in available_collections.items():
            available_gift_counts[collection_name] = len(gifts)
        
        # Filter valid requests to only include those that have available gifts
        # Group requests by collection and apply gift count limits
        collection_requests = defaultdict(list)
        for request in valid_requests:
            collection_name = request['gift_collection_name']
            collection_requests[collection_name].append(request)
        
        final_valid_requests = []
        exceeded_requests = []
        
        for collection_name, requests in collection_requests.items():
            available_count = available_gift_counts.get(collection_name, 0)
            
            if len(requests) <= available_count:
                # All requests can be fulfilled
                final_valid_requests.extend(requests)
            else:
                # Take only the first N requests (oldest first)
                final_valid_requests.extend(requests[:available_count])
                exceeded_requests.extend(requests[available_count:])
        
        # Update assigned_requests to only include final valid ones
        assigned_requests.clear()
        assigned_requests.extend(final_valid_requests)
        
        print("\n📦 Доступные коллекции на аккаунте:")
        for collection_name, gifts in available_collections.items():
            print(f"   {collection_name}: {len(gifts)} подарков")
        
        if exceeded_requests:
            print(f"\n⚠️ ПРЕВЫШЕН ЛИМИТ ПОДАРКОВ:")
            collection_exceeded = defaultdict(list)
            for req in exceeded_requests:
                collection_exceeded[req['gift_collection_name']].append(req)
            
            for collection_name, requests in collection_exceeded.items():
                available_count = available_gift_counts.get(collection_name, 0)
                print(f"   {collection_name}: {len(requests)} лишних заявок (доступно: {available_count})")
                for req in requests:
                    user_name = req['first_name'] or req['username'] or f"ID{req['telegram_id']}"
                    print(f"      - {user_name} (заявка {req['request_id']})")
            
            print(f"\n📊 Итоговый результат:")
            print(f"   ✅ Будут отправлены: {len(final_valid_requests)}")
            print(f"   ⏭️ Остаются pending: {len(exceeded_requests)}")
        
        # Calculate total costs in USD for final summary
        if final_valid_requests:
            total_final_cost_stars = sum(Decimal(str(req['price'])) for req in final_valid_requests)
            total_final_cost_usd = self.stars_to_usd(total_final_cost_stars)
            
            print(f"\n💰 ИТОГОВЫЕ РАСХОДЫ:")
            print(f"   ⭐ Звёзды: {total_final_cost_stars} ⭐")
            print(f"   💵 USD: ${total_final_cost_usd:.2f}")
            
            if blocked_requests:
                blocked_cost_stars = sum(Decimal(str(req['price'])) for req in blocked_requests)
                blocked_cost_usd = self.stars_to_usd(blocked_cost_stars)
                print(f"   💡 Экономия от фильтрации: {blocked_cost_stars} ⭐ (${blocked_cost_usd:.2f})")
        
        print("\n" + "="*80)
        print(f"⚠️  ВНИМАНИЕ: После подтверждения {len(final_valid_requests)} подарков будут отправлены НЕМЕДЛЕННО!")
        print("="*80)
        
        while True:
            confirmation = input("\n❓ Продолжить отправку? (yes/no): ").lower().strip()
            if confirmation in ['yes']:
                return True
            elif confirmation in ['no']:
                return False
            else:
                print("❌ Пожалуйста, введите 'yes' или 'no'")
    
    async def send_gift_to_user(self, user_id: int, business_gift_id: str) -> Dict[str, Any]:
        """Send gift to user via aiogram"""
        try:
            logger.info(f"🎁 Отправляем подарок {business_gift_id} пользователю {user_id}")
            
            
            # 🔧 CORRECT FIX: Use transferGift for business gifts with owned_gift_id
            result = await self.bot.transfer_gift(
                business_connection_id=self.business_connection_id,
                owned_gift_id=business_gift_id,
                new_owner_chat_id=user_id,
                star_count=self.gift_transfer_star_cost  # Cost from env variable
            )
            #result = False
            
            logger.info(f"✅ Подарок успешно отправлен пользователю {user_id}")
            return {
                'success': True,
                'result': result
            }
            
        except TelegramAPIError as e:
            logger.error(f"❌ Telegram API error sending gift to {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'error_code': getattr(e, 'error_code', None)
            }
        except Exception as e:
            logger.error(f"❌ Unexpected error sending gift to {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def update_payment_request_status(self, request_id: int, status: str, cancel_reason: str = None):
        """Update payment request status in database"""
        async with self.Session() as session:
            if status == 'approved':
                query = text("""
                    UPDATE payment_requests 
                    SET status = :status, approved_at = NOW()
                    WHERE id = :request_id
                """)
                params = {'status': status, 'request_id': request_id}
            elif status == 'completed':
                query = text("""
                    UPDATE payment_requests 
                    SET status = :status, completed_at = NOW()
                    WHERE id = :request_id
                """)
                params = {'status': status, 'request_id': request_id}
            elif status == 'canceled' and cancel_reason:
                query = text("""
                    UPDATE payment_requests 
                    SET status = :status, cancel_reason = :cancel_reason
                    WHERE id = :request_id
                """)
                params = {'status': status, 'cancel_reason': cancel_reason, 'request_id': request_id}
            else:
                query = text("""
                    UPDATE payment_requests 
                    SET status = :status
                    WHERE id = :request_id
                """)
                params = {'status': status, 'request_id': request_id}
            
            await session.execute(query, params)
            await session.commit()
            
            if cancel_reason:
                logger.info(f"✅ Updated payment request {request_id} status to {status} with reason: {cancel_reason}")
            else:
                logger.info(f"✅ Updated payment request {request_id} status to {status}")
    
    async def close(self):
        """Close bot and database connections"""
        await self.bot.session.close()
        await self.engine.dispose()
        logger.info("🔒 Gift sender service closed")
    
    async def process_approved_requests(self) -> Dict[str, int]:
        """Process all approved payment requests with automatic gift assignment"""
        logger.info("🔄 Начинаем обработку одобренных запросов...")
        
        # Step 0: Ensure we have business connection ID
        logger.info("🔍 Шаг 0: Проверяем business connection...")
        connection_id = await self.check_business_connections()
        
        if not connection_id:
            logger.error("❌ Не удалось получить Business Connection ID!")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        # Step 1: Get available gifts from business account
        logger.info("📦 Шаг 1: Получаем подарки с бизнес-аккаунта...")
        available_gifts = await self.get_available_business_gifts()
        
        if not available_gifts:
            logger.error("❌ Не удалось получить подарки с бизнес-аккаунта!")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        # Group gifts by collections for display
        available_collections = self.group_gifts_by_collection(available_gifts)
        logger.info(f"📦 Найдено {len(available_collections)} коллекций с {len(available_gifts)} подарками")
        
        # Step 2: Get approved payment requests
        logger.info("📋 Шаг 2: Получаем одобренные запросы...")
        approved_requests = await self.get_approved_payment_requests()
        
        if not approved_requests:
            logger.info("ℹ️ Нет одобренных запросов для обработки")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        logger.info(f"📋 Найдено {len(approved_requests)} одобренных запросов")
        
        # Step 3: Auto-assign business gift IDs
        logger.info("🔄 Шаг 3: Автоматическое сопоставление подарков...")
        assigned_requests = await self.auto_assign_business_gift_ids(approved_requests, available_gifts)
        
        if not assigned_requests:
            logger.error("❌ Не удалось сопоставить ни одного подарка!")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        # Step 4: Display summary and get confirmation
        logger.info("📋 Шаг 4: Показываем сводку и запрашиваем подтверждение...")
        confirmed = await self.display_assignment_summary(assigned_requests, available_collections)
        
        if not confirmed:
            logger.info("⏹️ Отправка отменена пользователем")
            return {'processed': 0, 'successful': 0, 'failed': 0}
        
        # Step 5: Send gifts
        logger.info("🚀 Шаг 5: Отправляем подарки...")
        processed = 0
        successful = 0
        failed = 0
        
        for request in assigned_requests:
            try:
                user_name = request['first_name'] or request['username'] or f"ID{request['telegram_id']}"
                logger.info(f"🔄 Обрабатываем запрос {request['request_id']} для {user_name}")
                logger.info(f"🎁 Подарок: {request['matched_gift_name']} (ID: {request['business_gift_id']})")
                
                # Send gift
                result = await self.send_gift_to_user(
                    user_id=request['telegram_id'],
                    business_gift_id=request['business_gift_id']
                )
                
                processed += 1
                
                if result['success']:
                    # Mark as completed
                    await self.update_payment_request_status(request['request_id'], 'completed')
                    successful += 1
                    logger.info(f"✅ Подарок успешно отправлен пользователю {user_name}")
                else:
                    # Mark as failed and record error
                    #await self.update_payment_request_status(request['request_id'], 'canceled')
                    failed += 1
                    logger.error(f"❌ Не удалось отправить подарок пользователю {user_name}: {result.get('error')}")
                
                # Small delay between requests to avoid rate limiting
                await asyncio.sleep(1.0)
                
            except Exception as e:
                logger.error(f"❌ Неожиданная ошибка при обработке запроса {request['request_id']}: {e}")
                #await self.update_payment_request_status(request['request_id'], 'canceled')
                processed += 1
                failed += 1
        
        logger.info(f"📊 Обработка завершена: {processed} обработано, {successful} успешно, {failed} неудачно")
        
        return {
            'processed': processed,
            'successful': successful,
            'failed': failed
        }
    
    async def get_all_pending_requests(self) -> List[Dict[str, Any]]:
        """Get all pending payment requests from database"""
        async with self.Session() as session:
            query = text("""
                SELECT 
                    pr.id,
                    pr.user_id,
                    u.telegram_id,
                    pr.gift_id,
                    pr.gift_name,
                    pr.price,
                    g.name as gift_collection_name,
                    u.username,
                    u.first_name,
                    u.last_name,
                    pr.created_at,
                    pr.status
                FROM payment_requests pr
                JOIN gifts g ON pr.gift_id = g.id
                JOIN users u ON pr.user_id = u.id
                WHERE pr.status = 'pending'
                ORDER BY pr.created_at ASC
            """)
            
            result = await session.execute(query)
            rows = result.fetchall()
            
            return [
                {
                    'request_id': row.id,
                    'user_id': row.user_id,
                    'telegram_id': row.telegram_id,
                    'gift_id': row.gift_id,
                    'gift_name': row.gift_name,
                    'gift_collection_name': row.gift_collection_name,
                    'price': row.price,
                    'username': row.username,
                    'first_name': row.first_name,
                    'last_name': row.last_name,
                    'created_at': row.created_at,
                    'status': row.status
                }
                for row in rows
            ]
    
    async def display_all_pending_requests(self):
        """Display all pending payment requests"""
        pending_requests = await self.get_all_pending_requests()
        
        print("\n" + "="*80)
        print("📋 ВСЕ PENDING ЗАЯВКИ")
        print("="*80)
        
        if not pending_requests:
            print("❌ Нет pending заявок!")
            return
        
        print(f"\n📋 Найдено {len(pending_requests)} pending заявок:\n")
        
        for i, request in enumerate(pending_requests, 1):
            user_name = request['first_name'] or request['username'] or f"ID{request['telegram_id']}"
            print(f"{i:2d}. 👤 {user_name} (ID: {request['telegram_id']})")
            print(f"    🎁 Коллекция: {request['gift_collection_name']}")
            print(f"    💰 Цена: {request['price']} ⭐")
            print(f"    📅 Создана: {request['created_at']}")
            print(f"    🆔 Request ID: {request['request_id']}")
            print()
    
    async def display_pending_summary_by_gift_type(self):
        """Display summary of pending requests grouped by gift type"""
        pending_requests = await self.get_all_pending_requests()
        
        print("\n" + "="*80)
        print("📊 СВОДКА PENDING ЗАЯВОК ПО ТИПАМ ПОДАРКОВ")
        print("="*80)
        
        if not pending_requests:
            print("❌ Нет pending заявок!")
            return
        
        # Check if Telethon is available for message checking
        if not self.api_id or not self.api_hash:
            print("⚠️ Telethon credentials not provided - показываем все заявки без проверки сообщений!")
            valid_requests = pending_requests
            invalid_requests = []
        else:
            print("🔍 Фильтруем заявки по истории сообщений...")
            
            # Filter requests by message history
            valid_requests = []
            invalid_requests = []
            
            for request in pending_requests:
                user_id = request['telegram_id']
                
                # Check message history
                try:
                    has_recent_messages, message_info = await self.check_user_recent_messages_telethon(user_id)
                except Exception as e:
                    logger.error(f"❌ Error checking messages for user {user_id}: {e}")
                    has_recent_messages = False
                
                if has_recent_messages:
                    valid_requests.append(request)
                else:
                    invalid_requests.append(request)
        
        # Group valid requests by gift collection name
        gift_summary = defaultdict(list)
        for request in valid_requests:
            gift_name = request['gift_collection_name']
            gift_summary[gift_name].append(request)
        
        print(f"\n📊 Результат фильтрации:")
        print(f"   ✅ Показаны: {len(valid_requests)} заявок")
        print(f"   ❌ Скрыты (no_message): {len(invalid_requests)} заявок")
        
        if valid_requests:
            print(f"\n📊 Заявки в {len(gift_summary)} коллекциях:\n")
            
            total_cost = 0
            for gift_name, requests in gift_summary.items():
                count = len(requests)
                total_price = sum(Decimal(str(req['price'])) for req in requests)
                total_cost += total_price
                total_price_usd = self.stars_to_usd(total_price)
                
                print(f"🎁 {gift_name}:")
                print(f"   📦 Количество: {count} заявок")
                print(f"   💰 Общая стоимость: {total_price} ⭐ (${total_price_usd:.2f})")
                users_list = ', '.join(req['first_name'] or req['username'] or f"ID{req['telegram_id']}" for req in requests)
                print(f"   👥 Пользователи: {users_list}")
                print()
            
            total_cost_usd = self.stars_to_usd(total_cost)
            print(f"💰 ИТОГО (валидные): {len(valid_requests)} заявок на сумму {total_cost} ⭐ (${total_cost_usd:.2f})")
        
        # Show invalid requests summary
        if invalid_requests:
            print(f"\n🚫 СКРЫТЫЕ ЗАЯВКИ (нет сообщений за {self.user_interaction_hours}ч):")
            invalid_gift_summary = defaultdict(list)
            for request in invalid_requests:
                gift_name = request['gift_collection_name']
                invalid_gift_summary[gift_name].append(request)
            
            invalid_total_cost = 0
            for gift_name, requests in invalid_gift_summary.items():
                count = len(requests)
                total_price = sum(Decimal(str(req['price'])) for req in requests)
                invalid_total_cost += total_price
                total_price_usd = self.stars_to_usd(total_price)
                
                print(f"   🎁 {gift_name}: {count} заявок ({total_price} ⭐ / ${total_price_usd:.2f})")
                users_list = ', '.join(req['first_name'] or req['username'] or f"ID{req['telegram_id']}" for req in requests[:3])
                if len(requests) > 3:
                    users_list += f" и еще {len(requests) - 3}"
                print(f"      👥 {users_list}")
            
            invalid_total_cost_usd = self.stars_to_usd(invalid_total_cost)
            print(f"\n💰 ИТОГО (скрытые): {len(invalid_requests)} заявок на сумму {invalid_total_cost} ⭐ (${invalid_total_cost_usd:.2f})")
            
            # Ask if user wants to cancel invalid requests
            print("\n" + "="*80)
            print("❓ ОТМЕНА ЗАЯВОК БЕЗ СООБЩЕНИЙ")
            print("="*80)
            print(f"Найдено {len(invalid_requests)} заявок от пользователей, которые не писали сообщения за {self.user_interaction_hours} часов.")
            
            while True:
                confirmation = input("\n❓ Отменить эти заявки (статус canceled, причина no_message)? (yes/no): ").lower().strip()
                if confirmation in ['yes']:
                    # Cancel invalid requests
                    canceled_count = 0
                    for request in invalid_requests:
                        try:
                            await self.update_payment_request_status(request['request_id'], 'canceled', 'no_message')
                            canceled_count += 1
                        except Exception as e:
                            logger.error(f"❌ Failed to cancel request {request['request_id']}: {e}")
                    
                    print(f"✅ Отменено {canceled_count} заявок из {len(invalid_requests)}")
                    break
                elif confirmation in ['no']:
                    print("⏭️ Заявки оставлены без изменений")
                    break
                else:
                    print("❌ Пожалуйста, введите 'yes' или 'no'")
        
        # Show final summary with total USD amounts
        if valid_requests or invalid_requests:
            print("\n" + "="*80)
            print("💰 ОБЩАЯ СВОДКА ПО ТРАТАМ USD")
            print("="*80)
            
            if valid_requests:
                valid_total_usd = self.stars_to_usd(total_cost)
                print(f"✅ Валидные заявки: {len(valid_requests)} шт. на сумму ${valid_total_usd:.2f}")
            
            if invalid_requests:
                invalid_total_usd = self.stars_to_usd(invalid_total_cost)
                print(f"❌ Скрытые заявки: {len(invalid_requests)} шт. на сумму ${invalid_total_usd:.2f}")
            
            if valid_requests and invalid_requests:
                grand_total_stars = total_cost + invalid_total_cost
                grand_total_usd = self.stars_to_usd(grand_total_stars)
                print(f"🔢 ВСЕГО: {len(valid_requests) + len(invalid_requests)} заявок на сумму ${grand_total_usd:.2f}")
                print(f"💡 Потенциальная экономия от фильтрации: ${invalid_total_usd:.2f}")
            
            print("="*80)
    
    async def auto_approve_pending_requests(self) -> Dict[str, int]:
        """Auto-approve pending requests that have matching gifts available"""
        logger.info("🔄 Начинаем auto-approve pending заявок...")
        
        # Get available gifts
        connection_id = await self.check_business_connections()
        if not connection_id:
            print("❌ Не удалось получить Business Connection ID!")
            return {'approved': 0, 'total': 0}
        
        available_gifts = await self.get_available_business_gifts()
        if not available_gifts:
            print("❌ Не удалось получить подарки с бизнес-аккаунта!")
            return {'approved': 0, 'total': 0}
        
        # Get pending requests
        pending_requests = await self.get_all_pending_requests()
        if not pending_requests:
            print("❌ Нет pending заявок!")
            return {'approved': 0, 'total': 0}
        
        print("\n" + "="*80)
        print("🤖 AUTO-APPROVE PENDING ЗАЯВОК")
        print("="*80)
        
        print(f"\n📋 Найдено {len(pending_requests)} pending заявок")
        print(f"📦 Доступно {len(available_gifts)} подарков")
        
        # Group available gifts by collection name and count them
        available_gift_counts = defaultdict(int)
        for gift in available_gifts:
            if (gift.get('type') == 'unique' 
                and gift.get('can_be_transferred', False)
                and gift.get('gift_name')
                and gift.get('business_gift_id')):
                available_gift_counts[gift['gift_name']] += 1
        
        logger.info(f"📊 Доступные подарки по коллекциям: {dict(available_gift_counts)}")
        
        approved_count = 0
        skipped_count = 0
        canceled_count = 0
        total_count = len(pending_requests)
        
        # Check if Telethon is available for message checking
        if not self.api_id or not self.api_hash:
            print("⚠️ Telethon credentials not provided - SKIPPING message history check!")
            logger.warning("⚠️ Message history check skipped - no Telethon credentials")
            # Skip message checking and proceed with all requests
            valid_requests = pending_requests
        else:
            print("🔍 Проверяем историю сообщений для каждого пользователя...\n")
            
            # Filter requests by message history first
            valid_requests = []
            for request in pending_requests:
                user_name = request['first_name'] or request['username'] or f"ID{request['telegram_id']}"
                user_id = request['telegram_id']
                
                # Check message history
                try:
                    has_recent_messages, message_info = await self.check_user_recent_messages_telethon(user_id)
                except Exception as e:
                    logger.error(f"❌ Error checking messages for user {user_id}: {e}")
                    has_recent_messages = False
                    message_info = f"Check failed: {str(e)}"
                
                if has_recent_messages:
                    valid_requests.append(request)
                else:
                    print(f"❌ Отклоняем заявку {request['request_id']}: {user_name} - {message_info}")
                    try:
                        await self.update_payment_request_status(request['request_id'], 'canceled', 'no_message')
                        canceled_count += 1
                        logger.info(f"✅ Canceled request {request['request_id']} due to no recent messages")
                    except Exception as e:
                        logger.error(f"❌ Failed to cancel request {request['request_id']}: {e}")
            
            print(f"\n📊 Фильтрация по сообщениям:")
            print(f"   ✅ Прошли проверку: {len(valid_requests)}")
            print(f"   ❌ Отклонены (no_message): {canceled_count}")
        
        # Process valid requests in order (oldest first)
        for request in valid_requests:
            collection_name = request['gift_collection_name']
            user_name = request['first_name'] or request['username'] or f"ID{request['telegram_id']}"
            
            # Check if we have available gifts for this collection
            available_count = 0
            for gift_name, count in available_gift_counts.items():
                if gift_name.startswith(collection_name) and count > 0:
                    available_count = count
                    break
            
            if available_count > 0:
                # We have a gift available - approve the request
                try:
                    await self.update_payment_request_status(request['request_id'], 'approved')
                    approved_count += 1
                    print(f"✅ Одобрена заявка {request['request_id']}: {user_name} → {collection_name}")
                    
                    # Reduce available count for this collection
                    for gift_name in available_gift_counts:
                        if gift_name.startswith(collection_name) and available_gift_counts[gift_name] > 0:
                            available_gift_counts[gift_name] -= 1
                            logger.info(f"📉 Осталось {gift_name}: {available_gift_counts[gift_name]}")
                            break
                            
                except Exception as e:
                    logger.error(f"❌ Failed to approve request {request['request_id']}: {e}")
                    print(f"❌ Ошибка одобрения заявки {request['request_id']}: {e}")
            else:
                skipped_count += 1
                print(f"⏭️ Пропущена заявка {request['request_id']}: {user_name} → {collection_name} (нет подарка)")
        
        print(f"\n📊 Результат auto-approve:")
        print(f"   ✅ Одобрено: {approved_count}")
        print(f"   ⏭️ Пропущено: {skipped_count}")
        print(f"   ❌ Отклонено (no_message): {canceled_count}")
        print(f"   📋 Всего: {total_count}")
        
        return {'approved': approved_count, 'skipped': skipped_count, 'canceled': canceled_count, 'total': total_count}
    
    async def show_interactive_menu(self) -> str:
        """Show interactive menu and return user choice"""
        print("\n" + "="*80)
        print("🎁 GIFT SENDER - ИНТЕРАКТИВНОЕ МЕНЮ")
        print("="*80)
        
        print("\n📋 Выберите действие:")
        print("1️⃣ Отправить подарки - обработать approved заявки")
        print("2️⃣ Вывести все pending заявки")
        print("3️⃣ Вывести сводку по pending заявкам по типам подарков")
        print("4️⃣ Auto-approve pending заявок (если есть подходящие подарки)")
        print("0️⃣ Выход")
        
        while True:
            choice = input("\n❓ Ваш выбор (1-4, 0 для выхода): ").strip()
            if choice in ['1', '2', '3', '4', '0']:
                return choice
            else:
                print("❌ Пожалуйста, введите число от 0 до 4")
    
    async def close(self):
        """Close bot and database connections"""
        await self.bot.session.close()
        await self.engine.dispose()
        logger.info("🔒 Gift sender service closed")


async def main():
    """Main function with interactive menu"""
    print("🚀 Запуск автоматического отправщика подарков")
    print("=" * 60)
    logger.info("🚀 Starting Advanced Gift Sender Script")
    
    try:
        # Initialize service
        service = GiftSenderService()
        
        while True:
            # Show interactive menu
            choice = await service.show_interactive_menu()
            
            if choice == '0':
                print("👋 До свидания!")
                break
            
            elif choice == '1':
                # Process approved requests with automatic assignment
                stats = await service.process_approved_requests()
                
                # Log statistics
                print("\n" + "=" * 60)
                print("📊 ИТОГОВАЯ СТАТИСТИКА:")
                print(f"   Обработано: {stats['processed']}")
                print(f"   Успешно: {stats['successful']}")
                print(f"   Неудачно: {stats['failed']}")
                print("=" * 60)
                
                logger.info("=" * 50)
                logger.info("📊 FINAL STATISTICS:")
                logger.info(f"   Processed: {stats['processed']}")
                logger.info(f"   Successful: {stats['successful']}")
                logger.info(f"   Failed: {stats['failed']}")
                logger.info("=" * 50)
            
            elif choice == '2':
                # Display all pending requests
                await service.display_all_pending_requests()
            
            elif choice == '3':
                # Display pending summary by gift type
                await service.display_pending_summary_by_gift_type()
            
            elif choice == '4':
                # Auto-approve pending requests
                stats = await service.auto_approve_pending_requests()
                print(f"\n✅ Auto-approve завершен:")
                print(f"   ✅ Одобрено: {stats['approved']}")
                print(f"   ⏭️ Пропущено: {stats['skipped']}")
                print(f"   ❌ Отклонено: {stats['canceled']}")
                print(f"   📋 Всего: {stats['total']}")
            
            # Wait for user input before showing menu again
            input("\n⏸️ Нажмите Enter для возврата в меню...")
        
        # Close service and Telethon client
        await service.close_telegram_client()
        await service.close()
        
        logger.info("✅ Gift sender script completed successfully")
        print("✅ Скрипт отправки подарков завершен успешно")
        
    except KeyboardInterrupt:
        logger.info("⏹️ Script interrupted by user")
        print("\n⏹️ Скрипт прерван пользователем")
    except Exception as e:
        logger.error(f"❌ Fatal error in gift sender script: {e}")
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())