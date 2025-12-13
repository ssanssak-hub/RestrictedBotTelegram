# -*- coding: utf-8 -*-
# main.py - فایل اصلی راه‌اندازی ربات تلگرام

import asyncio
import sys
import logging
from pathlib import Path

# تنظیمات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# رفع مشکل asyncio در ویندوز
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# اضافه کردن مسیر پروژه
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

async def main():
    """تابع اصلی اجرای ربات"""
    try:
        logger.info("🤖 ربات تلگرام در حال راه‌اندازی...")
        
        # ۱. بارگذاری تنظیمات
        try:
            from config import TOKEN, BOT_CONFIG
            logger.info("✅ تنظیمات بارگذاری شد")
            
            # بررسی اعتبار توکن
            if not TOKEN or TOKEN == "YOUR_TOKEN_HERE":
                logger.error("❌ توکن معتبر در config.py تنظیم نشده است")
                print("\n⚠️  لطفا توکن ربات خود را در فایل config.py قرار دهید")
                print("   TOKEN = 'توکن_ربات_شما'")
                return
                
        except ImportError as e:
            logger.error(f"❌ فایل config.py یافت نشد: {e}")
            print("\n📁 لطفا فایل config.py را ایجاد کنید با محتوای زیر:")
            print("""
TOKEN = 'توکن_ربات_شما'
BOT_CONFIG = {
    'admin_id': 123456789,  # آیدی عددی ادمین
    'log_channel': '@channel_username',  # کانال لاگ (اختیاری)
}
            """)
            return
        except Exception as e:
            logger.error(f"❌ خطا در بارگذاری تنظیمات: {e}")
            return
        
        # ۲. ایجاد اپلیکیشن تلگرام
        try:
            from telegram.ext import ApplicationBuilder
            from telegram import __version__ as telegram_version
            
            logger.info(f"📦 کتابخانه تلگرام نسخه {telegram_version}")
            
            app = ApplicationBuilder() \
                .token(TOKEN) \
                .pool_timeout(30) \
                .connect_timeout(30) \
                .read_timeout(30) \
                .write_timeout(30) \
                .build()
                
            logger.info("✅ اپلیکیشن تلگرام ایجاد شد")
            
        except Exception as e:
            logger.error(f"❌ خطا در ایجاد اپلیکیشن: {e}")
            return
        
        # ۳. ثبت دستورات اصلی
        try:
            from handlers import setup_handlers
            await setup_handlers(app)
            logger.info("✅ هندلرها ثبت شدند")
            
            # نمایش دستورات ثبت شده
            bot = await app.bot.get_me()
            logger.info(f"🔗 ربات @{bot.username} آماده فعالیت است!")
            
            # نمایش اطلاعات در کنسول
            print("\n" + "="*50)
            print(f"🤖 ربات: @{bot.username}")
            print(f"🆔 آیدی ربات: {bot.id}")
            print(f"📛 نام ربات: {bot.first_name}")
            print("="*50)
            print("✅ ربات با موفقیت راه‌اندازی شد!")
            print("📝 برای متوقف کردن ربات از Ctrl+C استفاده کنید")
            print("="*50 + "\n")
            
        except ImportError:
            logger.error("❌ پوشه handlers یافت نشد")
            print("\n📁 پوشه handlers را ایجاد کنید و فایل __init__.py در آن قرار دهید")
            return
        except Exception as e:
            logger.error(f"❌ خطا در ثبت هندلرها: {e}")
            return
        
        # ۴. اجرای ربات
        try:
            await app.run_polling(
                drop_pending_updates=True,
                allowed_updates=["message", "callback_query", "inline_query"]
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 توقف ربات توسط کاربر")
            print("\n🛑 ربات متوقف شد")
        except Exception as e:
            logger.error(f"⚠️ خطا در حین اجرای ربات: {e}")
            raise
            
    except Exception as e:
        logger.critical(f"💥 خطای بحرانی در اجرای ربات: {e}")
        print(f"\n❌ خطای بحرانی: {e}")
        return

def check_dependencies():
    """بررسی وابستگی‌های پروژه"""
    required_packages = ['python-telegram-bot', 'pathlib']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)
    
    if missing_packages:
        print("\n❌ برخی وابستگی‌ها نصب نیستند:")
        for pkg in missing_packages:
            print(f"   - {pkg}")
        print("\n📦 برای نصب از دستور زیر استفاده کنید:")
        print(f"   pip install {' '.join(missing_packages)}")
        return False
    
    return True

if __name__ == "__main__":
    print("🔍 بررسی وابستگی‌ها...")
    
    if check_dependencies():
        # اجرای ربات
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n👋 خداحافظ!")
        except Exception as e:
            logger.error(f"💥 خطای غیرمنتظره: {e}")
            print(f"\n⚠️ خطای غیرمنتظره رخ داد. لطفا لاگ‌ها را بررسی کنید.")
    else:
        sys.exit(1)
