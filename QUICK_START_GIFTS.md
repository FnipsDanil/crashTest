# 🎁 Быстрый старт - Автоматическая отправка подарков

## ⚡ Краткая инструкция (5 минут)

### 1. Создай session для userbot

```bash
cd /crash/session-generator
sh run.sh
```

Введи:
- API ID и API Hash с https://my.telegram.org/apps
- Номер телефона
- Код из Telegram
- Имя session: `userbot_session`

Скопируй session:
```bash
cp userbot_session.session ../userbot-gifter/sessions/
```

### 2. Обнови `.env`

Замени значения в `/crash/.env`:

```bash
TELEGRAM_USERBOT_API_ID=21033982  # Твой API ID
TELEGRAM_USERBOT_API_HASH=079914024f8e6f7d92babdf13b3de0c9  # Твой API Hash
```

### 3. Примени миграцию БД

```bash
cd /crash/backend
poetry run alembic upgrade head
```

### 4. Запусти систему

```bash
cd /crash
docker-compose up -d --build
```

### 5. Проверь работу

```bash
# Логи backend
docker logs -f api | grep "Auto Gift"

# Логи userbot
docker logs -f userbot-gifter
```

## 📝 Как работает

1. Пользователь покупает уникальный подарок → создаётся `payment_request` (status=pending)
2. Админ одобряет: `UPDATE payment_requests SET status='approved' WHERE id=123;`
3. Auto Gift Sender каждые 30 секунд:
   - Проверяет approved запросы
   - Проверяет верификацию пользователя (писал ли он userbot'у)
   - Отправляет подарок через userbot API
   - Обновляет статус на completed/canceled

## 🔧 Быстрые команды

### Одобрить запрос:
```sql
UPDATE payment_requests SET status='approved', approved_at=NOW() WHERE id=<id>;
```

### Посмотреть очередь:
```sql
SELECT * FROM payment_requests WHERE status='approved';
```

### Проверить userbot API:
```bash
curl http://localhost:8001/list-gifts
```

---

📖 **Полная документация:** [GIFT_AUTOMATION_SETUP.md](GIFT_AUTOMATION_SETUP.md)
