 Инструкция в Markdown (сохрани как pgweb-guide.md)

# 📘 Инструкция по безопасному запуску pgweb в Docker (без SSL)

## 📦 Требования

- PostgreSQL работает в Docker-сети `crash-stars-game_crash-stars-network`
- Контейнер PostgreSQL имеет имя `postgres`
- Данные для подключения:
  - **user**: `crash_stars_user`
  - **password**: `Strong_DB_Pass_uArP4rybqHFo7cqS3QrF`
  - **database**: `crash_stars_db`

## 🚀 Запуск Pgweb

```bash
docker run --rm -p 127.0.0.1:8081:8081 \
  --network crash-stars-game_crash-stars-network \
  sosedoff/pgweb \
  --url="postgres://crash_stars_user:Strong_DB_Pass_uArP4rybqHFo7cqS3QrF@postgres:5432/crash_stars_db?sslmode=disable"

    Pgweb будет доступен только локально на сервере: http://localhost:8081

    Контейнер автоматически удаляется после завершения (--rm)

    Пароль передаётся безопасно, внутри Docker-сети

🔐 Доступ извне (через SSH-туннель)

На своём локальном компьютере:

ssh -L 8081:localhost:8081 your_user@your_server_ip

Теперь открой браузер на своей машине:

http://localhost:8081