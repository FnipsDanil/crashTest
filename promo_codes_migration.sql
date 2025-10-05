-- Миграция системы промокодов для Crash Stars Game
-- Выполнить после основной схемы database_schema.sql

-- ================================================================
-- ДОБАВЛЕНИЕ ПОЛЯ withdrawal_locked_balance В ТАБЛИЦУ users
-- ================================================================

-- Добавляем поле для отслеживания заблокированного баланса от промокодов
ALTER TABLE users ADD COLUMN IF NOT EXISTS withdrawal_locked_balance DECIMAL(12,2) DEFAULT 0.00 NOT NULL;

-- Добавляем constraint для проверки неотрицательности заблокированного баланса
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'check_withdrawal_locked_balance_non_negative' 
                   AND table_name = 'users') THEN
        ALTER TABLE users ADD CONSTRAINT check_withdrawal_locked_balance_non_negative 
        CHECK (withdrawal_locked_balance >= 0.00);
    END IF;
END $$;

-- ================================================================
-- СОЗДАНИЕ ТАБЛИЦЫ promo_codes
-- ================================================================

CREATE TABLE IF NOT EXISTS promo_codes (
    id BIGSERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    balance_reward DECIMAL(12,2) NOT NULL,
    withdrawal_requirement DECIMAL(12,2), -- NULL = без требований к выводу
    max_uses INTEGER NOT NULL,
    current_uses INTEGER DEFAULT 0 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE -- NULL = без истечения
);

-- Создаем индексы для promo_codes
CREATE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code);
CREATE INDEX IF NOT EXISTS idx_promo_codes_active ON promo_codes(is_active);
CREATE INDEX IF NOT EXISTS idx_promo_codes_expires ON promo_codes(expires_at);

-- Добавляем constraints для promo_codes
DO $$
BEGIN
    -- check_balance_reward_positive
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'check_balance_reward_positive' 
                   AND table_name = 'promo_codes') THEN
        ALTER TABLE promo_codes ADD CONSTRAINT check_balance_reward_positive 
        CHECK (balance_reward > 0.00);
    END IF;
    
    -- check_max_uses_positive
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'check_max_uses_positive' 
                   AND table_name = 'promo_codes') THEN
        ALTER TABLE promo_codes ADD CONSTRAINT check_max_uses_positive 
        CHECK (max_uses > 0);
    END IF;
    
    -- check_current_uses_non_negative
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'check_current_uses_non_negative' 
                   AND table_name = 'promo_codes') THEN
        ALTER TABLE promo_codes ADD CONSTRAINT check_current_uses_non_negative 
        CHECK (current_uses >= 0);
    END IF;
    
    -- check_current_uses_not_exceed_max
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'check_current_uses_not_exceed_max' 
                   AND table_name = 'promo_codes') THEN
        ALTER TABLE promo_codes ADD CONSTRAINT check_current_uses_not_exceed_max 
        CHECK (current_uses <= max_uses);
    END IF;
END $$;

-- ================================================================
-- СОЗДАНИЕ ТАБЛИЦЫ promo_code_uses
-- ================================================================

CREATE TABLE IF NOT EXISTS promo_code_uses (
    id BIGSERIAL PRIMARY KEY,
    promo_code_id BIGINT NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    balance_granted DECIMAL(12,2) NOT NULL,
    withdrawal_requirement DECIMAL(12,2), -- Копия требования на момент использования
    used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Создаем индексы для promo_code_uses
CREATE INDEX IF NOT EXISTS idx_promo_code_uses_promo_code_id ON promo_code_uses(promo_code_id);
CREATE INDEX IF NOT EXISTS idx_promo_code_uses_user_id ON promo_code_uses(user_id);
CREATE INDEX IF NOT EXISTS idx_promo_code_uses_used_at ON promo_code_uses(used_at);

-- Уникальный constraint - один промокод на пользователя
CREATE UNIQUE INDEX IF NOT EXISTS idx_promo_code_uses_unique 
ON promo_code_uses(promo_code_id, user_id);

-- Добавляем constraints для promo_code_uses
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'check_balance_granted_positive' 
                   AND table_name = 'promo_code_uses') THEN
        ALTER TABLE promo_code_uses ADD CONSTRAINT check_balance_granted_positive 
        CHECK (balance_granted > 0.00);
    END IF;
END $$;

-- ================================================================
-- ОБНОВЛЕНИЕ CONSTRAINT ДЛЯ TRANSACTIONS
-- ================================================================

-- Добавляем новый тип транзакции promo_code_bonus
-- Сначала удаляем старый constraint, потом создаем новый

DO $$
BEGIN
    -- Проверяем существует ли constraint
    IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
               WHERE constraint_name = 'check_valid_transaction_amounts') THEN
        -- Удаляем старый constraint
        ALTER TABLE transactions DROP CONSTRAINT check_valid_transaction_amounts;
    END IF;
    
    -- Создаем новый constraint с поддержкой promo_code_bonus
    ALTER TABLE transactions ADD CONSTRAINT check_valid_transaction_amounts
    CHECK (
        (type IN ('game_win', 'deposit', 'referral_bonus', 'withdrawal', 'refund', 'promo_code_bonus') AND amount > 0.00) OR
        (type IN ('game_loss', 'gift_purchase') AND amount < 0.00) OR
        (type NOT IN ('game_win', 'deposit', 'referral_bonus', 'game_loss', 'withdrawal', 'gift_purchase', 'refund', 'promo_code_bonus'))
    );
END $$;

-- ================================================================
-- ФУНКЦИЯ ДЛЯ АВТОМАТИЧЕСКОГО РАЗБЛОКИРОВАНИЯ БАЛАНСА ПРИ ПОПОЛНЕНИИ
-- ================================================================

CREATE OR REPLACE FUNCTION unlock_balance_on_deposit()
RETURNS TRIGGER AS $$
BEGIN
    -- Обрабатываем только пополнения баланса
    IF NEW.type = 'deposit' AND NEW.status = 'completed' AND NEW.amount > 0 THEN
        -- Разблокируем баланс пропорционально пополнению
        UPDATE users 
        SET withdrawal_locked_balance = GREATEST(0, withdrawal_locked_balance - NEW.amount)
        WHERE id = NEW.user_id 
          AND withdrawal_locked_balance > 0;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаем триггер для автоматического разблокирования
DROP TRIGGER IF EXISTS trigger_unlock_balance_on_deposit ON transactions;
CREATE TRIGGER trigger_unlock_balance_on_deposit
    AFTER INSERT ON transactions
    FOR EACH ROW 
    WHEN (NEW.type = 'deposit' AND NEW.status = 'completed')
    EXECUTE FUNCTION unlock_balance_on_deposit();

-- ================================================================
-- ФУНКЦИЯ ДЛЯ ВАЛИДАЦИИ ПРОМОКОДОВ
-- ================================================================

CREATE OR REPLACE FUNCTION validate_promo_code_use()
RETURNS TRIGGER AS $$
BEGIN
    -- Проверяем, что промокод активен
    IF NOT EXISTS (
        SELECT 1 FROM promo_codes 
        WHERE id = NEW.promo_code_id 
          AND is_active = TRUE 
          AND (expires_at IS NULL OR expires_at > NOW())
          AND current_uses < max_uses
    ) THEN
        RAISE EXCEPTION 'Промокод неактивен, истек или исчерпан';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Создаем триггер для валидации
DROP TRIGGER IF EXISTS trigger_validate_promo_code_use ON promo_code_uses;
CREATE TRIGGER trigger_validate_promo_code_use
    BEFORE INSERT ON promo_code_uses
    FOR EACH ROW EXECUTE FUNCTION validate_promo_code_use();

-- ================================================================
-- ФУНКЦИЯ ДЛЯ СТАТИСТИКИ ПО ПРОМОКОДАМ
-- ================================================================

CREATE OR REPLACE FUNCTION get_promo_code_stats(p_code VARCHAR DEFAULT NULL)
RETURNS TABLE (
    code VARCHAR,
    balance_reward DECIMAL,
    max_uses INTEGER,
    current_uses INTEGER,
    remaining_uses INTEGER,
    total_granted DECIMAL,
    created_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        pc.code,
        pc.balance_reward,
        pc.max_uses,
        pc.current_uses,
        (pc.max_uses - pc.current_uses) as remaining_uses,
        COALESCE(SUM(pcu.balance_granted), 0::DECIMAL) as total_granted,
        pc.created_at,
        pc.expires_at,
        pc.is_active
    FROM promo_codes pc
    LEFT JOIN promo_code_uses pcu ON pc.id = pcu.promo_code_id
    WHERE (p_code IS NULL OR pc.code = p_code)
    GROUP BY pc.id, pc.code, pc.balance_reward, pc.max_uses, pc.current_uses, pc.created_at, pc.expires_at, pc.is_active
    ORDER BY pc.created_at DESC;
END;
$$ LANGUAGE plpgsql;

-- ================================================================
-- ИНДЕКСЫ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ
-- ================================================================

-- Составные индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_promo_codes_active_expires 
ON promo_codes(is_active, expires_at) 
WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_promo_code_uses_user_used_at 
ON promo_code_uses(user_id, used_at DESC);

-- ================================================================
-- ПОЛЕЗНЫЕ ЗАПРОСЫ ДЛЯ АДМИНИСТРИРОВАНИЯ
-- ================================================================

-- Создаем представление для активных промокодов
CREATE OR REPLACE VIEW active_promo_codes AS
SELECT 
    code,
    balance_reward,
    withdrawal_requirement,
    max_uses,
    current_uses,
    (max_uses - current_uses) as remaining_uses,
    CASE 
        WHEN expires_at IS NULL THEN 'Без истечения'
        WHEN expires_at > NOW() THEN 'Активен до ' || expires_at::DATE
        ELSE 'Истек'
    END as status,
    created_at
FROM promo_codes 
WHERE is_active = TRUE 
  AND (expires_at IS NULL OR expires_at > NOW())
  AND current_uses < max_uses
ORDER BY created_at DESC;

-- Создаем представление для статистики использования промокодов
CREATE OR REPLACE VIEW promo_usage_stats AS
SELECT 
    DATE(pcu.used_at) as usage_date,
    COUNT(*) as total_uses,
    COUNT(DISTINCT pcu.user_id) as unique_users,
    SUM(pcu.balance_granted) as total_granted,
    AVG(pcu.balance_granted) as avg_granted
FROM promo_code_uses pcu
GROUP BY DATE(pcu.used_at)
ORDER BY usage_date DESC;

-- ================================================================
-- КОММЕНТАРИИ К ТАБЛИЦАМ
-- ================================================================

COMMENT ON TABLE promo_codes IS 'Таблица промокодов с настройками активации и вознаграждений';
COMMENT ON TABLE promo_code_uses IS 'История использования промокодов пользователями';
COMMENT ON COLUMN users.withdrawal_locked_balance IS 'Заблокированный баланс от промокодов (требует пополнения для вывода)';

COMMENT ON COLUMN promo_codes.code IS 'Уникальный код промокода (только A-Z, 0-9)';
COMMENT ON COLUMN promo_codes.balance_reward IS 'Размер награды в звездах';
COMMENT ON COLUMN promo_codes.withdrawal_requirement IS 'Сумма пополнения для разблокировки вывода (NULL = без ограничений)';
COMMENT ON COLUMN promo_codes.max_uses IS 'Максимальное количество активаций';
COMMENT ON COLUMN promo_codes.current_uses IS 'Текущее количество использований';

-- ================================================================
-- ЗАВЕРШЕНИЕ МИГРАЦИИ
-- ================================================================

-- Выводим статистику созданных объектов
DO $$
BEGIN
    RAISE NOTICE '✅ Миграция промокодов завершена успешно!';
    RAISE NOTICE '📊 Создано таблиц: 2 (promo_codes, promo_code_uses)';
    RAISE NOTICE '🔧 Создано функций: 3 (unlock_balance_on_deposit, validate_promo_code_use, get_promo_code_stats)';
    RAISE NOTICE '🎯 Создано представлений: 2 (active_promo_codes, promo_usage_stats)';
    RAISE NOTICE '⚡ Создано индексов: 8';
    RAISE NOTICE '🔒 Создано constraints: 7';
    RAISE NOTICE ' ';
    RAISE NOTICE '🚀 Система промокодов готова к использованию!';
    RAISE NOTICE '📝 Используйте файл test_promo_codes.sql для создания тестовых промокодов';
END $$;