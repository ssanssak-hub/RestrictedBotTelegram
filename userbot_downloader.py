#!/usr/bin/env python3
# userbot_downloader.py - UserBot ایمن برای دانلود از کانال‌ها

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto
import asyncio
import os
import json
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path

# تنظیمات لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('userbot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SafeUserBotDownloader:
    def __init__(self, api_id: int, api_hash: str):
        """
        Initialize Safe UserBot Downloader
        
        Args:
            api_id: API ID from my.telegram.org
            api_hash: API Hash from my.telegram.org
        """
        self.api_id = api_id
        self.api_hash = api_hash
        self.client = None
        
        # پوشه‌های پروژه
        self.base_dir = Path(__file__).parent
        self.downloads_dir = self.base_dir / "downloads"
        self.data_dir = self.base_dir / "data"
        
        # ایجاد پوشه‌های لازم
        for directory in [self.downloads_dir, self.data_dir]:
            directory.mkdir(exist_ok=True)
        
        # فایل‌های دیتابیس
        self.files_db = self.data_dir / "files_database.json"
        self.channels_db = self.data_dir / "channels.json"
        self.stats_db = self.data_dir / "stats.json"
        
        # تنظیمات ایمنی
        self.safety_settings = {
            'max_downloads_per_day': 50,
            'min_delay_between_actions': 1.5,  # seconds
            'max_delay_between_actions': 6.0,  # seconds
            'cooldown_after_error': 30,  # seconds
            'working_hours': [(9, 13), (16, 23)],  # 9AM-1PM, 4PM-11PM
            'skip_weekends': False,
        }
        
        # آمار
        self.stats = self.load_stats()
        self.today = datetime.now().date()
        
        # لیست کانال‌های مانیتور شده
        self.monitored_channels = self.load_channels()
        
        logger.info("SafeUserBotDownloader initialized")
    
    def load_stats(self) -> dict:
        """بارگذاری آمار از فایل"""
        try:
            if self.stats_db.exists():
                with open(self.stats_db, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading stats: {e}")
        
        return {
            'total_downloads': 0,
            'today_downloads': 0,
            'last_reset': datetime.now().isoformat(),
            'errors': 0,
            'last_error': None
        }
    
    def save_stats(self):
        """ذخیره آمار"""
        try:
            with open(self.stats_db, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving stats: {e}")
    
    def load_channels(self) -> list:
        """بارگذاری کانال‌های مانیتور شده"""
        try:
            if self.channels_db.exists():
                with open(self.channels_db, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading channels: {e}")
        
        return []
    
    def save_channels(self):
        """ذخیره کانال‌ها"""
        try:
            with open(self.channels_db, 'w', encoding='utf-8') as f:
                json.dump(self.monitored_channels, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving channels: {e}")
    
    async def human_delay(self, min_sec: float = None, max_sec: float = None):
        """
        تاخیر تصادفی برای شبیه‌سازی رفتار انسانی
        """
        if min_sec is None:
            min_sec = self.safety_settings['min_delay_between_actions']
        if max_sec is None:
            max_sec = self.safety_settings['max_delay_between_actions']
        
        delay = random.uniform(min_sec, max_sec)
        logger.debug(f"Human delay: {delay:.2f} seconds")
        await asyncio.sleep(delay)
    
    def is_safe_to_operate(self) -> bool:
        """بررسی شرایط ایمن برای فعالیت"""
        now = datetime.now()
        
        # بررسی روزهای آخر هفته
        if self.safety_settings['skip_weekends'] and now.weekday() >= 5:  # Sat=5, Sun=6
            logger.info("Today is weekend, skipping operation")
            return False
        
        # بررسی ساعت کاری
        current_hour = now.hour
        for start, end in self.safety_settings['working_hours']:
            if start <= current_hour < end:
                return True
        
        logger.info(f"Outside working hours ({current_hour}:00)")
        return False
    
    def can_download_more(self) -> bool:
        """بررسی امکان دانلود بیشتر"""
        # بررسی ریست روزانه
        today = datetime.now().date()
        if today != self.today:
            self.today = today
            self.stats['today_downloads'] = 0
            self.stats['last_reset'] = datetime.now().isoformat()
            self.save_stats()
        
        # بررسی محدودیت روزانه
        if self.stats['today_downloads'] >= self.safety_settings['max_downloads_per_day']:
            logger.warning(f"Daily download limit reached: {self.stats['today_downloads']}")
            return False
        
        return True
    
    async def simulate_typing(self, chat_id):
        """شبیه‌سازی عمل تایپ کردن"""
        try:
            async with self.client.action(chat_id, 'typing'):
                typing_duration = random.uniform(1.0, 3.0)
                await asyncio.sleep(typing_duration)
        except:
            pass
    
    async def download_file(self, message, retry_count: int = 0) -> dict:
        """
        دانلود فایل از پیام با قابلیت تلاش مجدد
        
        Returns:
            dict: اطلاعات فایل دانلود شده یا None
        """
        max_retries = 3
        
        try:
            if not message.media:
                logger.warning("Message has no media")
                return None
            
            # تعیین نام فایل
            if message.document:
                file_name = message.document.attributes[0].file_name
                file_ext = os.path.splitext(file_name)[1]
            elif message.video:
                file_name = f"video_{message.id}.mp4"
                file_ext = '.mp4'
            elif message.audio:
                file_name = f"audio_{message.id}.mp3"
                file_ext = '.mp3'
            elif message.photo:
                file_name = f"photo_{message.id}.jpg"
                file_ext = '.jpg'
            else:
                logger.warning(f"Unsupported media type: {type(message.media)}")
                return None
            
            # ایجاد نام منحصربفرد
            base_name = os.path.splitext(file_name)[0]
            counter = 1
            while (self.downloads_dir / file_name).exists():
                file_name = f"{base_name}_{counter}{file_ext}"
                counter += 1
            
            file_path = self.downloads_dir / file_name
            
            # شبیه‌سازی تایپ قبل از دانلود
            await self.simulate_typing(message.chat_id)
            
            # تاخیر انسانی
            await self.human_delay()
            
            logger.info(f"Downloading: {file_name}")
            
            # دانلود با callback پیشرفت
            def progress_callback(current, total):
                percent = (current / total) * 100
                if percent % 25 == 0:  # هر 25% لاگ کن
                    logger.info(f"Download progress: {percent:.1f}%")
            
            # دانلود فایل
            await message.download_media(
                file=str(file_path),
                progress_callback=progress_callback
            )
            
            # بررسی اندازه فایل
            file_size = file_path.stat().st_size
            if file_size == 0:
                logger.error(f"Downloaded file is empty: {file_name}")
                file_path.unlink()  # حذف فایل خالی
                
                if retry_count < max_retries:
                    logger.info(f"Retrying download (attempt {retry_count + 1})")
                    await asyncio.sleep(5)
                    return await self.download_file(message, retry_count + 1)
                return None
            
            # ثبت اطلاعات فایل
            file_info = {
                'id': message.id,
                'chat_id': message.chat_id,
                'chat_title': getattr(message.chat, 'title', 'Unknown'),
                'file_name': file_name,
                'file_path': str(file_path),
                'file_size': file_size,
                'file_type': file_ext.replace('.', '').upper(),
                'download_time': datetime.now().isoformat(),
                'caption': message.text or message.message or '',
                'message_date': message.date.isoformat() if message.date else None,
                'forwarded': bool(message.fwd_from),
                'forwarded_from': str(message.fwd_from.from_id) if message.fwd_from else None
            }
            
            # به‌روزرسانی آمار
            self.stats['total_downloads'] += 1
            self.stats['today_downloads'] += 1
            self.save_stats()
            
            logger.info(f"✅ Downloaded successfully: {file_name} ({file_size:,} bytes)")
            
            # تاخیر بعد از دانلود موفق
            await self.human_delay(3, 8)
            
            return file_info
            
        except Exception as e:
            logger.error(f"Download failed: {str(e)}")
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            self.save_stats()
            
            if retry_count < max_retries:
                logger.info(f"Retrying after error (attempt {retry_count + 1})")
                await asyncio.sleep(10 * (retry_count + 1))
                return await self.download_file(message, retry_count + 1)
            
            return None
    
    async def save_file_info(self, file_info: dict):
        """ذخیره اطلاعات فایل در دیتابیس"""
        try:
            # بارگذاری دیتابیس موجود
            files = []
            if self.files_db.exists():
                with open(self.files_db, 'r', encoding='utf-8') as f:
                    files = json.load(f)
            
            # اضافه کردن فایل جدید
            files.append(file_info)
            
            # ذخیره دیتابیس
            with open(self.files_db, 'w', encoding='utf-8') as f:
                json.dump(files, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"File info saved: {file_info['file_name']}")
            
        except Exception as e:
            logger.error(f"Error saving file info: {e}")
    
    async def add_channel(self, channel_identifier: str):
        """اضافه کردن کانال جدید برای مانیتورینگ"""
        try:
            entity = await self.client.get_entity(channel_identifier)
            
            channel_info = {
                'id': entity.id,
                'username': getattr(entity, 'username', None),
                'title': getattr(entity, 'title', 'Unknown'),
                'added_date': datetime.now().isoformat(),
                'last_check': None,
                'active': True
            }
            
            # بررسی تکراری نبودن
            for chan in self.monitored_channels:
                if chan['id'] == channel_info['id']:
                    logger.info(f"Channel already monitored: {channel_info['title']}")
                    return False
            
            self.monitored_channels.append(channel_info)
            self.save_channels()
            
            logger.info(f"✅ Channel added: {channel_info['title']}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding channel: {e}")
            return False
    
    async def process_message(self, message):
        """پردازش پیام دریافتی"""
        try:
            # بررسی شرایط ایمن
            if not self.is_safe_to_operate():
                logger.debug("Not safe to operate, skipping message")
                return
            
            if not self.can_download_more():
                logger.warning("Download limit reached, skipping message")
                return
            
            # بررسی نوع پیام
            if not message.media:
                # پیام متنی با لینک
                if message.text and 't.me/' in message.text:
                    await self.process_message_link(message.text)
                return
            
            # دانلود فایل
            file_info = await self.download_file(message)
            
            if file_info:
                # ذخیره اطلاعات
                await self.save_file_info(file_info)
                
                # گزارش موفقیت
                chat_title = file_info['chat_title']
                file_name = file_info['file_name']
                logger.info(f"✅ Processed: {file_name} from {chat_title}")
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await asyncio.sleep(self.safety_settings['cooldown_after_error'])
    
    async def process_message_link(self, link: str):
        """پردازش لینک مستقیم پیام"""
        try:
            # پارس کردن لینک: https://t.me/channel/123
            parts = link.strip().split('/')
            if len(parts) < 5:
                logger.warning(f"Invalid link format: {link}")
                return
            
            channel_part = parts[-2]
            try:
                message_id = int(parts[-1])
            except ValueError:
                logger.warning(f"Invalid message ID in link: {link}")
                return
            
            # دریافت پیام
            message = await self.client.get_messages(channel_part, ids=message_id)
            
            if message:
                await self.process_message(message)
            else:
                logger.warning(f"Message not found: {link}")
                
        except Exception as e:
            logger.error(f"Error processing link {link}: {e}")
    
    async def setup_handlers(self):
        """تنظیم هندلرهای رویداد"""
        
        # هندلر برای پیام‌های جدید در کانال‌های مانیتور شده
        @self.client.on(events.NewMessage(chats=[c['id'] for c in self.monitored_channels if c['active']]))
        async def channel_message_handler(event):
            await self.process_message(event.message)
        
        # هندلر برای پیام‌های فوروارد شده به UserBot
        @self.client.on(events.NewMessage(incoming=True))
        async def forwarded_message_handler(event):
            if event.message.fwd_from:
                logger.info(f"📩 Forwarded message from {event.message.fwd_from.from_id}")
                await self.process_message(event.message)
        
        # هندلر برای دستورات
        @self.client.on(events.NewMessage(pattern=r'^/addchannel (.+)$'))
        async def add_channel_handler(event):
            channel_identifier = event.pattern_match.group(1)
            success = await self.add_channel(channel_identifier)
            
            if success:
                await event.reply(f"✅ کانال اضافه شد")
            else:
                await event.reply(f"❌ خطا در اضافه کردن کانال")
        
        @self.client.on(events.NewMessage(pattern=r'^/stats$'))
        async def stats_handler(event):
            stats_text = (
                f"📊 آمار UserBot:\n"
                f"• کل دانلود‌ها: {self.stats['total_downloads']}\n"
                f"• دانلود امروز: {self.stats['today_downloads']}\n"
                f"• خطاها: {self.stats['errors']}\n"
                f"• کانال‌های فعال: {len([c for c in self.monitored_channels if c['active']])}\n"
                f"• آخرین ریست: {self.stats['last_reset']}"
            )
            await event.reply(stats_text)
    
    async def start(self):
        """شروع UserBot"""
        logger.info("Starting SafeUserBotDownloader...")
        
        # ایجاد کلاینت با تنظیمات
        self.client = TelegramClient(
            session=str(self.data_dir / 'userbot_session'),
            api_id=self.api_id,
            api_hash=self.api_hash,
            device_model="iPhone 13 Pro",
            system_version="iOS 15.4",
            app_version="8.4.1",
            lang_code="fa",
            system_lang_code="fa-IR"
        )
        
        try:
            # اتصال
            await self.client.start()
            
            me = await self.client.get_me()
            logger.info(f"✅ Logged in as: {me.first_name} (@{me.username})")
            logger.info(f"📱 Phone: {me.phone}")
            
            # تنظیم هندلرها
            await self.setup_handlers()
            
            # نمایش وضعیت
            logger.info("=" * 50)
            logger.info(f"Monitored channels: {len(self.monitored_channels)}")
            logger.info(f"Download directory: {self.downloads_dir}")
            logger.info(f"Daily limit: {self.safety_settings['max_downloads_per_day']}")
            logger.info("=" * 50)
            logger.info("✅ UserBot is running. Press Ctrl+C to stop.")
            logger.info("Commands: /addchannel <link>, /stats")
            
            # نگه داشتن ربات فعال
            await self.client.run_until_disconnected()
            
        except KeyboardInterrupt:
            logger.info("Received interrupt, shutting down...")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            await self.disconnect()
    
    async def disconnect(self):
        """قطع ارتباط ایمن"""
        if self.client and self.client.is_connected():
            await self.client.disconnect()
            logger.info("Disconnected from Telegram")
        
        # ذخیره نهایی آمار
        self.save_stats()

# تابع اصلی
async def main():
    """تابع اصلی اجرای برنامه"""
    
    # خوانتن تنظیمات از فایل config
    config_file = Path(__file__).parent / "config.json"
    if not config_file.exists():
        # ایجاد فایل config پیش‌فرض
        default_config = {
            "api_id": "YOUR_API_ID_HERE",
            "api_hash": "YOUR_API_HASH_HERE",
            "monitored_channels": [
                "https://t.me/sample_channel"
            ]
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        print(f"⚠️  فایل config.json ایجاد شد. لطفاً مقادیر را پر کنید.")
        print(f"   فایل: {config_file}")
        return
    
    # بارگذاری تنظیمات
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    api_id = config.get("api_id")
    api_hash = config.get("api_hash")
    
    if not api_id or not api_hash or api_id == "YOUR_API_ID_HERE":
        print("❌ لطفاً api_id و api_hash را در فایل config.json تنظیم کنید.")
        print("   از my.telegram.org دریافت کنید.")
        return
    
    # ایجاد و اجرای UserBot
    downloader = SafeUserBotDownloader(int(api_id), api_hash)
    
    # اضافه کردن کانال‌های از پیش تعریف شده
    for channel in config.get("monitored_channels", []):
        await downloader.add_channel(channel)
    
    # اجرای UserBot
    await downloader.start()

if __name__ == "__main__":
    # اجرای برنامه
    asyncio.run(main())
