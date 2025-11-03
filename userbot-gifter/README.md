# Userbot-Gifter Service

Объединенный сервис, который содержит функционал:
- **Gifter**: API для отправки подарков через Telegram
- **Userbot**: Слушатель входящих сообщений и верификация отправителей

## Функционал

### Gifter API
- `POST /transfer-gift` - Отправка подарка по префиксу имени
- `GET /health` - Проверка здоровья сервиса

### Userbot Listener
- Автоматическое прослушивание входящих сообщений
- Добавление отправителей в таблицу `verified_senders`
- Кэширование диалогов для избежания спам-блока

## Особенности
- Использует **единый файл сессии** Telegram (`easygifter_session.session`)
- Единый Telethon клиент для всех операций
- Асинхронная архитектура на FastAPI

## Запуск

```bash
poetry install
poetry run python main.py
```

Или через Docker:

```bash
docker build -t userbot-gifter .
docker run -p 5050:5050 --env-file .env userbot-gifter
```
