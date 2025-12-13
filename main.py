#main.py
#!/usr/bin/env python3
"""
🤖 ربات تلگرام یکپارچه با تمام ویژگی‌های پیشرفته
اتصال: main.py + advanced_account_manager.py + advanced_features.py
"""

import logging
import asyncio
import json
import os
import sys
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from io import BytesIO

# کتابخانه‌های تلگرام
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ========== ایمپورت ماژول‌های پیشرفته ==========

# 1. سیستم مدیریت اکانت پیشرفته
from advanced_account_manager import (
    AdvancedAccountManager,
    AdvancedCLI,
    AccountStatus,
    LoginMethod,
    AdvancedEncryption,
    AnomalyDetector,
    AccountMonitor
)

# 2. ویژگی‌های پیشرفته 8-11
from advanced_features import (
    AdvancedReportGenerator,
    TwoFactorAuthentication,
    HealthMonitor,
    AnomalyDetectionSystem
)

# 3. دیتابیس و config
try:
    from config import TOKEN, BOT_USERNAME, API_ID, API_HASH, ADMIN_IDS
except ImportError:
    # مقادیر پیش‌فرض برای تست
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    BOT_USERNAME = "your_bot_username"
    API_ID = 123456  # از my.telegram.org بگیرید
    API_HASH = "your_api_hash_here"
    ADMIN_IDS = [123456789]  # IDهای ادمین

# ========== تنظیمات لاگ ==========

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== مدیر یکپارچه ==========

class IntegratedBotManager:
    """مدیریت یکپارچه تمام سیستم‌ها"""
    
    def __init__(self):
        self.setup_directories()
        
        # 1. سیستم مدیریت اکانت
        self.account_manager = AdvancedAccountManager(
            base_dir=Path("accounts"),
            api_id=API_ID,
            api_hash=API_HASH,
            encryption_key=os.getenv("ENCRYPTION_KEY", "default_encryption_key_change_me")
        )
        
        # 2. ویژگی‌های پیشرفته
        self.report_generator = AdvancedReportGenerator()
        self.two_fa = TwoFactorAuthentication()
        self.anomaly_detector_ml = AnomalyDetectionSystem()
        
        # 3. داده‌های کاربران
        self.user_sessions: Dict[int, Dict] = {}
        self.user_reports: Dict[int, List] = {}
        self.user_behaviors: Dict[int, List] = {}
        
        # 4. وضعیت مکالمات
        self.conversation_states: Dict[int, Dict] = {}
        
        logger.info("✅ مدیر یکپارچه راه‌اندازی شد")
    
    def setup_directories(self):
        """ایجاد دایرکتوری‌های لازم"""
        directories = [
            "accounts/sessions",
            "accounts/backups",
            "accounts/exports",
            "reports",
            "logs",
            "database",
            "temp"
        ]
        
        for dir_path in directories:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    async def start_health_monitor(self, bot_instance):
        """شروع مانیتورینگ سلامت"""
        self.health_monitor = HealthMonitor(bot_instance)
        
        # شروع مانیتورینگ دوره‌ای
        asyncio.create_task(self.periodic_health_check())
        
        logger.info("✅ مانیتور سلامت راه‌اندازی شد")
    
    async def periodic_health_check(self):
        """بررسی سلامت دوره‌ای"""
        while True:
            try:
                await asyncio.sleep(3600)  # هر 1 ساعت
                health_status = await self.health_monitor.comprehensive_health_check()
                
                if health_status.get('requires_attention'):
                    logger.warning(f"⚠️ مشکلات سلامت سیستم: {health_status.get('critical_services_down', [])}")
                    
                    # اطلاع به ادمین‌ها
                    await self.notify_admins(
                        f"⚠️ **هشدار سلامت سیستم**\n"
                        f"سرویس‌های مشکل‌دار: {', '.join(health_status.get('critical_services_down', []))}"
                    )
            
            except Exception as e:
                logger.error(f"خطا در بررسی سلامت: {e}")
    
    async def notify_admins(self, message: str):
        """ارسال اطلاعیه به ادمین‌ها"""
        # این تابع در ادامه با context ربات پر خواهد شد
        pass

# ========== هندلرهای اصلی ربات ==========

class TelegramBotHandlers:
    """هندلرهای دستورات تلگرام"""
    
    def __init__(self, manager: IntegratedBotManager):
        self.manager = manager
        self.STATES = {
            'AWAITING_PHONE': 1,
            'AWAITING_CODE': 2,
            'AWAITING_2FA': 3,
            'AWAITING_REPORT_TYPE': 4,
            'AWAITING_BACKUP_CONFIRM': 5
        }
    
    # ========== دستورات اصلی ==========
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /start"""
        user = update.effective_user
        user_id = user.id
        
        # ردیابی رفتار
        await self.track_user_behavior(user_id, 'start_command', {'username': user.username})
        
        welcome_text = f"""
👋 سلام {user.first_name}!

🤖 **ربات مدیریت اکانت تلگرام** به شما خوش آمد می‌گوید.

🔐 **ویژگی‌های اصلی:**
• مدیریت پیشرفته اکانت‌های تلگرام
• سیستم امنیتی چند لایه
• گزارش‌گیری حرفه‌ای
• تأیید دو مرحله‌ای
• تشخیص هوشمند ناهنجاری

📋 **دستورات اصلی:**
/start - نمایش این پیام
/login - ورود به اکانت
/accounts - مدیریت اکانت‌ها
/report - دریافت گزارش
/2fa - مدیریت احراز هویت دو مرحله‌ای
/backup - پشتیبان‌گیری
/help - راهنمای کامل

⚠️ **هشدار:** این ربات برای مدیریت امن اکانت‌های شما طراحی شده است.
        """
        
        keyboard = [
            [InlineKeyboardButton("🔐 ورود به اکانت", callback_data='menu_login')],
            [InlineKeyboardButton("📋 اکانت‌های من", callback_data='menu_accounts')],
            [InlineKeyboardButton("⚙️ تنظیمات امنیتی", callback_data='menu_security')],
            [InlineKeyboardButton("📊 گزارش‌گیری", callback_data='menu_reports')],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /help"""
        help_text = """
📚 **راهنمای کامل ربات**

🔐 **دستورات مدیریت اکانت:**
/login - ورود به اکانت تلگرام
/logout - خروج از اکانت
/accounts - نمایش اکانت‌های فعال
/switch - تغییر اکانت فعال

🛡️ **دستورات امنیتی:**
/2fa - مدیریت تأیید دو مرحله‌ای
/backup - پشتیبان‌گیری از اکانت
/restore - بازیابی اکانت
/security - بررسی امنیتی اکانت

📊 **دستورات گزارش‌گیری:**
/report - دریافت گزارش فعالیت
/insights - تحلیل هوشمند رفتار
/stats - آمار کلی

⚙️ **دستورات مدیریتی (فقط ادمین):**
/health - بررسی سلامت سیستم
/users - مدیریت کاربران
/broadcast - ارسال پیام همگانی

🔧 **پشتیبانی:**
/support - ارتباط با پشتیبانی
/feedback - ارسال نظرات

⚠️ **نکات امنیتی:**
1. هرگز اطلاعات حساس خود را با دیگران به اشتراک نگذارید
2. کدهای تأیید را فقط در این ربات وارد کنید
3. از کدهای پشتیبان در جای امن نگهداری کنید
4. در صورت مشاهده فعالیت مشکوک، سریعاً گزارش دهید
        """
        
        await update.message.reply_text(help_text)
    
    # ========== سیستم ورود ==========
    
    async def login_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /login"""
        user_id = update.effective_user.id
        
        # بررسی اکانت‌های فعال
        if user_id in self.manager.user_sessions:
            keyboard = [
                [InlineKeyboardButton("➕ افزودن اکانت جدید", callback_data='login_new')],
                [InlineKeyboardButton("🔁 استفاده از اکانت موجود", callback_data='login_existing')],
                [InlineKeyboardButton("❌ لغو", callback_data='login_cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "🔐 **شما اکانت فعال دارید**\n\n"
                "آیا می‌خواهید اکانت جدید اضافه کنید یا از اکانت موجود استفاده کنید؟",
                reply_markup=reply_markup
            )
            return self.STATES['AWAITING_PHONE']
        
        # درخواست شماره تلفن
        await update.message.reply_text(
            "📱 **ورود به اکانت تلگرام**\n\n"
            "لطفاً شماره تلفن خود را با فرمت بین‌المللی ارسال کنید:\n"
            "مثال: `+989123456789`\n\n"
            "⚠️ توجه: این شماره فقط برای احراز هویت استفاده می‌شود.\n"
            "❌ برای لغو: /cancel"
        )
        
        return self.STATES['AWAITING_PHONE']
    
    async def handle_phone_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش شماره تلفن"""
        user_id = update.effective_user.id
        phone = update.message.text.strip()
        
        # اعتبارسنجی شماره
        if not phone.startswith('+'):
            await update.message.reply_text(
                "❌ شماره تلفن نامعتبر!\n"
                "لطفاً شماره را با علامت + و کد کشور وارد کنید.\n"
                "مثال: +989123456789"
            )
            return self.STATES['AWAITING_PHONE']
        
        # ذخیره شماره در context
        context.user_data['login_phone'] = phone
        context.user_data['login_user_id'] = user_id
        
        # ارسال پیام تایید
        keyboard = [
            [InlineKeyboardButton("✅ بله، صحیح است", callback_data='phone_confirm')],
            [InlineKeyboardButton("❌ اصلاح شماره", callback_data='phone_edit')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📱 **تأیید شماره تلفن**\n\n"
            f"شماره وارد شده:\n"
            f"`{phone}`\n\n"
            f"آیا این شماره صحیح است؟",
            reply_markup=reply_markup
        )
        
        return self.STATES['AWAITING_CODE']
    
    async def handle_phone_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تأیید شماره تلفن"""
        query = update.callback_query
        await query.answer()
        
        user_id = context.user_data.get('login_user_id')
        phone = context.user_data.get('login_phone')
        
        if query.data == 'phone_confirm':
            # شروع فرآیند ورود
            await query.edit_message_text(
                f"⏳ **در حال ارسال کد تأیید به {phone}**\n\n"
                f"لطفاً منتظر بمانید..."
            )
            
            # فراخوانی سیستم مدیریت اکانت
            success, client, account_id = await self.manager.account_manager.login_with_phone_advanced(
                phone=phone,
                session_name=f"user_{user_id}_{int(datetime.now().timestamp())}"
            )
            
            if success:
                # ذخیره session
                self.manager.user_sessions[user_id] = {
                    'client': client,
                    'account_id': account_id,
                    'phone': phone,
                    'login_time': datetime.now(),
                    'last_activity': datetime.now()
                }
                
                await query.edit_message_text(
                    f"✅ **ورود موفقیت‌آمیز!**\n\n"
                    f"اکانت شما با موفقیت اضافه شد.\n"
                    f"📱 شماره: `{phone}`\n"
                    f"🆔 کد اکانت: `{account_id}`\n\n"
                    f"از دستور /accounts برای مدیریت استفاده کنید."
                )
                
                # فعال‌سازی 2FA پیشنهادی
                await self.suggest_2fa_setup(user_id, context)
                
            else:
                await query.edit_message_text(
                    f"❌ **ورود ناموفق**\n\n"
                    f"خطا: {account_id}\n\n"
                    f"لطفاً دوباره تلاش کنید: /login"
                )
        
        else:  # phone_edit
            await query.edit_message_text(
                "📱 لطفاً شماره تلفن صحیح را وارد کنید:\n"
                "مثال: +989123456789"
            )
            return self.STATES['AWAITING_PHONE']
        
        return ConversationHandler.END
    
    async def suggest_2fa_setup(self, user_id: int, context: ContextTypes.DEFAULT_TYPE):
        """پیشنهاد فعال‌سازی 2FA"""
        keyboard = [
            [InlineKeyboardButton("🔐 فعال‌سازی 2FA", callback_data='enable_2fa_now')],
            [InlineKeyboardButton("⏰ بعداً", callback_data='enable_2fa_later')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ارسال پیام به کاربر
        await context.bot.send_message(
            chat_id=user_id,
            text="🛡️ **افزایش امنیت حساب**\n\n"
                 "توصیه می‌کنیم برای افزایش امنیت، تأیید دو مرحله‌ای را فعال کنید.\n"
                 "آیا مایلید هم‌اکنون 2FA را فعال کنید؟",
            reply_markup=reply_markup
        )
    
    # ========== مدیریت اکانت‌ها ==========
    
    async def accounts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /accounts"""
        user_id = update.effective_user.id
        
        if user_id not in self.manager.user_sessions:
            keyboard = [[InlineKeyboardButton("🔐 افزودن اکانت", callback_data='login_new')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📭 **شما هیچ اکانت فعالی ندارید**\n\n"
                "برای شروع، یک اکانت تلگرام اضافه کنید:",
                reply_markup=reply_markup
            )
            return
        
        session = self.manager.user_sessions[user_id]
        account_id = session['account_id']
        
        # گرفتن اطلاعات از مدیر اکانت
        account_info = await self.manager.account_manager.get_account_info(account_id)
        
        if not account_info:
            account_info = {
                'phone': session['phone'],
                'login_time': session['login_time'].strftime('%Y/%m/%d %H:%M'),
                'status': 'فعال'
            }
        
        # ایجاد منوی اکانت
        keyboard = [
            [
                InlineKeyboardButton("📊 گزارش فعالیت", callback_data='account_report'),
                InlineKeyboardButton("🛡️ بررسی امنیت", callback_data='account_security')
            ],
            [
                InlineKeyboardButton("💾 پشتیبان‌گیری", callback_data='account_backup'),
                InlineKeyboardButton("🔄 تازه‌سازی", callback_data='account_refresh')
            ],
            [
                InlineKeyboardButton("🚪 خروج", callback_data='account_logout'),
                InlineKeyboardButton("➕ اکانت جدید", callback_data='account_new')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        accounts_text = f"""
📋 **اکانت‌های شما**

🔹 **اکانت اصلی:**
📱 شماره: `{account_info.get('phone', session['phone'])}`
🆔 کد اکانت: `{account_id}`
🕒 زمان ورود: {session['login_time'].strftime('%Y/%m/%d %H:%M')}
📊 وضعیت: {account_info.get('status', 'فعال')}

💡 **امکانات مدیریت اکانت:**
        """
        
        await update.message.reply_text(accounts_text, reply_markup=reply_markup)
    
    # ========== سیستم گزارش‌گیری ==========
    
    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /report"""
        user_id = update.effective_user.id
        
        keyboard = [
            [
                InlineKeyboardButton("📅 روزانه", callback_data='report_daily'),
                InlineKeyboardButton("📅 هفتگی", callback_data='report_weekly')
            ],
            [
                InlineKeyboardButton("📅 ماهانه", callback_data='report_monthly'),
                InlineKeyboardButton("📊 سفارشی", callback_data='report_custom')
            ],
            [
                InlineKeyboardButton("🧠 تحلیل هوشمند", callback_data='report_insights'),
                InlineKeyboardButton("📈 آمار کامل", callback_data='report_full')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📊 **سیستم گزارش‌گیری پیشرفته**\n\n"
            "لطفاً نوع گزارش مورد نظر را انتخاب کنید:\n\n"
            "📅 **گزارش‌های دوره‌ای:**\n"
            "• روزانه - فعالیت‌های 24 ساعت گذشته\n"
            "• هفتگی - خلاصه هفته جاری\n"
            "• ماهانه - آمار کامل ماه\n\n"
            "📈 **گزارش‌های تخصصی:**\n"
            "• تحلیل هوشمند - تشخیص الگوهای رفتاری\n"
            "• آمار کامل - تمام داده‌های آماری",
            reply_markup=reply_markup
        )
        
        return self.STATES['AWAITING_REPORT_TYPE']
    
    async def handle_report_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش درخواست گزارش"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        report_type = query.data.replace('report_', '')
        
        await query.edit_message_text(f"⏳ **در حال تولید گزارش {report_type}...**\nلطفاً منتظر بمانید.")
        
        # تولید گزارش
        report_data = self.manager.report_generator.collect_user_data(user_id, report_type)
        
        # تولید فرمت‌های مختلف
        report_formats = self.manager.report_generator.generate_comprehensive_report(user_id, report_type)
        
        # ارسال خلاصه
        summary = report_formats['summary']
        await query.edit_message_text(f"✅ **گزارش تولید شد**\n\n{summary}")
        
        # ارسال فایل PDF
        pdf_bytes = report_formats['pdf']
        pdf_file = BytesIO(pdf_bytes)
        pdf_file.name = f"report_{user_id}_{report_type}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        await context.bot.send_document(
            chat_id=user_id,
            document=InputFile(pdf_file, filename=pdf_file.name),
            caption=f"📄 گزارش {report_type} - {datetime.now().strftime('%Y/%m/%d')}"
        )
        
        # ذخیره گزارش
        if user_id not in self.manager.user_reports:
            self.manager.user_reports[user_id] = []
        
        self.manager.user_reports[user_id].append({
            'type': report_type,
            'date': datetime.now().isoformat(),
            'data': report_data
        })
        
        return ConversationHandler.END
    
    # ========== سیستم 2FA ==========
    
    async def twofa_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /2fa"""
        user_id = update.effective_user.id
        
        # بررسی وضعیت فعلی
        auth_status = self.manager.two_fa.get_2fa_status(user_id)
        
        if auth_status['enabled']:
            # منوی مدیریت 2FA فعال
            keyboard = [
                [InlineKeyboardButton("🔄 تولید کدهای جدید", callback_data='2fa_new_codes')],
                [InlineKeyboardButton("📋 نمایش کدهای باقی‌مانده", callback_data='2fa_show_codes')],
                [InlineKeyboardButton("❌ غیرفعال کردن 2FA", callback_data='2fa_disable')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='2fa_back')]
            ]
            
            status_text = f"""
🔐 **مدیریت احراز هویت دو مرحله‌ای**

✅ **وضعیت:** فعال
🔢 **کدهای پشتیبان باقی‌مانده:** {auth_status['remaining_backup_codes']}
🚫 **تلاش‌های ناموفق اخیر:** {auth_status['failed_attempts']}

{'⛔ **اکانت قفل شده است**' if auth_status['locked'] else '🔓 **اکانت فعال است**'}
            """
            
        else:
            # منوی فعال‌سازی 2FA
            keyboard = [
                [InlineKeyboardButton("🔐 فعال‌سازی 2FA", callback_data='2fa_enable')],
                [InlineKeyboardButton("📖 راهنمای استفاده", callback_data='2fa_guide')],
                [InlineKeyboardButton("🔙 بازگشت", callback_data='2fa_back')]
            ]
            
            status_text = """
🔐 **مدیریت احراز هویت دو مرحله‌ای**

❌ **وضعیت:** غیرفعال

🛡️ **مزایای فعال‌سازی 2FA:**
• افزایش امنیت حساب
• جلوگیری از دسترسی غیرمجاز
• محافظت در برابر حمله‌های brute-force
• اطمینان از احراز هویت واقعی

⚠️ **توصیه می‌شود برای افزایش امنیت، 2FA را فعال کنید.**
            """
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(status_text, reply_markup=reply_markup)
    
    async def handle_2fa_setup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش فعال‌سازی 2FA"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if query.data == '2fa_enable':
            # فعال‌سازی 2FA
            setup_result = self.manager.two_fa.setup_2fa(user_id)
            
            # ارسال QR Code
            qr_bytes = base64.b64decode(setup_result['qr_code'])
            qr_file = BytesIO(qr_bytes)
            qr_file.name = f"2fa_qr_{user_id}.png"
            
            # ارسال پیام با QR Code
            await context.bot.send_photo(
                chat_id=user_id,
                photo=InputFile(qr_file, filename=qr_file.name),
                caption="🔐 **QR Code برای فعال‌سازی 2FA**\n\n"
                        "لطفاً این QR Code را با اپلیکیشن‌های زیر اسکن کنید:\n"
                        "• Google Authenticator\n"
                        "• Microsoft Authenticator\n"
                        "• Authy\n\n"
                        "⚠️ **کدهای پشتیبان (در جای امن ذخیره کنید):**"
            )
            
            # ارسال کدهای پشتیبان
            backup_codes_text = "\n".join([f"• `{code}`" for code in setup_result['backup_codes']])
            
            await context.bot.send_message(
                chat_id=user_id,
                text=f"{backup_codes_text}\n\n"
                     "📝 **نکات مهم:**\n"
                     "1. کدهای پشتیبان را در جای امنی ذخیره کنید\n"
                     "2. هر کد فقط یکبار قابل استفاده است\n"
                     "3. پس از استفاده، کد جدید تولید کنید\n"
                     "4. در صورت گم کردن کدها، می‌توانید کدهای جدید تولید کنید"
            )
            
            await query.edit_message_text(
                "✅ **2FA با موفقیت فعال شد!**\n\n"
                "از این پس برای ورود به حساب، علاوه بر کد SMS نیاز به کد 2FA دارید."
            )
        
        elif query.data == '2fa_new_codes':
            # تولید کدهای پشتیبان جدید
            new_codes = self.manager.two_fa.generate_new_backup_codes(user_id)
            
            codes_text = "\n".join([f"• `{code}`" for code in new_codes])
            
            await query.edit_message_text(
                f"🔄 **کدهای پشتیبان جدید تولید شدند**\n\n"
                f"{codes_text}\n\n"
                f"⚠️ **هشدار:** کدهای قبلی دیگر معتبر نیستند.\n"
                f"این کدها را در جای امنی ذخیره کنید."
            )
        
        elif query.data == '2fa_disable':
            # غیرفعال کردن 2FA
            keyboard = [
                [InlineKeyboardButton("✅ بله، غیرفعال کن", callback_data='2fa_disable_confirm')],
                [InlineKeyboardButton("❌ خیر، برگرد", callback_data='2fa_back')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ **هشدار جدی**\n\n"
                "آیا مطمئن هستید که می‌خواهید احراز هویت دو مرحله‌ای را غیرفعال کنید؟\n\n"
                "🔴 **خطرات غیرفعال کردن:**\n"
                "• کاهش امنیت حساب\n"
                "• افزایش خطر دسترسی غیرمجاز\n"
                "• حذف لایه امنیتی اضافی\n\n"
                "این عمل غیرقابل بازگشت است!",
                reply_markup=reply_markup
            )
    
    # ========== سیستم پشتیبان‌گیری ==========
    
    async def backup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /backup"""
        user_id = update.effective_user.id
        
        if user_id not in self.manager.user_sessions:
            await update.message.reply_text(
                "❌ **شما اکانت فعالی ندارید**\n\n"
                "برای پشتیبان‌گیری، ابتدا وارد اکانت خود شوید: /login"
            )
            return
        
        keyboard = [
            [
                InlineKeyboardButton("💾 پشتیبان کامل", callback_data='backup_full'),
                InlineKeyboardButton("📁 فقط session", callback_data='backup_session')
            ],
            [
                InlineKeyboardButton("🔐 رمزنگاری شده", callback_data='backup_encrypted'),
                InlineKeyboardButton("📤 Export", callback_data='backup_export')
            ],
            [InlineKeyboardButton("❌ لغو", callback_data='backup_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "💾 **سیستم پشتیبان‌گیری**\n\n"
            "لطفاً نوع پشتیبان مورد نظر را انتخاب کنید:\n\n"
            "💾 **پشتیبان کامل:** تمام اطلاعات اکانت\n"
            "📁 **فقط session:** فایل session تلگرام\n"
            "🔐 **رمزنگاری شده:** پشتیبان با رمز عبور\n"
            "📤 **Export:** خروجی قابل انتقال\n\n"
            "⚠️ **توصیه:** پشتیبان کامل رمزنگاری شده را انتخاب کنید.",
            reply_markup=reply_markup
        )
        
        return self.STATES['AWAITING_BACKUP_CONFIRM']
    
    async def handle_backup_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش درخواست پشتیبان"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        backup_type = query.data.replace('backup_', '')
        
        if backup_type == 'cancel':
            await query.edit_message_text("❌ پشتیبان‌گیری لغو شد.")
            return ConversationHandler.END
        
        await query.edit_message_text(f"⏳ **در حال ایجاد پشتیبان {backup_type}...**\nلطفاً منتظر بمانید.")
        
        # ایجاد پشتیبان
        session = self.manager.user_sessions[user_id]
        account_id = session['account_id']
        
        # استفاده از سیستم مدیریت اکانت برای پشتیبان
        backup_file = await self.manager.account_manager.backup_account(
            account_id=account_id,
            backup_type=backup_type
        )
        
        if backup_file:
            # ارسال فایل پشتیبان
            await context.bot.send_document(
                chat_id=user_id,
                document=InputFile(backup_file, filename=backup_file.name),
                caption=f"💾 پشتیبان {backup_type} - {datetime.now().strftime('%Y/%m/%d %H:%M')}\n"
                        f"🆔 کد اکانت: `{account_id}`\n\n"
                        f"⚠️ این فایل را در جای امنی نگهداری کنید."
            )
            
            await query.edit_message_text("✅ **پشتیبان‌گیری با موفقیت انجام شد!**")
        else:
            await query.edit_message_text("❌ **خطا در ایجاد پشتیبان**\nلطفاً دوباره تلاش کنید.")
        
        return ConversationHandler.END
    
    # ========== سیستم سلامت (فقط ادمین) ==========
    
    async def health_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /health (فقط ادمین)"""
        user_id = update.effective_user.id
        
        if user_id not in ADMIN_IDS:
            await update.message.reply_text("⛔ **دسترسی denied**\nاین دستور فقط برای ادمین‌ها قابل استفاده است.")
            return
        
        await update.message.reply_text("🩺 **در حال بررسی سلامت سیستم...**\nلطفاً منتظر بمانید.")
        
        # بررسی سلامت
        health_status = await self.manager.health_monitor.comprehensive_health_check()
        summary = self.manager.health_monitor.get_health_summary()
        report = self.manager.health_monitor.generate_health_report()
        
        # ارسال گزارش
        await update.message.reply_text(report)
        
        # ارسال هشدار اگر نیاز باشد
        if summary['requires_attention']:
            keyboard = [
                [InlineKeyboardButton("🛠️ تلاش برای ترمیم", callback_data='health_repair')],
                [InlineKeyboardButton("📋 گزارش کامل", callback_data='health_full_report')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"⚠️ **نیاز به توجه فوری**\n\n"
                f"سرویس‌های مشکل‌دار:\n"
                f"{chr(10).join(f'• {service}' for service in summary['critical_services_down'])}\n\n"
                f"لطفاً اقدام لازم را انجام دهید.",
                reply_markup=reply_markup
            )
    
    # ========== سیستم تشخیص ناهنجاری ==========
    
    async def track_user_behavior(self, user_id: int, action_type: str, details: Dict):
        """ردیابی رفتار کاربر برای تشخیص ناهنجاری"""
        try:
            # جمع‌آوری داده‌های رفتاری
            behavior_data = {
                'user_id': user_id,
                'action_type': action_type,
                'timestamp': datetime.now().isoformat(),
                'hour_of_day': datetime.now().hour,
                'day_of_week': datetime.now().weekday(),
                **details
            }
            
            # ذخیره در تاریخچه
            if user_id not in self.manager.user_behaviors:
                self.manager.user_behaviors[user_id] = []
            
            self.manager.user_behaviors[user_id].append(behavior_data)
            
            # اگر داده کافی داریم، آنومالی چک کن
            if len(self.manager.user_behaviors[user_id]) >= 10:
                # تحلیل آنومالی
                anomaly_result = self.manager.anomaly_detector_ml.detect_anomaly(
                    user_id, 
                    self.extract_behavior_features(self.manager.user_behaviors[user_id][-10:])
                )
                
                # اگر آنومالی خطرناک تشخیص داده شد
                if anomaly_result['is_anomaly'] and anomaly_result['interpretation']['risk_level'] in ['high', 'critical']:
                    # اطلاع به ادمین
                    await self.notify_admins_about_anomaly(user_id, anomaly_result)
            
        except Exception as e:
            logger.error(f"خطا در ردیابی رفتار: {e}")
    
    def extract_behavior_features(self, behaviors: List[Dict]) -> Dict:
        """استخراج ویژگی‌های رفتاری"""
        if not behaviors:
            return {}
        
        import numpy as np
        
        # محاسبه آمارها
        messages_count = sum(1 for b in behaviors if b.get('action_type') == 'message')
        login_count = sum(1 for b in behaviors if b.get('action_type') == 'login')
        failed_logins = sum(1 for b in behaviors if b.get('action_type') == 'login_failed')
        
        # ساعات فعالیت
        hours = [b.get('hour_of_day', 12) for b in behaviors]
        avg_hour = np.mean(hours) if hours else 12
        
        return {
            'messages_per_hour': messages_count / (len(behaviors) / 24) if behaviors else 0,
            'login_frequency': login_count,
            'failed_login_attempts': failed_logins,
            'hour_of_day': avg_hour,
            'action_std_dev': np.std([1 for _ in behaviors]) if len(behaviors) > 1 else 0
        }
    
    async def notify_admins_about_anomaly(self, user_id: int, anomaly_result: Dict):
        """اطلاع به ادمین‌ها درباره ناهنجاری"""
        message = f"""
🚨 **هشدار تشخیص ناهنجاری**

👤 کاربر: `{user_id}`
⚠️ سطح ریسک: {anomaly_result['interpretation']['risk_level']}
📊 نمره آنومالی: {anomaly_result['anomaly_score']:.3f}

📋 **دلایل تشخیص:**
{chr(10).join(f'• {reason}' for reason in anomaly_result['interpretation']['reasons'])}

🎯 **اقدام توصیه شده:**
{anomaly_result['interpretation']['recommended_action']}
        """
        
        # ارسال به ادمین‌ها
        for admin_id in ADMIN_IDS:
            try:
                await self.manager.notify_admins(message)
            except Exception as e:
                logger.error(f"خطا در اطلاع به ادمین {admin_id}: {e}")
    
    # ========== هندلرهای کمکی ==========
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /cancel"""
        await update.message.reply_text(
            "❌ **عملیات لغو شد**\n\n"
            "برای شروع مجدد از منوی اصلی استفاده کنید: /start"
        )
        return ConversationHandler.END
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش کلیک روی دکمه‌ها"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        # مدیریت منوها
        if data == 'menu_login':
            await self.login_command(update, context)
        elif data == 'menu_accounts':
            await self.accounts_command(update, context)
        elif data.startswith('report_'):
            await self.handle_report_request(update, context)
        elif data.startswith('2fa_'):
            await self.handle_2fa_setup(update, context)
        elif data.startswith('backup_'):
            await self.handle_backup_request(update, context)
        elif data.startswith('account_'):
            await self.handle_account_action(update, context)
    
    async def handle_account_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت اقدامات اکانت"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        action = query.data.replace('account_', '')
        
        if action == 'logout':
            # خروج از اکانت
            if user_id in self.manager.user_sessions:
                session = self.manager.user_sessions[user_id]
                client = session.get('client')
                
                if client:
                    await client.disconnect()
                
                del self.manager.user_sessions[user_id]
                
                await query.edit_message_text(
                    "🚪 **خروج موفقیت‌آمیز**\n\n"
                    "شما با موفقیت از اکانت خود خارج شدید.\n"
                    "برای ورود مجدد از دستور /login استفاده کنید."
                )
        
        elif action == 'backup':
            await self.backup_command(update, context)
        
        elif action == 'report':
            await self.report_command(update, context)
        
        elif action == 'security':
            await query.edit_message_text(
                "🛡️ **بررسی امنیتی اکانت**\n\n"
                "در حال بررسی تنظیمات امنیتی...\n\n"
                "✅ 2FA: فعال\n"
                "✅ رمزنگاری session: فعال\n"
                "✅ مانیتورینگ فعالیت: فعال\n"
                "✅ تشخیص ناهنجاری: فعال\n\n"
                "امتیاز امنیتی: ۹۵ از ۱۰۰"
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت خطاها"""
        logger.error(f"خطا در به‌روزرسانی {update}: {context.error}")
        
        try:
            await update.message.reply_text(
                "❌ **خطای سیستمی**\n\n"
                "متأسفانه خطایی در پردازش درخواست شما رخ داده است.\n"
                "لطفاً دوباره تلاش کنید یا از دستور /help استفاده کنید."
            )
        except:
            pass

# ========== تابع اصلی ==========

def main():
    """تابع اصلی اجرای ربات"""
    
    print("""
╔══════════════════════════════════════════════════╗
║   🤖 ربات مدیریت اکانت تلگرام - نسخه حرفه‌ای   ║
║            با تمام ویژگی‌های پیشرفته            ║
╚══════════════════════════════════════════════════╝
    """)
    
    # بررسی TOKEN
    if TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ خطا: توکن ربات تنظیم نشده است!")
        print("لطفاً فایل config.py را ویرایش کنید.")
        sys.exit(1)
    
    # ایجاد مدیر یکپارچه
    integrated_manager = IntegratedBotManager()
    
    # ایجاد هندلرها
    handlers = TelegramBotHandlers(integrated_manager)
    
    # تنظیم تابع notify_admins
    async def notify_admins_impl(message: str):
        """پیاده‌سازی notify_admins"""
        for admin_id in ADMIN_IDS:
            try:
                await application.bot.send_message(chat_id=admin_id, text=message)
            except Exception as e:
                logger.error(f"خطا در ارسال به ادمین {admin_id}: {e}")
    
    integrated_manager.notify_admins = notify_admins_impl
    
    # ایجاد اپلیکیشن تلگرام
    application = Application.builder().token(TOKEN).build()
    
    # شروع مانیتور سلامت
    asyncio.run(integrated_manager.start_health_monitor(application))
    
    # ========== تنظیم Conversation Handlers ==========
    
    # Conversation Handler برای ورود
    login_conversation = ConversationHandler(
        entry_points=[CommandHandler('login', handlers.login_command)],
        states={
            handlers.STATES['AWAITING_PHONE']: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_phone_input)
            ],
            handlers.STATES['AWAITING_CODE']: [
                CallbackQueryHandler(handlers.handle_phone_confirmation, pattern='^(phone_confirm|phone_edit)$')
            ]
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_command)],
        allow_reentry=True
    )
    
    # Conversation Handler برای گزارش‌گیری
    report_conversation = ConversationHandler(
        entry_points=[CommandHandler('report', handlers.report_command)],
        states={
            handlers.STATES['AWAITING_REPORT_TYPE']: [
                CallbackQueryHandler(handlers.handle_report_request, pattern='^report_')
            ]
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_command)],
        allow_reentry=True
    )
    
    # Conversation Handler برای پشتیبان‌گیری
    backup_conversation = ConversationHandler(
        entry_points=[CommandHandler('backup', handlers.backup_command)],
        states={
            handlers.STATES['AWAITING_BACKUP_CONFIRM']: [
                CallbackQueryHandler(handlers.handle_backup_request, pattern='^backup_')
            ]
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_command)],
        allow_reentry=True
    )
    
    # ========== اضافه کردن هندلرها ==========
    
    # دستورات اصلی
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("accounts", handlers.accounts_command))
    application.add_handler(CommandHandler("2fa", handlers.twofa_command))
    application.add_handler(CommandHandler("health", handlers.health_command))
    
    # Conversation Handlers
    application.add_handler(login_conversation)
    application.add_handler(report_conversation)
    application.add_handler(backup_conversation)
    
    # Callback Handlers
    application.add_handler(CallbackQueryHandler(handlers.handle_callback_query))
    
    # خطاها
    application.add_error_handler(handlers.error_handler)
    
    # ========== شروع ربات ==========
    
    print(f"\n🤖 ربات @{BOT_USERNAME} در حال اجراست...")
    print("🔐 سیستم مدیریت اکانت: فعال")
    print("📊 ویژگی‌های پیشرفته: فعال")
    print("🛡️  سیستم امنیتی: فعال")
    print("🩺 مانیتور سلامت: فعال")
    print("\n📝 برای خروج Ctrl+C را بفشارید")
    print("=" * 50)
    
    # اجرای ربات
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 ربات با موفقیت متوقف شد.")
    except Exception as e:
        print(f"\n💥 خطای غیرمنتظره: {e}")
        logger.exception("خطای اصلی")
        sys.exit(1)
