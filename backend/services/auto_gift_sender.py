"""
Automatic Gift Sender Service

This service automatically processes approved payment requests and sends unique gifts
via the userbot-gifter API. It runs as a background task and checks for pending requests.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import PaymentRequest, User, VerifiedSender, Gift
from services.database_service import DatabaseService

logger = logging.getLogger(__name__)

# Configuration
USERBOT_GIFTER_URL = os.getenv("USERBOT_GIFTER_URL", "http://userbot-gifter:8001")
CHECK_INTERVAL = int(os.getenv("GIFT_SENDER_CHECK_INTERVAL", "30"))  # seconds
MESSAGE_VERIFICATION_HOURS = int(os.getenv("MESSAGE_VERIFICATION_HOURS", "48"))
AUTO_APPROVE_ENABLED = os.getenv("AUTO_APPROVE_GIFTS", "false").lower() == "true"


class AutoGiftSender:
    """Service for automatic gift sending"""

    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.is_running = False

    async def start(self):
        """Start the automatic gift sender background task"""
        self.is_running = True
        logger.info("🚀 Auto Gift Sender service started")

        while self.is_running:
            try:
                await self.process_pending_requests()
            except Exception as e:
                logger.error(f"❌ Error in auto gift sender loop: {e}", exc_info=True)

            await asyncio.sleep(CHECK_INTERVAL)

    async def stop(self):
        """Stop the automatic gift sender"""
        self.is_running = False
        await self.http_client.aclose()
        logger.info("🛑 Auto Gift Sender service stopped")

    async def process_pending_requests(self):
        """Process all approved payment requests"""
        async for session in get_db():
            try:
                # Get all approved payment requests
                result = await session.execute(
                    select(PaymentRequest)
                    .where(PaymentRequest.status == 'approved')
                    .order_by(PaymentRequest.approved_at)
                )
                requests = result.scalars().all()

                if not requests:
                    logger.debug("No approved payment requests to process")
                    return

                logger.info(f"📦 Found {len(requests)} approved gift requests to process")

                for request in requests:
                    try:
                        await self.process_single_request(session, request)
                    except Exception as e:
                        logger.error(f"❌ Error processing request {request.id}: {e}", exc_info=True)
                        # Continue with next request even if this one fails

                await session.commit()

            except Exception as e:
                logger.error(f"❌ Error in process_pending_requests: {e}", exc_info=True)
                await session.rollback()
            finally:
                await session.close()
                break  # Exit the async for loop after processing

    async def process_single_request(self, session: AsyncSession, request: PaymentRequest):
        """Process a single payment request"""
        logger.info(f"🎁 Processing gift request #{request.id} for user {request.user_id}")

        # Get user info
        user = await session.get(User, request.user_id)
        if not user:
            logger.error(f"❌ User {request.user_id} not found")
            await self.cancel_request(session, request, "user_not_found")
            return

        # Check if user is verified (sent messages recently)
        is_verified = await self.check_user_verification(session, user.telegram_id)
        if not is_verified:
            logger.warning(f"⚠️ User {user.telegram_id} is not verified (no recent messages)")
            await self.cancel_request(session, request, "no_message")
            return

        # Get gift info
        gift = await session.get(Gift, request.gift_id)
        if not gift:
            logger.error(f"❌ Gift {request.gift_id} not found")
            await self.cancel_request(session, request, "gift_not_found")
            return

        # Check if gift is still unique and active
        if not gift.is_unique or not gift.is_active:
            logger.warning(f"⚠️ Gift {gift.id} is not unique or not active")
            await self.cancel_request(session, request, "gift_not_available")
            return

        # Send gift via userbot-gifter API
        success = await self.send_gift_via_userbot(
            gift_name_prefix=gift.business_gift_id or gift.id,
            recipient_telegram_id=user.telegram_id
        )

        if success:
            # Mark request as completed
            request.status = 'completed'
            request.completed_at = datetime.utcnow()
            logger.info(f"✅ Gift request #{request.id} completed successfully")
        else:
            # Mark as failed (will retry on next cycle)
            logger.error(f"❌ Failed to send gift for request #{request.id}")
            # Don't cancel - might be temporary issue, will retry next cycle

    async def check_user_verification(self, session: AsyncSession, telegram_id: int) -> bool:
        """Check if user has sent messages within the verification window"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=MESSAGE_VERIFICATION_HOURS)

            result = await session.execute(
                select(VerifiedSender)
                .where(
                    and_(
                        VerifiedSender.chat_id == telegram_id,
                        VerifiedSender.last_message_at >= cutoff_time,
                        VerifiedSender.is_blocked == False
                    )
                )
            )
            sender = result.scalar_one_or_none()

            if sender:
                logger.info(f"✅ User {telegram_id} is verified (last message: {sender.last_message_at})")
                return True
            else:
                logger.warning(f"⚠️ User {telegram_id} is not verified or message too old")
                return False

        except Exception as e:
            logger.error(f"❌ Error checking verification for user {telegram_id}: {e}")
            return False

    async def send_gift_via_userbot(self, gift_name_prefix: str, recipient_telegram_id: int) -> bool:
        """Send gift via userbot-gifter API"""
        try:
            url = f"{USERBOT_GIFTER_URL}/transfer-gift"
            payload = {
                "gift_name_prefix": gift_name_prefix,
                "recipient_id": recipient_telegram_id,
                "star_count": 25  # Transfer cost
            }

            logger.info(f"📤 Sending gift transfer request: {payload}")

            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info(f"📥 Userbot response: {result}")

            if result.get("status") == "success":
                logger.info(f"✅ Gift sent successfully: {result.get('slug')}")
                return True
            else:
                logger.error(f"❌ Gift transfer failed: {result.get('message')}")
                return False

        except httpx.HTTPStatusError as e:
            logger.error(f"❌ HTTP error sending gift: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending gift via userbot: {e}", exc_info=True)
            return False

    async def cancel_request(self, session: AsyncSession, request: PaymentRequest, reason: str):
        """Cancel a payment request with a reason"""
        logger.warning(f"🚫 Canceling request #{request.id} - reason: {reason}")

        request.status = 'canceled'
        request.cancel_reason = reason

        # The auto_refund trigger in the database will handle the refund automatically
        logger.info(f"💰 Auto-refund trigger will refund {request.price_stars} stars to user {request.user_id}")


# Global instance
auto_gift_sender = AutoGiftSender()


async def start_auto_gift_sender():
    """Start the auto gift sender service"""
    await auto_gift_sender.start()


async def stop_auto_gift_sender():
    """Stop the auto gift sender service"""
    await auto_gift_sender.stop()
