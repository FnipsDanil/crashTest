"""Payment service for Telegram Stars integration"""

import os
import time
import json
import secrets
import hashlib
import hmac
import aiohttp
import logging
from typing import Dict, Any, Optional

# Setup logging
logger = logging.getLogger(__name__)

# Payment configuration from environment
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")

class PaymentService:
    """Handles payment operations"""
    
    def __init__(self, provider_token: str = PAYMENT_PROVIDER_TOKEN, webhook_secret: str = WEBHOOK_SECRET):
        self.provider_token = provider_token
        self.webhook_secret = webhook_secret
        self.bot_token = TG_BOT_TOKEN
    
    async def create_telegram_invoice(self, user_id: int, amount: int, title: str, description: str) -> Dict[str, Any]:
        """Create Telegram Stars invoice"""
        if not self.bot_token:
            raise ValueError("TG_BOT_TOKEN not configured")
        
        # 🔒 SECURITY FIX: Строгая валидация типа и значения
        try:
            user_id = int(user_id)  # Валидация user_id
            amount = int(amount)    # Валидация amount
        except (ValueError, TypeError):
            raise ValueError("User ID and amount must be valid integers")
        
        # Проверка диапазонов
        if user_id <= 0:
            raise ValueError("Invalid user ID")
        if not (10 <= amount <= 1000000):  # Минимальный депозит 10 звёзд
            raise ValueError("Invalid amount. Must be between 10 and 1000000 stars")
        
        # Generate unique payment payload
        payment_payload = f"stars_{user_id}_{amount}_{secrets.token_hex(8)}"
        
        # Invoice data for Telegram Stars
        invoice_data = {
            "chat_id": user_id,
            "title": title,
            "description": description,
            "payload": payment_payload,
            "currency": "XTR",  # Telegram Stars
            "prices": [{"label": f"{amount} звёзд", "amount": amount}]
        }
        
        async with aiohttp.ClientSession() as session:
            # Send invoice
            url = f"https://api.telegram.org/bot{self.bot_token}/sendInvoice"
            async with session.post(url, json=invoice_data) as response:
                data = await response.json()
                
                if not data.get("ok"):
                    error_msg = data.get("description", "Unknown error")
                    raise RuntimeError(f"Failed to create invoice: {error_msg}")
                
                message_id = data.get("result", {}).get("message_id")
                
                # Create invoice link
                invoice_link = None
                invoice_slug = None
                
                try:
                    link_url = f"https://api.telegram.org/bot{self.bot_token}/createInvoiceLink"
                    async with session.post(link_url, json=invoice_data) as link_response:
                        link_data = await link_response.json()
                        if link_data.get("ok"):
                            invoice_link = link_data["result"]
                            invoice_slug = invoice_link.split('/')[-1] if invoice_link else None
                except Exception as e:
                    logger.warning(f"⚠️ Failed to create invoice link: {e}")
                
                return {
                    "payment_payload": payment_payload,
                    "message_id": message_id,
                    "invoice_link": invoice_link,
                    "invoice_slug": invoice_slug,
                    "amount": amount
                }
    
    def validate_webhook_secret_token(self, secret_token: str) -> bool:
        """Validate webhook secret token from Telegram (X-Telegram-Bot-Api-Secret-Token header)"""
        if not self.webhook_secret:
            logger.error("🚨 No webhook secret configured, rejecting request for security")
            return False
        
        if not secret_token:
            logger.error("🚨 No secret token provided in webhook request")
            return False
        
        # ✅ ПРАВИЛЬНО: Telegram Bot API использует простое сравнение secret token
        # НЕ HMAC подписи! Документация: https://core.telegram.org/bots/api#setwebhook
        return hmac.compare_digest(secret_token, self.webhook_secret)
    
    def validate_webhook_signature(self, request_body: bytes, signature: str) -> bool:
        """DEPRECATED: Use validate_webhook_secret_token instead. 
        Kept for backward compatibility."""
        logger.warning("⚠️ Using deprecated validate_webhook_signature method. Use validate_webhook_secret_token instead.")
        return self.validate_webhook_secret_token(signature)
    
    async def _get_webhook_info(self) -> dict:
        """Получить информацию о текущем webhook"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{self.bot_token}/getWebhookInfo"
                async with session.get(url) as response:
                    result = await response.json()
                    if result.get("ok"):
                        return result.get("result", {})
                    return {}
        except Exception as e:
            logger.error(f"❌ Ошибка при получении webhook info: {e}")
            return {}

    async def setup_webhook(self, webhook_base_url: str) -> bool:
        """Настроить webhook для платежей Telegram Stars"""
        import uuid
        request_id = str(uuid.uuid4())[:8]
        logger.info(f"🔧 [{request_id}] Starting webhook setup for URL: {webhook_base_url}")
        
        if not self.bot_token:
            logger.error(f"🚨 [{request_id}] TG_BOT_TOKEN not configured, cannot setup webhook")
            return False
        
        # 🔒 SECURITY FIX: Webhook secret обязателен для production
        if not self.webhook_secret:
            logger.error(f"🚨 [{request_id}] WEBHOOK_SECRET обязателен для безопасности платежей")
            logger.error(f"🔧 [{request_id}] Настройте переменную окружения WEBHOOK_SECRET")
            return False
            
        webhook_url = f"{webhook_base_url}/webhook/telegram"
        
        # 🔧 GUNICORN FIX: Проверяем текущий webhook перед настройкой
        try:
            current_webhook = await self._get_webhook_info()
            current_url = current_webhook.get("url", "")
            
            if current_url == webhook_url:
                logger.info(f"✅ [{request_id}] Webhook already configured correctly")
                return True
            
        except Exception as e:
            logger.warning(f"⚠️ [{request_id}] Could not check current webhook: {e} - proceeding with setup")
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
                data = {
                    "url": webhook_url,
                    "allowed_updates": ["pre_checkout_query", "message", "callback_query"],
                    "secret_token": self.webhook_secret  # 🔒 ОБЯЗАТЕЛЬНО для безопасности
                }
                
                logger.info(f"🔒 [{request_id}] Webhook настраивается с обязательной проверкой подписи")
                
                async with session.post(url, json=data) as response:
                    result = await response.json()
                    
                    if result.get("ok"):
                        logger.info(f"✅ [{request_id}] Telegram webhook настроен успешно: {webhook_url}")
                        return True
                    else:
                        error_desc = result.get("description", "Unknown error")
                        logger.error(f"❌ [{request_id}] Не удалось настроить webhook: {error_desc}")
                        return False
                        
        except Exception as e:
            logger.error(f"❌ [{request_id}] Ошибка при настройке webhook: {e}")
            return False
    
    def get_payment_info(self, payload: str) -> Dict[str, Any]:
        """Parse payment payload to extract info with enhanced security"""
        try:
            # 🔒 SECURITY FIX: Валидация payload перед парсингом
            if not isinstance(payload, str) or len(payload) > 500:  # Защита от слишком больших payload
                logger.warning(f"🚨 Invalid payload format or too long: {len(payload) if isinstance(payload, str) else type(payload)}")
                return {"type": "unknown", "payload": str(payload)[:100]}
            
            parts = payload.split('_')
            
            if len(parts) >= 3 and parts[0] == 'stars':
                # 🔒 SECURITY FIX: Строгая валидация каждой части
                try:
                    user_id = int(parts[1])
                    amount = int(parts[2])
                    
                    # Дополнительные проверки безопасности  
                    if user_id <= 0 or user_id > 999999999999:  # Telegram user_id может быть очень большим
                        logger.warning(f"🚨 User ID outside expected range: {user_id}")
                        raise ValueError("Invalid user_id range")
                    if amount < 10 or amount > 1000000:  # Минимальный депозит 10 звёзд
                        raise ValueError("Invalid amount range")
                        
                    return {
                        "type": "stars",
                        "user_id": user_id,
                        "amount": amount,
                        "token": parts[3] if len(parts) > 3 else None
                    }
                except ValueError as e:
                    logger.warning(f"🚨 Invalid payload data: {e}")
                    return {"type": "unknown", "payload": payload}
                    
        except (ValueError, IndexError, AttributeError) as e:
            logger.warning(f"🚨 Payload parsing error: {e}")
        
        return {"type": "unknown", "payload": payload}
    
    def get_stats(self) -> Dict[str, Any]:
        """Get payment service statistics"""
        return {
            "bot_token_configured": bool(self.bot_token),
            "provider_token_configured": bool(self.provider_token),
            "webhook_secret_configured": bool(self.webhook_secret)
        }