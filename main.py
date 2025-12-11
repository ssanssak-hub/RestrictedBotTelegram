#!/usr/bin/env python3
"""
ربات دانلود/آپلود تلگرام - نسخه کامل
ویژگی‌ها:
1. دانلود از کانال/گروه‌های تلگرام
2. آپلود به کاربران
3. مدیریت sessionهای امن
4. محدودیت‌های هوشمند
5. سرعت بالا با بهینه‌سازی
"""

import asyncio
import logging
import sys
from pathlib import Path

# اضافه کردن مسیر به sys.path
sys.path.append(str(Path(__file__).parent))

from bot.bot_core import TelegramBot
from userbot.userbot_core import UserBotManager
from core.database import DatabaseManager
from core.limits_manager import LimitsManager
from core.speed_optimizer import SpeedOptimizer

# تنظیمات لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/main.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

class DownloadManager:
    """مدیریت اصلی سیستم"""
    
    def __init__(self):
        self.config = self.load_config()
        self.db = DatabaseManager()
        self.limits = LimitsManager()
        self.speed_optimizer = SpeedOptimizer()
        
        self.bot = None
        self.userbot_manager = None
        
        self.is_running = False
        
    def load_config(self):
        """بارگذاری تنظیمات"""
        import json
        
        config_files = {
            'bot': 'config/bot_config.json',
            'userbot': 'config/userbot_config.json',
            'limits': 'config/limits_config.json',
            'speed': 'config/speed_config.json'
        }
        
        config = {}
        for key, file_path in config_files.items():
            path = Path(file_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    config[key] = json.load(f)
            else:
                logger.warning(f"Config file not found: {file_path}")
                config[key] = {}
        
        return config
    
    async def initialize(self):
        """مقداردهی اولیه سیستم"""
        logger.info("Initializing Download Manager...")
        
        # 1. ایجاد دیتابیس
        await self.db.initialize()
        logger.info("Database initialized")
        
        # 2. بارگذاری محدودیت‌ها
        await self.limits.load_config()
        logger.info("Limits manager initialized")
        
        # 3. شروع ربات تلگرام (در thread جدا)
        if self.config.get('bot', {}).get('enabled', True):
            self.start_telegram_bot()
            logger.info("Telegram bot starting...")
        
        # 4. شروع UserBot (اگر فعال باشد)
        if self.config.get('userbot', {}).get('enabled', False):
            await self.start_userbot_manager()
            logger.info("UserBot manager starting...")
        
        logger.info("✅ Download Manager initialized successfully")
    
    def start_telegram_bot(self):
        """شروع ربات تلگرام"""
        from threading import Thread
        
        def run_bot():
            bot_config = self.config.get('bot', {})
            bot = TelegramBot(
                token=bot_config.get('token'),
                api_id=bot_config.get('api_id'),
                api_hash=bot_config.get('api_hash'),
                db=self.db,
                limits=self.limits,
                speed_optimizer=self.speed_optimizer
            )
            
            self.bot = bot
            
            try:
                bot.start()
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
            except Exception as e:
                logger.error(f"Bot error: {e}")
        
        bot_thread = Thread(target=run_bot, daemon=True)
        bot_thread.start()
    
    async def start_userbot_manager(self):
        """شروع مدیریت UserBot"""
        userbot_config = self.config.get('userbot', {})
        
        self.userbot_manager = UserBotManager(
            api_id=userbot_config.get('api_id'),
            api_hash=userbot_config.get('api_hash'),
            db=self.db,
            limits=self.limits,
            speed_optimizer=self.speed_optimizer
        )
        
        await self.userbot_manager.initialize()
        
        # شروع UserBot در پس‌زمینه
        asyncio.create_task(self.userbot_manager.start())
    
    async def run(self):
        """اجرای اصلی سیستم"""
        self.is_running = True
        
        try:
            await self.initialize()
            
            logger.info("🚀 System is running. Press Ctrl+C to stop.")
            
            # حلقه اصلی
            while self.is_running:
                await asyncio.sleep(1)
                
                # اجرای کارهای دوره‌ای
                await self.run_periodic_tasks()
        
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"System error: {e}")
        finally:
            await self.shutdown()
    
    async def run_periodic_tasks(self):
        """کارهای دوره‌ای"""
        try:
            # پاکسازی کش هر 5 دقیقه
            await self.speed_optimizer.clean_cache()
            
            # به‌روزرسانی آمار هر 10 دقیقه
            await self.update_stats()
            
            # پشتیبان‌گیری هر ساعت
            await self.backup_system()
            
        except Exception as e:
            logger.error(f"Periodic task error: {e}")
    
    async def update_stats(self):
        """به‌روزرسانی آمار"""
        stats = {
            'total_users': await self.db.get_user_count(),
            'total_files': await self.db.get_file_count(),
            'total_downloads': await self.db.get_total_downloads(),
            'system_status': 'running'
        }
        
        logger.info(f"📊 Stats: {stats}")
    
    async def backup_system(self):
        """پشتیبان‌گیری از سیستم"""
        import shutil
        import datetime
        
        backup_dir = Path('backups')
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'backup_{timestamp}.zip'
        
        try:
            # پشتیبان از دیتابیس
            db_path = Path('data/database.db')
            if db_path.exists():
                shutil.copy2(db_path, backup_path)
                logger.info(f"✅ Backup created: {backup_path}")
        except Exception as e:
            logger.error(f"Backup error: {e}")
    
    async def shutdown(self):
        """خاموش کردن سیستم"""
        logger.info("Shutting down system...")
        
        self.is_running = False
        
        # توقف ربات
        if self.bot:
            self.bot.stop()
        
        # توقف UserBot
        if self.userbot_manager:
            await self.userbot_manager.shutdown()
        
        # بستن دیتابیس
        await self.db.close()
        
        logger.info("System shutdown complete")

# تابع اصلی
async def main():
    """تابع اصلی اجرا"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Telegram Download Manager')
    parser.add_argument('--mode', choices=['bot', 'userbot', 'both', 'web'],
                       default='both', help='Run mode')
    parser.add_argument('--config', default='config/', help='Config directory')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--test', action='store_true', help='Test mode')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug mode enabled")
    
    if args.test:
        logger.info("Running in test mode")
        # اجرای تست‌ها
        import subprocess
        subprocess.run([sys.executable, "-m", "pytest", "tests/"])
        return
    
    # ایجاد و اجرای سیستم
    manager = DownloadManager()
    
    try:
        await manager.run()
    except KeyboardInterrupt:
        logger.info("System stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
