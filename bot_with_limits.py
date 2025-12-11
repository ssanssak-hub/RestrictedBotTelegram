#!/usr/bin/env python3
# bot_with_limits.py - ربات با سیستم محدودیت کامل

import telebot
from telebot import types
import json
import time
from datetime import datetime
from pathlib import Path
from limits_manager import LimitsManager, LimitType
import threading
import queue

class LimitedBot:
    """ربات با سیستم محدودیت کامل"""
    
    def __init__(self, token: str):
        self.bot = telebot.TeleBot(token)
        self.limits_manager = LimitsManager()
        self.user_states = {}
        self.download_queue = queue.Queue()
        
        # شروع worker برای دانلود‌ها
        self._start_download_workers()
        
        # تنظیم هندلرها
        self.setup_handlers()
        
        # شروع cleaner برای ریست دوره‌ای
        self._start_limit_cleaner()
        
        logger.info("LimitedBot initialized")
    
    def _start_download_workers(self, num_workers: int = 3):
        """شروع workerها برای مدیریت دانلود همزمان"""
        def download_worker():
            while True:
                try:
                    task = self.download_queue.get()
                    if task is None:  # سیگنال خاتمه
                        break
                    
                    user_id, file_id, file_info = task
                    self._process_download(user_id, file_id, file_info)
                    
                    self.download_queue.task_done()
                    
                except Exception as e:
                    logger.error(f"Download worker error: {e}")
        
        for i in range(num_workers):
            thread = threading.Thread(target=download_worker, daemon=True)
            thread.start()
        
        logger.info(f"Started {num_workers} download workers")
    
    def _start_limit_cleaner(self):
        """شروع cleaner برای ریست محدودیت‌های دوره‌ای"""
        def cleaner():
            while True:
                time.sleep(3600)  # هر ساعت بررسی
                self._clean_expired_limits()
        
        thread = threading.Thread(target=cleaner, daemon=True)
        thread.start()
        
        logger.info("Limit cleaner started")
    
    def _clean_expired_limits(self):
        """پاکسازی محدودیت‌های منقضی شده"""
        try:
            # این تابع باید در LimitsManager پیاده‌سازی شود
            # برای سادگی، فعلاً فقط لاگ می‌کنیم
            logger.info("Cleaning expired limits...")
        except Exception as e:
            logger.error(f"Cleaner error: {e}")
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            user_id = message.from_user.id
            username = message.from_user.username
            
            # ثبت کاربر جدید
            self._register_user(user_id, username)
            
            # نمایش منو
            self.show_main_menu(user_id)
            
            # ارسال آمار
            self.send_user_stats(user_id)
        
        @self.bot.message_handler(func=lambda m: m.text == '📥 دانلود فایل')
        def download_handler(message):
            user_id = message.from_user.id
            
            # بررسی محدودیت کاربران
            user_limit = self.limits_manager.check_global_limit(
                LimitType.USER_COUNT
            )
            
            if not user_limit['allowed']:
                self.bot.send_message(
                    user_id,
                    "⛔ ربات به حداکثر تعداد کاربران رسیده است.\n"
                    "لطفاً بعداً تلاش کنید."
                )
                return
            
            # نمایش لیست فایل‌ها
            self.show_file_list(user_id)
        
        @self.bot.message_handler(func=lambda m: m.text == '📊 آمار من')
        def stats_handler(message):
            user_id = message.from_user.id
            self.send_user_stats(user_id)
        
        @self.bot.message_handler(func=lambda m: m.text == '💎 ارتقا حساب')
        def upgrade_handler(message):
            user_id = message.from_user.id
            self.show_upgrade_options(user_id)
        
        @self.bot.message_handler(commands=['admin'])
        def admin_handler(message):
            user_id = message.from_user.id
            
            # بررسی ادمین بودن
            if not self._is_admin(user_id):
                self.bot.send_message(user_id, "⛔ دسترسی denied!")
                return
            
            self.show_admin_panel(user_id)
    
    def _register_user(self, user_id: int, username: str):
        """ثبت کاربر جدید"""
        # بررسی محدودیت تعداد کاربران
        user_limit = self.limits_manager.check_global_limit(
            LimitType.USER_COUNT
        )
        
        if not user_limit['allowed']:
            # کاربر نمی‌تواند ثبت نام کند
            return False
        
        # افزایش شمارش کاربر
        self.limits_manager.increment_global_usage(LimitType.USER_COUNT)
        
        # ذخیره اطلاعات کاربر
        self.user_states[user_id] = {
            'username': username,
            'join_date': datetime.now().isoformat(),
            'total_downloads': 0,
            'total_size': 0,
            'last_activity': time.time()
        }
        
        return True
    
    def show_main_menu(self, chat_id: int):
        """نمایش منوی اصلی"""
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        # بررسی tier کاربر
        user_tier = self.limits_manager.get_user_tier(chat_id)
        
        if user_tier == 'free':
            keyboard.row('📥 دانلود فایل (۱۰ تای رایگان)')
            keyboard.row('📊 آمار من', '💎 ارتقا حساب')
            keyboard.row('ℹ️ راهنما', '📞 پشتیبانی')
        elif user_tier == 'premium':
            keyboard.row('📥 دانلود فایل (۵۰ تای روزانه)')
            keyboard.row('📊 آمار من', '📁 فایل‌های من')
            keyboard.row('⚙️ تنظیمات', '📞 پشتیبانی')
        else:  # vip
            keyboard.row('📥 دانلود فایل (نامحدود)')
            keyboard.row('📊 آمار من', '📁 فایل‌های من')
            keyboard.row('⚙️ تنظیمات', '👑 پنل VIP')
        
        welcome_text = self._get_welcome_text(chat_id)
        
        self.bot.send_message(chat_id, welcome_text, reply_markup=keyboard)
    
    def _get_welcome_text(self, user_id: int) -> str:
        """متن خوشآمدگویی با اطلاعات محدودیت"""
        stats = self.limits_manager.get_user_stats(user_id)
        tier = stats['tier']
        
        if tier == 'free':
            daily_limit = stats['limits']['daily_downloads']['limit']
            total_limit = stats['limits']['total_downloads']['limit']
            
            return (
                f"👋 به ربات ما خوش آمدید!\n\n"
                f"🎯 شما در حال استفاده از حساب <b>رایگان</b> هستید.\n"
                f"📥 دانلود روزانه: {daily_limit} فایل\n"
                f"📦 کل دانلود: حداکثر {total_limit} فایل\n\n"
                f"💎 برای دریافت محدودیت بیشتر، حساب خود را ارتقا دهید."
            )
        
        elif tier == 'premium':
            daily_limit = stats['limits']['daily_downloads']['limit']
            
            return (
                f"👋 به ربات ما خوش آمدید!\n\n"
                f"✨ شما کاربر <b>پریمیوم</b> هستید!\n"
                f"📥 دانلود روزانه: {daily_limit} فایل\n"
                f"🚀 سرعت دانلود بالا\n"
                f"📊 آمار پیشرفته\n\n"
                f"از امکانات ویژه لذت ببرید!"
            )
        
        else:  # vip
            return (
                f"👑 به ربات ما خوش آمدید!\n\n"
                f"💎 شما کاربر <b>VIP</b> هستید!\n"
                f"📥 دانلود نامحدود\n"
                f"⚡ سرعت بسیار بالا\n"
                f"🎯 اولویت در صف دانلود\n"
                f"📊 آمار کامل\n\n"
                f"با تشکر از اعتماد شما!"
            )
    
    def send_user_stats(self, chat_id: int):
        """ارسال آمار کاربر"""
        stats = self.limits_manager.get_user_stats(chat_id)
        tier = stats['tier']
        
        # ساختن متن آمار
        stats_text = f"📊 <b>آمار حساب {tier.upper()}</b>\n\n"
        
        for limit_key, limit_info in stats['limits'].items():
            used = limit_info['used']
            limit = limit_info['limit']
            remaining = limit_info['remaining']
            percent = limit_info['percent_used']
            
            # نمایش progress bar
            bar_length = 10
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            stats_text += (
                f"• {self._get_limit_name(limit_key)}:\n"
                f"  {bar} {percent:.1f}%\n"
                f"  📥 استفاده شده: {used}\n"
                f"  📦 باقیمانده: {remaining}\n"
                f"  🎯 سقف: {limit}\n"
            )
            
            if limit_info['next_reset']:
                reset_time = limit_info['next_reset'][:16].replace('T', ' ')
                stats_text += f"  ⏰ ریست: {reset_time}\n"
            
            stats_text += "\n"
        
        # نمایش تخلفات
        if stats['violations']:
            stats_text += "⚠️ <b>اخطارها:</b>\n"
            for violation in stats['violations'][:3]:  # فقط 3 تا آخر
                stats_text += (
                    f"• {violation['limit_type']}: "
                    f"تجاوز {violation['exceeded_by']}\n"
                )
        
        self.bot.send_message(chat_id, stats_text, parse_mode='HTML')
    
    def _get_limit_name(self, limit_key: str) -> str:
        """نام فارسی محدودیت"""
        names = {
            'daily_downloads': '📥 دانلود روزانه',
            'total_downloads': '📦 کل دانلود‌ها',
            'download_size': '💾 حجم فایل',
            'concurrent_downloads': '⚡ دانلود همزمان',
            'bandwidth': '🌐 پهنای باند',
            'api_requests': '🔁 درخواست‌ها'
        }
        return names.get(limit_key, limit_key)
    
    def show_file_list(self, chat_id: int):
        """نمایش لیست فایل‌ها با بررسی محدودیت"""
        # 1. بررسی محدودیت دانلود روزانه
        daily_check = self.limits_manager.check_user_limit(
            chat_id, LimitType.DAILY_DOWNLOADS
        )
        
        if not daily_check['allowed']:
            remaining_time = daily_check.get('next_reset', 'امروز')
            self.bot.send_message(
                chat_id,
                f"⛔ محدودیت دانلود روزانه شما تکمیل شده است.\n\n"
                f"📊 استفاده شده: {daily_check['used']}/{daily_check['limit']}\n"
                f"⏰ ریست مجدد: {remaining_time}\n\n"
                f"💎 برای دانلود بیشتر، حساب خود را ارتقا دهید."
            )
            return
        
        # 2. بررسی محدودیت کل دانلود
        total_check = self.limits_manager.check_user_limit(
            chat_id, LimitType.TOTAL_DOWNLOADS
        )
        
        if not total_check['allowed']:
            self.bot.send_message(
                chat_id,
                f"⛔ شما به سقف کل دانلود‌ها رسیده‌اید.\n\n"
                f"📊 استفاده شده: {total_check['used']}/{total_check['limit']}\n\n"
                f"💎 برای دانلود بیشتر، حساب خود را ارتقا دهید."
            )
            return
        
        # 3. نمایش هشدار اگر نزدیک به محدودیت باشد
        if daily_check['warning']:
            self.bot.send_message(
                chat_id,
                f"⚠️ شما {daily_check['used']} از {daily_check['limit']} "
                f"دانلود روزانه خود را استفاده کرده‌اید.\n"
                f"📊 باقیمانده: {daily_check['remaining']}"
            )
        
        # 4. نمایش لیست فایل‌ها
        files = self._get_available_files()
        
        if not files:
            self.bot.send_message(chat_id, "📭 در حال حاضر فایلی موجود نیست.")
            return
        
        keyboard = types.InlineKeyboardMarkup()
        
        for i, file_info in enumerate(files[:20]):  # حداکثر 20 فایل
            file_name = file_info['name']
            file_size_mb = file_info['size_mb']
            
            # بررسی محدودیت حجم فایل
            size_check = self.limits_manager.check_user_limit(
                chat_id, LimitType.DOWNLOAD_SIZE, file_size_mb
            )
            
            if not size_check['allowed']:
                btn_text = f"⛔ {file_name} ({file_size_mb}MB)"
                callback_data = f"size_limit_{file_info['id']}"
            else:
                btn_text = f"📥 {file_name} ({file_size_mb}MB)"
                callback_data = f"download_{file_info['id']}"
            
            keyboard.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=callback_data
            ))
        
        self.bot.send_message(
            chat_id,
            f"📁 <b>فایل‌های موجود</b>\n\n"
            f"📊 دانلود امروز: {daily_check['used']}/{daily_check['limit']}\n"
            f"📦 کل دانلود: {total_check['used']}/{total_check['limit']}\n"
            f"💾 محدودیت حجم: {size_check['limit']}MB\n\n"
            f"برای دانلود روی فایل کلیک کنید:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    
    @self.bot.callback_query_handler(func=lambda call: call.data.startswith('download_'))
    def download_callback_handler(call):
        """هندلر دانلود فایل"""
        user_id = call.from_user.id
        file_id = call.data.replace('download_', '')
        
        # دریافت اطلاعات فایل
        file_info = self._get_file_info(file_id)
        if not file_info:
            self.bot.answer_callback_query(call.id, "❌ فایل یافت نشد")
            return
        
        file_size_mb = file_info['size_mb']
        
        # 1. بررسی محدودیت حجم فایل
        size_check = self.limits_manager.check_user_limit(
            user_id, LimitType.DOWNLOAD_SIZE, file_size_mb
        )
        
        if not size_check['allowed']:
            self.bot.answer_callback_query(
                call.id, 
                f"⛔ حجم فایل بیشتر از محدودیت شما است ({size_check['limit']}MB)"
            )
            return
        
        # 2. بررسی محدودیت دانلود روزانه
        daily_check = self.limits_manager.check_user_limit(
            user_id, LimitType.DAILY_DOWNLOADS
        )
        
        if not daily_check['allowed']:
            self.bot.answer_callback_query(call.id, "⛔ محدودیت دانلود روزانه")
            return
        
        # 3. بررسی محدودیت کل دانلود
        total_check = self.limits_manager.check_user_limit(
            user_id, LimitType.TOTAL_DOWNLOADS
        )
        
        if not total_check['allowed']:
            self.bot.answer_callback_query(call.id, "⛔ محدودیت کل دانلود")
            return
        
        # 4. بررسی محدودیت دانلود همزمان
        concurrent_check = self.limits_manager.check_user_limit(
            user_id, LimitType.CONCURRENT_DOWNLOADS
        )
        
        if not concurrent_check['allowed']:
            self.bot.answer_callback_query(
                call.id, 
                f"⛔ حداکثر {concurrent_check['limit']} دانلود همزمان مجاز است"
            )
            return
        
        # 5. بررسی پهنای باند
        bandwidth_check = self.limits_manager.check_user_limit(
            user_id, LimitType.BANDWIDTH, file_size_mb
        )
        
        if not bandwidth_check['allowed']:
            self.bot.answer_callback_query(
                call.id,
                f"⛔ محدودیت پهنای باند: {bandwidth_check['used']}/{bandwidth_check['limit']}GB"
            )
            return
        
        # 6. اضافه کردن به صف دانلود
        self.download_queue.put((user_id, file_id, file_info))
        
        # افزایش محدودیت‌ها
        self.limits_manager.increment_user_usage(
            user_id, LimitType.DAILY_DOWNLOADS
        )
        self.limits_manager.increment_user_usage(
            user_id, LimitType.TOTAL_DOWNLOADS
        )
        self.limits_manager.increment_user_usage(
            user_id, LimitType.DOWNLOAD_SIZE, file_size_mb
        )
        self.limits_manager.increment_user_usage(
            user_id, LimitType.BANDWIDTH, file_size_mb
        )
        self.limits_manager.increment_user_usage(
            user_id, LimitType.CONCURRENT_DOWNLOADS
        )
        
        # پاسخ به کاربر
        remaining_daily = daily_check['remaining'] - 1
        remaining_total = total_check['remaining'] - 1
        
        self.bot.answer_callback_query(
            call.id,
            f"✅ در صف دانلود قرار گرفت\n"
            f"📥 امروز: {remaining_daily} باقیمانده\n"
            f"📦 کل: {remaining_total} باقیمانده"
        )
        
        # ارسال پیام تأیید
        self.bot.send_message(
            user_id,
            f"📥 فایل '{file_info['name']}' در صف دانلود قرار گرفت.\n\n"
            f"📊 وضعیت دانلود:\n"
            f"• حجم: {file_size_mb}MB\n"
            f"• موقعیت در صف: {self.download_queue.qsize()}\n"
            f"• دانلود امروز: {daily_check['used'] + 1}/{daily_check['limit']}\n"
            f"• کل دانلود: {total_check['used'] + 1}/{total_check['limit']}"
        )
    
    def _process_download(self, user_id: int, file_id: str, file_info: dict):
        """پردازش دانلود"""
        try:
            # شبیه‌سازی دانلود
            file_size_mb = file_info['size_mb']
            download_time = file_size_mb * 0.5  # فرض: 0.5 ثانیه به ازای هر مگابایت
            
            # اطلاع شروع دانلود
            self.bot.send_message(
                user_id,
                f"⏬ دانلود '{file_info['name']}' شروع شد...\n"
                f"⏳ زمان تخمینی: {download_time:.1f} ثانیه"
            )
            
            time.sleep(min(download_time, 10))  # حداکثر 10 ثانیه
            
            # شبیه‌سازی ارسال فایل
            # در واقعیت اینجا فایل ارسال می‌شود
            
            # اطلاع پایان دانلود
            self.bot.send_message(
                user_id,
                f"✅ دانلود '{file_info['name']}' تکمیل شد!\n\n"
                f"📥 فایل با موفقیت دانلود شد.\n"
                f"💾 حجم: {file_size_mb}MB"
            )
            
            # کاهش محدودیت دانلود همزمان
            self.limits_manager.increment_user_usage(
                user_id, LimitType.CONCURRENT_DOWNLOADS, -1
            )
            
            logger.info(f"Download completed for user {user_id}: {file_info['name']}")
            
        except Exception as e:
            logger.error(f"Download error for user {user_id}: {e}")
            
            # برگرداندن محدودیت‌ها در صورت خطا
            self.limits_manager.increment_user_usage(
                user_id, LimitType.DAILY_DOWNLOADS, -1
            )
            self.limits_manager.increment_user_usage(
                user_id, LimitType.TOTAL_DOWNLOADS, -1
            )
            self.limits_manager.increment_user_usage(
                user_id, LimitType.DOWNLOAD_SIZE, -file_info['size_mb']
            )
            self.limits_manager.increment_user_usage(
                user_id, LimitType.BANDWIDTH, -file_info['size_mb']
            )
            self.limits_manager.increment_user_usage(
                user_id, LimitType.CONCURRENT_DOWNLOADS, -1
            )
            
            self.bot.send_message(
                user_id,
                f"❌ خطا در دانلود فایل:\n{str(e)}"
            )
    
    def show_upgrade_options(self, chat_id: int):
        """نمایش گزینه‌های ارتقا"""
        keyboard = types.InlineKeyboardMarkup()
        
        keyboard.add(types.InlineKeyboardButton(
            "💎 پریمیوم - ماهانه 50,000 تومان",
            callback_data="upgrade_premium_monthly"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "💎 پریمیوم - سالانه 500,000 تومان (2 ماه رایگان)",
            callback_data="upgrade_premium_yearly"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "👑 VIP - ماهانه 150,000 تومان",
            callback_data="upgrade_vip_monthly"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "👑 VIP - سالانه 1,500,000 تومان (2 ماه رایگان)",
            callback_data="upgrade_vip_yearly"
        ))
        
        # مقایسه امکانات
        comparison_text = """
💎 <b>مقایسه پلن‌ها:</b>

<b>رایگان (Free):</b>
• ۱۰ دانلود روزانه
• حداکثر ۱۰۰ دانلود کل
• حداکثر حجم فایل: ۵۰۰MB
• ۳ دانلود همزمان
• پشتیبانی پایه

<b>💎 پریمیوم (Premium):</b>
• ۵۰ دانلود روزانه
• دانلود نامحدود کل
• حداکثر حجم فایل: ۲GB
• ۵ دانلود همزمان
• سرعت دانلود بالا
• پشتیبانی ویژه
• آمار پیشرفته

<b>👑 VIP:</b>
• دانلود روزانه نامحدود
• دانلود کل نامحدود
• حداکثر حجم فایل: نامحدود
• ۱۰ دانلود همزمان
• سرعت دانلود بسیار بالا
• اولویت در صف دانلود
• پشتیبانی VIP 24/7
• آمار کامل
"""
        
        self.bot.send_message(
            chat_id,
            comparison_text,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    
    def show_admin_panel(self, chat_id: int):
        """پنل مدیریت"""
        keyboard = types.InlineKeyboardMarkup()
        
        keyboard.add(types.InlineKeyboardButton(
            "📊 آمار کلی سیستم",
            callback_data="admin_stats"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "👥 مدیریت کاربران",
            callback_data="admin_users"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "⚙️ تنظیمات محدودیت‌ها",
            callback_data="admin_limits"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "💰 گزارش مالی",
            callback_data="admin_finance"
        ))
        
        keyboard.add(types.InlineKeyboardButton(
            "📈 نمودارها",
            callback_data="admin_charts"
        ))
        
        self.bot.send_message(
            chat_id,
            "👨‍💼 <b>پنل مدیریت</b>\n\n"
            "لطفاً گزینه مورد نظر را انتخاب کنید:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
    
    @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_stats')
    def admin_stats_handler(call):
        """آمار کلی سیستم"""
        user_id = call.from_user.id
        
        # جمع‌آوری آمار
        total_users = self.limits_manager.get_global_usage(LimitType.USER_COUNT)
        total_files = self.limits_manager.get_global_usage(LimitType.FILE_COUNT)
        total_downloads = self.limits_manager.get_global_usage(LimitType.TOTAL_DOWNLOADS)
        bandwidth_used = self.limits_manager.get_global_usage(LimitType.BANDWIDTH)
        
        # محاسبه درصدها
        user_limit = self.limits_manager.limits_config['user_count'].max_value
        file_limit = self.limits_manager.limits_config['file_count'].max_value
        bandwidth_limit = self.limits_manager.limits_config['bandwidth'].max_value
        
        stats_text = (
            f"📊 <b>آمار کلی سیستم</b>\n\n"
            f"👥 کاربران: {total_users:,} / {user_limit:,} "
            f"({total_users/user_limit*100:.1f}%)\n"
            f"📁 فایل‌ها: {total_files:,} / {file_limit:,} "
            f"({total_files/file_limit*100:.1f}%)\n"
            f"📥 کل دانلود‌ها: {total_downloads:,}\n"
            f"🌐 پهنای باند: {bandwidth_used:,}GB / {bandwidth_limit:,}GB "
            f"({bandwidth_used/bandwidth_limit*100:.1f}%)\n\n"
            f"<b>توزیع کاربران:</b>\n"
            f"• رایگان: 75%\n"
            f"• پریمیوم: 20%\n"
            f"• VIP: 5%"
        )
        
        self.bot.send_message(user_id, stats_text, parse_mode='HTML')
        self.bot.answer_callback_query(call.id)
    
    def _get_available_files(self) -> list:
        """دریافت لیست فایل‌های موجود"""
        # این تابع باید از دیتابیس خوانده شود
        # برای نمونه، فایل‌های تستی
        return [
            {'id': '1', 'name': 'کتاب آموزشی.pdf', 'size_mb': 5},
            {'id': '2', 'name': 'ویدیو آموزش پایتون.mp4', 'size_mb': 150},
            {'id': '3', 'name': 'آهنگ جدید.mp3', 'size_mb': 8},
            {'id': '4', 'name': 'نرم‌افزار کاربردی.zip', 'size_mb': 300},
            {'id': '5', 'name': 'مقاله علمی.docx', 'size_mb': 2},
            {'id': '6', 'name': 'فیلم سینمایی.mkv', 'size_mb': 1200},
            {'id': '7', 'name': 'کتاب صوتی.ogg', 'size_mb': 50},
            {'id': '8', 'name': 'پروژه نمونه.rar', 'size_mb': 80}
        ]
    
    def _get_file_info(self, file_id: str) -> dict:
        """دریافت اطلاعات فایل"""
        files = self._get_available_files()
        for file in files:
            if file['id'] == file_id:
                return file
        return None
    
    def _is_admin(self, user_id: int) -> bool:
        """بررسی ادمین بودن"""
        # در واقعیت باید از دیتابیس خوانده شود
        admins = [123456789, 987654321]  # آیدی ادمین‌ها
        return user_id in admins
    
    def start(self):
        """شروع ربات"""
        logger.info("🤖 ربات با محدودیت شروع به کار کرد...")
        self.bot.polling(none_stop=True)

# تابع اصلی
def main():
    """شروع ربات"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Telegram Bot with Limits')
    parser.add_argument('--token', required=True, help='Bot token from @BotFather')
    parser.add_argument('--config', default='config/bot_config.json', 
                       help='Config file path')
    
    args = parser.parse_args()
    
    # بارگذاری config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {args.config}")
        return
    
    # ایجاد و اجرای ربات
    bot = LimitedBot(args.token)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
