#!/usr/bin/env python3
"""
Скрипт для генерации session файла Telethon.
Запустите этот скрипт и следуйте инструкциям.
"""

from telethon.sync import TelegramClient
import os

print("=" * 60)
print("🔐 Генератор Session файла для Telethon")
print("=" * 60)
print()

# Запрашиваем данные у пользователя
print("📝 Введите данные из https://my.telegram.org/apps")
print()

api_id = input("API ID: ").strip()
api_hash = input("API Hash: ").strip()

if not api_id or not api_hash:
    print("❌ API ID и API Hash обязательны!")
    exit(1)

try:
    api_id = int(api_id)
except ValueError:
    print("❌ API ID должен быть числом!")
    exit(1)

print()
print("📱 Введите имя для session файла (без расширения .session)")
session_name = input("Имя файла (например, gifter_session): ").strip()

if not session_name:
    session_name = "gifter_session"
    print(f"ℹ️ Используется имя по умолчанию: {session_name}")

print()
print("🔄 Создание session...")
print()

# Создаем клиент
client = TelegramClient(session_name, api_id, api_hash)

print("📞 Подключение к Telegram...")
print()
print("⚠️  ВАЖНО: Номер телефона в международном формате!")
print("   Примеры: +79991234567, +380991234567, +12025551234")
print()

async def phone_code_callback():
    """Запрашиваем телефон с валидацией"""
    phone = input("📱 Введите номер телефона (с +): ").strip()

    # Проверяем наличие +
    if not phone.startswith('+'):
        print("⚠️  Добавляем + в начало номера...")
        phone = '+' + phone.lstrip('+')

    # Убираем пробелы и дефисы
    phone = phone.replace(' ', '').replace('-', '')

    print(f"✅ Используется номер: {phone}")
    return phone

client.start(phone=phone_code_callback)

print()
print("=" * 60)
print("✅ Session файл успешно создан!")
print("=" * 60)
print()
print(f"📁 Файл сохранен: {session_name}.session")
print()

# Получаем информацию о аккаунте
me = client.get_me()
print("👤 Информация об аккаунте:")
print(f"   - Имя: {me.first_name} {me.last_name or ''}")
print(f"   - Username: @{me.username or 'не указан'}")
print(f"   - ID: {me.id}")
print(f"   - Телефон: {me.phone}")
print()

print("📋 Что делать дальше:")
print(f"   1. Скопируйте файл '{session_name}.session' в нужную папку")
print(f"   2. Для gifter: cp {session_name}.session ../gifter/")
print(f"   3. Для userbot: cp {session_name}.session ../userbot/")
print()
print("⚠️  ВАЖНО: Не используйте один session файл одновременно в двух процессах!")
print("   Создайте два разных session файла для gifter и userbot,")
print("   если хотите использовать их параллельно.")
print()

client.disconnect()

print("✅ Готово!")
