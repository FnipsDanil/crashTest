# 🎮 Управление игровой конфигурацией

## Обзор
Система позволяет гибко настраивать параметры crash-игры через PostgreSQL и API в реальном времени без перезапуска сервера.

## ✅ Исправленные проблемы
- **Decimal/float конфликты**: Все арифметические операции теперь используют Decimal для точности
- **Безопасность генерации**: Криптографически стойкий ГСЧ для crash_point
- **Типы данных**: Корректная конвертация между строками, Decimal и числами

## 📊 Настраиваемые параметры

### Основные параметры
```json
{
  "growth_rate": "1.01",          // Коэффициент роста за тик (1.0 - 1.1)
  "tick_ms": 60,                  // Интервал обновления в мс (10-1000)
  "max_coefficient": "100.0",     // Максимальный коэффициент (10-1000)  
  "waiting_time": 10,             // Время между раундами в сек (1-60)
  "join_time": 2                  // Время для входа в игру в сек (1-60)
}
```

### Распределение crash_point
```json
{
  "crash_ranges": [
    {"min": "1.1", "max": "3.0", "probability": "0.7"},   // 70% низкие
    {"min": "3.0", "max": "10.0", "probability": "0.2"},  // 20% средние  
    {"min": "10.0", "max": "50.0", "probability": "0.1"}  // 10% высокие
  ]
}
```

**Валидация:**
- Сумма всех `probability` должна равняться 1.0 (±0.001)
- Диапазоны не должны перекрываться
- `min < max` для каждого диапазона

## 🔧 API эндпоинты

### Получить конфигурацию
```bash
GET /api/admin/game-config
```

### Обновить параметры
```bash
PUT /api/admin/game-config
Content-Type: application/json

{
  "growth_rate": "1.015",
  "tick_ms": 40,
  "crash_ranges": [
    {"min": "1.1", "max": "2.5", "probability": "0.8"},
    {"min": "2.5", "max": "20.0", "probability": "0.2"}
  ]
}
```

### Предустановки
```bash
# Просмотр доступных предустановок
GET /api/admin/game-config/presets

# Применение предустановки
POST /api/admin/game-config/apply-preset/aggressive
POST /api/admin/game-config/apply-preset/conservative  
POST /api/admin/game-config/apply-preset/balanced
```

### Управление
```bash
# Сброс к дефолту
POST /api/admin/game-config/reset

# Валидация без применения
POST /api/admin/game-config/validate
Content-Type: application/json
{...config...}

# Текущая эффективная конфигурация из памяти
GET /api/admin/game-config/current-effective

# Перезагрузка из БД
POST /api/admin/game-config/reload
```

## 🎯 Предустановки

### Conservative (Консервативная)
- **Риск**: Низкий
- **Описание**: Частые малые крахи, меньше волатильности
- **Параметры**: 
  - growth_rate: "1.008" (медленный рост)
  - tick_ms: 80 (редкие обновления)
  - crash_ranges: 80% до 2.5x, 15% до 8x, 5% до 30x

### Balanced (Сбалансированная) 
- **Риск**: Средний
- **Описание**: Дефолтная конфигурация
- **Параметры**: Базовые значения

### Aggressive (Агрессивная)
- **Риск**: Высокий  
- **Описание**: Быстрый рост, большие выигрыши
- **Параметры**:
  - growth_rate: "1.012" (быстрый рост)
  - tick_ms: 50 (частые обновления)  
  - crash_ranges: 60% до 2x, 25% до 15x, 15% до 100x

## 🔒 Безопасность

### Генерация crash_point
- **Источник энтропии**: `secrets.SystemRandom()` (криптографически стойкий)
- **Двухуровневая случайность**:
  1. Выбор диапазона: случайное число 0-1
  2. Значение в диапазоне: равномерное распределение
- **Независимость**: Каждый crash_point генерируется независимо
- **Невозможность предсказания**: Использует энтропию ОС

### Пример генерации
```python
# 1. Выбираем диапазон
rand = Decimal(str(secure_random.random()))  # 0.0-1.0
cumulative_prob = Decimal('0')

for range_config in crash_ranges:
    cumulative_prob += Decimal(str(range_config["probability"]))
    if rand <= cumulative_prob:
        # 2. Генерируем значение в диапазоне
        min_val = Decimal(str(range_config["min"]))
        max_val = Decimal(str(range_config["max"]))
        rand_uniform = Decimal(str(secure_random.random()))
        crash_point = min_val + (max_val - min_val) * rand_uniform
        return crash_point.quantize(Decimal('0.01'))
```

## 💾 Хранение данных

### PostgreSQL `system_settings`
```sql
CREATE TABLE system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Запись конфигурации
INSERT INTO system_settings (key, value, description) VALUES (
    'game_config', 
    '{"growth_rate": "1.01", "tick_ms": 60, ...}',
    'Game configuration settings'
);
```

### Формат хранения
- **Decimal значения**: Хранятся как строки для точности
- **Целые числа**: Хранятся как числа
- **JSONB**: Поддержка индексов и запросов

### Загрузка при старте
```python
# main.py
stored_config = await DatabaseService.get_system_setting(session, "game_config")
if stored_config:
    update_game_config(stored_config)  # Конвертирует строки -> Decimal
```

## 🧪 Тестирование

Запуск тестов:
```bash
cd backend
python test_config_simple.py
```

Проверяет:
- ✅ Загрузку дефолтной конфигурации
- ✅ Обновление конфигурации из строк в Decimal
- ✅ Арифметические операции с Decimal
- ✅ Валидацию сумм вероятностей

## 📈 Мониторинг

### Логирование
```
INFO - game.engine - 🎲 Secure crash point: 3.39 (range 3.0-10.0)
INFO - config.settings - ✅ Game config loaded from PostgreSQL system_settings  
INFO - api.admin_routes - Game configuration updated via admin API
```

### Метрики для отслеживания
- Средний crash_point по диапазонам
- Распределение реальных вероятностей vs настроенных
- Время выполнения генерации crash_point
- Количество изменений конфигурации

## 🚨 Рекомендации

### Безопасность
1. **Добавить аутентификацию** для admin API
2. **Ограничить права** на изменение конфигурации
3. **Логировать все изменения** с пользователем и временем
4. **Создать backup** перед изменениями

### Производительность  
1. **Кэшировать** эффективную конфигурацию в памяти
2. **Валидировать** изменения перед применением
3. **Тестировать** новые настройки на dev среде

### Мониторинг
1. **Отслеживать** распределение crash_point
2. **Алерты** при аномальных значениях  
3. **Метрики** производительности game engine

## 🔄 Примеры использования

### Увеличить скорость игры
```bash
curl -X PUT http://localhost:8000/api/admin/game-config \
  -H "Content-Type: application/json" \
  -d '{
    "growth_rate": "1.02", 
    "tick_ms": 30
  }'
```

### Сделать игру более предсказуемой
```bash  
curl -X PUT http://localhost:8000/api/admin/game-config \
  -H "Content-Type: application/json" \
  -d '{
    "crash_ranges": [
      {"min": "1.5", "max": "2.5", "probability": "0.9"},
      {"min": "2.5", "max": "5.0", "probability": "0.1"}
    ]
  }'
```

### Откат к безопасным настройкам
```bash
curl -X POST http://localhost:8000/api/admin/game-config/apply-preset/conservative
```

---

**✅ Готово к использованию!** 
Все изменения применяются мгновенно без перезапуска сервера.