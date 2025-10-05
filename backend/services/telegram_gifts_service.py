"""
Telegram Gifts API service for sending gifts to users.
Based on Telegram Bot API documentation: https://core.telegram.org/bots/api#sendgift
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from decimal import Decimal
import httpx

from config.settings import TG_BOT_TOKEN

logger = logging.getLogger(__name__)


class TelegramGiftsService:
    """Service for interacting with Telegram Gifts API."""
    
    def __init__(self, bot_token: str = None):
        self.bot_token = bot_token or TG_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        if not self.bot_token:
            logger.error("❌ Telegram bot token not configured")
            raise ValueError("TG_BOT_TOKEN is required")
        else:
            pass
    
    async def send_gift(self, user_id: int, gift_id: str, pay_for_upgrade: bool = False) -> Dict[str, Any]:
        """
        Send a gift to a user via Telegram API.
        
        Args:
            user_id: Telegram user ID
            gift_id: Telegram gift ID 
            pay_for_upgrade: Whether to pay for gift upgrade
            
        Returns:
            Dict with API response
            
        Raises:
            Exception: If API call fails
        """
        endpoint = f"{self.api_url}/sendGift"
        
        payload = {
            "user_id": user_id,
            "gift_id": gift_id,
            "pay_for_upgrade": pay_for_upgrade
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
                    logger.info(f"✅ Gift sent successfully: {response_data}")
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
                error_msg = f"Failed to send gift: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
    
    async def get_business_account_gifts(self, 
                                       offset: Optional[int] = None, 
                                       limit: Optional[int] = None,
                                       is_saved: Optional[bool] = None,
                                       is_unlimited: Optional[bool] = None,
                                       is_unique: Optional[bool] = None,
                                       sort_by_price: Optional[bool] = None) -> Dict[str, Any]:
        """
        Get gifts from business account.
        
        Args:
            offset: Offset for pagination
            limit: Limit for pagination 
            is_saved: Filter by saved/unsaved gifts
            is_unlimited: Filter by unlimited/limited gifts
            is_unique: Filter by unique gifts
            sort_by_price: Sort by price instead of send date
            
        Returns:
            Dict with API response containing owned gifts
        """
        endpoint = f"{self.api_url}/getBusinessAccountGifts"
        
        payload = {}
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if is_saved is not None:
            payload["is_saved"] = is_saved
        if is_unlimited is not None:
            payload["is_unlimited"] = is_unlimited
        if is_unique is not None:
            payload["is_unique"] = is_unique
        if sort_by_price is not None:
            payload["sort_by_price"] = sort_by_price
        
        logger.info(f"📡 Getting business account gifts with params: {payload}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    endpoint,
                    params=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                response_data = response.json()
                
                if response.status_code == 200 and response_data.get("ok"):
                    logger.info(f"✅ Business account gifts retrieved successfully")
                    return {
                        "success": True,
                        "data": response_data["result"]
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
                error_msg = f"Failed to get business account gifts: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
    
    async def get_business_account_star_balance(self) -> Dict[str, Any]:
        """
        Get star balance of business account.
        
        Returns:
            Dict with API response containing star balance
        """
        endpoint = f"{self.api_url}/getBusinessAccountStarBalance"
        
        logger.info(f"📡 Getting business account star balance")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    endpoint,
                    headers={"Content-Type": "application/json"}
                )
                
                response_data = response.json()
                
                if response.status_code == 200 and response_data.get("ok"):
                    balance = response_data["result"]
                    logger.info(f"✅ Business account star balance: {balance}")
                    return {
                        "success": True,
                        "balance": balance
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
                error_msg = f"Failed to get business account star balance: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
    
    async def send_business_account_gift(self, user_id: int, gift_id: str) -> Dict[str, Any]:
        """
        Send gift from business account to user.
        
        Args:
            user_id: Telegram user ID
            gift_id: Business account gift ID
            
        Returns:
            Dict with API response
        """
        endpoint = f"{self.api_url}/sendBusinessAccountGift"
        
        payload = {
            "user_id": user_id,
            "gift_id": gift_id
        }
        
        logger.info(f"📡 Sending business account gift {gift_id} to user {user_id}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                response_data = response.json()
                
                if response.status_code == 200 and response_data.get("ok"):
                    logger.info(f"✅ Business account gift sent successfully: {response_data}")
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
                error_msg = f"Failed to send business account gift: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }


# Singleton instance
telegram_gifts_service = TelegramGiftsService() if TG_BOT_TOKEN else None


async def send_telegram_gift_direct(user_id: int, gift_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Direct function to send Telegram gift - used in main.py
    
    Args:
        user_id: Telegram user ID
        gift_dict: Gift dictionary with telegram_gift_id
        
    Returns:
        Dict with success status and details
    """
    
    if not telegram_gifts_service:
        logger.error("❌ Telegram gifts service not initialized (TG_BOT_TOKEN missing?)")
        return {
            "success": False,
            "error": "Telegram gifts service not available"
        }
    
    telegram_gift_id = gift_dict.get("telegram_gift_id")
    if not telegram_gift_id:
        logger.error(f"❌ No telegram_gift_id in gift data: {gift_dict}")
        return {
            "success": False,
            "error": "Missing telegram_gift_id"
        }
    
    
    result = await telegram_gifts_service.send_gift(user_id, telegram_gift_id)
    
    if result["success"]:
        logger.info(f"✅ Gift {gift_dict.get('name')} sent successfully to user {user_id}")
    else:
        logger.error(f"❌ Failed to send gift {gift_dict.get('name')} to user {user_id}: {result.get('error')}")
    
    return result


async def send_unique_gift_direct(user_id: int, gift_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Direct function to send unique gift from business account - used for unique gifts
    
    Args:
        user_id: Telegram user ID
        gift_dict: Gift dictionary with business_gift_id for unique gifts
        
    Returns:
        Dict with success status and details
    """
    logger.info(f"🎁 send_unique_gift_direct called: user_id={user_id}")
    logger.info(f"🔍 Gift data: {gift_dict.keys()}")
    
    if not telegram_gifts_service:
        logger.error("❌ Telegram gifts service not initialized (TG_BOT_TOKEN missing?)")
        return {
            "success": False,
            "error": "Telegram gifts service not available"
        }
    
    business_gift_id = gift_dict.get("business_gift_id")
    if not business_gift_id:
        logger.error(f"❌ No business_gift_id in unique gift data: {gift_dict}")
        return {
            "success": False,
            "error": "Missing business_gift_id for unique gift"
        }
    
    logger.info(f"🎁 Sending unique gift {gift_dict.get('name')} (Business ID: {business_gift_id}) to user {user_id}")
    
    result = await telegram_gifts_service.send_business_account_gift(user_id, business_gift_id)
    
    if result["success"]:
        logger.info(f"✅ Unique gift {gift_dict.get('name')} sent successfully to user {user_id}")
    else:
        logger.error(f"❌ Failed to send unique gift {gift_dict.get('name')} to user {user_id}: {result.get('error')}")
    
    return result