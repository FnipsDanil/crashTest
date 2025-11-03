from fastapi import FastAPI
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.functions.payments import GetPaymentFormRequest, SendStarsFormRequest, GetSavedStarGiftsRequest
from telethon.tl.types import InputInvoiceStarGiftTransfer, InputSavedStarGiftSlug
from contextlib import asynccontextmanager
import logging
import asyncio
from typing import Optional
import psycopg2
from datetime import datetime

# Загружаем переменные окружения
load_dotenv()

logger = logging.getLogger("uvicorn")

# Telethon client - единая сессия для всех функций
API_ID = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION_PATH = os.getenv("SESSION_PATH", "easygifter_session")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "db"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "dbname": os.getenv("DB_NAME")
}

class GiftTransferRequest(BaseModel):
    gift_name_prefix: str  # например "SnoopDogg" - префикс для поиска
    recipient_id: int  # chat_id или username
    star_count: int = 25

# Кэш для подарков
gifts_cache = []
gifts_cache_time = 0

async def get_saved_gifts(force_refresh: bool = False):
    """Получает список сохраненных подарков из Telegram"""
    global gifts_cache, gifts_cache_time

    # Кэш на 5 минут
    import time
    if not force_refresh and gifts_cache and (time.time() - gifts_cache_time) < 300:
        logger.info(f"📦 Using cached gifts ({len(gifts_cache)} items)")
        return gifts_cache

    try:
        logger.info("🔍 Fetching saved gifts from Telegram...")

        # Получаем InputPeer собственного профиля
        me = await client.get_me()
        my_peer = await client.get_input_entity(me)

        all_gifts = []
        offset = ""

        while True:
            result = await client(GetSavedStarGiftsRequest(
                peer=my_peer,
                offset=offset,
                limit=100
            ))

            if hasattr(result, 'gifts'):
                all_gifts.extend(result.gifts)
                logger.info(f"📦 Fetched {len(result.gifts)} gifts (total: {len(all_gifts)})")

            # Проверяем есть ли еще подарки
            if not hasattr(result, 'next_offset') or not result.next_offset:
                break
            offset = result.next_offset

        gifts_cache = all_gifts
        gifts_cache_time = time.time()

        logger.info(f"✅ Total saved gifts: {len(all_gifts)}")
        return all_gifts
    except Exception as e:
        logger.error(f"❌ Error fetching gifts: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []

async def find_gift_by_prefix(prefix: str, force_refresh: bool = False) -> Optional[str]:
    """
    Находит подарок по префиксу имени и возвращает его slug.
    Например: prefix="SnoopDogg" -> slug="snoopdogg-437873"
    """
    try:
        gifts = await get_saved_gifts(force_refresh=force_refresh)

        # Нормализуем префикс
        prefix_lower = prefix.lower().replace(" ", "")

        logger.info(f"🔎 Searching for gift with prefix: {prefix} (normalized: {prefix_lower})")
        logger.info(f"📊 Total gifts in inventory: {len(gifts)}")

        for gift in gifts:
            # Проверяем атрибуты подарка
            gift_slug = None

            if hasattr(gift, 'slug'):
                gift_slug = gift.slug
            elif hasattr(gift, 'gift') and hasattr(gift.gift, 'slug'):
                gift_slug = gift.gift.slug

            if gift_slug:
                # Логируем все найденные slugs для отладки
                logger.info(f"📦 Found gift slug: {gift_slug}")

                # Проверяем совпадение по префиксу
                if gift_slug.lower().startswith(prefix_lower):
                    logger.info(f"✅ Found matching gift: {gift_slug}")

                    # Проверяем дополнительные атрибуты подарка
                    can_transfer = getattr(gift, 'can_be_transferred', True)
                    if not can_transfer:
                        logger.warning(f"⚠️ Gift {gift_slug} cannot be transferred, skipping...")
                        continue

                    return gift_slug

        # Выводим все доступные slugs для отладки
        all_slugs = []
        for gift in gifts:
            gift_slug = None
            if hasattr(gift, 'slug'):
                gift_slug = gift.slug
            elif hasattr(gift, 'gift') and hasattr(gift.gift, 'slug'):
                gift_slug = gift.gift.slug
            if gift_slug:
                all_slugs.append(gift_slug)

        logger.warning(f"❌ No gift found with prefix: {prefix}")
        logger.info(f"📜 Available gift slugs: {', '.join(all_slugs[:50])}")  # Первые 50 для не загромождения логов
        return None

    except Exception as e:
        logger.error(f"❌ Error finding gift: {e}")
        return None

async def transfer_gift_by_slug(slug: str, recipient_id: int, max_retries: int = 5):
    """
    Перевод уникального подарка по slug на целевой InputPeer.
    Автоматически повторяет попытку при ошибке STARGIFT_OWNER_INVALID.
    """
    retry_count = 0
    base_delay = 2  # секунды

    while retry_count <= max_retries:
        try:
            # Получаем сущность пользователя (это загрузит информацию в кэш)
            logger.info(f"🔍 Getting entity for recipient: {recipient_id}")
            entity = await client.get_entity(recipient_id)

            # Теперь получаем InputPeer
            to_input_peer = await client.get_input_entity(entity)

            # Создаем invoice для transfer подарка
            invoice = InputInvoiceStarGiftTransfer(
                stargift=InputSavedStarGiftSlug(slug=slug),
                to_id=to_input_peer
            )

            # Получаем форму оплаты
            if retry_count > 0:
                logger.info(f"📋 Getting payment form for slug: {slug} (retry {retry_count}/{max_retries})")
            else:
                logger.info(f"📋 Getting payment form for slug: {slug}")

            form = await client(GetPaymentFormRequest(invoice=invoice))

            # Отправляем подарок
            logger.info(f"🎁 Sending gift {slug} to {recipient_id}")
            result = await client(SendStarsFormRequest(form_id=form.form_id, invoice=invoice))

            logger.info(f"✅ Gift {slug} successfully sent to {recipient_id}")
            return result

        except Exception as e:
            error_str = str(e)

            # Проверяем на ошибку STARGIFT_OWNER_INVALID
            if "STARGIFT_OWNER_INVALID" in error_str and retry_count < max_retries:
                retry_count += 1
                delay = base_delay * (2 ** (retry_count - 1))  # Экспоненциальная задержка
                logger.warning(f"⚠️ STARGIFT_OWNER_INVALID error, retrying in {delay}s (attempt {retry_count}/{max_retries})")
                await asyncio.sleep(delay)
                continue

            # Если это другая ошибка или исчерпаны попытки
            logger.error(f"❌ Error transferring gift: {e}")
            raise

async def cache_dialogs():
    """Кэширование диалогов для избежания спам-блока"""
    try:
        logger.info("📚 Загрузка диалогов для кэширования...")
        dialogs = await client.get_dialogs()
        logger.info(f"✅ Закэшировано {len(dialogs)} диалогов")
    except Exception as e:
        logger.error(f"❌ Ошибка при кэшировании диалогов: {e}")

# Обработчик входящих сообщений для userbot функционала
@client.on(events.NewMessage(incoming=True))
async def handle_incoming_message(event):
    """Обрабатывает входящие сообщения и добавляет отправителей в verified_senders"""
    sender = await event.get_sender()
    chat_id = sender.id
    username = sender.username or "unknown"
    logger.info(f"📥 Сообщение от @{username} ({chat_id})")

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        # Get sender info
        first_name = getattr(sender, 'first_name', None) or ''
        last_name = getattr(sender, 'last_name', None) or ''

        cur.execute("""
            INSERT INTO verified_senders (
                chat_id, username, first_name, last_name,
                verified_at, last_message_at, message_count, is_blocked
            )
            VALUES (%s, %s, %s, %s, %s, %s, 1, FALSE)
            ON CONFLICT (chat_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                last_message_at = EXCLUDED.last_message_at,
                message_count = verified_senders.message_count + 1;
        """, (chat_id, username, first_name, last_name, datetime.utcnow(), datetime.utcnow()))
        conn.commit()
        cur.close()
        conn.close()
        logger.info(f"✅ @{username} добавлен/обновлён в verified_senders")
    except Exception as e:
        logger.error(f"❌ Ошибка БД: {e}")

@asynccontextmanager
async def lifespan(application: FastAPI):
    try:
        logger.info("🚀 Starting Telethon client...")
        await client.start()
        logger.info("✅ Telethon client started")

        # Кэшируем диалоги при старте
        await cache_dialogs()

        # Запускаем обработку сообщений в фоне
        logger.info("👂 Listening for incoming messages...")

        yield
    finally:
        logger.info("🔌 Disconnecting Telethon client...")
        await client.disconnect()
        logger.info("✅ Telethon client disconnected")

app = FastAPI(lifespan=lifespan)

@app.post("/transfer-gift")
async def transfer_gift_endpoint(data: GiftTransferRequest):
    max_attempts = 5
    attempt = 0
    base_delay = 2

    while attempt < max_attempts:
        try:
            if attempt > 0:
                logger.info(f"🔄 Retry attempt {attempt}/{max_attempts} for gift_name_prefix={data.gift_name_prefix}")
            else:
                logger.info(f"📥 Received transfer request: gift_name_prefix={data.gift_name_prefix}, recipient={data.recipient_id}")

            # При повторной попытке обновляем кэш подарков
            force_refresh = attempt > 0
            if force_refresh:
                logger.info("🔄 Refreshing gifts cache...")

            # Ищем подарок по префиксу
            slug = await find_gift_by_prefix(data.gift_name_prefix, force_refresh=force_refresh)

            if not slug:
                error_msg = f"Gift with prefix '{data.gift_name_prefix}' not found in inventory"
                logger.error(f"❌ {error_msg}")
                return {"status": "error", "message": error_msg}

            logger.info(f"🎁 Found gift slug: {slug}")

            # Отправляем подарок
            result = await transfer_gift_by_slug(
                slug=slug,
                recipient_id=data.recipient_id,
                max_retries=0  # Отключаем внутренний retry
            )

            if result:
                logger.info(f"✅ Successfully sent gift: {slug} to {data.recipient_id}")
                return {"status": "success", "message": "gift transferred successfully", "slug": slug}
            else:
                raise Exception("gift isn't transferred")

        except Exception as e:
            error_str = str(e)

            # Проверяем на ошибку STARGIFT_OWNER_INVALID
            if "STARGIFT_OWNER_INVALID" in error_str and attempt < max_attempts - 1:
                attempt += 1
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(f"⚠️ STARGIFT_OWNER_INVALID error, retrying in {delay}s (attempt {attempt}/{max_attempts})")
                await asyncio.sleep(delay)
                # Принудительно обновляем кэш на следующей итерации
                continue

            # Если это другая ошибка или исчерпаны попытки
            logger.error(f"❌ Got exception: {e}")
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": "Max retry attempts reached"}

@app.get("/health")
def health():
    return "OK"

@app.get("/list-gifts")
async def list_gifts_endpoint():
    """Endpoint для просмотра всех доступных подарков в инвентаре"""
    try:
        gifts = await get_saved_gifts(force_refresh=True)

        gift_list = []
        for gift in gifts:
            gift_slug = None
            if hasattr(gift, 'slug'):
                gift_slug = gift.slug
            elif hasattr(gift, 'gift') and hasattr(gift.gift, 'slug'):
                gift_slug = gift.gift.slug

            if gift_slug:
                can_transfer = getattr(gift, 'can_be_transferred', True)
                gift_list.append({
                    "slug": gift_slug,
                    "can_transfer": can_transfer
                })

        return {
            "status": "success",
            "total": len(gift_list),
            "gifts": gift_list
        }
    except Exception as e:
        logger.error(f"❌ Error listing gifts: {e}")
        return {"status": "error", "message": str(e)}