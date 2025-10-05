"""
Сервис для получения курса TON и расчёта цен в звёздах
"""
import os
import time
import asyncio
import aiohttp
import logging
from decimal import Decimal, ROUND_UP
from typing import Optional

logger = logging.getLogger(__name__)

class TonPriceService:
    """Сервис для работы с ценами TON"""
    
    COINGECKO_API_URL = "https://api.coingecko.com/api/v3/coins/the-open-network"
    
    def __init__(self):
        # Цена одной звезды в USD (из .env)
        self.star_price_usd = Decimal(os.getenv('STAR_PRICE_USD', '0.015'))
        # Кеширование курса TON/USD
        self._cached_rate = None
        self._cache_timestamp = 0
        self._cache_ttl = 300  # 5 минут
    
    async def get_ton_usd_rate(self) -> Optional[Decimal]:
        """Получить курс TON/USD с CoinGecko API с кешированием и retry"""
        current_time = time.time()
        
        # Проверяем кеш
        if (self._cached_rate is not None and 
            current_time - self._cache_timestamp < self._cache_ttl):
            logger.debug(f"📈 Using cached TON/USD rate: {self._cached_rate}")
            return self._cached_rate
        
        # Пытаемся получить свежий курс с retry
        for attempt in range(3):  # 3 попытки
            try:
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.COINGECKO_API_URL,
                        timeout=aiohttp.ClientTimeout(total=15)  # Увеличен timeout
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            ton_usd_rate = Decimal(str(data['market_data']['current_price']['usd']))
                            
                            # Сохраняем в кеш
                            self._cached_rate = ton_usd_rate
                            self._cache_timestamp = current_time
                            
                            return ton_usd_rate
                        else:
                            logger.warning(f"⚠️ CoinGecko API error: status {response.status}")
                            
            except Exception as e:
                logger.warning(f"⚠️ Attempt {attempt + 1} failed: {e}")
                
                # Если это не последняя попытка, ждем перед retry
                if attempt < 2:
                    await asyncio.sleep(1)  # 1 секунда между попытками
        
        # Если все попытки неудачны, используем старый кеш если есть
        if self._cached_rate is not None:
            logger.warning(f"⚠️ Using stale cached TON/USD rate: {self._cached_rate}")
            return self._cached_rate
            
        logger.error("❌ Failed to fetch TON/USD rate after all retries and no cache available")
        return None
    
    def calculate_stars_price(self, usd_price: Decimal, ton_usd_rate: Decimal = None) -> int:
        """
        Рассчитать цену в звёздах из цены в USD
        
        Формула:
        1. Цена уже в USD (ton_price теперь интерпретируется как USD)
        2. Конвертируем USD в звёзды: usd_price / star_price_usd
        3. Добавляем наценку +20%
        4. Добавляем фиксированные +25 звёзд
        5. Округляем вверх до целого числа
        
        Args:
            usd_price: Цена в USD (ранее называлась ton_price, но теперь интерпретируется как USD)
            ton_usd_rate: Курс TON/USD (больше не используется, оставлен для совместимости)
        """
        try:
            logger.debug(f"💱 Price in USD: ${usd_price}")
            
            # Конвертируем USD в звёзды
            stars_base = usd_price / self.star_price_usd
            logger.debug(f"💎 ${usd_price} USD = {stars_base} stars (base)")
            
            # Добавляем наценку 20%
            stars_with_markup = stars_base * Decimal('1.20')
            logger.debug(f"💰 With 20% markup: {stars_with_markup} stars")
            
            # Добавляем фиксированные 25 звёзд
            stars_final = stars_with_markup + Decimal('25')
            logger.debug(f"⭐ With +25 stars: {stars_final} stars")
            
            # Округляем вверх до целого числа
            stars_rounded = int(stars_final.quantize(Decimal('1'), rounding=ROUND_UP))
            
            return stars_rounded
            
        except Exception as e:
            logger.error(f"❌ Error calculating stars price: {e}")
            raise
    
    async def get_stars_price_for_ton(self, ton_price: Decimal) -> Optional[int]:
        """
        Получить цену в звёздах для заданной цены в USD
        
        Args:
            ton_price: Цена в USD (поле называется ton_price для совместимости, но теперь содержит USD)
            
        Returns:
            Цена в звёздах или None при ошибке
        """
        try:
            return self.calculate_stars_price(ton_price)
        except Exception as e:
            logger.error(f"❌ Cannot calculate stars price: {e}")
            return None

# Глобальный экземпляр сервиса
ton_price_service = TonPriceService()