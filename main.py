# -*- coding: utf-8 -*-
# main.py - فایل اصلی راه‌اندازی ربات تلگرام

import asyncio
import sys
import logging
import signal
from pathlib import Path
from datetime import datetime

# تنظیمات پیشرفته logging
log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
log_datefmt = '%Y-%m-%d %H:%M:%S'

# ایجاد پوشه logs اگر وجود ندارد
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# فایل لاگ با تاریخ
log_file = log_dir / f"bot_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    datefmt=log_datefmt,
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# کاهش لاگ‌های کتابخانه‌های دیگر
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# رفع مشکل asyncio در ویندوز
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# اضافه کردن مسیر پروژه
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# متغیرهای سراسری
app = None
bot_start_time = None

async def shutdown(application):
    """خاموش کردن امن ربات"""
    logger.info("🔄 در حال خاموش کردن ربات...")
    
    try:
        # ارسال پیام خداحافظی به ادمین (اگر تنظیم شده)
        if application.bot_data.get('admin_id'):
            try:
                await application.bot.send_message(
                    chat_id=application.bot_data['admin_id'],
                    text="🛑 ربات در حال خاموش شدن..."
                )
            except Exception as e:
                logger.warning(f"خطا در ارسال پیام خداحافظی: {e}")
        
        await application.stop()
        await application.shutdown()
        logger.info("✅ ربات با موفقیت خاموش شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در خاموش کردن ربات: {e}")

def signal_handler(signum, frame):
    """مدیریت سیگنال‌های توقف"""
    logger.info(f"📡 دریافت سیگنال توقف: {signum}")
    print("\n🛑 درخواست توقف ربات دریافت شد...")
    
    if app:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(shutdown(app))

async def startup_message(application):
    """ارسال پیام راه‌اندازی به ادمین"""
    try:
        from config import BOT_CONFIG
        
        if 'admin_id' in BOT_CONFIG and BOT_CONFIG['admin_id']:
            bot_info = await application.bot.get_me()
            start_time_str = bot_start_time.strftime('%Y-%m-%d %H:%M:%S')
            
            message = (
                "✅ **ربات راه‌اندازی شد**\n\n"
                f"🤖 نام: {bot_info.first_name}\n"
                f"🔗 یوزرنیم: @{bot_info.username}\n"
                f"🆔 آیدی: `{bot_info.id}`\n"
                f"⏰ زمان شروع: {start_time_str}\n"
                f"💻 سرور: {sys.platform}\n"
                f"🐍 پایتون: {sys.version.split()[0]}"
            )
            
            await application.bot.send_message(
                chat_id=BOT_CONFIG['admin_id'],
                text=message,
                parse_mode='Markdown'
            )
            logger.info("✅ پیام راه‌اندازی برای ادمین ارسال شد")
            
    except Exception as e:
        logger.warning(f"خطا در ارسال پیام راه‌اندازی: {e}")

async def check_bot_info(application):
    """بررسی اطلاعات ربات"""
    try:
        bot = await application.bot.get_me()
        
        # ذخیره اطلاعات در application.bot_data
        application.bot_data['bot_info'] = {
            'id': bot.id,
            'username': bot.username,
            'first_name': bot.first_name,
            'last_name': bot.last_name,
            'is_bot': bot.is_bot
        }
        
        # بررسی اینکه آیا ربات می‌تواند پیام‌ها را بخواند
        try:
            await application.bot.get_updates(offset=-1, limit=1)
            logger.info("✅ ربات قادر به دریافت آپدیت‌ها است")
        except Exception as e:
            logger.warning(f"⚠️ هشدار: ممکن است مشکل در اتصال باشد: {e}")
            
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در بررسی اطلاعات ربات: {e}")
        return False

def check_dependencies():
    """بررسی وابستگی‌های پروژه"""
    required_packages = {
        'python-telegram-bot': 'telegram',
        'httpx': 'httpx',
        'aiohttp': 'aiohttp'
    }
    
    missing_packages = []
    installed_packages = []
    
    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name)
            installed_packages.append(package_name)
        except ImportError:
            missing_packages.append(package_name)
    
    if installed_packages:
        print("✅ وابستگی‌های نصب شده:")
        for pkg in installed_packages:
            print(f"   📦 {pkg}")
    
    if missing_packages:
        print("\n❌ وابستگی‌های مفقود:")
        for pkg in missing_packages:
            print(f"   ⚠️  {pkg}")
        
        print("\n🔧 برای نصب از دستور زیر استفاده کنید:")
        print(f"   pip install {' '.join(missing_packages)}")
        
        # پیشنهاد نصب همه
        all_packages = list(required_packages.keys())
        print(f"\n💡 پیشنهاد: همه وابستگی‌ها را نصب کنید:")
        print(f"   pip install {' '.join(all_packages)}")
        
        return False
    
    return True

async def setup_bot(application):
    """تنظیم اولیه ربات"""
    try:
        # ثبت سیگنال‌های توقف
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)
        else:
            logger.info("⚠️ سیستم عامل ویندوز - سیگنال‌ها پشتیبانی نمی‌شوند")
        
        # بارگذاری تنظیمات
        from config import TOKEN, BOT_CONFIG
        
        # بررسی توکن
        if not TOKEN or TOKEN.strip() == "YOUR_TOKEN_HERE":
            logger.error("❌ توکن در config.py تنظیم نشده است")
            return False
            
        if len(TOKEN) < 40:  # توکن‌های تلگرام معمولا بلند هستند
            logger.warning("⚠️ طول توکن غیرمعمول است - ممکن است نامعتبر باشد")
        
        # ذخیره تنظیمات در application
        application.bot_data['config'] = BOT_CONFIG
        application.bot_data['admin_id'] = BOT_CONFIG.get('admin_id')
        
        # بررسی اطلاعات ربات
        if not await check_bot_info(application):
            return False
        
        # بارگذاری هندلرها
        try:
            from handlers import setup_handlers
            await setup_handlers(application)
            logger.info("✅ همه هندلرها ثبت شدند")
        except ImportError as e:
            logger.error(f"❌ خطا در بارگذاری هندلرها: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ خطا در ثبت هندلرها: {e}")
            return False
        
        # ارسال پیام راه‌اندازی
        await startup_message(application)
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
        print("\n📁 لطفا فایل config.py را ایجاد کنید")
        return False
    except Exception as e:
        logger.error(f"❌ خطا در تنظیم اولیه: {e}")
        return False

async def graceful_shutdown(application):
    """خاموش کردن ملایم با انتظار برای تکمیل کارها"""
    logger.info("⏳ در حال تکمیل کارهای جاری...")
    
    # منتظر ماندن برای تکمیل کارهای در حال اجرا
    import time
    start_time = time.time()
    timeout = 30  # 30 ثانیه
    
    while application.update_queue.qsize() > 0:
        if time.time() - start_time > timeout:
            logger.warning("⏰ زمان انتظار برای تکمیل کارها به پایان رسید")
            break
        await asyncio.sleep(1)
    
    await shutdown(application)

async def health_check(application):
    """بررسی سلامت ربات در حین اجرا"""
    try:
        # بررسی اتصال به API تلگرام
        await application.bot.get_me()
        
        # بررسی حافظه
        import psutil
        memory = psutil.virtual_memory()
        
        health_status = {
            "status": "healthy",
            "uptime": str(datetime.now() - bot_start_time),
            "memory_percent": memory.percent,
            "queue_size": application.update_queue.qsize(),
            "last_update": datetime.now().isoformat()
        }
        
        application.bot_data['health'] = health_status
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}

async def periodic_tasks(application):
    """وظایف دوره‌ای در پس‌زمینه"""
    while True:
        try:
            # هر 10 دقیقه اجرا شود
            await asyncio.sleep(600)
            
            # لاگ آمار
            logger.info(f"📊 آمار صف: {application.update_queue.qsize()}")
            
            # Health check خودکار
            await health_check(application)
            
            # Cleanup temporary data
            await cleanup_temp_data(application)
            
        except Exception as e:
            logger.error(f"خطا در وظایف دوره‌ای: {e}")

def check_environment():
    """بررسی محیط اجرا"""
    env_vars = ['TOKEN', 'ADMIN_ID']  # متغیرهای محیطی ضروری
    
    missing = []
    for var in env_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        logger.warning(f"⚠️ متغیرهای محیطی گمشده: {missing}")
        print("💡 نکته: می‌توانید از فایل .env استفاده کنید")
        return False
    return True

# برای تست ربات در حالت توسعه
def setup_test_mode(application):
    """تنظیمات حالت تست"""
    if os.getenv('BOT_ENV') == 'test':
        logger.info("🧪 حالت تست فعال شد")
        application.bot_data['test_mode'] = True
        
        # غیرفعال کردن برخی قابلیت‌ها در تست
        application.bot_data['send_notifications'] = False
        
        # تغییرات برای تست
        logger.info("🔧 تغییرات حالت تست اعمال شد")

async def main():
    """تابع اصلی اجرای ربات"""
    global app, bot_start_time
    
    bot_start_time = datetime.now()
    
    try:
        logger.info("="*60)
        logger.info("🚀 شروع راه‌اندازی ربات تلگرام")
        logger.info(f"📅 زمان شروع: {bot_start_time}")
        logger.info(f"📁 پوشه پروژه: {PROJECT_ROOT}")
        logger.info(f"📝 فایل لاگ: {log_file}")
        logger.info("="*60)
        
        # ۱. ایجاد اپلیکیشن
        try:
            from telegram.ext import ApplicationBuilder
            
            app = ApplicationBuilder() \
                .token(TOKEN) \
                .pool_timeout(60) \
                .connect_timeout(60) \
                .read_timeout(60) \
                .write_timeout(60) \
                .build()
                
            logger.info("✅ اپلیکیشن تلگرام ایجاد شد")
            
        except NameError:
            logger.error("❌ متغیر TOKEN تعریف نشده است")
            return
        except Exception as e:
            logger.error(f"❌ خطا در ایجاد اپلیکیشن: {e}")
            return
        
        # ۲. تنظیمات اولیه
        if not await setup_bot(app):
            logger.error("❌ خطا در تنظیمات اولیه ربات")
            return
        
        # ۳. نمایش اطلاعات نهایی
        bot_info = app.bot_data.get('bot_info', {})
        runtime_info = app.bot_data.get('config', {})
        
        print("\n" + "="*60)
        print("🤖 **ربات آماده فعالیت است!**")
        print("="*60)
        print(f"📛 نام ربات: {bot_info.get('first_name', 'نامشخص')}")
        print(f"🔗 یوزرنیم: @{bot_info.get('username', 'نامشخص')}")
        print(f"🆔 آیدی: {bot_info.get('id', 'نامشخص')}")
        print(f"👤 ادمین: {runtime_info.get('admin_id', 'تنظیم نشده')}")
        print(f"📊 کانال لاگ: {runtime_info.get('log_channel', 'تنظیم نشده')}")
        print(f"⏰ زمان شروع: {bot_start_time.strftime('%H:%M:%S')}")
        print("="*60)
        print("✅ ربات با موفقیت راه‌اندازی شد!")
        print("📡 در حال گوش دادن به پیام‌ها...")
        print("🛑 برای توقف: Ctrl+C")
        print("="*60 + "\n")
        
        # ۴. اجرای ربات
        try:
            await app.run_polling(
                drop_pending_updates=True,
                allowed_updates=[
                    "message", 
                    "callback_query", 
                    "inline_query",
                    "chat_member",
                    "my_chat_member"
                ],
                close_loop=False
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 توقف ربات توسط کاربر (Ctrl+C)")
        except Exception as e:
            logger.error(f"⚠️ خطا در حین اجرای ربات: {e}", exc_info=True)
            raise
            
    except Exception as e:
        logger.critical(f"💥 خطای بحرانی در اجرای ربات: {e}", exc_info=True)
        print(f"\n❌ خطای بحرانی: {e}")
        
    finally:
        # پاکسازی منابع
        if app:
            await shutdown(app)
        
        end_time = datetime.now()
        runtime = end_time - bot_start_time
        
        logger.info(f"⏱️ مدت زمان اجرا: {runtime}")
        logger.info("👋 خداحافظ!")
        print(f"\n⏱️ مدت زمان اجرا: {runtime}")
        print("👋 خداحافظ!")

if __name__ == "__main__":
    print("🔍 بررسی وابستگی‌ها و تنظیمات...")
    print("="*50)
    
    if check_dependencies():
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n\n🛑 ربات توسط کاربر متوقف شد")
        except Exception as e:
            print(f"\n❌ خطای غیرمنتظره: {e}")
            logger.critical(f"خطای غیرمنتظره: {e}", exc_info=True)
    else:
        print("\n❌ لطفا وابستگی‌ها را نصب کنید و دوباره تلاش کنید")
        sys.exit(1)
