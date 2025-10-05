-- Тестовые промокоды для демонстрации системы
-- Выполнить после применения миграции 002_add_promo_codes

-- 1. Простой промокод без требований к выводу
INSERT INTO promo_codes (code, balance_reward, withdrawal_requirement, max_uses, current_uses, is_active, expires_at) 
VALUES ('WELCOME100', 100.00, NULL, 1000, 0, true, NULL);

-- 2. Промокод с требованием пополнения для вывода
INSERT INTO promo_codes (code, balance_reward, withdrawal_requirement, max_uses, current_uses, is_active, expires_at) 
VALUES ('BONUS50', 50.00, 50.00, 500, 0, true, NULL);

-- 3. Ограниченный промокод для VIP пользователей
INSERT INTO promo_codes (code, balance_reward, withdrawal_requirement, max_uses, current_uses, is_active, expires_at) 
VALUES ('VIP1000', 1000.00, 500.00, 10, 0, true, NULL);

-- 4. Промокод с истечением срока (истекает через месяц)
INSERT INTO promo_codes (code, balance_reward, withdrawal_requirement, max_uses, current_uses, is_active, expires_at) 
VALUES ('MONTH200', 200.00, 100.00, 100, 0, true, NOW() + INTERVAL '1 month');

-- 5. Тестовый промокод для разработки
INSERT INTO promo_codes (code, balance_reward, withdrawal_requirement, max_uses, current_uses, is_active, expires_at) 
VALUES ('TEST123', 25.00, NULL, 9999, 0, true, NULL);

-- 6. Новогодний промокод
INSERT INTO promo_codes (code, balance_reward, withdrawal_requirement, max_uses, current_uses, is_active, expires_at) 
VALUES ('NEWYEAR2025', 2025.00, 1000.00, 2025, 0, true, '2025-02-01'::timestamp);

-- Проверка созданных промокодов
SELECT 
    code,
    balance_reward,
    withdrawal_requirement,
    max_uses,
    current_uses,
    is_active,
    expires_at,
    created_at
FROM promo_codes
ORDER BY created_at DESC;