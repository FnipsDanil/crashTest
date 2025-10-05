"""
Telegram Alerts Service for notifying about pending payment requests
"""

import logging
import os
from typing import Dict, Any
import httpx
from decimal import Decimal

logger = logging.getLogger(__name__)

# Get tokens from environment variables
TELEGRAM_ALERT_BOT_TOKEN = os.getenv('TELEGRAM_ALERT_BOT_TOKEN')
ADMIN_CHAT_ID = os.getenv('ADMIN_CHAT_ID')

class TelegramAlertsService:
    """Service for sending Telegram alerts to admin"""
    
    def __init__(self, alert_bot_token: str = None, admin_chat_id: str = None):
        self.alert_bot_token = alert_bot_token or TELEGRAM_ALERT_BOT_TOKEN
        self.admin_chat_id = admin_chat_id or ADMIN_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.alert_bot_token}" if self.alert_bot_token else None
        
        if not self.alert_bot_token:
            logger.error("❌ Telegram alert bot token not configured")
            raise ValueError("TELEGRAM_ALERT_BOT_TOKEN is required")
        
        if not self.admin_chat_id:
            logger.warning("⚠️ Admin chat ID not configured - alerts will be disabled")
        else:
            pass
    
    async def send_alert(self, message: str) -> Dict[str, Any]:
        """
        Send alert message to admin chat
        
        Args:
            message: Alert message text
            
        Returns:
            Dict with success status and details
        """
        if not self.admin_chat_id:
            logger.warning("⚠️ Cannot send alert - admin chat ID not configured")
            return {
                "success": False,
                "error": "Admin chat ID not configured"
            }
        
        endpoint = f"{self.api_url}/sendMessage"
        
        payload = {
            "chat_id": self.admin_chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                response_data = response.json()
                
                if response.status_code == 200 and response_data.get("ok"):
                    return {
                        "success": True,
                        "data": response_data
                    }
                else:
                    error_msg = response_data.get("description", "Unknown error")
                    logger.error(f"❌ Telegram API error: {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "code": response_data.get("error_code")
                    }
                    
            except httpx.TimeoutException:
                error_msg = "Telegram API timeout"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
            except Exception as e:
                error_msg = f"Failed to send alert: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
    
    async def notify_pending_payment_request(self, user_id: int, username: str, gift_name: str, price: Decimal) -> Dict[str, Any]:
        """
        Send notification about new pending payment request
        
        Args:
            user_id: Telegram user ID
            username: User's username
            gift_name: Name of the requested gift
            price: Price of the gift
            
        Returns:
            Dict with success status and details
        """
        from datetime import datetime
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        message = (
            f"🔔 <b>Новый запрос на вывод уникального подарка</b>\n\n"
            f"👤 Пользователь: {username or 'Без имени'} (ID: {user_id})\n"
            f"🎁 Подарок: {gift_name}\n"
            f"💰 Цена: {price} звёзд\n"
            f"⏰ Время: {current_time}\n\n"
            f"ℹ️ Проверьте таблицу payment_requests в базе данных"
        )
        
        return await self.send_alert(message)


# Global instance - will be None if tokens are not configured
telegram_alerts_service = None

try:
    if TELEGRAM_ALERT_BOT_TOKEN and ADMIN_CHAT_ID:
        telegram_alerts_service = TelegramAlertsService()
    else:
        logger.warning("⚠️ Telegram alerts disabled - missing TELEGRAM_ALERT_BOT_TOKEN or ADMIN_CHAT_ID")
except Exception as e:
    logger.error(f"❌ Failed to initialize Telegram alerts service: {e}")


async def send_pending_payment_alert(user_id: int, username: str, gift_name: str, price: Decimal):
    """
    Send alert about pending payment request
    
    Args:
        user_id: Telegram user ID
        username: User's username  
        gift_name: Name of the requested gift
        price: Price of the gift
    """
    if not telegram_alerts_service:
        logger.warning("⚠️ Cannot send alert - Telegram alerts service not initialized")
        return
    
    try:
        result = await telegram_alerts_service.notify_pending_payment_request(
            user_id, username, gift_name, price
        )
        
        if result["success"]:
            pass
        else:
            logger.error(f"❌ Failed to send pending payment alert: {result.get('error')}")
            
    except Exception as e:
        logger.error(f"❌ Error sending pending payment alert: {e}")