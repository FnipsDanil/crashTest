import asyncio
import aiohttp
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Токен бота из переменной окружения
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("TG_BOT_TOKEN не найден в переменных окружения")

# Ссылка на фронтенд и backend
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://localhost:5173/")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
SUPPORT_USER_ID = os.getenv("SUPPORT_USER_ID", "")  # ID второго аккаунта для поддержки

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


async def send_telegram_gift(user_id: int, gift_id: str, from_user_name: str = "Crash Stars Game"):
    """Отправить реальный Telegram подарок пользователю"""
    try:
        # Отправляем подарок через aiogram
        result = await bot.send_gift(
            user_id=user_id,
            gift_id=gift_id,
            text=f"🎉 Подарок от {from_user_name}!\n\n💰 Вывод из игры Crash Stars выполнен успешно!"
        )
        print(f"✅ Подарок {gift_id} отправлен пользователю {user_id}")
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки подарка: {e}")
        return False

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Обработка команды /start"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить игру", web_app=WebAppInfo(url=WEB_APP_URL))],
        [
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"),
            InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="support"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ])
    
    await message.answer(
        "🎮 <b>Добро пожаловать в Crasher!</b>\n\n"
        "🎯 Играй, побеждай и выводи подарки!\n"
        "🎁 Твои выигрыши можно вывести в виде реальных Telegram подарков\n\n"
        "Нажми кнопку ниже, чтобы начать:",
        reply_markup=keyboard
    )

@dp.message(F.text == "/support")
async def command_support_handler(message: Message) -> None:
    """Обработка команды /support"""
    await handle_support_request(message.chat.id)

@dp.callback_query(F.data == "support")
async def callback_support_handler(callback: types.CallbackQuery) -> None:
    """Обработка нажатия кнопки поддержки"""
    await callback.answer()
    await handle_support_request(callback.from_user.id, callback.message)

@dp.callback_query(F.data == "help")
async def callback_help_handler(callback: types.CallbackQuery) -> None:
    """Обработка нажатия кнопки помощи"""
    await callback.answer()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить игру", web_app=WebAppInfo(url=WEB_APP_URL))],
        [
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"),
            InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="support"),
            InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
        ]
    ])
    
    await callback.message.edit_text(
        text="ℹ️ <b>Инструкция по игре Crash Stars</b>\n\n"
             "🎮 <b>Как играть:</b>\n"
             "• Делайте ставки и наблюдайте за множителем графика\n"
             "• Заберите выигрыш до того, как множитель графика упадет\n"
             "• Чем дольше ждете, тем больше множитель\n\n"
             "🎁 <b>Вывод подарков:</b>\n"
             "• Выигранные монеты можно обменять на Telegram подарки\n"
             "• Обработка уникальных подарков занимает до 24 часов\n"
             "• Обычные подарки отправляются мгновенно\n\n"
             "• После покупки уникалього подарка необходимо написать в чат боту любое сообщение, иначе заявка автоматически отклонится спустя некоторое время\n\n"
             "• Для покупки подарка необходимо выиграть (без учёта проигрышей) сумму, равную половине стоимости подарка\n\n"
             "💰 <b>Баланс:</b>\n"
             "• При покупке подарка средства списываются сразу\n"
             "• Статус заявки можно отслеживать в профиле\n\n"
             "❓ Остались вопросы? Обратитесь в поддержку!",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "main_menu")
async def callback_main_menu_handler(callback: types.CallbackQuery) -> None:
    """Возврат к главному меню"""
    await callback.answer()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить игру", web_app=WebAppInfo(url=WEB_APP_URL))],
        [
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"),
            InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
        ]
    ])
    
    await callback.message.edit_text(
        text="🎮 <b>Добро пожаловать в Crash Stars!</b>\n\n"
             "🎯 Играй, побеждай и выводи подарки!\n"
             "🎁 Твои выигрыши можно вывести в виде реальных Telegram подарков\n\n"
             "Нажми кнопку ниже, чтобы начать:",
        reply_markup=keyboard
    )

async def handle_support_request(chat_id: int, message_to_edit = None) -> None:
    """Общая обработка запросов поддержки"""
    if not SUPPORT_USER_ID:
        text = (
            "❌ <b>Техподдержка временно недоступна</b>\n\n"
            "Попробуйте обратиться позже."
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
        ])
        
        if message_to_edit:
            await message_to_edit.edit_text(text=text, reply_markup=keyboard)
        else:
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)
        return
    
    # Создаем правильную ссылку для открытия чата/профиля поддержки
    if SUPPORT_USER_ID.isdigit():
        # Если user_id - открываем профиль пользователя
        support_url = f"tg://user?id={SUPPORT_USER_ID}"
        button_text = "👤 Открыть профиль поддержки"
        instructions = (
            "👇 <b>Как связаться с поддержкой:</b>\n"
            "1️⃣ Нажмите кнопку ниже\n"
            "2️⃣ Откроется профиль специалиста\n"
            "3️⃣ Нажмите <b>\"Написать\"</b> для отправки сообщения"
        )
    else:
        # Если username - открываем чат напрямую
        username = SUPPORT_USER_ID.lstrip('@')
        support_url = f"https://t.me/{username}"
        button_text = "💬 Написать в поддержку"
        instructions = (
            "👇 <b>Как связаться с поддержкой:</b>\n"
            "1️⃣ Нажмите кнопку ниже\n"
            "2️⃣ Откроется чат с поддержкой\n"
            "3️⃣ Напишите ваш вопрос"
        )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=button_text, url=support_url)],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ])
    
    text = (
        "🆘 <b>Техническая поддержка</b>\n\n"
        "📝 Если у вас возникли вопросы или проблемы с:\n"
        "• Выводом подарков\n"
        "• Игровым балансом\n"
        "• Работой приложения\n"
        "• Статусом заявок\n\n"
        f"{instructions}\n\n"
        "⏰ Время ответа: обычно в течение 1-2 часов"
    )
    
    if message_to_edit:
        await message_to_edit.edit_text(text=text, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

async def notify_gift_withdrawal(user_id: int, gift_name: str, cost: int):
    """Уведомить пользователя о выводе подарка"""
    try:
        await bot.send_message(
            chat_id=user_id,
            text=f"🎁 <b>Вывод подарка выполнен!</b>\n\n"
                 f"📦 Подарок: {gift_name}\n"
                 f"💰 Потрачено игровых монет: {cost}\n\n"
                 f"🚀 Подарок отправлен в ваш Telegram!"
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")

async def main() -> None:
    """Запуск бота"""
    print("🤖 Бот запущен с поддержкой Telegram подарков...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())