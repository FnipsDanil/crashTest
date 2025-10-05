"""
Business Connection Helper Script
Helps to get Business Connection ID by listening for business_connection updates
"""

import os
import sys
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import BusinessConnection
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class BusinessConnectionHelper:
    """Helper service to capture business connection ID"""
    
    def __init__(self):
        self.bot_token = os.getenv('TG_BOT_SENDER_TOKEN')
        
        if not self.bot_token:
            raise ValueError("TG_BOT_SENDER_TOKEN environment variable is required")
        
        # Initialize bot and dispatcher
        self.bot = Bot(token=self.bot_token)
        self.dp = Dispatcher()
        
        # Register handlers
        self.dp.business_connection.register(self.handle_business_connection)
        
        logger.info(f"✅ Business connection helper initialized")
        logger.info(f"🤖 Bot token: ...{self.bot_token[-10:]}")
    
    async def handle_business_connection(self, business_connection: BusinessConnection):
        """Handle business connection updates"""
        try:
            connection_id = business_connection.id
            user = business_connection.user
            is_enabled = business_connection.is_enabled
            can_reply = business_connection.can_reply
            
            print("\n" + "🎉" * 60)
            print("✅ BUSINESS CONNECTION RECEIVED!")
            print("🎉" * 60)
            print(f"\n🔑 Connection ID: {connection_id}")
            print(f"👤 Business User: {user.first_name} (@{user.username})")
            print(f"🟢 Enabled: {is_enabled}")
            print(f"💬 Can Reply: {can_reply}")
            print(f"📅 Connected: {business_connection.date}")
            
            # Save to environment file
            env_file_path = ".env"
            connection_line = f"BUSINESS_CONNECTION_ID={connection_id}"
            
            try:
                # Read existing .env file
                env_lines = []
                if os.path.exists(env_file_path):
                    with open(env_file_path, 'r', encoding='utf-8') as f:
                        env_lines = [line.strip() for line in f.readlines()]
                
                # Remove existing BUSINESS_CONNECTION_ID line
                env_lines = [line for line in env_lines if not line.startswith('BUSINESS_CONNECTION_ID=')]
                
                # Add new connection ID
                env_lines.append(connection_line)
                
                # Write back to .env file
                with open(env_file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(env_lines) + '\n')
                
                print(f"\n💾 Connection ID saved to {env_file_path}")
                
            except Exception as e:
                logger.error(f"❌ Failed to save to .env file: {e}")
                print(f"❌ Не удалось сохранить в .env файл: {e}")
            
            print("\n📋 Copy this for manual setup:")
            print(f"BUSINESS_CONNECTION_ID={connection_id}")
            print("\n🚀 Теперь можете запустить gift_sender.py!")
            print("🎉" * 60)
            
            logger.info(f"✅ Business connection received: {connection_id}")
            
        except Exception as e:
            logger.error(f"❌ Error handling business connection: {e}")
    
    async def start_listening(self):
        """Start listening for business connection updates"""
        try:
            print("🎯 ИНСТРУКЦИЯ ПО ПОЛУЧЕНИЮ BUSINESS CONNECTION ID")
            print("=" * 60)
            print("1. 📱 Откройте Telegram на телефоне")
            print("2. ⚙️ Зайдите в Settings > Business")
            print("3. 🤖 Найдите раздел 'Chatbots' или 'Боты'")
            print("4. ➕ Нажмите 'Add Bot' или 'Добавить бота'")
            print(f"5. 🔍 Найдите бота @{(await self.bot.get_me()).username}")
            print("6. ✅ Подключите бота к своему бизнес-аккаунту")
            print("7. 📨 Скрипт автоматически получит Connection ID")
            print("=" * 60)
            print("🔄 Ожидаем подключения бизнес-аккаунта...")
            print("⏹️ Нажмите Ctrl+C для выхода")
            print()
            
            # Start polling
            await self.dp.start_polling(self.bot)
            
        except KeyboardInterrupt:
            logger.info("⏹️ Script stopped by user")
            print("\n⏹️ Скрипт остановлен пользователем")
        except Exception as e:
            logger.error(f"❌ Error during polling: {e}")
            print(f"❌ Ошибка: {e}")
        finally:
            await self.bot.session.close()


async def main():
    """Main function"""
    try:
        helper = BusinessConnectionHelper()
        await helper.start_listening()
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        print(f"❌ Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())