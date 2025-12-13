#main.py
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# ایمپورت ماژول‌های داخلی
from config import TOKEN, BOT_USERNAME
from handlers import (
    start_handler,
    help_handler,
    echo_handler,
    error_handler
)

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """تابع اصلی اجرای ربات"""
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(TOKEN).build()
    
    # اضافه کردن هندلرهای دستورات
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # هندلر برای پیام‌های متنی
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))
    
    # هندلر برای خطاها
    application.add_error_handler(error_handler)
    
    # شروع ربات
    print(f"🤖 ربات @{BOT_USERNAME} در حال اجراست...")
    print("برای خروج Ctrl+C را بفشارید")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
