import hashlib
import secrets
import time
from decimal import Decimal, getcontext, ROUND_DOWN
from typing import List, Dict, Any, Optional
import os
from tqdm import tqdm

# Установка точности decimal
getcontext().prec = 10

# 🔧 Конфигурация crash-игры (вместо внешнего GAME_CONFIG)
CRASH_RANGES = [
  ]


class CrashGenerator:
    def __init__(self, house_edge: Decimal = Decimal('0.09')):
        """
        Математически корректный генератор с двумя методами:
        
        1. "truncated" - Усеченное экспоненциальное распределение
        2. "pareto" - Парето распределение с конечным средним
        """
        self.house_edge = house_edge
        self.rtp = Decimal('1.0') - house_edge
        
        # Усеченное распределение: ограничиваем максимум для конечного среднего
        self.max_multiplier = Decimal('1000.0')  # Максимум 1000x
        # Вычисляем корректировочный коэффициент для желаемого RTP
        self._calculate_truncated_coefficient()
    
    def _calculate_truncated_coefficient(self):
        """Вычисляем коэффициент для получения нужного RTP при усечении"""
        # Приблизительное вычисление для коэффициента коррекции
        # Основано на том, что среднее усеченного 1/x примерно ln(max_mult)
        import math
        expected_avg_raw = math.log(float(self.max_multiplier))
        # Коэффициент для получения желаемого RTP
        self.truncated_coeff = self.rtp * Decimal(str(expected_avg_raw))

    def generate_crash_point(self, client_entropy: Optional[str] = None) -> Decimal:
        entropy = secrets.token_hex(32)
        if client_entropy:
            entropy += f"|{client_entropy}"
        hash_val = hashlib.sha256(entropy.encode()).hexdigest()
        int_val = int(hash_val[:13], 16)
        rand = Decimal(int_val) / Decimal(16 ** 13)
        
        # Защита от краевых случаев
        if rand <= Decimal('1e-13'):
            rand = Decimal('1e-13')
        if rand >= Decimal('0.999999'):
            rand = Decimal('0.999999')
        
        # Двухуровневая система для редких высоких множителей
        
        # Вероятность получить "обычный" crash (1x-10x) vs "высокий" (10x-100x)
        high_mult_probability = Decimal('0.02')  # Только 2% шанс на высокие множители
        medium_mult_probability = Decimal('0.045') # Только 1.5% шанс на средние множители
        
        if rand < high_mult_probability:
            # РЕДКИЕ высокие множители (10x-100x)
            # Используем оставшуюся часть rand для генерации в диапазоне 10-100
            high_rand = (rand / high_mult_probability)  # Нормализуем к [0,1)
            if high_rand <= Decimal('1e-13'):
                high_rand = Decimal('1e-13')
            
            # Генерируем от 10 до 100 с правильным логарифмическим распределением
            # Используем логарифмическое распределение для равномерного покрытия диапазона
            import math
            log_min = math.log(10.0)   # ln(10) ≈ 2.30
            log_max = math.log(100.0)  # ln(100) ≈ 4.61
            log_crash = log_min + float(high_rand) * (log_max - log_min)
            crash = Decimal(str(math.exp(log_crash)))
            crash = crash.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            crash = min(crash, Decimal('100.0'))  # Максимум 100x
        elif rand < medium_mult_probability and rand > high_mult_probability:
            # РЕДКИЕ высокие множители (10x-100x)
            # Используем оставшуюся часть rand для генерации в диапазоне 10-100
            high_rand = (rand / medium_mult_probability)  # Нормализуем к [0,1)
            if high_rand <= Decimal('1e-13'):
                high_rand = Decimal('1e-13')
            
            # Генерируем от 10 до 100 с правильным логарифмическим распределением
            # Используем логарифмическое распределение для равномерного покрытия диапазона
            import math
            log_min = math.log(4.0)   # ln(10) ≈ 2.30
            log_max = math.log(10.0)  # ln(100) ≈ 4.61
            log_crash = log_min + float(high_rand) * (log_max - log_min)
            crash = Decimal(str(math.exp(log_crash)))
            crash = crash.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            crash = min(crash, Decimal('10.0'))  # Максимум 10x
        else:
            # ОБЫЧНЫЕ множители (1x-10x) с house edge
            # Берем оставшуюся вероятность и применяем house edge
            normal_rand = (rand - high_mult_probability) / (Decimal('1.0') - high_mult_probability)
            
            # Применяем агрессивный house edge только к обычным множителям
            adjusted_rand = normal_rand + (Decimal('1.0') - normal_rand) * self.house_edge * Decimal('1.5')
            
            crash = Decimal('1.0') / adjusted_rand
            crash = min(crash, Decimal('10.0'))  # Ограничиваем "обычные" до 10x
        
        crash = crash.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        return max(crash, Decimal('1.00'))


# 🎯 Симуляция стратегий
def simulate_strategy(strategy_name: str, crash_points: List[Decimal]) -> Dict[str, Any]:
    balance = Decimal("0")
    cashouts = []
    MAX_BET = Decimal("10000")

    state = {
        "bet": Decimal("1"),
        "base_bet": Decimal("1"),
        "streak": 0,
        "fib_seq": [1, 1],
        "fib_index": 0,
        "dalembert_bet": Decimal("1"),
        "kelly_balance": Decimal("50000"),
        "percentage_balance": Decimal("50000"),
        "martingale_bet": Decimal("1")
    }

    for round_index, crash in enumerate(crash_points):
        try:
            if strategy_name.startswith("fixed_"):
                target = Decimal(strategy_name.split("_")[1])
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "random_cashout":
                target = Decimal(secrets.SystemRandom().uniform(1.01, 3.0))
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "high_risk":
                bet = Decimal("1")
                if crash >= 10:
                    balance += (crash - 1) * bet
                    cashouts.append(float(crash))
                else:
                    balance -= bet
                    cashouts.append(0.0)

            elif strategy_name == "greedy_early":
                target = Decimal("1.05")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "greedy_late":
                target = Decimal("3.0")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "risky_random":
                target = Decimal(secrets.SystemRandom().uniform(2.5, 5.0))
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "ladder":
                step = Decimal("0.1")
                target = Decimal("1.5") + (round_index % 5) * step
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "reverse_martingale":
                bet = min(state["bet"], MAX_BET)
                target = Decimal("1.5")
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["bet"] = min(state["bet"] * 2, MAX_BET)
                else:
                    balance -= bet
                    state["bet"] = Decimal("1")
                cashouts.append(float(target))

            elif strategy_name == "lowball":
                target = Decimal("1.01")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "survivor":
                target = Decimal("1.15")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "martingale":
                bet = state["martingale_bet"]
                target = Decimal("2.0")
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["martingale_bet"] = Decimal("1")
                else:
                    balance -= bet
                    new_bet = state["martingale_bet"] * 2
                    state["martingale_bet"] = min(new_bet, MAX_BET)
                cashouts.append(float(target))

            elif strategy_name == "dalembert":
                bet = min(state["dalembert_bet"], MAX_BET)
                target = Decimal("1.5")
                if crash >= target:
                    profit = bet * (target - Decimal("1"))
                    balance += profit
                    state["dalembert_bet"] = max(Decimal("1"), bet - Decimal("1"))
                else:
                    balance -= bet
                    state["dalembert_bet"] = min(bet + Decimal("1"), MAX_BET)
                cashouts.append(float(target))

            elif strategy_name == "fibonacci":
                target = Decimal("1.8")
                fib = state["fib_seq"]
                index = state["fib_index"]
                bet = min(Decimal(fib[index]), MAX_BET)
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    index = max(0, index - 2)
                else:
                    balance -= bet
                    index += 1
                    if index >= len(fib) and fib[-1] + fib[-2] <= MAX_BET:
                        fib.append(fib[-1] + fib[-2])
                    elif index >= len(fib):
                        index = len(fib) - 1  # Остаемся на максимальной ставке
                state["fib_index"] = index
                cashouts.append(float(target))

            elif strategy_name == "percentage_bet":
                target = Decimal("1.5")
                perc_balance = state["percentage_balance"]
                bet = perc_balance * Decimal("0.01")
                if crash >= target:
                    profit = bet * (target - 1)
                    perc_balance += profit
                    balance += profit
                else:
                    perc_balance -= bet
                    balance -= bet
                state["percentage_balance"] = max(perc_balance, Decimal("0"))
                cashouts.append(float(target))

            elif strategy_name == "adaptive_wait":
                target = Decimal("1.4")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "kelly":
                if "kelly_balance" not in state:
                    state["kelly_balance"] = Decimal("100")
                kelly_balance = state["kelly_balance"]
                
                target = Decimal("2.0")
                p = Decimal("0.45")  # Примерная вероятность выигрыша для 2.0x
                b = target - 1  # Коэффициент выплаты
                f = (p * (b + 1) - 1) / b if b > 0 else Decimal("0")
                f = max(Decimal("0"), min(f, Decimal("0.25")))  # Ограничиваем долю
                
                bet = kelly_balance * f if f > 0 else Decimal("1")
                bet = min(bet, MAX_BET)
                bet = max(bet, Decimal("1"))  # Минимальная ставка
                
                if crash >= target:
                    profit = bet * (target - 1)
                    kelly_balance += profit
                    balance += profit
                else:
                    kelly_balance -= bet
                    balance -= bet
                
                state["kelly_balance"] = max(kelly_balance, Decimal("1"))
                cashouts.append(float(target))

            elif strategy_name == "stop_loss_take_profit":
                stop_loss = Decimal("-50")
                take_profit = Decimal("50")
                if balance <= stop_loss or balance >= take_profit:
                    break
                target = Decimal("1.5")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "trend_following":
                target = Decimal("2.0") if secrets.randbelow(2) else Decimal("1.1")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "random_walk":
                target = Decimal("1.5")  # Возможность расширить
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "anti_martingale":
                bet = min(state["bet"], MAX_BET)
                target = Decimal("2.0")
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["bet"] = min(state["bet"] * 2, MAX_BET)
                    state["streak"] += 1
                else:
                    balance -= bet
                    state["bet"] = Decimal("1")
                    state["streak"] = 0
                if state["streak"] >= 3:
                    state["bet"] = Decimal("1")
                    state["streak"] = 0
                cashouts.append(float(target))

            elif strategy_name == "labouchere":
                if "labouchere_seq" not in state:
                    state["labouchere_seq"] = [1, 2, 3, 4]
                seq = state["labouchere_seq"]
                if not seq:
                    seq = [1, 2, 3, 4]
                    state["labouchere_seq"] = seq
                bet = min(Decimal(seq[0] + seq[-1]), MAX_BET) if len(seq) > 1 else min(Decimal(seq[0]), MAX_BET)
                target = Decimal("2.0")
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    seq.pop(0)
                    if seq:
                        seq.pop()
                else:
                    balance -= bet
                    seq.append(int(bet))
                cashouts.append(float(target))

            elif strategy_name == "paroli":
                bet = min(state["bet"], MAX_BET)
                target = Decimal("2.0")
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["streak"] += 1
                    state["bet"] = min(state["bet"] * 2, MAX_BET)
                    if state["streak"] >= 3:
                        state["bet"] = Decimal("1")
                        state["streak"] = 0
                else:
                    balance -= bet
                    state["bet"] = Decimal("1")
                    state["streak"] = 0
                cashouts.append(float(target))

            elif strategy_name == "oscars_grind":
                if "oscars_profit" not in state:
                    state["oscars_profit"] = Decimal("0")
                bet = min(state["bet"], MAX_BET)
                target = Decimal("2.0")
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["oscars_profit"] += profit
                    if state["oscars_profit"] >= Decimal("1"):
                        state["bet"] = Decimal("1")
                        state["oscars_profit"] = Decimal("0")
                    else:
                        state["bet"] = min(state["bet"] + Decimal("1"), MAX_BET)
                else:
                    balance -= bet
                    state["oscars_profit"] -= bet
                cashouts.append(float(target))

            elif strategy_name == "mean_reversion":
                if "recent_crashes" not in state:
                    state["recent_crashes"] = []
                state["recent_crashes"].append(crash)
                if len(state["recent_crashes"]) > 10:
                    state["recent_crashes"] = state["recent_crashes"][-10:]
                
                avg_recent = sum(state["recent_crashes"]) / len(state["recent_crashes"]) if state["recent_crashes"] else Decimal("2.0")
                if avg_recent > Decimal("2.5"):
                    target = Decimal("1.3")
                elif avg_recent < Decimal("1.5"):
                    target = Decimal("3.0")
                else:
                    target = Decimal("2.0")
                
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "volatility_adaptive":
                if "crash_history" not in state:
                    state["crash_history"] = []
                state["crash_history"].append(crash)
                if len(state["crash_history"]) > 20:
                    state["crash_history"] = state["crash_history"][-20:]
                
                if len(state["crash_history"]) >= 5:
                    crashes = [float(c) for c in state["crash_history"]]
                    mean_crash = sum(crashes) / len(crashes)
                    variance = sum((x - mean_crash) ** 2 for x in crashes) / len(crashes)
                    volatility = variance ** 0.5
                    
                    if volatility > 2.0:
                        target = Decimal("1.2")
                    elif volatility < 0.5:
                        target = Decimal("4.0")
                    else:
                        target = Decimal("2.0")
                else:
                    target = Decimal("2.0")
                
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "whittacker":
                if "whittacker_stage" not in state:
                    state["whittacker_stage"] = 0
                    state["whittacker_bet"] = Decimal("1")
                
                stages = [Decimal("1.5"), Decimal("2.0"), Decimal("3.0"), Decimal("5.0")]
                target = stages[state["whittacker_stage"]]
                bet = state["whittacker_bet"]
                
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["whittacker_stage"] = (state["whittacker_stage"] + 1) % len(stages)
                    state["whittacker_bet"] = Decimal("1")
                else:
                    balance -= bet
                    state["whittacker_bet"] = min(bet * Decimal("1.5"), MAX_BET)
                cashouts.append(float(target))

            elif strategy_name == "pattern_hunter":
                if "pattern_history" not in state:
                    state["pattern_history"] = []
                state["pattern_history"].append(crash)
                if len(state["pattern_history"]) > 50:
                    state["pattern_history"] = state["pattern_history"][-50:]
                
                low_crashes = sum(1 for c in state["pattern_history"][-10:] if c < Decimal("2.0"))
                if low_crashes >= 7:
                    target = Decimal("5.0")
                elif low_crashes <= 3:
                    target = Decimal("1.2")
                else:
                    target = Decimal("2.0")
                
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "momentum_trader":
                if "momentum_history" not in state:
                    state["momentum_history"] = []
                state["momentum_history"].append(crash)
                if len(state["momentum_history"]) > 5:
                    state["momentum_history"] = state["momentum_history"][-5:]
                
                if len(state["momentum_history"]) >= 3:
                    trend = state["momentum_history"][-1] - state["momentum_history"][-3]
                    if trend > Decimal("1.0"):
                        target = Decimal("4.0")
                    elif trend < Decimal("-1.0"):
                        target = Decimal("1.3")
                    else:
                        target = Decimal("2.0")
                else:
                    target = Decimal("2.0")
                
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "sequence_tracker":
                if "sequence_memory" not in state:
                    state["sequence_memory"] = []
                state["sequence_memory"].append(crash)
                if len(state["sequence_memory"]) > 100:
                    state["sequence_memory"] = state["sequence_memory"][-100:]
                
                if len(state["sequence_memory"]) >= 10:
                    last_10 = state["sequence_memory"][-10:]
                    high_count = sum(1 for c in last_10 if c >= Decimal("3.0"))
                    low_count = sum(1 for c in last_10 if c <= Decimal("1.5"))
                    
                    if high_count >= 3:
                        target = Decimal("1.4")
                    elif low_count >= 5:
                        target = Decimal("6.0")
                    else:
                        target = Decimal("2.2")
                else:
                    target = Decimal("2.0")
                
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "dynamic_kelly":
                if "kelly_history" not in state:
                    state["kelly_history"] = []
                    state["kelly_wins"] = 0
                    state["kelly_total"] = 0
                
                state["kelly_history"].append(crash)
                state["kelly_total"] += 1
                
                test_target = Decimal("2.0")
                if crash >= test_target:
                    state["kelly_wins"] += 1
                
                if state["kelly_total"] >= 10:
                    win_rate = Decimal(str(state["kelly_wins"] / state["kelly_total"]))
                    payout_odds = test_target - 1
                    f_kelly = (win_rate * test_target - 1) / payout_odds if payout_odds > 0 else Decimal("0")
                    f_kelly = max(Decimal("0.01"), min(f_kelly, Decimal("0.25")))
                    
                    kelly_balance = state.get("kelly_balance", Decimal("100"))
                    bet = kelly_balance * f_kelly
                else:
                    bet = Decimal("1")
                    kelly_balance = Decimal("100")
                
                target = test_target
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    kelly_balance = kelly_balance + profit if "kelly_balance" in state else Decimal("100") + profit
                else:
                    balance -= bet
                    kelly_balance = kelly_balance - bet if "kelly_balance" in state else Decimal("100") - bet
                
                state["kelly_balance"] = max(kelly_balance, Decimal("1"))
                cashouts.append(float(target))

            elif strategy_name == "contrarian":
                if "contrarian_history" not in state:
                    state["contrarian_history"] = []
                state["contrarian_history"].append(crash)
                if len(state["contrarian_history"]) > 20:
                    state["contrarian_history"] = state["contrarian_history"][-20:]
                
                if len(state["contrarian_history"]) >= 5:
                    recent_avg = sum(state["contrarian_history"][-5:]) / 5
                    if recent_avg > Decimal("3.0"):
                        target = Decimal("1.3")
                        bet = Decimal("2")
                    elif recent_avg < Decimal("1.5"):
                        target = Decimal("4.0")
                        bet = Decimal("2")
                    else:
                        target = Decimal("2.0")
                        bet = Decimal("1")
                else:
                    target = Decimal("2.0")
                    bet = Decimal("1")
                
                balance += bet * (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "risk_parity":
                if "rp_balance" not in state:
                    state["rp_balance"] = Decimal("100")
                    state["rp_drawdown"] = Decimal("0")
                
                current_balance = state["rp_balance"]
                max_risk = current_balance * Decimal("0.02")
                
                if current_balance > Decimal("120"):
                    target = Decimal("1.5")
                    bet = max_risk / Decimal("0.5")
                elif current_balance < Decimal("80"):
                    target = Decimal("3.0")
                    bet = max_risk / Decimal("2.0")
                else:
                    target = Decimal("2.0")
                    bet = max_risk / Decimal("1.0")
                
                bet = min(bet, MAX_BET)
                
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["rp_balance"] += profit
                else:
                    balance -= bet
                    state["rp_balance"] -= bet
                
                state["rp_balance"] = max(state["rp_balance"], Decimal("10"))
                cashouts.append(float(target))

            elif strategy_name == "adaptive_threshold":
                if "threshold_wins" not in state:
                    state["threshold_wins"] = 0
                    state["threshold_total"] = 0
                    state["current_threshold"] = Decimal("2.0")
                
                target = state["current_threshold"]
                bet = Decimal("1")
                
                state["threshold_total"] += 1
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["threshold_wins"] += 1
                else:
                    balance -= bet
                
                if state["threshold_total"] % 10 == 0:
                    win_rate = state["threshold_wins"] / state["threshold_total"]
                    if win_rate > 0.6:
                        state["current_threshold"] = min(state["current_threshold"] + Decimal("0.2"), Decimal("5.0"))
                    elif win_rate < 0.4:
                        state["current_threshold"] = max(state["current_threshold"] - Decimal("0.2"), Decimal("1.2"))
                
                cashouts.append(float(target))

            elif strategy_name == "compound_growth":
                if "cg_balance" not in state:
                    state["cg_balance"] = Decimal("100")
                    state["cg_target_multiplier"] = Decimal("1.0")
                
                current_balance = state["cg_balance"]
                growth_rate = current_balance / Decimal("100")
                
                if growth_rate > Decimal("1.5"):
                    target = Decimal("1.3")
                    bet_fraction = Decimal("0.05")
                elif growth_rate < Decimal("0.5"):
                    target = Decimal("4.0")
                    bet_fraction = Decimal("0.1")
                else:
                    target = Decimal("2.0")
                    bet_fraction = Decimal("0.02")
                
                bet = current_balance * bet_fraction
                bet = min(bet, MAX_BET)
                
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["cg_balance"] += profit
                else:
                    balance -= bet
                    state["cg_balance"] -= bet
                
                state["cg_balance"] = max(state["cg_balance"], Decimal("10"))
                cashouts.append(float(target))

            elif strategy_name == "statistical_arbitrage":
                if "stat_arb_history" not in state:
                    state["stat_arb_history"] = []
                    state["stat_arb_mean"] = Decimal("2.0")
                    state["stat_arb_std"] = Decimal("1.0")
                
                state["stat_arb_history"].append(crash)
                if len(state["stat_arb_history"]) > 50:
                    state["stat_arb_history"] = state["stat_arb_history"][-50:]
                
                if len(state["stat_arb_history"]) >= 10:
                    values = [float(c) for c in state["stat_arb_history"]]
                    mean_val = sum(values) / len(values)
                    variance = sum((x - mean_val) ** 2 for x in values) / len(values)
                    std_val = variance ** 0.5
                    
                    state["stat_arb_mean"] = Decimal(str(mean_val))
                    state["stat_arb_std"] = Decimal(str(std_val))
                    
                    z_score = (crash - state["stat_arb_mean"]) / state["stat_arb_std"] if state["stat_arb_std"] > 0 else Decimal("0")
                    
                    if z_score > Decimal("1.5"):
                        target = Decimal("1.2")
                        bet = Decimal("2")
                    elif z_score < Decimal("-1.5"):
                        target = Decimal("5.0")
                        bet = Decimal("2")
                    else:
                        target = state["stat_arb_mean"]
                        bet = Decimal("1")
                else:
                    target = Decimal("2.0")
                    bet = Decimal("1")
                
                balance += bet * (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "gambler_fallacy":
                if "gf_recent_outcomes" not in state:
                    state["gf_recent_outcomes"] = []
                    state["gf_base_target"] = Decimal("2.0")
                
                # Определяем target на основе ПРОШЛЫХ результатов
                if len(state["gf_recent_outcomes"]) >= 5:
                    wins_in_last_5 = sum(state["gf_recent_outcomes"][-5:])
                    if wins_in_last_5 >= 4:
                        target = Decimal("1.3")
                        bet = Decimal("2")
                    elif wins_in_last_5 <= 1:
                        target = Decimal("4.0")
                        bet = Decimal("2")
                    else:
                        target = state["gf_base_target"]
                        bet = Decimal("1")
                else:
                    target = state["gf_base_target"]
                    bet = Decimal("1")
                
                bet = min(bet, MAX_BET)
                
                # Делаем ставку
                balance += bet * (target - 1) if crash >= target else -bet
                
                # ПОТОМ записываем результат ЭТОГО раунда
                result = crash >= target
                state["gf_recent_outcomes"].append(result)
                if len(state["gf_recent_outcomes"]) > 10:
                    state["gf_recent_outcomes"] = state["gf_recent_outcomes"][-10:]
                
                cashouts.append(float(target))

            elif strategy_name == "hot_hand":
                if "hh_streak" not in state:
                    state["hh_streak"] = 0
                    state["hh_target"] = Decimal("2.0")
                
                # Определяем target для ЭТОГО раунда на основе прошлых результатов
                if state["hh_streak"] >= 3:
                    target = min(state["hh_target"] + Decimal("0.3"), Decimal("4.0"))
                    bet = Decimal("1")
                elif state["hh_streak"] == 0:
                    target = max(state["hh_target"] - Decimal("0.2"), Decimal("1.2"))
                    bet = Decimal("1")
                else:
                    target = state["hh_target"]
                    bet = Decimal("1")
                
                # Делаем ставку
                balance += bet * (target - 1) if crash >= target else -bet
                
                # ПОТОМ обновляем streak на основе результата ЭТОГО раунда
                if crash >= target:
                    state["hh_streak"] += 1
                else:
                    state["hh_streak"] = 0
                
                state["hh_target"] = target
                cashouts.append(float(target))

            elif strategy_name == "loss_aversion":
                if "la_balance" not in state:
                    state["la_balance"] = Decimal("100")
                    state["la_reference"] = Decimal("100")
                
                current_balance = state["la_balance"]
                reference = state["la_reference"]
                
                if current_balance < reference:
                    target = Decimal("3.0")
                    bet = min(Decimal("5"), current_balance * Decimal("0.1"))
                else:
                    target = Decimal("1.5")
                    bet = Decimal("1")
                
                if crash >= target:
                    profit = bet * (target - 1)
                    balance += profit
                    state["la_balance"] += profit
                else:
                    balance -= bet
                    state["la_balance"] -= bet
                
                if len(cashouts) % 100 == 0:
                    state["la_reference"] = state["la_balance"]
                
                cashouts.append(float(target))

            elif strategy_name == "machine_learning_simple":
                if "ml_features" not in state:
                    state["ml_features"] = []
                    state["ml_targets"] = []
                    state["ml_weights"] = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
                
                if len(state["ml_features"]) >= 3:
                    last_3 = state["ml_features"][-3:]
                    weights = state["ml_weights"]
                    prediction = sum(w * f for w, f in zip(weights, last_3))
                    
                    if prediction > Decimal("2.5"):
                        target = Decimal("1.4")
                    elif prediction < Decimal("1.5"):
                        target = Decimal("4.0")
                    else:
                        target = Decimal("2.0")
                else:
                    target = Decimal("2.0")
                
                state["ml_features"].append(crash)
                if len(state["ml_features"]) > 20:
                    state["ml_features"] = state["ml_features"][-20:]
                
                bet = Decimal("1")
                balance += bet * (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "regime_switching":
                if "regime_history" not in state:
                    state["regime_history"] = []
                    state["current_regime"] = "normal"
                
                state["regime_history"].append(crash)
                if len(state["regime_history"]) > 30:
                    state["regime_history"] = state["regime_history"][-30:]
                
                if len(state["regime_history"]) >= 20:
                    recent_20 = state["regime_history"][-20:]
                    high_vol = sum(1 for c in recent_20 if c > Decimal("3.0") or c < Decimal("1.2"))
                    
                    if high_vol >= 8:
                        state["current_regime"] = "volatile"
                    elif high_vol <= 3:
                        state["current_regime"] = "stable"
                    else:
                        state["current_regime"] = "normal"
                
                if state["current_regime"] == "volatile":
                    target = Decimal("1.3")
                    bet = Decimal("2")
                elif state["current_regime"] == "stable":
                    target = Decimal("3.5")
                    bet = Decimal("2")
                else:
                    target = Decimal("2.0")
                    bet = Decimal("1")
                
                balance += bet * (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "psychological_anchoring":
                if "anchor_value" not in state:
                    state["anchor_value"] = Decimal("2.0")
                    state["anchor_rounds"] = 0
                
                anchor = state["anchor_value"]
                rounds_since_anchor = state["anchor_rounds"]
                
                if rounds_since_anchor > 20:
                    state["anchor_value"] = crash
                    state["anchor_rounds"] = 0
                    anchor = crash
                
                state["anchor_rounds"] += 1
                
                if crash > anchor * Decimal("1.5"):
                    target = anchor * Decimal("0.8")
                elif crash < anchor * Decimal("0.7"):
                    target = anchor * Decimal("1.3")
                else:
                    target = anchor
                
                target = max(Decimal("1.1"), min(target, Decimal("5.0")))
                bet = Decimal("1")
                balance += bet * (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "wait_mid":
                target = Decimal("2.0")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            elif strategy_name == "wait_high":
                target = Decimal("5.0")
                bet = Decimal("1")
                balance += (target - 1) if crash >= target else -bet
                cashouts.append(float(target))

            # Проверяем balance на NaN или Infinite, прерываем если так
            if balance.is_nan() or balance.is_infinite():
                print(f"Invalid balance {balance} at round {round_index} for strategy {strategy_name}")
                break

        except Exception as e:
            print(f"Ошибка в стратегии '{strategy_name}' на раунде {round_index}: {e}")
            continue

    avg_cashout = round(sum(cashouts) / len(cashouts), 2) if cashouts else 0

    # Проверка перед quantize
    try:
        if balance.is_nan() or balance.is_infinite():
            final_balance = Decimal("0.00")
        else:
            final_balance = balance.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    except:
        final_balance = Decimal("0.00")

    try:
        profit_calc = float(-balance / len(crash_points)) * 100
        if profit_calc == float('inf') or profit_calc == float('-inf') or profit_calc != profit_calc:  # NaN check
            casino_profit_percent = 0.0
        else:
            casino_profit_percent = round(profit_calc, 2)
    except:
        casino_profit_percent = 0.0

    return {
        "strategy": strategy_name,
        "rounds": len(crash_points),
        "final_balance": final_balance,
        "average_cashout": avg_cashout,
        "casino_profit_percent": casino_profit_percent
    }


def run_simulation(num_rounds: int = 10000):
    print(f"🔐 Using secure CrashGenerator for {num_rounds} rounds...\n")
    generator = CrashGenerator()

    crash_points = [generator.generate_crash_point() for _ in tqdm(range(num_rounds), desc="🧪 Generating crash points")]
    
    # Статистика crash точек
    high_crashes = [c for c in crash_points if c >= 10]
    avg_high_crash = sum(high_crashes) / len(high_crashes) if high_crashes else 0
    print(f"📈 Crash точек >= 10: {len(high_crashes)} из {len(crash_points)} ({len(high_crashes)/len(crash_points)*100:.2f}%)")
    print(f"📊 Средняя crash точка >= 10: {avg_high_crash:.2f}")
    print(f"📊 Максимальная crash точка: {max(crash_points)}")
    print(f"📊 Средняя crash точка: {sum(crash_points)/len(crash_points):.2f}")
    
    # Вывод первых 100 значений
    sample_points = crash_points[:1000]
    sample_str = ", ".join([f"{float(point):.2f}" for point in sample_points])
    print(f"📋 Первые 100 crash точек: {sample_str}")
    
    # Математическое ожидание для high_risk
    prob_win = len(high_crashes) / len(crash_points)
    expected_profit = prob_win * (float(avg_high_crash) - 1) - (1 - prob_win) * 1
    print(f"🧮 Мат. ожидание high_risk: {expected_profit:.4f} (House profit: {-expected_profit*100:.2f}%)\n")

    strategies = [
        *[f"fixed_{i/10:.1f}" for i in range(11, 1001)],

        "greedy_early", "greedy_late",
        "wait_mid", "wait_high",
        "risky_random", "ladder",
        "reverse_martingale", "lowball", "survivor",

        "random_cashout", "high_risk",

        "martingale", "anti_martingale", "dalembert", "fibonacci",

        "percentage_bet", "adaptive_wait",

        "kelly", "stop_loss_take_profit",

        "trend_following", "random_walk",

        "labouchere", "paroli", "oscars_grind",

        "mean_reversion", "volatility_adaptive",

        "whittacker", "pattern_hunter", "momentum_trader",

        "sequence_tracker", "dynamic_kelly", "contrarian",

        "risk_parity", "adaptive_threshold", "compound_growth",

        "statistical_arbitrage",

        "gambler_fallacy", "hot_hand", "loss_aversion",

        "machine_learning_simple", "regime_switching", "psychological_anchoring"
    ]

    for strat in strategies:
        result = simulate_strategy(strat, crash_points)
        print(f"📊 {result['strategy']:>13} | Balance: {result['final_balance']:>8} | "
            f"Avg Cashout: {result['average_cashout']:>5} | "
            f"Profit: {result['casino_profit_percent']:>6}% | "
            f"Rounds: {result['rounds']}")


if __name__ == "__main__":
    print("Start balance for all strategies: 0.00\n")
    run_simulation(100000)
