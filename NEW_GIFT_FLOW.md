# 🎁 Новый Flow отправки уникальных подарков (Instant Delivery)

## 🚀 Что изменилось

**Старая логика (система заявок):**
1. Пользователь покупает подарок
2. Создаётся `payment_request` со статусом `pending`
3. Админ вручную одобряет
4. Auto Gift Sender отправляет подарок
5. Ожидание: до 24 часов

**Новая логика (мгновенная отправка):**
1. Пользователь покупает подарок
2. Backend проверяет `verified_senders` - писал ли пользователь userbot'у
3. Если **верифицирован** → отправка подарка **мгновенно** через userbot API
4. Если **не верифицирован** → возврат средств + сообщение об ошибке
5. Ожидание: **0 секунд** (мгновенно!)

## 🔄 Новый процесс

### Для пользователя:

```
┌─────────────────────────────────────┐
│ 1. Пользователь пишет userbot'у     │
│    (один раз, действует 48 часов)   │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 2. Пользователь нажимает "Получить" │
│    на уникальном подарке            │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│ 3. Backend проверяет верификацию    │
└─────────────────────────────────────┘
       ↙                       ↘
  ✅ Verified            ❌ Not Verified
       ↓                         ↓
┌──────────────────┐    ┌─────────────────────┐
│ Подарок          │    │ Ошибка + возврат    │
│ отправлен        │    │ средств + инструкция│
│ МГНОВЕННО! 🎉    │    │ как написать боту   │
└──────────────────┘    └─────────────────────┘
```

### Технический flow:

```python
# POST /purchase-gift
if gift.is_unique:
    # 1. Проверяем verified_senders
    verified = await check_verified_sender(
        user_telegram_id,
        within_hours=48
    )

    if not verified:
        # 2a. Не верифицирован → возврат средств
        await refund_balance(user_id, gift_price)
        return {
            "success": False,
            "error": "Напишите боту @your_userbot для получения подарка",
            "verification_required": True
        }

    # 2b. Верифицирован → отправка через userbot
    try:
        result = await userbot_api.transfer_gift(
            gift_name_prefix=gift.business_gift_id,
            recipient_id=user_telegram_id,
            star_count=25
        )

        if result.success:
            return {
                "success": True,
                "message": f"Подарок '{gift.name}' успешно отправлен!"
            }
    except Exception as e:
        # 3. Ошибка отправки → возврат средств
        await refund_balance(user_id, gift_price)
        return {
            "success": False,
            "error": "Не удалось отправить. Средства возвращены."
        }
```

## 🔑 Верификация пользователей

### Как пользователь становится верифицированным:

1. Пользователь пишет **любое сообщение** userbot'у
2. Userbot обрабатывает событие `NewMessage`
3. Добавляет/обновляет запись в `verified_senders`:

```python
@client.on(events.NewMessage(incoming=True))
async def handle_incoming_message(event):
    sender = await event.get_sender()

    # Добавляем в verified_senders
    INSERT INTO verified_senders (chat_id, username, last_message_at)
    VALUES (sender.id, sender.username, NOW())
    ON CONFLICT (chat_id) DO UPDATE
        SET last_message_at = NOW(), message_count = message_count + 1
```

### Условия верификации:

```sql
SELECT * FROM verified_senders
WHERE chat_id = <user_telegram_id>
  AND last_message_at > NOW() - INTERVAL '48 hours'  -- Настраивается через MESSAGE_VERIFICATION_HOURS
  AND is_blocked = FALSE
```

## 📊 Преимущества новой системы

### Для пользователей:
- ✅ **Мгновенное получение** подарков (0 секунд вместо 24 часов)
- ✅ **Простая верификация** - просто написать userbot'у один раз
- ✅ **Автоматический возврат** при ошибке
- ✅ **Понятные сообщения** об ошибках с инструкциями

### Для администратора:
- ✅ **Нет ручной работы** - всё автоматически
- ✅ **Защита от фрода** через верификацию
- ✅ **Логирование всех операций**
- ✅ **Можно заблокировать** подозрительных через `is_blocked`

### Для системы:
- ✅ **Меньше нагрузки** на БД (нет таблицы `payment_requests`)
- ✅ **Меньше кода** для поддержки
- ✅ **Прозрачная логика** - всё в одном endpoint
- ✅ **Retry встроен** в userbot-gifter API

## ⚙️ Конфигурация

### Environment Variables

```bash
# Username userbot'а (без @)
USERBOT_USERNAME=your_userbot_username

# URL userbot API
USERBOT_GIFTER_URL=http://userbot-gifter:8000

# Время действия верификации (в часах)
MESSAGE_VERIFICATION_HOURS=48
```

### Изменённые файлы

| Файл | Изменение |
|------|-----------|
| `backend/main.py` | Логика `/purchase-gift` для уникальных подарков |
| `.env` | Добавлена `USERBOT_USERNAME` |
| `docker-compose.yml` | Добавлена env var в backend |

## 🧪 Тестирование

### 1. Тест верификации

```bash
# Проверяем, что пользователь НЕ верифицирован
docker compose exec -T postgres psql -U crash_stars_user -d crash_stars_db -c \
  "SELECT * FROM verified_senders WHERE chat_id = <telegram_id>;"

# Ожидаемый результат: пусто
```

### 2. Тест покупки без верификации

```bash
curl -X POST http://localhost:8000/purchase-gift \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Init-Data: <valid_init_data>" \
  -d '{"gift_id": "unique_gift_id"}'

# Ожидаемый ответ:
{
  "success": false,
  "error": "Для получения уникального подарка необходимо написать боту @your_userbot...",
  "verification_required": true
}

# Проверяем возврат средств:
# SELECT balance FROM users WHERE telegram_id = <telegram_id>;
```

### 3. Верификация пользователя

```
1. Напиши userbot'у любое сообщение
2. Проверь verified_senders:

docker compose exec -T postgres psql -U crash_stars_user -d crash_stars_db -c \
  "SELECT chat_id, username, last_message_at, is_blocked FROM verified_senders WHERE chat_id = <telegram_id>;"

# Ожидаемый результат: запись с актуальным last_message_at
```

### 4. Тест покупки с верификацией

```bash
curl -X POST http://localhost:8000/purchase-gift \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Init-Data: <valid_init_data>" \
  -d '{"gift_id": "unique_gift_id"}'

# Ожидаемый ответ:
{
  "success": true,
  "message": "Уникальный подарок 'Gift Name' успешно отправлен!",
  "gift_sent": {...},
  "new_balance": "123.45"
}
```

### 5. Проверка логов

```bash
# Backend logs
docker logs -f api | grep -E "(verified|unique gift)"

# Ожидаемые сообщения:
# ✅ User 123456789 verified, sending unique gift via userbot
# ✅ Unique gift 'Gift Name' sent to user 123456789

# Userbot logs
docker logs -f userbot-gifter | grep "transfer-gift"

# Ожидаемые сообщения:
# 📥 Received transfer request: gift_name_prefix=...
# ✅ Gift sent successfully: slug=...
```

## 🛡️ Безопасность

### Защита от фрода

1. **Верификация через сообщения**
   - Пользователь должен написать userbot'у
   - Проверка last_message_at < 48 часов

2. **Ручная блокировка**
   ```sql
   UPDATE verified_senders
   SET is_blocked = TRUE, notes = 'Suspicious activity'
   WHERE chat_id = <telegram_id>;
   ```

3. **Автоматический возврат**
   - При любой ошибке средства возвращаются автоматически
   - Создаётся транзакция типа `refund`

4. **Логирование**
   - Все операции логируются
   - Можно отследить любую покупку

### Мониторинг

```sql
-- Неверифицированные попытки покупки (из логов)
SELECT COUNT(*) FROM logs WHERE message LIKE '%not verified%';

-- Заблокированные пользователи
SELECT COUNT(*) FROM verified_senders WHERE is_blocked = TRUE;

-- Активные верифицированные (за последние 48ч)
SELECT COUNT(*) FROM verified_senders
WHERE last_message_at > NOW() - INTERVAL '48 hours'
  AND is_blocked = FALSE;
```

## 🚫 Что удалено

### Auto Gift Sender service больше НЕ используется

- ❌ Проверка `payment_requests` каждые 30 секунд
- ❌ Обработка очереди approved запросов
- ❌ Telegram alerts админу

**Но:** Сервис оставлен в коде на случай, если понадобится ручная обработка. Просто не создаётся `payment_requests`.

### Таблица `payment_requests` больше НЕ используется

- ❌ Создание pending requests
- ❌ Одобрение админом
- ❌ Отслеживание статуса

**Но:** Таблица оставлена в БД на случай, если нужна история или откат.

## 📝 Инструкции для пользователя

### Сообщение при ошибке верификации:

```
❌ Не удалось получить подарок

Для получения уникального подарка необходимо:

1. Написать боту @your_userbot любое сообщение
2. Вернуться и попробовать снова

Ваши средства возвращены на баланс.
```

### Сообщение при успехе:

```
✅ Подарок успешно отправлен!

Уникальный подарок 'Delicious Cake' был отправлен вам в Telegram.
Проверьте личные сообщения от бота.
```

---

**Дата обновления:** 2025-01-14
**Версия:** 2.0 (Instant Delivery)
**Статус:** ✅ Готово к использованию
