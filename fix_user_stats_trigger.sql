-- Исправление триггера user_stats для правильного подсчета всех игр
-- Проблема: total_games увеличивался только при победах в определенных случаях
-- Решение: total_games должно увеличиваться на 1 при каждой игре (победе или поражении)

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
    
    -- 🔒 ИСПРАВЛЕНО: Правильная логика подсчета игр - каждая игра увеличивает total_games на 1
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
        -- 🔒 ИСПРАВЛЕНО: При выигрыше ВСЕГДА увеличиваем total_games на 1
        -- Каждая игра (победа или поражение) должна увеличивать общее количество игр
        INSERT INTO user_stats (user_id, total_games, games_won, games_lost, total_wagered, total_won, wagered_balance, best_multiplier, avg_multiplier)
        VALUES (NEW.user_id, 1, 1, 0, 0, win_amount, win_amount, COALESCE(NEW.multiplier, 0), new_avg_multiplier)
        ON CONFLICT (user_id) DO UPDATE SET
            -- 🔒 ИСПРАВЛЕНО: ВСЕГДА увеличиваем total_games на 1 при каждой игре
            total_games = user_stats.total_games + 1,
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

-- Триггер уже существует, функция будет обновлена автоматически