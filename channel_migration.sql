-- =====================================================
-- РУЧНАЯ МИГРАЦИЯ: Канальные бонусы
-- Выполни этот SQL в PostgreSQL
-- docker exec -i postgres psql -U crash_stars_user -d crash_stars_db < channel_migration.sql
-- =====================================================

-- 1. Создаём таблицу для канальных бонусов
CREATE TABLE IF NOT EXISTS channel_subscription_bonuses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel_id VARCHAR(255) NOT NULL,
    bonus_amount DECIMAL(12, 2) NOT NULL,
    subscription_verified_at TIMESTAMP WITH TIME ZONE,
    bonus_claimed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    attempts_count INTEGER NOT NULL DEFAULT 1,
    last_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Внешний ключ на пользователей
    CONSTRAINT fk_channel_bonus_user 
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    
    -- 🔒 ОДИН БОНУС НА КАНАЛ НА ПОЛЬЗОВАТЕЛЯ НАВСЕГДА
    CONSTRAINT uq_user_channel_bonus 
        UNIQUE (user_id, channel_id),
    
    -- 🔒 ТОЛЬКО ПОЗИТИВНЫЕ БОНУСЫ
    CONSTRAINT check_positive_bonus 
        CHECK (bonus_amount > 0),
    
    -- 🔒 ЛИМИТ ПОПЫТОК ПРОТИВ СПАМА
    CONSTRAINT check_attempts_limit 
        CHECK (attempts_count <= 10 AND attempts_count > 0)
);

-- 2. Индексы для быстрой работы
CREATE INDEX IF NOT EXISTS idx_channel_bonuses_user_channel 
    ON channel_subscription_bonuses (user_id, channel_id);

CREATE INDEX IF NOT EXISTS idx_channel_bonuses_claimed_at 
    ON channel_subscription_bonuses (bonus_claimed_at);

CREATE INDEX IF NOT EXISTS idx_channel_bonuses_user_id 
    ON channel_subscription_bonuses (user_id);

CREATE INDEX IF NOT EXISTS idx_channel_bonuses_channel_id 
    ON channel_subscription_bonuses (channel_id);

-- 3. Добавляем конфигурацию канального бонуса
-- 🚨 ПОМЕНЯЙ @your_channel НА СВОЙ РЕАЛЬНЫЙ КАНАЛ!
INSERT INTO system_settings (key, value, description) VALUES 
('channel_bonus_config', '{
    "enabled": true,
    "default_bonus_amount": 5.0,
    "channels": {
        "@crasherapp": {
            "bonus_amount": 5.0,
            "enabled": true,
            "description": "Main channel subscription bonus"
        }
    },
    "max_attempts_per_user": 5,
    "cooldown_minutes": 5
}', 'Configuration for channel subscription bonuses')
ON CONFLICT (key) DO NOTHING;

-- 4. Проверяем что всё создалось
SELECT 'Таблица создана!' as status;
SELECT COUNT(*) as table_exists FROM information_schema.tables 
WHERE table_name = 'channel_subscription_bonuses';

SELECT 'Конфигурация добавлена!' as status;
SELECT * FROM system_settings WHERE key = 'channel_bonus_config';

-- 5. Показываем структуру таблицы
SELECT 'Структура таблицы:' as info;
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'channel_subscription_bonuses' 
ORDER BY ordinal_position;
