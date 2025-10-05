# Настройка Grafana для мониторинга PostgreSQL

## Пошаговая инструкция по безопасной настройке

### 1. Переменные окружения
Добавьте в ваш `.env` файл:

```bash
# Grafana настройки
GRAFANA_ADMIN_PASSWORD=your_strong_admin_password_here
GRAFANA_SECRET_KEY=your_long_random_secret_key_here
GRAFANA_DOMAIN=que-crash.fun

# PostgreSQL пароль для read-only пользователя
GRAFANA_DB_PASSWORD=your_secure_db_password_here
```

### 2. Создание HTTP Basic Auth для nginx
Создайте файл `.htpasswd` для дополнительной защиты:

```bash
# Установите apache2-utils если его нет
sudo apt-get install apache2-utils

# Создайте файл с паролем для доступа к Grafana
sudo htpasswd -c /etc/nginx/.htpasswd grafana_user
```

### 3. Создание read-only пользователя в PostgreSQL
Выполните SQL скрипт `grafana_readonly_user.sql`:

```bash
# Подключитесь к PostgreSQL и выполните:
docker exec -i postgres psql -U your_postgres_user -d your_database < grafana_readonly_user.sql

# Или через psql:
docker exec -it postgres psql -U your_postgres_user -d your_database
\i /docker-entrypoint-initdb.d/grafana_readonly_user.sql
```

Не забудьте заменить пароль в скрипте на реальный из переменной `GRAFANA_DB_PASSWORD`.

### 4. Создание конфигурации провизионинга
Создайте директорию для настроек Grafana:

```bash
mkdir -p ./grafana/provisioning/datasources
mkdir -p ./grafana/provisioning/dashboards
```

### 5. Безопасность

#### Уровни защиты:
1. **Двойная аутентификация**: HTTP Basic Auth в nginx + собственная аутентификация Grafana
2. **Read-only доступ**: Пользователь БД может только читать данные
3. **Внутренняя сеть**: Grafana доступна только через nginx proxy
4. **HTTPS**: Все соединения зашифрованы
5. **IP ограничения**: Можно ограничить доступ по IP

#### Дополнительные меры безопасности:
- Используйте VPN для доступа к Grafana
- Настройте OAuth через Google/GitHub вместо локальных пользователей
- Включите логирование всех действий в Grafana
- Регулярно обновляйте пароли

### 6. Запуск и доступ

```bash
# Запустите новую конфигурацию мониторинга
docker-compose up -d node-exporter prometheus grafana

# Доступ к сервисам:
# Grafana: https://que-crash.fun/grafana/
# Prometheus: https://que-crash.fun/prometheus/

# Логины для Grafana:
# HTTP Basic Auth: grafana_user / (пароль из .htpasswd)
# Grafana: admin / (пароль из GRAFANA_ADMIN_PASSWORD)
```

### 6.1. Потребление ресурсов (оптимизированная конфигурация)

- **node-exporter**: ~16-32MB RAM, минимальное CPU
- **prometheus**: ~64-128MB RAM, ~500MB диска (7 дней данных)
- **grafana**: ~128-256MB RAM
- **Общее потребление**: ~208-416MB RAM дополнительно

Система настроена для минимального потребления ресурсов:
- Увеличены интервалы сбора метрик (30-60 сек)
- Ограничено время хранения данных (7 дней)
- Отключены ненужные коллекторы в node-exporter
- Установлены лимиты памяти для контейнеров

### 7. Настройка Data Source в Grafana

После входа в Grafana:
1. Configuration → Data Sources → Add data source
2. Выберите PostgreSQL
3. Настройки подключения:
   - Host: `postgres:5432`
   - Database: `your_database_name`
   - User: `grafana_readonly`
   - Password: `your_secure_db_password_here`
   - SSL Mode: `disable` (внутренняя сеть Docker)

### 8. Примеры полезных запросов для мониторинга

#### PostgreSQL запросы:
```sql
-- Активные соединения
SELECT count(*) FROM pg_stat_activity WHERE state = 'active';

-- Размер базы данных
SELECT pg_size_pretty(pg_database_size(current_database()));

-- Топ медленных запросов (если включен pg_stat_statements)
SELECT query, calls, total_time, mean_time 
FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 10;

-- Статистика таблиц
SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del 
FROM pg_stat_user_tables 
ORDER BY n_tup_ins DESC;
```

#### Prometheus запросы для системного мониторинга:
```promql
# Использование CPU
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Использование RAM
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Использование диска
100 - ((node_filesystem_avail_bytes * 100) / node_filesystem_size_bytes)

# Загрузка системы
node_load1

# Сетевой трафик (входящий)
rate(node_network_receive_bytes_total[5m])

# Сетевой трафик (исходящий)
rate(node_network_transmit_bytes_total[5m])
```

## Важные замечания по безопасности

⚠️ **Не рекомендуется** открывать прямой доступ к Grafana из интернета без:
- VPN соединения
- IP whitelisting
- Дополнительной аутентификации

✅ **Рекомендуется**:
- Использовать VPN для доступа к мониторингу
- Настроить алерты в Telegram через Grafana
- Регулярно проверять логи доступа nginx
- Использовать сильные пароли и менять их регулярно