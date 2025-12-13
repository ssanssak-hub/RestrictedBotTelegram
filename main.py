# main.py (نسخه اصلاح شده)
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram import Update

# ایمپورت ماژول‌های داخلی
from config import TOKEN, BOT_USERNAME, API_ID, API_HASH
from handlers import (
    start_handler,
    help_handler,
    echo_handler,
    error_handler
)

# ایمپورت سیستم مدیریت اکانت
from advanced_account_manager import AdvancedAccountManager, AdvancedCLI
import asyncio

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ایجاد instance از مدیر اکانت
account_manager = None

async def init_account_manager():
    """مقداردهی اولیه سیستم مدیریت اکانت"""
    global account_manager
    try:
        account_manager = AdvancedAccountManager(
            base_dir="accounts",
            api_id=API_ID,
            api_hash=API_HASH
        )
        logger.info("✅ سیستم مدیریت اکانت راه‌اندازی شد")
    except Exception as e:
        logger.error(f"❌ خطا در راه‌اندازی مدیریت اکانت: {e}")

async def login_handler(update: Update, context):
    """دستور /login برای ورود اکانت کاربر"""
    user_id = update.effective_user.id
    
    # ارسال پیام راهنما
    await update.message.reply_text(
        "🔐 **سیستم ورود پیشرفته**\n\n"
        "لطفاً شماره تلفن خود را با +98 ارسال کنید:\n"
        "مثال: +989123456789\n\n"
        "⚠️ توجه: این شماره فقط برای احراز هویت استفاده می‌شود"
    )
    
    # ذخیره وضعیت برای دریافت شماره
    context.user_data['awaiting_phone'] = True

async def my_accounts_handler(update: Update, context):
    """دستور /accounts برای نمایش اکانت‌های کاربر"""
    user_id = update.effective_user.id
    
    if not account_manager:
        await update.message.reply_text("⚠️ سیستم مدیریت اکانت در حال راه‌اندازی است...")
        return
    
    # نمایش اکانت‌های کاربر (شبیه‌سازی)
    accounts_info = "📋 **اکانت‌های شما:**\n\n"
    
    # در اینجا باید از دیتابیس account_manager اکانت‌های کاربر رو بخونید
    accounts_info += "1️⃣ **اکانت اصلی** - فعال ✅\n"
    accounts_info += "2️⃣ **اکانت دوم** - غیرفعال ⚠️\n\n"
    accounts_info += "برای مدیریت هر اکانت از دستورات زیر استفاده کنید:\n"
    accounts_info += "/login - افزودن اکانت جدید\n"
    accounts_info += "/logout - خروج از اکانت\n"
    accounts_info += "/backup - پشتیبان‌گیری\n"
    
    await update.message.reply_text(accounts_info)

async def backup_handler(update: Update, context):
    """دستور /backup برای پشتیبان‌گیری"""
    user_id = update.effective_user.id
    
    if not account_manager:
        await update.message.reply_text("⚠️ سیستم مدیریت اکانت در حال راه‌اندازی است...")
        return
    
    # ایجاد دکمه برای تایید
    keyboard = [
        [InlineKeyboardButton("✅ بله، پشتیبان بگیر", callback_data='backup_yes')],
        [InlineKeyboardButton("❌ خیر", callback_data='backup_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💾 **پشتیبان‌گیری از اکانت**\n\n"
        "آیا مایلید از اکانت فعلی پشتیبان بگیرید؟\n"
        "⚠️ این فایل به صورت رمزنگاری شده ذخیره می‌شود.",
        reply_markup=reply_markup
    )

async def handle_phone_number(update: Update, context):
    """پردازش شماره تلفن دریافتی"""
    user_id = update.effective_user.id
    phone = update.message.text
    
    if 'awaiting_phone' in context.user_data:
        # اعتبارسنجی شماره
        if not phone.startswith('+98') or len(phone) != 13:
            await update.message.reply_text("❌ شماره تلفن نامعتبر!\nلطفاً شماره را با فرمت +989123456789 وارد کنید.")
            return
        
        # ارسال پیام تایید
        await update.message.reply_text(
            f"📱 **تایید شماره**\n\n"
            f"شماره شما: `{phone}`\n\n"
            f"آیا این شماره صحیح است؟\n"
            f"برای تایید /confirm را ارسال کنید.\n"
            f"برای اصلاح دوباره شماره را وارد کنید."
        )
        
        context.user_data['phone'] = phone
        context.user_data['awaiting_confirmation'] = True
        del context.user_data['awaiting_phone']

async def confirm_login(update: Update, context):
    """تایید نهایی ورود"""
    if 'phone' in context.user_data:
        phone = context.user_data['phone']
        
        # شروع فرآیند ورود با مدیر اکانت
        await update.message.reply_text(
            f"⏳ **در حال ورود با شماره {phone}**\n\n"
            f"لطفاً منتظر بمانید..."
        )
        
        try:
            # فراخوانی سیستم مدیریت اکانت
            success, client, account_id = await account_manager.login_with_phone_advanced(phone=phone)
            
            if success:
                # ذخیره اطلاعات در دیتابیس ربات
                # (در اینجا باید اطلاعات رو به دیتابیس ربات اصلی اضافه کنید)
                
                await update.message.reply_text(
                    f"✅ **ورود موفق!**\n\n"
                    f"اکانت شما با موفقیت اضافه شد.\n"
                    f"🆔 کد اکانت: `{account_id}`\n\n"
                    f"از دستور /accounts برای مدیریت استفاده کنید."
                )
            else:
                await update.message.reply_text(
                    f"❌ **ورود ناموفق**\n\n"
                    f"خطا: {account_id}\n\n"
                    f"لطفاً دوباره تلاش کنید."
                )
            
        except Exception as e:
            await update.message.reply_text(f"❌ خطای سیستمی: {str(e)}")
        
        # پاک کردن داده‌های موقت
        context.user_data.clear()

async def message_handler(update: Update, context):
    """هندلر پیام‌های متنی"""
    text = update.message.text
    
    # اگر کاربر در مرحله دریافت شماره است
    if 'awaiting_phone' in context.user_data:
        await handle_phone_number(update, context)
        return
    
    # اگر کاربر در مرحله تایید است
    if 'awaiting_confirmation' in context.user_data:
        if text == '/confirm':
            await confirm_login(update, context)
        else:
            # شماره جدید وارد شده
            await handle_phone_number(update, context)
        return
    
    # پردازش عادی پیام
    await echo_handler(update, context)

def main():
    """تابع اصلی اجرای ربات"""
    
    # مقداردهی اولیه مدیر اکانت
    asyncio.run(init_account_manager())
    
    # ایجاد اپلیکیشن
    application = Application.builder().token(TOKEN).build()
    
    # اضافه کردن هندلرهای دستورات
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("login", login_handler))
    application.add_handler(CommandHandler("accounts", my_accounts_handler))
    application.add_handler(CommandHandler("backup", backup_handler))
    application.add_handler(CommandHandler("confirm", confirm_login))
    
    # هندلر برای پیام‌های متنی
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # هندلر برای خطاها
    application.add_error_handler(error_handler)
    
    # شروع ربات
    print(f"🤖 ربات @{BOT_USERNAME} در حال اجراست...")
    print("🔐 سیستم مدیریت اکانت فعال")
    print("برای خروج Ctrl+C را بفشارید")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
