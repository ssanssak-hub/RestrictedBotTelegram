#interfaces/telegram_ui.py
"""
رابط تلگرام پیشرفته با نمایش سرعت real-time
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application, CommandHandler, MessageHandler,
        CallbackQueryHandler, filters, ContextTypes
    )
    from telegram.constants import ParseMode
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

from core.monitor import AdaptiveSpeedMonitor
from core.optimizer import IntelligentSpeedOptimizer
from config.settings import config_manager

logger = logging.getLogger(__name__)

class TelegramSpeedBot:
    """ربات تلگرام با نمایش سرعت real-time"""
    
    def __init__(self, token: str, speed_monitor: AdaptiveSpeedMonitor, 
                 speed_optimizer: IntelligentSpeedOptimizer):
        if not HAS_TELEGRAM:
            raise ImportError("python-telegram-bot is not installed")
        
        self.token = token
        self.speed_monitor = speed_monitor
        self.speed_optimizer = speed_optimizer
        self.application = None
        
        # وضعیت کاربران
        self.user_sessions: Dict[int, Dict] = {}
        
        logger.info("TelegramSpeedBot initialized")
    
    async def start(self):
        """شروع ربات"""
        try:
            self.application = Application.builder().token(self.token).build()
            
            # ثبت handlers
            self._setup_handlers()
            
            # شروع ربات
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("✅ Telegram bot started successfully")
            
            # نگه داشتن ربات در حال اجرا
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
    
    def _setup_handlers(self):
        """تنظیم handlers ربات"""
        # دستورات
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("download", self.download_command))
        self.application.add_handler(CommandHandler("upload", self.upload_command))
        self.application.add_handler(CommandHandler("speed", self.speed_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("settings", self.settings_command))
        
        # پیام‌های متنی
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.text_message
        ))
        
        # فایل‌ها
        self.application.add_handler(MessageHandler(
            filters.Document.ALL, self.document_handler
        ))
        
        # Callback queries
        self.application.add_handler(CallbackQueryHandler(self.callback_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /start"""
        user = update.effective_user
        
        welcome_text = """
        🚀 به ربات مدیریت سرعت خوش آمدید!

        ✨ **ویژگی‌ها:**
        • دانلود با نمایش سرعت real-time
        • آپلود با بهینه‌سازی هوشمند
        • پیش‌بینی سرعت با هوش مصنوعی
        • نمودارهای تحلیلی

        📋 **دستورات:**
        /download - دانلود فایل
        /upload - آپلود فایل
        /speed - تست سرعت
        /stats - آمار سیستم
        /settings - تنظیمات

        برای شروع، یک فایل ارسال کنید یا از دستورات استفاده کنید.
        """
        
        keyboard = [
            [InlineKeyboardButton("📥 دانلود", callback_data="download")],
            [InlineKeyboardButton("📤 آپلود", callback_data="upload")],
            [InlineKeyboardButton("⚡ تست سرعت", callback_data="speedtest")],
            [InlineKeyboardButton("📊 آمار", callback_data="stats")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /download"""
        # دریافت URL یا اطلاعات فایل
        if not context.args:
            await update.message.reply_text(
                "لطفاً لینک فایل را وارد کنید:\n"
                "مثال: /download https://example.com/file.zip"
            )
            return
        
        url = context.args[0]
        user_id = update.effective_user.id
        
        # شروع دانلود
        await self.start_download(update, user_id, url)
    
    async def start_download(self, update: Update, user_id: int, url: str):
        """شروع دانلود با نمایش سرعت"""
        message = await update.message.reply_text(
            "🔍 در حال بررسی فایل...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # ثبت انتقال در مانیتور
            transfer_id = f"tg_dl_{user_id}_{int(asyncio.get_event_loop().time())}"
            
            # دریافت اطلاعات فایل
            file_info = await self.speed_optimizer._analyze_file(url, Path("downloads"))
            
            if not file_info.get('size'):
                await message.edit_text("❌ نتوانستم اطلاعات فایل را دریافت کنم.")
                return
            
            # ثبت در مانیتور
            await self.speed_monitor.register_transfer(
                transfer_id=transfer_id,
                user_id=str(user_id),
                file_name=url.split('/')[-1],
                file_size=file_info['size'],
                transfer_type='download',
                priority=5
            )
            
            # شروع دانلود
            await message.edit_text(
                f"✅ فایل شناسایی شد!\n"
                f"📁 حجم: {file_info['size'] / (1024*1024):.2f} MB\n"
                f"⚡ شروع دانلود با بهینه‌سازی..."
            )
            
            # دانلود فایل
            destination = Path("downloads") / url.split('/')[-1]
            result = await self.speed_optimizer.download_file(
                url=url,
                destination=destination,
                progress_callback=lambda data: self._update_progress(
                    transfer_id, message, data
                )
            )
            
            if result['success']:
                # ارسال فایل
                await self._send_downloaded_file(
                    update, user_id, destination, result
                )
            else:
                await message.edit_text(f"❌ خطا در دانلود: {result.get('error', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            await message.edit_text(f"❌ خطا: {str(e)}")
    
    async def _update_progress(self, transfer_id: str, message, speed_data):
        """به‌روزرسانی پیشرفت در تلگرام"""
        try:
            # فرمت متن
            progress_text = self._format_progress_text(speed_data)
            
            # ویرایش پیام
            await message.edit_text(
                progress_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Progress update error: {e}")
    
    def _format_progress_text(self, speed_data) -> str:
        """قالب‌بندی متن پیشرفت"""
        progress_bar = self._create_progress_bar(speed_data.progress_percent)
        
        # تبدیل واحدها
        if speed_data.speed_mbps >= 1:
            speed_text = f"{speed_data.speed_mbps:.2f} MB/s"
        elif speed_data.speed_kbps >= 1:
            speed_text = f"{speed_data.speed_kbps:.2f} KB/s"
        else:
            speed_text = f"{speed_data.speed_bps:.0f} B/s"
        
        # فرمت زمان
        if speed_data.eta_seconds < 60:
            eta_text = f"{speed_data.eta_seconds:.0f} ثانیه"
        elif speed_data.eta_seconds < 3600:
            eta_text = f"{speed_data.eta_seconds/60:.0f} دقیقه"
        else:
            eta_text = f"{speed_data.eta_seconds/3600:.1f} ساعت"
        
        return f"""
        📥 **در حال دانلود...**
        
        {progress_bar} {speed_data.progress_percent:.1f}%
        
        ⚡ **سرعت:** {speed_text}
        ⏳ **زمان باقیمانده:** {eta_text}
        💾 **حجم:** {speed_data.bytes_transferred/(1024*1024):.2f} / {speed_data.total_bytes/(1024*1024):.2f} MB
        
        🔄 **پیش‌بینی:** {self._get_speed_prediction(speed_data)}
        """
    
    def _create_progress_bar(self, percentage: float, length: int = 20) -> str:
        """ایجاد progress bar"""
        filled = int(length * percentage / 100)
        bar = '█' * filled + '░' * (length - filled)
        return f"[{bar}]"
    
    def _get_speed_prediction(self, speed_data) -> str:
        """دریافت پیش‌بینی سرعت"""
        # اینجا می‌توان از AI predictor استفاده کرد
        if speed_data.speed_mbps > 10:
            return "عالی 🚀"
        elif speed_data.speed_mbps > 5:
            return "خوب 👍"
        elif speed_data.speed_mbps > 1:
            return "متوسط 📶"
        else:
            return "ضعیف 🐌"
    
    async def _send_downloaded_file(self, update: Update, user_id: int, 
                                  file_path: Path, result: Dict):
        """ارسال فایل دانلود شده"""
        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=file_path.name,
                    caption=f"✅ دانلود کامل شد!\n"
                           f"⚡ سرعت متوسط: {result.get('speed_mbps', 0):.2f} MB/s\n"
                           f"⏱️ زمان: {result.get('time', 0):.2f} ثانیه"
                )
            
            # حذف فایل موقت
            file_path.unlink(missing_ok=True)
            
        except Exception as e:
            logger.error(f"Send file error: {e}")
            await update.message.reply_text(f"❌ خطا در ارسال فایل: {str(e)}")
    
    async def upload_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /upload"""
        await update.message.reply_text(
            "لطفاً فایل مورد نظر را ارسال کنید.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def document_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت فایل ارسالی"""
        document = update.message.document
        user_id = update.effective_user.id
        
        if not document:
            return
        
        # شروع آپلود
        await self.start_upload(update, user_id, document)
    
    async def start_upload(self, update: Update, user_id: int, document):
        """شروع آپلود"""
        message = await update.message.reply_text(
            "📤 در حال آماده‌سازی آپلود...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # دریافت فایل
            file = await document.get_file()
            
            # ثبت انتقال
            transfer_id = f"tg_ul_{user_id}_{int(asyncio.get_event_loop().time())}"
            
            await self.speed_monitor.register_transfer(
                transfer_id=transfer_id,
                user_id=str(user_id),
                file_name=document.file_name,
                file_size=document.file_size,
                transfer_type='upload',
                priority=5
            )
            
            # آپلود
            await message.edit_text(
                f"✅ فایل شناسایی شد!\n"
                f"📁 {document.file_name}\n"
                f"💾 حجم: {document.file_size / (1024*1024):.2f} MB\n"
                f"⚡ شروع آپلود با بهینه‌سازی..."
            )
            
            # اینجا می‌توان آپلود به سرور یا سرویس cloud را پیاده کرد
            # فعلاً فقط شبیه‌سازی می‌کنیم
            await self._simulate_upload(transfer_id, message, document.file_size)
            
        except Exception as e:
            logger.error(f"Upload error: {e}")
            await message.edit_text(f"❌ خطا در آپلود: {str(e)}")
    
    async def _simulate_upload(self, transfer_id: str, message, file_size: int):
        """شبیه‌سازی آپلود"""
        chunk_size = 1024 * 1024  # 1MB
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        
        for chunk_num in range(total_chunks):
            # به‌روزرسانی پیشرفت
            transferred = min((chunk_num + 1) * chunk_size, file_size)
            
            await self.speed_monitor.update_transfer_progress(
                transfer_id=transfer_id,
                bytes_transferred=transferred,
                total_bytes=file_size
            )
            
            # تأخیر شبیه‌سازی
            await asyncio.sleep(0.1)
        
        # تکمیل
        await self.speed_monitor.complete_transfer(
            transfer_id,
            success=True
        )
        
        await message.edit_text("✅ آپلود با موفقیت تکمیل شد!")
    
    async def speed_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /speed - تست سرعت"""
        message = await update.message.reply_text(
            "🧪 در حال اجرای تست سرعت...",
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # اجرای تست سرعت
            result = await self._run_speed_test()
            
            # نمایش نتایج
            result_text = self._format_speed_test_results(result)
            
            await message.edit_text(
                result_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Speed test error: {e}")
            await message.edit_text(f"❌ خطا در تست سرعت: {str(e)}")
    
    async def _run_speed_test(self) -> Dict:
        """اجرای تست سرعت"""
        # اینجا می‌توان از speedtest-cli یا سرویس‌های آنلاین استفاده کرد
        # فعلاً شبیه‌سازی می‌کنیم
        import random
        
        return {
            'download': random.uniform(10, 100),  # Mbps
            'upload': random.uniform(5, 50),      # Mbps
            'ping': random.randint(10, 100),      # ms
            'server': 'Iran, Tehran',
            'timestamp': asyncio.get_event_loop().time()
        }
    
    def _format_speed_test_results(self, result: Dict) -> str:
        """قالب‌بندی نتایج تست سرعت"""
        return f"""
        📊 **نتایج تست سرعت**
        
        ⬇️ **دانلود:** {result['download']:.2f} Mbps
        ⬆️ **آپلود:** {result['upload']:.2f} Mbps
        📍 **پینگ:** {result['ping']} ms
        🌐 **سرور:** {result['server']}
        
        📈 **وضعیت:** {self._evaluate_speed(result['download'], result['upload'])}
        """
    
    def _evaluate_speed(self, download: float, upload: float) -> str:
        """ارزیابی سرعت"""
        avg = (download + upload) / 2
        
        if avg > 50:
            return "عالی 🚀"
        elif avg > 20:
            return "خوب 👍"
        elif avg > 5:
            return "متوسط 📶"
        else:
            return "ضعیف 🐌"
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /stats - آمار سیستم"""
        try:
            # دریافت آمار از مانیتور
            stats = await self.speed_monitor.get_system_overview()
            
            stats_text = self._format_stats(stats)
            
            await update.message.reply_text(
                stats_text,
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await update.message.reply_text(f"❌ خطا در دریافت آمار: {str(e)}")
    
    def _format_stats(self, stats: Dict) -> str:
        """قالب‌بندی آمار"""
        return f"""
        📈 **آمار سیستم**
        
        🔄 **انتقال‌های فعال:** {stats.get('active_transfers', 0)}
        👥 **کاربران منحصربه‌فرد:** {stats.get('unique_users', 0)}
        
        ⚡ **سرعت متوسط:**
        ⬇️ دانلود: {stats.get('avg_download_speed', 0):.2f} Mbps
        ⬆️ آپلود: {stats.get('avg_upload_speed', 0):.2f} Mbps
        
        📊 **ترافیک کل:**
        ⬇️ دانلود: {stats.get('total_throughput_mbps', 0):.2f} Mbps
        🧠 **هوش مصنوعی:** {'فعال ✅' if stats.get('ai_enabled') else 'غیرفعال ❌'}
        
        ⏱️ **آپتایم:** {stats.get('uptime_seconds', 0):.0f} ثانیه
        """
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /settings - تنظیمات"""
        keyboard = [
            [InlineKeyboardButton("⚡ تنظیمات سرعت", callback_data="speed_settings")],
            [InlineKeyboardButton("🔒 تنظیمات امنیتی", callback_data="security_settings")],
            [InlineKeyboardButton("📊 تنظیمات نمایش", callback_data="display_settings")],
            [InlineKeyboardButton("↩️ بازگشت", callback_data="back")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚙️ **تنظیمات سیستم**\n\n"
            "لطفاً بخش مورد نظر را انتخاب کنید:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    async def text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت پیام‌های متنی"""
        text = update.message.text
        
        if text.startswith('http'):
            # اگر متن URL باشد
            await self.start_download(update, update.effective_user.id, text)
        else:
            await update.message.reply_text(
                "از دستورات استفاده کنید یا فایل/لینک ارسال کنید.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت callback queries"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "download":
            await query.edit_message_text(
                "لطفاً لینک فایل را وارد کنید:\n"
                "یا از دستور /download استفاده کنید."
            )
        elif data == "upload":
            await query.edit_message_text(
                "لطفاً فایل مورد نظر را ارسال کنید.\n"
                "یا از دستور /upload استفاده کنید."
            )
        elif data == "speedtest":
            await self.speed_command(update, context)
        elif data == "stats":
            await self.stats_command(update, context)
        elif data == "back":
            await self.start_command(update, context)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /help"""
        help_text = """
        📋 **راهنما**
        
        **دستورات اصلی:**
        /start - شروع ربات
        /download <url> - دانلود فایل
        /upload - آپلود فایل
        /speed - تست سرعت اینترنت
        /stats - نمایش آمار سیستم
        /settings - تنظیمات
        /help - این راهنما
        
        **نحوه استفاده:**
        1. برای دانلود: لینک فایل را بفرستید یا از /download استفاده کنید
        2. برای آپلود: فایل را ارسال کنید
        3. سرعت انتقال به صورت real-time نمایش داده می‌شود
        
        **پشتیبانی:** @your_support_channel
        """
        
        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def shutdown(self):
        """خاموش کردن ربات"""
        if self.application:
            await self.application.stop()
            await self.application.shutdown()
        
        logger.info("Telegram bot shutdown complete")
