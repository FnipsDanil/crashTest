"""
Crash point generation for crash game.
Handles random crash point generation based on configured probabilities.
"""

import secrets
import hashlib
import time
import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional

from config.settings import GAME_CONFIG

# Setup logging
logger = logging.getLogger(__name__)


class CrashGenerator:
    """Generates crash points based on configured probability ranges."""
    
    def __init__(self, database_service=None, house_edge: Decimal = Decimal('0.17')):
        """Initialize with database service for dynamic house_edge or fallback value."""
        # СТАРАЯ СИСТЕМА С CRASH_RANGES (закомментирована)
        # self.crash_ranges = crash_ranges or GAME_CONFIG["crash_ranges"]
        
        # НОВАЯ СИСТЕМА С ДИНАМИЧЕСКИМ HOUSE_EDGE ИЗ БД
        self.database_service = database_service
        self.fallback_house_edge = house_edge  # Fallback если БД недоступна
        self.secure_random = secrets.SystemRandom()
        
        # 🔒 SECURITY: Anti-prediction measures
        self.entropy_pool = []  # Track recent results for entropy
        self.max_entropy_size = 50  # Keep last 50 results
        self.server_seed = None
        self.round_counter = 0
        
        # ЗАКОММЕНТИРОВАНО - валидация crash_ranges больше не нужна
        # self._validate_ranges()
    
    # СТАРАЯ ВАЛИДАЦИЯ CRASH_RANGES - ЗАКОММЕНТИРОВАНА
    # def _validate_ranges(self) -> None:
    #     """Validate that probability ranges sum to 1.0 and house edge is reasonable."""
    #     total_probability = sum(Decimal(str(r["probability"])) for r in self.crash_ranges)
    pass
    
    async def _get_house_edge_from_db(self) -> Decimal:
        """Get current house_edge from database or return fallback."""
        if not self.database_service:
            logger.warning("🏦 No database service available, using fallback house_edge")
            return self.fallback_house_edge
        
        try:
            from database import AsyncSessionLocal
            from services.database_service import DatabaseService
            
            async with AsyncSessionLocal() as session:
                config = await DatabaseService.get_system_setting(session, "game_config")
                if config and "house_edge" in config:
                    house_edge = config["house_edge"]
                    # Ensure it's a Decimal
                    if isinstance(house_edge, str):
                        house_edge = Decimal(house_edge)
                    elif not isinstance(house_edge, Decimal):
                        house_edge = Decimal(str(house_edge))
                    
                    logger.debug(f"🏦 House edge loaded from database: {house_edge*100:.2f}%")
                    return house_edge
                else:
                    logger.warning("🏦 No house_edge found in database config, using fallback")
                    return self.fallback_house_edge
                    
        except Exception as e:
            logger.error(f"🏦 Error loading house_edge from database: {e}")
            return self.fallback_house_edge

    def _validate_house_edge(self, house_edge: Decimal) -> None:
        """Validate house edge for new algorithm."""
        logger.info(f"🏦 NEW Algorithm House edge analysis:")
        logger.info(f"  House edge: {house_edge*100:.2f}%")
        logger.info(f"  RTP: {(Decimal('1') - house_edge)*100:.2f}%")
        
        # Critical security check
        if house_edge < Decimal('0.05'):  # Less than 5% house edge
            logger.warning(f"⚠️ WARNING: Very low house edge {house_edge*100:.2f}% - Minimal profit margin")
            
        if house_edge > Decimal('0.20'):  # More than 20% house edge  
            logger.warning(f"⚠️ WARNING: Very high house edge {house_edge*100:.2f}% - May be unfair to players")
    
    # СТАРЫЙ РАСЧЕТ EXPECTED VALUE ДЛЯ CRASH_RANGES - ЗАКОММЕНТИРОВАН
    # def _calculate_expected_value(self) -> Decimal:
    #     """
    #     Calculate mathematical expected value for crash game.
    #     🔒 CRITICAL: Fixed calculation for proper house edge.
    #     
    #     In crash game:
    #     - Player bets 1 unit
    #     - If game crashes at X and player didn't cashout: player loses 1 unit
    #     - If player cashes out at Y < X: player gets Y units (net gain Y-1)
    #     
    #     Expected payout per unit bet should be < 1.0 for positive house edge.
    #     """
    #     total_expected = Decimal('0')
    #     for r in self.crash_ranges:
    #         min_val = Decimal(str(r["min"]))
    #         max_val = Decimal(str(r["max"]))
    #         prob = Decimal(str(r["probability"]))
    #         
    #         # 🔒 CORRECTED CALCULATION:
    #         # For crash game, expected return is the RECIPROCAL of crash multiplier
    #         # because player wins (crash_point * bet) if they cashout before crash
    #         # but loses entire bet if they don't cashout
    #         
    #         # Average crash point in this range  
    #         avg_crash = (min_val + max_val) / 2
    #         
    #         # Expected return per unit bet in this range
    #         # Simplified model: assume players have 0% success rate (worst case for house)
    #         # This gives upper bound on expected payout
    #         expected_payout_if_win = avg_crash  # Player gets this if they win
    #         
    #         # In reality, players can't predict crash point perfectly
    #         # Assume uniform distribution and random cashout strategy
    #         # Expected payout ≈ (1/avg_crash) because higher crashes are less likely to be hit
    #         
    #         # Use conservative estimate: 1/sqrt(avg_crash) for moderate house edge
    #         expected_return_per_range = (Decimal('1') / avg_crash.sqrt()) * prob
    #         total_expected += expected_return_per_range
    #         
    #     return total_expected
    
    # СТАРАЯ РЕАЛИЗАЦИЯ С CRASH_RANGES - ЗАКОММЕНТИРОВАНА
    # def generate_crash_point(self, client_entropy: Optional[str] = None) -> Decimal:
    #     """
    #     Generate a cryptographically secure crash point with anti-prediction measures.
    #     
    #     Args:
    #         client_entropy: Optional client-provided entropy for provable fairness
    #         
    #     Returns:
    #         Generated crash point with proper house edge
    #     """
    #     # 🔒 SECURITY: Use only cryptographically secure entropy sources (NO TIME DEPENDENCY)
    #     # Generate multiple sources of cryptographic entropy
    #     primary_entropy = secrets.token_hex(32)    # 256 bits of primary entropy
    #     secondary_entropy = secrets.token_hex(16)  # 128 bits of secondary entropy
    #     tertiary_entropy = secrets.token_hex(8)    # 64 bits of tertiary entropy
    #     
    #     # Combine multiple entropy sources (all cryptographically secure)
    #     entropy_sources = [primary_entropy, secondary_entropy, tertiary_entropy]
    #     if client_entropy:
    #         entropy_sources.append(client_entropy)
    #     if hasattr(self, 'entropy_pool') and self.entropy_pool:
    #         entropy_sources.append(','.join(map(str, self.entropy_pool[-3:])))
    #         
    #     # Create deterministic but unpredictable seed
    #     combined_entropy = '|'.join(entropy_sources)
    #     seed_hash = hashlib.sha256(combined_entropy.encode()).hexdigest()
    #     
    #     # Convert hash to decimal for range selection (first 13 hex chars)
    #     hex_substr = seed_hash[:13]
    #     random_int = int(hex_substr, 16)
    #     max_val = 16 ** 13
    #     rand = Decimal(random_int) / Decimal(max_val)
    #     
    #     # Standard range selection with cryptographic randomness
    #     cumulative_prob = Decimal('0')
    #     for range_config in self.crash_ranges:
    #         range_prob = Decimal(str(range_config["probability"]))
    #         cumulative_prob += range_prob
    #         
    #         if rand <= cumulative_prob:
    #             min_val = Decimal(str(range_config["min"]))
    #             max_val = Decimal(str(range_config["max"]))
    #             
    #             # Generate position within range using second hash
    #             position_seed = f"{seed_hash}:position"
    #             position_hash = hashlib.sha256(position_seed.encode()).hexdigest()
    #             position_hex = position_hash[:13]
    #             position_random = int(position_hex, 16)
    #             rand_uniform = Decimal(position_random) / Decimal(16 ** 13)
    #             
    #             # Calculate final crash point
    #             crash_point = min_val + (max_val - min_val) * rand_uniform
    #             generated = crash_point.quantize(Decimal('0.01'))
    #             
    #             # Track for entropy (initialize if needed)
    #             if not hasattr(self, 'entropy_pool'):
    #                 self.entropy_pool = []
    #             self.entropy_pool.append(generated)
    #             if len(self.entropy_pool) > 50:  # Keep last 50
    #                 self.entropy_pool = self.entropy_pool[-50:]
    #             
    #             return generated
    #     
    #     # Fallback to last range if something goes wrong
    #     last_range = self.crash_ranges[-1]
    #     min_val = Decimal(str(last_range["min"]))
    #     max_val = Decimal(str(last_range["max"]))
    #     fallback_hash = hashlib.sha256(f"fallback:{combined_entropy}".encode()).hexdigest()
    #     fallback_hex = fallback_hash[:13]
    #     fallback_random = int(fallback_hex, 16)
    #     rand_uniform = Decimal(fallback_random) / Decimal(16 ** 13)
    #     fallback = (min_val + (max_val - min_val) * rand_uniform).quantize(Decimal('0.01'))
    #     return fallback

    async def generate_crash_point(self, client_entropy: Optional[str] = None) -> Decimal:
        """
        НОВАЯ РЕАЛИЗАЦИЯ ИЗ crash_simulator_new.py с динамическим house_edge из БД
        Математически корректный генератор с двухуровневой системой.
        
        Args:
            client_entropy: Optional client-provided entropy for provable fairness
            
        Returns:
            Generated crash point with proper house edge from database
        """
        from decimal import ROUND_DOWN
        
        # 🏦 КРИТИЧНО: Получаем актуальный house_edge из БД перед каждой генерацией
        house_edge = await self._get_house_edge_from_db()
        
        # 🔒 SECURITY: Криптографически стойкая генерация энтропии
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
            # ИСПРАВЛЕНИЕ: используем логарифмическое распределение для равномерного покрытия 10-100x
            import math
            log_min = math.log(10.0)   # ln(10)
            log_max = math.log(100.0)  # ln(100)
            log_crash = log_min + float(high_rand) * (log_max - log_min)
            crash = Decimal(str(math.exp(log_crash)))
            crash = min(crash, Decimal('100.0'))  # Максимум 100x
        elif rand < medium_mult_probability and rand > high_mult_probability:
            # РЕДКИЕ высокие множители (4x-10x)
            # Используем оставшуюся часть rand для генерации в диапазоне 4-10
            high_rand = (rand / medium_mult_probability)  # Нормализуем к [0,1)
            if high_rand <= Decimal('1e-13'):
                high_rand = Decimal('1e-13')
            
            # Генерируем от 4 до 10 с правильным логарифмическим распределением
            # Используем логарифмическое распределение для равномерного покрытия диапазона
            import math
            log_min = math.log(4.0)
            log_max = math.log(10.0)
            log_crash = log_min + float(high_rand) * (log_max - log_min)
            crash = Decimal(str(math.exp(log_crash)))
            crash = crash.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
            crash = min(crash, Decimal('10.0'))  # Максимум 10x
        else:
            # ОБЫЧНЫЕ множители (1x-10x) с house edge ИЗ БД
            # Берем оставшуюся вероятность и применяем house edge
            normal_rand = (rand - high_mult_probability) / (Decimal('1.0') - high_mult_probability)
            
            # Применяем агрессивный house edge только к обычным множителям
            adjusted_rand = normal_rand + (Decimal('1.0') - normal_rand) * house_edge * Decimal('1.5')
            
            crash = Decimal('1.0') / adjusted_rand
            crash = min(crash, Decimal('10.0'))  # Ограничиваем "обычные" до 10x
        
        crash = crash.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
        final_crash = max(crash, Decimal('1.00'))
        
        # Track for entropy (initialize if needed)
        if not hasattr(self, 'entropy_pool'):
            self.entropy_pool = []
        self.entropy_pool.append(final_crash)
        if len(self.entropy_pool) > 50:  # Keep last 50
            self.entropy_pool = self.entropy_pool[-50:]
        
        return final_crash
    
    # СТАРАЯ СТАТИСТИКА CRASH_RANGES - ЗАКОММЕНТИРОВАНА
    # def get_range_stats(self) -> Dict[str, Any]:
    #     """Get statistics about crash ranges."""
    #     return {
    #         "total_ranges": len(self.crash_ranges),
    #         "ranges": [
    #             {
    #                 "min": r["min"],
    #                 "max": r["max"], 
    #                 "probability": r["probability"],
    #                 "description": self._get_range_description(r)
    #             }
    #             for r in self.crash_ranges
    #         ],
    #         "total_probability": sum(r["probability"] for r in self.crash_ranges)
    #     }
    
    async def get_algorithm_stats(self) -> Dict[str, Any]:
        """Get statistics about new algorithm with current house_edge from DB."""
        house_edge = await self._get_house_edge_from_db()
        return {
            "algorithm": "two_level_system",
            "house_edge": float(house_edge),
            "rtp": float(Decimal('1') - house_edge),
            "high_multiplier_probability": 0.02,
            "high_multiplier_range": "10x-100x",
            "normal_multiplier_range": "1x-10x"
        }
    
    # СТАРАЯ ФУНКЦИЯ ДЛЯ ОПИСАНИЯ CRASH_RANGES - ЗАКОММЕНТИРОВАНА
    # def _get_range_description(self, range_config: Dict[str, Any]) -> str:
    #     """Get human-readable description of a range."""
    #     prob_percent = range_config["probability"] * 100
    #     if range_config["max"] <= 3.0:
    #         return f"Низкие крахи ({prob_percent:.0f}%)"
    #     elif range_config["max"] <= 10.0:
    #         return f"Средние крахи ({prob_percent:.0f}%)"
    #     else:
    #         return f"Высокие крахи ({prob_percent:.0f}%)"
    
    async def test_distribution(self, num_tests: int = 1000) -> Dict[str, Any]:
        """Test crash point distribution for new algorithm (for debugging)."""
        if num_tests <= 0:
            return {"error": "Invalid test count"}
        
        # Get current house_edge from DB
        house_edge = await self._get_house_edge_from_db()
        
        results = []
        high_count = 0  # crashes >= 10x
        normal_count = 0  # crashes < 10x
        
        for _ in range(num_tests):
            crash_point = await self.generate_crash_point()
            results.append(crash_point)
            
            if crash_point >= Decimal('10.0'):
                high_count += 1
            else:
                normal_count += 1
        
        return {
            "total_tests": num_tests,
            "average_crash_point": round(sum(results) / len(results), 2),
            "min_crash_point": min(results),
            "max_crash_point": max(results),
            "distribution": {
                "high_multipliers (>=10x)": {
                    "count": high_count,
                    "actual_probability": round(high_count / num_tests, 3),
                    "expected_probability": 0.02
                },
                "normal_multipliers (<10x)": {
                    "count": normal_count,
                    "actual_probability": round(normal_count / num_tests, 3),
                    "expected_probability": 0.98
                }
            },
            "house_edge": float(house_edge),
            "algorithm": "two_level_system"
        }