# Health Exporter для мониторинга контейнеров

Легковесный экспортер для проверки здоровья всех контейнеров в Docker Compose и предоставления метрик для Prometheus.

## Что проверяется

- **backend** - HTTP запрос к `/health` 
- **frontend** - HTTP запрос к корню
- **postgres** - TCP соединение на порт 5432
- **redis** - TCP соединение на порт 6379  
- **pgbouncer** - TCP соединение на порт 6432
- **grafana** - HTTP запрос к `/api/health`
- **prometheus** - HTTP запрос к `/-/healthy`
- **nginx** - HTTP запрос к корню

## Эндпоинты

- `GET /metrics` - Метрики в формате Prometheus
- `GET /health` - Статус самого экспортера

## Метрики

- `container_health_status{service="...",status="..."}` - Статус контейнера (1=здоров, 0=нет)
- `container_response_time_seconds{service="..."}` - Время отклика в секундах
- `container_last_check_timestamp{service="..."}` - Timestamp последней проверки
- `health_exporter_up` - Статус самого экспортера

## Запуск

Экспортер автоматически запускается через Docker Compose:

```bash
docker-compose up -d health-exporter
```

Проверить статус:
```bash
curl http://localhost:8080/health
curl http://localhost:8080/metrics
```

## Настройки

В `app.py` можно изменить:
- Список проверяемых сервисов в `SERVICES`
- Таймауты проверок
- Интервал кэширования (по умолчанию 10 секунд)

## Ресурсы

- **Память**: 16-32 МБ
- **CPU**: минимальное потребление
- **Сеть**: только внутренняя между контейнерами

## Безопасность

- Работает под непривилегированным пользователем
- Только внутренние соединения между контейнерами
- Минимальный базовый образ Alpine