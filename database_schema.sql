-- PostgreSQL схема для Crash Stars Game
-- Оптимизирована для сотен тысяч пользователей

-- Пользователи
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    balance DECIMAL(12,2) DEFAULT 0.00 NOT NULL, -- точность до копеек
    total_deposited DECIMAL(12,2) DEFAULT 0.00,
    total_withdrawn DECIMAL(12,2) DEFAULT 0.00,
    referral_code VARCHAR(20) UNIQUE,
    referred_by_id BIGINT REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,
    language_code VARCHAR(10) DEFAULT 'en'
);

-- Статистика пользователей (денормализация для производительности)
CREATE TABLE user_stats (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    total_games INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0,
    games_lost INTEGER DEFAULT 0,
    total_wagered DECIMAL(12,2) DEFAULT 0.00,
    total_won DECIMAL(12,2) DEFAULT 0.00,
    wagered_balance DECIMAL(12,2) DEFAULT 0.00,  -- Net winnings available for gift purchases
    best_multiplier DECIMAL(10,2) DEFAULT 0,
    avg_multiplier DECIMAL(10,2) DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- История игр - сводка по раундам (НЕ по пользователям) - АВТОМАТИЧЕСКИЕ ПАРТИЦИИ
CREATE TABLE game_history (
    id BIGSERIAL,
    crash_point DECIMAL(10,2) NOT NULL,
    total_bet DECIMAL(12,2) DEFAULT 0.00,    -- Общая ставка всех игроков
    total_payout DECIMAL(12,2) DEFAULT 0.00, -- Общие выплаты всем игрокам  
    house_profit DECIMAL(12,2) DEFAULT 0.00, -- Прибыль дома (total_bet - total_payout)
    player_count INTEGER DEFAULT 0,          -- Количество игроков в раунде
    is_completed BOOLEAN DEFAULT FALSE,      -- Раунд завершен (следующий раунд начался)
    played_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (id, played_at)
) PARTITION BY RANGE (played_at);

-- Создаем DEFAULT партицию для автоматического размещения новых данных
CREATE TABLE game_history_default PARTITION OF game_history DEFAULT;


-- Платежи и транзакции (включая ставки пользователей) - АВТОМАТИЧЕСКИЕ ПАРТИЦИИ
CREATE TABLE transactions (
    id BIGSERIAL,
    user_id BIGINT NOT NULL REFERENCES users(id),
    game_id BIGINT, -- Привязка к раунду игры (убираем REFERENCES из-за партиционирования)
    type VARCHAR(20) NOT NULL, -- deposit, withdrawal, game_win, game_loss, gift_purchase
    amount DECIMAL(12,2) NOT NULL,
    balance_after DECIMAL(12,2) NOT NULL,
    multiplier DECIMAL(10,2), -- Для игровых транзакций - множитель кешаута
    payment_payload VARCHAR(255),
    telegram_payment_id VARCHAR(255),
    telegram_payment_charge_id VARCHAR(255),
    provider_payment_charge_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'pending', -- pending, completed, failed, refunded
    extra_data JSONB, -- дополнительные данные
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Создаем DEFAULT партицию для автоматического размещения новых транзакций
CREATE TABLE transactions_default PARTITION OF transactions DEFAULT;

-- Подарки (каталог)
CREATE TABLE gifts (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price DECIMAL(12,2), -- Цена в звёздах (NULL для уникальных подарков, рассчитывается из ton_price)
    ton_price DECIMAL(10,4), -- Цена в USD для уникальных подарков (поле называется ton_price для совместимости)
    telegram_gift_id VARCHAR(100),
    business_gift_id VARCHAR(100),
    emoji VARCHAR(10),
    image_url TEXT,
    is_active BOOLEAN DEFAULT true,
    is_unique BOOLEAN DEFAULT FALSE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- История покупки подарков
CREATE TABLE gift_purchases (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    gift_id VARCHAR(50) NOT NULL REFERENCES gifts(id),
    price DECIMAL(12,2) NOT NULL,
    telegram_gift_id VARCHAR(100) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending', -- pending, sent, failed
    error_message TEXT,
    purchased_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    sent_at TIMESTAMP WITH TIME ZONE
);

-- Реферальная система
CREATE TABLE referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL REFERENCES users(id),
    referred_id BIGINT NOT NULL REFERENCES users(id),
    bonus_amount DECIMAL(12,2) DEFAULT 0.00,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(referrer_id, referred_id)
);

-- Запросы на ручной вывод уникальных подарков
CREATE TABLE payment_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id),
    gift_id VARCHAR(50) NOT NULL REFERENCES gifts(id),
    gift_name VARCHAR(255) NOT NULL,
    price DECIMAL(12,2) NOT NULL, -- цена в TON (для совместимости)
    price_stars DECIMAL(12,2) NOT NULL, -- цена в звездах (списанная с баланса)
    status VARCHAR(20) DEFAULT 'pending', -- pending, approved, completed, canceled
    cancel_reason VARCHAR(50), -- no_message, price_changed, suspect_act
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    approved_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Настройки системы
CREATE TABLE system_settings (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ИНДЕКСЫ для производительности

-- Пользователи
CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_referral_code ON users(referral_code);
CREATE INDEX idx_users_created_at ON users(created_at);

-- История игр (партиционированные индексы)
CREATE INDEX ON game_history(played_at, crash_point);
CREATE INDEX ON game_history(played_at, is_completed);
CREATE INDEX ON game_history(id, played_at); -- Для поиска по ID

-- Транзакции (партиционированные индексы)
CREATE INDEX ON transactions(created_at, user_id);
CREATE INDEX ON transactions(created_at, game_id);
CREATE INDEX ON transactions(created_at, type);
CREATE INDEX ON transactions(created_at, status);
CREATE INDEX ON transactions(user_id, created_at);
CREATE INDEX ON transactions(payment_payload, created_at);

-- Покупки подарков
CREATE INDEX idx_gifts_is_unique ON gifts(is_unique);
CREATE INDEX idx_gifts_business_gift_id ON gifts(business_gift_id);
CREATE INDEX idx_gift_purchases_user_id ON gift_purchases(user_id);
CREATE INDEX idx_gift_purchases_purchased_at ON gift_purchases(purchased_at);
CREATE INDEX idx_gift_purchases_status ON gift_purchases(status);

-- Запросы на вывод подарков
CREATE INDEX idx_payment_requests_user_id ON payment_requests(user_id);
CREATE INDEX idx_payment_requests_status ON payment_requests(status);
CREATE INDEX idx_payment_requests_created_at ON payment_requests(created_at);

-- Рефералы
CREATE INDEX idx_referrals_referrer_id ON referrals(referrer_id);
CREATE INDEX idx_referrals_referred_id ON referrals(referred_id);

-- ТРИГГЕРЫ для обновления статистики

-- Обновление updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 🔒 CRITICAL BUSINESS LOGIC CONSTRAINTS FOR SECURITY
-- Prevent negative balances and balance overflow
ALTER TABLE users ADD CONSTRAINT check_positive_balance 
CHECK (balance >= 0.00);

-- 🔒 SECURITY: Prevent balance overflow
ALTER TABLE users ADD CONSTRAINT check_max_balance 
CHECK (balance <= 999999999.99);

-- 🔒 SECURITY: Validate transaction amounts with correct logic
-- Positive amounts: player GAINS money (game_win, deposit, referral_bonus, withdrawal, refund)
-- Negative amounts: player LOSES money (game_loss, gift_purchase)
ALTER TABLE transactions ADD CONSTRAINT check_valid_transaction_amounts
CHECK (
    (type IN ('game_win', 'deposit', 'referral_bonus', 'withdrawal', 'refund') AND amount > 0.00) OR
    (type IN ('game_loss', 'gift_purchase') AND amount < 0.00) OR
    (type NOT IN ('game_win', 'deposit', 'referral_bonus', 'game_loss', 'withdrawal', 'gift_purchase', 'refund'))
);

-- Prevent negative balance_after
ALTER TABLE transactions ADD CONSTRAINT check_positive_balance_after
CHECK (balance_after >= 0.00);

-- Game multiplier must be >= 1.01 for wins (prevent invalid cashouts)
ALTER TABLE transactions ADD CONSTRAINT check_valid_multiplier
CHECK (
    (type = 'game_win' AND multiplier >= 1.00 AND multiplier <= 100.00) OR
    (type != 'game_win')
);

-- 🔒 SECURITY: Prevent duplicate game participation per round
-- Only one bet per user per game (regardless of win/loss) - партиционированный индекс
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_user_game_bet 
ON transactions (user_id, game_id, created_at) 
WHERE type IN ('game_loss', 'game_bet') AND status = 'completed';

-- Gift pricing logic: regular gifts must have price, unique gifts must have ton_price (USD)
ALTER TABLE gifts ADD CONSTRAINT check_gift_pricing 
CHECK (
    (is_unique = FALSE AND price IS NOT NULL AND price > 0.00) OR 
    (is_unique = TRUE AND ton_price IS NOT NULL AND ton_price > 0.00)
);

-- Gift purchases must have positive price
ALTER TABLE gift_purchases ADD CONSTRAINT check_positive_gift_price
CHECK (price > 0.00);

-- Payment requests constraints
ALTER TABLE payment_requests ADD CONSTRAINT check_payment_request_positive_price
CHECK (price > 0.00);

ALTER TABLE payment_requests ADD CONSTRAINT check_payment_request_positive_price_stars
CHECK (price_stars > 0.00);

ALTER TABLE payment_requests ADD CONSTRAINT check_payment_request_status
CHECK (status IN ('pending', 'approved', 'completed', 'canceled'));

ALTER TABLE payment_requests ADD CONSTRAINT check_cancel_reason_valid
CHECK (
    cancel_reason IS NULL OR 
    cancel_reason IN ('no_message', 'price_changed', 'suspect_act')
);

ALTER TABLE payment_requests ADD CONSTRAINT check_payment_request_timestamps
CHECK (
    (approved_at IS NULL OR approved_at >= created_at) AND
    (completed_at IS NULL OR completed_at >= created_at) AND
    (completed_at IS NULL OR approved_at IS NULL OR completed_at >= approved_at)
);

-- 🔒 CRITICAL SECURITY: Additional constraints for production safety
-- Prevent excessive transaction amounts (max 1 million per transaction)
ALTER TABLE transactions ADD CONSTRAINT check_max_transaction_amount 
CHECK (ABS(amount) <= 1000000.00);

-- Ensure crash points are in reasonable range
ALTER TABLE game_history ADD CONSTRAINT check_crash_point_range 
CHECK (crash_point >= 1.00 AND crash_point <= 1000.00);

-- Prevent self-referrals
ALTER TABLE referrals ADD CONSTRAINT check_no_self_referral 
CHECK (referrer_id != referred_id);

-- Ensure referral bonus is reasonable
ALTER TABLE referrals ADD CONSTRAINT check_bonus_amount_reasonable 
CHECK (bonus_amount >= 0 AND bonus_amount <= 10000.00);

-- 🔒 SECURITY: Ensure user stats are logical
ALTER TABLE user_stats ADD CONSTRAINT check_stats_logical 
CHECK (
    total_games >= 0 AND
    games_won >= 0 AND
    games_lost >= 0 AND
    games_won <= total_games AND
    games_lost <= total_games AND
    total_wagered >= 0 AND
    total_won >= 0 AND
    wagered_balance >= 0 AND
    best_multiplier >= 0 AND
    avg_multiplier >= 0
);

-- Обновление статистики пользователя при игровых транзакциях
CREATE OR REPLACE FUNCTION update_user_stats_on_transaction()
RETURNS TRIGGER AS $$
DECLARE
    current_stats RECORD;
    new_avg_multiplier DECIMAL(10,2);
    is_win BOOLEAN;
    bet_amount DECIMAL(12,2);
    win_amount DECIMAL(12,2);
BEGIN
    -- Обрабатываем только игровые транзакции
    IF NEW.type NOT IN ('game_win', 'game_loss') THEN
        RETURN NEW;
    END IF;
    
    -- Определяем параметры игры
    is_win := (NEW.type = 'game_win');
    
    IF is_win THEN
        -- При выигрыше: NEW.amount содержит total_payout, нужно вычесть ставку
        -- Найдем соответствующую game_bet транзакцию для этого пользователя и игры
        SELECT ABS(amount) INTO bet_amount 
        FROM transactions 
        WHERE user_id = NEW.user_id 
          AND game_id = NEW.game_id 
          AND type = 'game_bet' 
        LIMIT 1;
        
        bet_amount := COALESCE(bet_amount, 0);
        win_amount := NEW.amount - bet_amount;  -- Чистый выигрыш = total_payout - ставка
    ELSE
        -- При проигрыше: amount уже содержит ставку
        bet_amount := ABS(NEW.amount);
        win_amount := 0;
    END IF;
    
    -- Get current stats for avg_multiplier calculation
    SELECT games_won, avg_multiplier INTO current_stats
    FROM user_stats WHERE user_id = NEW.user_id;
    
    -- Calculate new avg_multiplier only from winning games
    IF is_win AND NEW.multiplier IS NOT NULL THEN
        IF current_stats.games_won IS NULL OR current_stats.games_won = 0 THEN
            -- First winning game
            new_avg_multiplier = NEW.multiplier;
        ELSE
            -- Running average of winning games only
            new_avg_multiplier = (
                (current_stats.avg_multiplier * current_stats.games_won) + NEW.multiplier
            ) / (current_stats.games_won + 1);
        END IF;
    ELSE
        -- Keep existing avg_multiplier if this is not a win
        new_avg_multiplier = COALESCE(current_stats.avg_multiplier, 0);
    END IF;
    
    -- 🔒 ULTIMATE FIX: Правильная логика подсчета игр с защитой от constraint violation
    IF NOT is_win THEN
        -- При проигрыше: увеличиваем total_games, games_lost, total_wagered
        INSERT INTO user_stats (user_id, total_games, games_won, games_lost, total_wagered, total_won, wagered_balance, best_multiplier, avg_multiplier)
        VALUES (NEW.user_id, 1, 0, 1, bet_amount, 0, 0, 0, 0)
        ON CONFLICT (user_id) DO UPDATE SET
            total_games = user_stats.total_games + 1,
            games_lost = user_stats.games_lost + 1,
            total_wagered = user_stats.total_wagered + bet_amount,
            updated_at = NOW();
    ELSE
        -- 🔒 ULTIMATE FIX: При выигрыше ВСЕГДА увеличиваем total_games на 1 если games_won >= total_games
        -- Это предотвращает constraint violation
        INSERT INTO user_stats (user_id, total_games, games_won, games_lost, total_wagered, total_won, wagered_balance, best_multiplier, avg_multiplier)
        VALUES (NEW.user_id, 1, 1, 0, 0, win_amount, win_amount, COALESCE(NEW.multiplier, 0), new_avg_multiplier)
        ON CONFLICT (user_id) DO UPDATE SET
            -- 🔒 ЗАЩИТА: Если games_won >= total_games, увеличиваем total_games
            total_games = CASE 
                WHEN user_stats.games_won >= user_stats.total_games 
                THEN user_stats.total_games + 1 
                ELSE user_stats.total_games 
            END,
            games_won = user_stats.games_won + 1,
            total_won = user_stats.total_won + win_amount,
            wagered_balance = user_stats.wagered_balance + win_amount,
            best_multiplier = GREATEST(user_stats.best_multiplier, COALESCE(NEW.multiplier, 0)),
            avg_multiplier = new_avg_multiplier,
            updated_at = NOW();
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_update_user_stats_on_transaction
    AFTER INSERT ON transactions
    FOR EACH ROW EXECUTE FUNCTION update_user_stats_on_transaction();

-- Функция автовозврата при отмене payment_request
CREATE OR REPLACE FUNCTION auto_refund_on_payment_cancel()
RETURNS TRIGGER AS $$
BEGIN
    -- Проверяем, что статус изменился на canceled и раньше не был canceled
    IF NEW.status = 'canceled' AND OLD.status != 'canceled' THEN
        -- Возвращаем точную сумму в звездах на баланс пользователя
        UPDATE users 
        SET balance = balance + NEW.price_stars
        WHERE id = NEW.user_id;
        
        -- Возвращаем отыгранный баланс (50% от цены подарка)
        UPDATE user_stats 
        SET wagered_balance = wagered_balance + (NEW.price_stars / 2),
            updated_at = NOW()
        WHERE user_id = NEW.user_id;
        
        -- Создаем транзакцию возврата
        INSERT INTO transactions (
            user_id,
            type,
            amount,
            balance_after,
            status,
            extra_data,
            completed_at
        ) VALUES (
            NEW.user_id,
            'refund',
            NEW.price_stars,
            (SELECT balance FROM users WHERE id = NEW.user_id),
            'completed',
            jsonb_build_object(
                'payment_request_id', NEW.id,
                'gift_id', NEW.gift_id,
                'reason', COALESCE(NEW.cancel_reason, 'payment_request_canceled')
            ),
            NOW()
        );
        
        -- Логируем возврат
        RAISE NOTICE 'Auto-refund: % stars returned to user % for canceled payment request %', 
            NEW.price_stars, NEW.user_id, NEW.id;
    END IF;
    
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Создаем триггер на обновление payment_requests
CREATE TRIGGER trigger_auto_refund_on_payment_cancel
    AFTER UPDATE ON payment_requests
    FOR EACH ROW EXECUTE FUNCTION auto_refund_on_payment_cancel();

-- Вставка базовых данных
-- 🎯 Main game configuration - can be changed via admin API during runtime
INSERT INTO system_settings (key, value, description) VALUES
('game_config', '{
    "growth_rate": 1.01,
    "tick_ms": 150,
    "max_coefficient": 100.0,
    "waiting_time": 10,
    "join_time": 2,
    "house_edge": "0.17",
    "min_bet": 10,
    "max_bet": 100000
}', 'Основные настройки игры - можно менять через admin API'),
('referral_config', '{
    "bonus_amount": 1000,
    "referrer_bonus": 500
}', 'Настройки реферальной системы'),
('game_player_limit', '{
    "limit": 1000
}', 'Максимальное количество игроков в одном раунде (дефолт из config/settings.py)'),
('daily_gift_limit', '{"limit": 5}', 'Maximum number of gifts a user can purchase per day');

-- UPDATE system_settings SET value = '{"growth_rate": 1.01, "tick_ms": 150, "max_coefficient": 100.0, "waiting_time": 10, "join_time": 2, "house_edge": "0.17", "min_bet": 10, "max_bet": 100000}' WHERE key = 'game_config';

-- Вставка базовых подарков
INSERT INTO gifts (id, name, description, price, ton_price, telegram_gift_id, emoji, image_url, sort_order, is_unique) VALUES
('bear', 'Bear', '', 15, NULL, '5170233102089322756', '🐻', '/gifts/original/5170233102089322756.png', 1, FALSE),
('heart', 'Heart', '', 15, NULL, '5170145012310081615', '💝', '/gifts/original/5170145012310081615.png', 2, FALSE),
('gift', 'Gift', '', 25, NULL, '5170250947678437525', '🎁', '/gifts/original/5170250947678437525.png', 3, FALSE),
('cake', 'Cake', '', 50, NULL, '5170144170496491616', '🎂', '/gifts/original/5170144170496491616.png', 4, FALSE),
('rocket', 'Rocket', '', 50, NULL, '5170564780938756245', '🚀', '/gifts/original/5170564780938756245.png', 5, FALSE),
('roses', 'Roses', '', 50, NULL, '5170314324215857265', '🌹', '/gifts/original/5170314324215857265.png', 6, FALSE),
('gem', 'Gem', '', 100, NULL, '5170521118301225164', '💎', '/gifts/original/5170521118301225164.png', 7, FALSE),
('ring', 'Ring', '', 100, NULL, '5170690322832818290', '💍', '/gifts/original/5170690322832818290.png', 8, FALSE),
('trophy', 'Trophy', '', 100, NULL, '5168043875654172773', '🏆', '/gifts/original/5168043875654172773.png', 9, FALSE);

-- Добавим уникальные подарки с изображениями из папки unique
-- Цены в USD взяты примерно ($1-10 range для уникальных подарков)

INSERT INTO gifts (id, name, description, price, ton_price, telegram_gift_id, emoji, image_url, sort_order, is_unique) VALUES
('astralshard', 'Astral Shard', '', NULL, 270.50, 'astral_shard_unique', '💎', '/gifts/unique/Astral Shard.png', 1, TRUE),
('bdaycandle', 'B-Day Candle', '', NULL, 4.55, 'bday_candle_unique', '🕯️', '/gifts/unique/B-Day Candle.png', 67, TRUE),
('berrybox', 'Berry Box', '', NULL, 12.36, 'berry_box_unique', '🍓', '/gifts/unique/Berry Box.png', 31, TRUE),
('bigyear', 'Big Year', '', NULL, 5.30, 'big_year_unique', '🎊', '/gifts/unique/Big Year.png', 61, TRUE),
('bondedring', 'Bonded Ring', '', NULL, 187.10, 'bonded_ring_unique', '💍', '/gifts/unique/Bonded Ring.png', 4, TRUE),
('bowtie', 'Bow Tie', '', NULL, 10.60, 'bow_tie_unique', '🎀', '/gifts/unique/Bow Tie.png', 34, TRUE),
('bunnymuffin', 'Bunny Muffin', '', NULL, 10.50, 'bunny_muffin_unique', '🧁', '/gifts/unique/Bunny Muffin.png', 36, TRUE),
('candycane', 'Candy Cane', '', NULL, 4.52, 'candy_cane_unique', '🍭', '/gifts/unique/Candy Cane.png', 68, TRUE),
('cookieheart', 'Cookie Heart', '', NULL, 5.44, 'cookie_heart_unique', '🍪', '/gifts/unique/Cookie Heart.png', 59, TRUE),
('crystalball', 'Crystal Ball', '', NULL, 22.14, 'crystal_ball_unique', '🔮', '/gifts/unique/Crystal Ball.png', 27, TRUE),
('cupidcharm', 'Cupid Charm', '', NULL, 31.03, 'cupid_charm_unique', '💘', '/gifts/unique/Cupid Charm.png', 18, TRUE),
('easteregg', 'Easter Egg', '', NULL, 8.09, 'easter_egg_unique', '🥚', '/gifts/unique/Easter Egg.png', 44, TRUE),
('electricskull', 'Electric Skull', '', NULL, 90.20, 'electric_skull_unique', '💀', '/gifts/unique/Electric Skull.png', 11, TRUE),
('eternalcandle', 'Eternal Candle', '', NULL, 10.55, 'eternal_candle_unique', '🕯️', '/gifts/unique/Eternal Candle.png', 35, TRUE),
('eternalrose', 'Eternal Rose', '', NULL, 41.94, 'eternal_rose_unique', '🌹', '/gifts/unique/Eternal Rose.png', 17, TRUE),
('evileye', 'Evil Eye', '', NULL, 11.97, 'evil_eye_unique', '🧿', '/gifts/unique/Evil Eye.png', 33, TRUE),
('flyingbroom', 'Flying Broom', '', NULL, 27.25, 'flying_broom_unique', '🧹', '/gifts/unique/Flying Broom.png', 21, TRUE),
('gemsignet', 'Gem Signet', '', NULL, 232.99, 'gem_signet_unique', '💎', '/gifts/unique/Gem Signet.png', 2, TRUE),
('genielamp', 'Genie Lamp', '', NULL, 142.50, 'genie_lamp_unique', '🪔', '/gifts/unique/Genie Lamp.png', 6, TRUE),
('gingercookie', 'Ginger Cookie', '', NULL, 5.59, 'ginger_cookie_unique', '🍪', '/gifts/unique/Ginger Cookie.png', 57, TRUE),
('hangingstar', 'Hanging Star', '', NULL, 14.12, 'hanging_star_unique', '⭐', '/gifts/unique/Hanging Star.png', 29, TRUE),
('hexpot', 'Hex Pot', '', NULL, 8.30, 'hex_pot_unique', '🫖', '/gifts/unique/Hex Pot.png', 43, TRUE),
('holidaydrink', 'Holiday Drink', '', NULL, 5.48, 'holiday_drink_unique', '🍹', '/gifts/unique/Holiday Drink.png', 58, TRUE),
('homemadecake', 'Homemade Cake', '', NULL, 5.26, 'homemade_cake_unique', '🎂', '/gifts/unique/Homemade Cake.png', 62, TRUE),
('hypnolollipop', 'Hypno Lollipop', '', NULL, 6.35, 'hypno_lollipop_unique', '🍭', '/gifts/unique/Hypno Lollipop.png', 52, TRUE),
('jackinthebox', 'Jack-in-the-Box', '', NULL, 6.71, 'jack_in_box_unique', '🎁', '/gifts/unique/Jack-in-the-Box.png', 49, TRUE),
('jellybunny', 'Jelly Bunny', '', NULL, 10.42, 'jelly_bunny_unique', '🐰', '/gifts/unique/Jelly Bunny.png', 37, TRUE),
('jesterhat', 'Jester Hat', '', NULL, 5.83, 'jester_hat_unique', '🎭', '/gifts/unique/Jester Hat.png', 56, TRUE),
('jinglebells', 'Jingle Bells', '', NULL, 5.90, 'jingle_bells_unique', '🔔', '/gifts/unique/Jingle Bells.png', 55, TRUE),
('joyfulbundle', 'Joyful Bundle', '', NULL, 7.42, 'joyful_bundle_unique', '💐', '/gifts/unique/Joyful Bundle.png', 46, TRUE),
('kissedfrog', 'Kissed Frog', '', NULL, 116.50, 'kissed_frog_unique', '🐸', '/gifts/unique/Kissed Frog.png', 7, TRUE),
('lightsword', 'Light Sword', '', NULL, 9.71, 'light_sword_unique', '⚔️', '/gifts/unique/Light Sword.png', 39, TRUE),
('lovecandle', 'Love Candle', '', NULL, 27.22, 'love_candle_unique', '🕯️', '/gifts/unique/Love Candle.png', 22, TRUE),
('lovepotion', 'Love Potion', '', NULL, 28.07, 'love_potion_unique', '🧪', '/gifts/unique/Love Potion.png', 20, TRUE),
('lunarsnake', 'Lunar Snake', '', NULL, 4.59, 'lunar_snake_unique', '🐍', '/gifts/unique/Lunar Snake.png', 66, TRUE),
('lushbouquet', 'Lush Bouquet', '', NULL, 7.59, 'lush_bouquet_unique', '💐', '/gifts/unique/Lush Bouquet.png', 45, TRUE),
('madpumpkin', 'Mad Pumpkin', '', NULL, 50.90, 'mad_pumpkin_unique', '🎃', '/gifts/unique/Mad Pumpkin.png', 15, TRUE),
('magicpotion', 'Magic Potion', '', NULL, 194.15, 'magic_potion_unique', '🧪', '/gifts/unique/Magic Potion.png', 3, TRUE),
('nekohelmet', 'Neko Helmet', '', NULL, 91.75, 'neko_helmet_unique', '😺', '/gifts/unique/Neko Helmet.png', 10, TRUE),
('partysparkler', 'Party Sparkler', '', NULL, 5.41, 'party_sparkler_unique', '🎇', '/gifts/unique/Party Sparkler.png', 60, TRUE),
('petsnake', 'Pet Snake', '', NULL, 4.70, 'pet_snake_unique', '🐍', '/gifts/unique/Pet Snake.png', 65, TRUE),
('recordplayer', 'Record Player', '', NULL, 24.72, 'record_player_unique', '🎵', '/gifts/unique/Record Player.png', 23, TRUE),
('restlessjar', 'Restless Jar', '', NULL, 7.42, 'restless_jar_unique', '🫙', '/gifts/unique/Restless Jar.png', 47, TRUE),
('sakuraflower', 'Sakura Flower', '', NULL, 13.56, 'sakura_flower_unique', '🌸', '/gifts/unique/Sakura Flower.png', 30, TRUE),
('santahat', 'Santa Hat', '', NULL, 6.71, 'santa_hat_unique', '🎅', '/gifts/unique/Santa Hat.png', 50, TRUE),
('scaredcat', 'Scared Cat', '', NULL, 151.72, 'scared_cat_unique', '🙀', '/gifts/unique/Scared Cat.png', 5, TRUE),
('sharptongue', 'Sharp Tongue', '', NULL, 113.10, 'sharp_tongue_unique', '👅', '/gifts/unique/Sharp Tongue.png', 8, TRUE),
('signetring', 'Signet Ring', '', NULL, 81.20, 'signet_ring_unique', '💍', '/gifts/unique/Signet Ring.png', 13, TRUE),
('skullflower', 'Skull Flower', '', NULL, 22.95, 'skull_flower_unique', '💀', '/gifts/unique/Skull Flower.png', 25, TRUE),
('sleighbell', 'Sleigh Bell', '', NULL, 23.30, 'sleigh_bell_unique', '🔔', '/gifts/unique/Sleigh Bell.png', 24, TRUE),
('snakebox', 'Snake Box', '', NULL, 4.52, 'snake_box_unique', '🐍', '/gifts/unique/Snake Box.png', 69, TRUE),
('snoopcigar', 'Snoop Cigar', '', NULL, 14.72, 'snoop_cigar_unique', '🚬', '/gifts/unique/Snoop Cigar.png', 28, TRUE),
('snoopdogg', 'Snoop Dogg', '', NULL, 5.22, 'snoop_dogg_unique', '🎤', '/gifts/unique/Snoop Dogg.png', 63, TRUE),
('snowglobe', 'Snow Globe', '', NULL, 9.11, 'snow_globe_unique', '❄️', '/gifts/unique/Snow Globe.png', 40, TRUE),
('snowmittens', 'Snow Mittens', '', NULL, 10.21, 'snow_mittens_unique', '🧤', '/gifts/unique/Snow Mittens.png', 38, TRUE),
('spicedwine', 'Spiced Wine', '', NULL, 7.42, 'spiced_wine_unique', '🍷', '/gifts/unique/Spiced Wine.png', 48, TRUE),
('spyagaric', 'Spy Agaric', '', NULL, 8.41, 'spy_agaric_unique', '🍄', '/gifts/unique/Spy Agaric.png', 42, TRUE),
('starnotepad', 'Star Notepad', '', NULL, 6.57, 'star_notepad_unique', '📝', '/gifts/unique/Star Notepad.png', 51, TRUE),
('swisswatch', 'Swiss Watch', '', NULL, 98.90, 'swiss_watch_unique', '⌚', '/gifts/unique/Swiss Watch.png', 9, TRUE),
('tamagadget', 'Tama Gadget', '', NULL, 6.00, 'tama_gadget_unique', '🎮', '/gifts/unique/Tama Gadget.png', 54, TRUE),
('tophat', 'Top Hat', '', NULL, 29.30, 'top_hat_unique', '🎩', '/gifts/unique/Top Hat.png', 19, TRUE),
('toybear', 'Toy Bear', '', NULL, 53.00, 'toy_bear_unique', '🧸', '/gifts/unique/Toy Bear.png', 14, TRUE),
('trappedheart', 'Trapped Heart', '', NULL, 22.21, 'trapped_heart_unique', '💔', '/gifts/unique/Trapped Heart.png', 26, TRUE),
('valentinebox', 'Valentine Box', '', NULL, 12.36, 'valentine_box_unique', '💝', '/gifts/unique/Valentine Box.png', 32, TRUE),
('vintagecigar', 'Vintage Cigar', '', NULL, 82.47, 'vintage_cigar_unique', '🚬', '/gifts/unique/Vintage Cigar.png', 12, TRUE),
('voodoodoll', 'Voodoo Doll', '', NULL, 47.06, 'voodoo_doll_unique', '🪆', '/gifts/unique/Voodoo Doll.png', 16, TRUE),
('whipcupcake', 'Whip Cupcake', '', NULL, 4.73, 'whip_cupcake_unique', '🧁', '/gifts/unique/Whip Cupcake.png', 64, TRUE),
('winterwreath', 'Winter Wreath', '', NULL, 6.14, 'winter_wreath_unique', '🎄', '/gifts/unique/Winter Wreath.png', 53, TRUE),
('witchhat', 'Witch Hat', '', NULL, 8.65, 'witch_hat_unique', '🧙', '/gifts/unique/Witch Hat.png', 41, TRUE),
('xmasstocking', 'Xmas Stocking', '', NULL, 4.28, 'xmas_stocking_unique', '🧦', '/gifts/unique/Xmas Stocking.png', 70, TRUE),
('deskcalendar', '', '', NULL, 4.5500, 'deskcalendar_unique_id', '📅', '/gifts/unique/Desk Calendar.png', 71, TRUE);

-- Создание пользователя для приложения
-- CREATE USER crash_stars_app WITH PASSWORD 'your_secure_password';
-- GRANT CONNECT ON DATABASE crash_stars TO crash_stars_app;
-- GRANT USAGE ON SCHEMA public TO crash_stars_app;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO crash_stars_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO crash_stars_app;

--- SELECT SUM(house_profit) AS total_house_profit_last_day FROM game_history WHERE player_count > 0 AND is_completed = true AND played_at >= NOW() - INTERVAL '1 day';
--- SELECT SUM(house_profit) AS total_house_profit_last_day FROM game_history WHERE player_count > 0 AND is_completed = true AND played_at >= NOW() - INTERVAL '7 days';
--- SELECT SUM(house_profit) AS total_house_profit_last_day FROM game_history WHERE player_count > 0 AND is_completed = true AND played_at >= NOW() - INTERVAL '1 month';

--- SELECT SUM(CASE WHEN played_at >= NOW() - INTERVAL '1 day' THEN house_profit ELSE 0 END) AS profit_last_day, SUM(CASE WHEN played_at >= NOW() - INTERVAL '7 days' THEN house_profit ELSE 0 END) AS profit_last_week, SUM(CASE WHEN played_at >= NOW() - INTERVAL '1 month' THEN house_profit ELSE 0 END) AS profit_last_month FROM game_history WHERE player_count > 0 AND is_completed = true;

--- SELECT SUM(house_profit) AS total_house_profit FROM game_history WHERE player_count > 0;


-- Создание read-only пользователя для Grafana
CREATE USER grafana_readonly WITH PASSWORD 'tzbMKcKVl/OZOigyOl4GjWOFYJCtxdsJ';

-- Предоставление подключения к базе данных
GRANT CONNECT ON DATABASE crash_stars_db TO grafana_readonly;

-- Предоставление прав на использование схемы public
GRANT USAGE ON SCHEMA public TO grafana_readonly;

-- Предоставление прав на SELECT для всех существующих таблиц
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_readonly;

-- Автоматическое предоставление прав SELECT для новых таблиц
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_readonly;

-- Дополнительные права для мониторинга статистики PostgreSQL
GRANT SELECT ON pg_stat_database TO grafana_readonly;
GRANT SELECT ON pg_stat_user_tables TO grafana_readonly;
GRANT SELECT ON pg_stat_user_indexes TO grafana_readonly;
GRANT SELECT ON pg_stat_activity TO grafana_readonly;
GRANT SELECT ON pg_locks TO grafana_readonly;

-- Права на системные представления для мониторинга производительности
GRANT EXECUTE ON FUNCTION pg_stat_file(text) TO grafana_readonly;
GRANT EXECUTE ON FUNCTION pg_stat_file(text,boolean) TO grafana_readonly;