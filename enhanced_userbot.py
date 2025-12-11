#!/usr/bin/env python3
# enhanced_userbot.py - UserBot با سیستم مدیریت session پیشرفته

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from session_manager import AdvancedSessionManager, SessionClientWrapper

# تنظیمات لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('enhanced_userbot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EnhancedUserBot:
    """UserBot با مدیریت session پیشرفته"""
    
    def __init__(self, config_path: Path = Path("config.json")):
        self.config_path = config_path
        self.config = self._load_config()
        
        # مدیر session
        self.session_manager = None
        self.client_wrapper = None
        
        # وضعیت
        self.is_running = False
        self.stats = {
            'start_time': None,
            'total_operations': 0,
            'successful_ops': 0,
            'failed_ops': 0,
            'session_rotations': 0,
            'last_error': None
        }
    
    def _load_config(self) -> dict:
        """بارگذاری تنظیمات"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        raise FileNotFoundError(f"Config file not found: {self.config_path}")
    
    async def initialize(self):
        """مقداردهی اولیه سیستم"""
        logger.info("Initializing EnhancedUserBot...")
        
        # ایجاد مدیر session
        self.session_manager = AdvancedSessionManager()
        
        # ایجاد wrapper برای کلاینت
        self.client_wrapper = SessionClientWrapper(self.session_manager)
        
        # بررسی session‌های موجود
        active_session = await self.session_manager.get_active_session_info()
        
        if not active_session:
            logger.info("No active session found, creating new one...")
            
            # ایجاد session جدید
            await self.session_manager.create_new_session(
                api_id=self.config['api_id'],
                api_hash=self.config['api_hash'],
                phone=self.config.get('phone')
            )
        
        logger.info("Initialization complete")
    
    async def get_me(self):
        """دریافت اطلاعات کاربر فعلی"""
        async def get_me_internal(client):
            return await client.get_me()
        
        try:
            me = await self.client_wrapper.execute_with_retry(get_me_internal)
            logger.info(f"Logged in as: {me.first_name} (@{me.username})")
            return me
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
    
    async def download_from_channel(self, channel_identifier: str, limit: int = 10):
        """دانلود از کانال"""
        async def download_internal(client):
            from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
            
            # دریافت موجودیت کانال
            entity = await client.get_entity(channel_identifier)
            logger.info(f"Accessing channel: {entity.title}")
            
            downloaded = 0
            async for message in client.iter_messages(entity, limit=limit):
                if message.media:
                    # شبیه‌سازی تأخیر انسانی
                    await asyncio.sleep(1)
                    
                    # دانلود فایل
                    file_name = f"download_{message.id}"
                    await message.download_media(file=file_name)
                    
                    downloaded += 1
                    logger.info(f"Downloaded file #{downloaded}: {file_name}")
            
            return downloaded
        
        try:
            result = await self.client_wrapper.execute_with_retry(download_internal)
            self.stats['successful_ops'] += 1
            return result
        except Exception as e:
            self.stats['failed_ops'] += 1
            self.stats['last_error'] = str(e)
            logger.error(f"Download failed: {e}")
            return 0
    
    async def monitor_channels(self, channels: list):
        """مانیتورینگ کانال‌ها"""
        logger.info(f"Starting to monitor {len(channels)} channels")
        
        from telethon import events
        
        client = await self.client_wrapper.get_client()
        
        # ثبت هندلر برای همه کانال‌ها
        @client.on(events.NewMessage(chats=channels))
        async def channel_handler(event):
            try:
                self.stats['total_operations'] += 1
                
                if event.message.media:
                    logger.info(f"New file in {event.chat.title}")
                    
                    # دانلود با مدیریت session
                    await self._safe_download(event.message)
                    
                    self.stats['successful_ops'] += 1
                    
            except Exception as e:
                self.stats['failed_ops'] += 1
                logger.error(f"Error in channel handler: {e}")
        
        return channel_handler
    
    async def _safe_download(self, message):
        """دانلود ایمن با مدیریت خطا"""
        async def download_func(client):
            file_name = f"auto_download_{message.id}"
            await message.download_media(file=file_name)
            logger.info(f"Auto-downloaded: {file_name}")
            return True
        
        try:
            await self.client_wrapper.execute_with_retry(download_func)
        except Exception as e:
            logger.error(f"Safe download failed: {e}")
    
    async def run_maintenance(self):
        """اجرای عملیات نگهداری"""
        logger.info("Running maintenance tasks...")
        
        # چرخش session دوره‌ای
        await self.session_manager.rotate_sessions()
        self.stats['session_rotations'] += 1
        
        # پاکسازی session‌های قدیمی
        await self.session_manager.cleanup_old_sessions()
        
        # اعتبارسنجی session‌ها
        validation = await self.session_manager.validate_sessions()
        
        # دریافت گزارش
        report = await self.session_manager.export_session_report()
        
        logger.info(f"Maintenance complete. Active sessions: {report['active_sessions']}")
        
        return report
    
    async def get_status_report(self) -> dict:
        """دریافت گزارش وضعیت"""
        session_report = await self.session_manager.export_session_report() if self.session_manager else {}
        
        return {
            'bot_status': 'running' if self.is_running else 'stopped',
            'uptime': (
                (datetime.now() - self.stats['start_time']).total_seconds()
                if self.stats['start_time'] else 0
            ),
            'statistics': self.stats,
            'session_info': {
                'active_session': (
                    await self.session_manager.get_active_session_info()
                    if self.session_manager else None
                ),
                'total_sessions': session_report.get('total_sessions', 0),
                'rotation_count': self.stats['session_rotations']
            },
            'last_error': self.stats['last_error'],
            'timestamp': datetime.now().isoformat()
        }
    
    async def start(self):
        """شروع UserBot"""
        if self.is_running:
            logger.warning("UserBot is already running")
            return
        
        try:
            self.stats['start_time'] = datetime.now()
            self.is_running = True
            
            # مقداردهی اولیه
            await self.initialize()
            
            # دریافت اطلاعات کاربر
            me = await self.get_me()
            if not me:
                raise Exception("Failed to login")
            
            # مانیتورینگ کانال‌ها
            channels = self.config.get('monitored_channels', [])
            if channels:
                await self.monitor_channels(channels)
            
            logger.info("✅ EnhancedUserBot started successfully")
            
            # حلقه اصلی
            while self.is_running:
                try:
                    # نگه داشتن اتصال
                    client = await self.client_wrapper.get_client()
                    
                    # اجرای عملیات دوره‌ای
                    await self.run_periodic_tasks()
                    
                    # انتظار
                    await asyncio.sleep(60)
                    
                except KeyboardInterrupt:
                    logger.info("Received interrupt signal")
                    break
                except Exception as e:
                    logger.error(f"Main loop error: {e}")
                    await asyncio.sleep(30)  # استراحت قبل از تلاش مجدد
        
        except Exception as e:
            logger.error(f"Failed to start UserBot: {e}")
            raise
        
        finally:
            await self.stop()
    
    async def run_periodic_tasks(self):
        """اجرای کارهای دوره‌ای"""
        # هر 30 دقیقه نگهداری
        if self.stats['total_operations'] % 30 == 0:
            await self.run_maintenance()
        
        # گزارش وضعیت هر ساعت
        if self.stats['total_operations'] % 60 == 0:
            report = await self.get_status_report()
            logger.info(f"Status report: {report['statistics']['successful_ops']} successful operations")
    
    async def stop(self):
        """توقف UserBot"""
        logger.info("Stopping EnhancedUserBot...")
        
        self.is_running = False
        
        if self.client_wrapper:
            await self.client_wrapper.close()
        
        logger.info("EnhancedUserBot stopped")

# تابع اصلی
async def main():
    """تابع اصلی اجرا"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Enhanced UserBot with session management')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--action', choices=['start', 'status', 'rotate', 'cleanup', 'report'],
                       default='start', help='Action to perform')
    
    args = parser.parse_args()
    
    # ایجاد UserBot
    userbot = EnhancedUserBot(Path(args.config))
    
    try:
        if args.action == 'start':
            await userbot.start()
        
        elif args.action == 'status':
            await userbot.initialize()
            report = await userbot.get_status_report()
            print(json.dumps(report, indent=2, ensure_ascii=False))
        
        elif args.action == 'rotate':
            await userbot.initialize()
            await userbot.session_manager.rotate_sessions(force=True)
            print("✅ Sessions rotated")
        
        elif args.action == 'cleanup':
            await userbot.initialize()
            await userbot.session_manager.cleanup_old_sessions()
            print("✅ Old sessions cleaned up")
        
        elif args.action == 'report':
            await userbot.initialize()
            report = await userbot.session_manager.export_session_report()
            print(json.dumps(report, indent=2, ensure_ascii=False))
    
    except Exception as e:
        logger.error(f"Action failed: {e}")
    
    finally:
        await userbot.stop()

if __name__ == "__main__":
    asyncio.run(main())
