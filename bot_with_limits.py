#!/usr/bin/env python3
# bot_with_limits.py - ربات تلگرام پیشرفته با سیستم محدودیت کامل

import telebot
from telebot import types
import json
import time
import threading
import queue
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import asyncio
import sqlite3

# Import modules
try:
    from limits_manager import LimitsManager, LimitType
    HAS_LIMITS_MANAGER = True
except ImportError:
    HAS_LIMITS_MANAGER = False

# تنظیمات لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_limits.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DownloadTask:
    """کلاس وظیفه دانلود"""
    
    def __init__(self, user_id: int, file_id: str, file_info: dict):
        self.user_id = user_id
        self.file_id = file_id
        self.file_info = file_info
        self.status = 'pending'  # pending, downloading, completed, failed
        self.progress = 0
        self.start_time = None
        self.end_time = None
        self.speed = 0
        self.message_id = None

class PaymentSystem:
    """سیستم پرداخت و اشتراک"""
    
    def __init__(self):
        self.conn = sqlite3.connect('data/payments.db', check_same_thread=False)
        self.init_database()
    
    def init_database(self):
        cursor = self.conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tier TEXT,
            amount INTEGER,
            currency TEXT DEFAULT 'IRT',
            payment_method TEXT,
            transaction_id TEXT UNIQUE,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP,
            completed_at TIMESTAMP,
            expires_at TIMESTAMP
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            tier TEXT,
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            auto_renew BOOLEAN DEFAULT 1,
            payment_id INTEGER,
            FOREIGN KEY (payment_id) REFERENCES payments(id)
        )
        ''')
        self.conn.commit()
    
    def create_payment(self, user_id: int, tier: str, amount: int) -> Dict:
        """ایجاد درخواست پرداخت"""
        transaction_id = f"pay_{user_id}_{int(time.time())}"
        
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT INTO payments 
        (user_id, tier, amount, transaction_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, tier, amount, transaction_id, datetime.now().isoformat()))
        self.conn.commit()
        
        return {
            'payment_id': cursor.lastrowid,
            'transaction_id': transaction_id,
            'amount': amount,
            'tier': tier
        }
    
    def verify_payment(self, transaction_id: str) -> bool:
        """تأیید پرداخت"""
        cursor = self.conn.cursor()
        cursor.execute('''
        UPDATE payments 
        SET status = 'completed', completed_at = ?
        WHERE transaction_id = ? AND status = 'pending'
        ''', (datetime.now().isoformat(), transaction_id))
        
        if cursor.rowcount > 0:
            self.conn.commit()
            
            # ایجاد اشتراک
            cursor.execute('''
            SELECT user_id, tier FROM payments WHERE transaction_id = ?
            ''', (transaction_id,))
            result = cursor.fetchone()
            
            if result:
                user_id, tier = result
                self.create_subscription(user_id, tier)
            
            return True
        
        return False
    
    def create_subscription(self, user_id: int, tier: str):
        """ایجاد اشتراک"""
        start_date = datetime.now()
        
        if tier == 'premium':
            duration = timedelta(days=30)  # 30 روز
        elif tier == 'vip':
            duration = timedelta(days=30)
        else:
            return
        
        end_date = start_date + duration
        
        cursor = self.conn.cursor()
        cursor.execute('''
        INSERT OR REPLACE INTO subscriptions 
        (user_id, tier, start_date, end_date)
        VALUES (?, ?, ?, ?)
        ''', (user_id, tier, start_date.isoformat(), end_date.isoformat()))
        self.conn.commit()
    
    def get_user_subscription(self, user_id: int) -> Optional[Dict]:
        """دریافت اشتراک کاربر"""
        cursor = self.conn.cursor()
        cursor.execute('''
        SELECT tier, start_date, end_date, auto_renew
        FROM subscriptions 
        WHERE user_id = ? AND end_date > ?
        ''', (user_id, datetime.now().isoformat()))
        
        result = cursor.fetchone()
        if result:
            return {
                'tier': result[0],
                'start_date': result[1],
                'end_date': result[2],
                'auto_renew': bool(result[3]),
                'days_left': (datetime.fromisoformat(result[2]) - datetime.now()).days
            }
        return None

class AdvancedLimitedBot:
    """ربات پیشرفته با سیستم محدودیت کامل"""
    
    def __init__(self, token: str):
        self.bot = telebot.TeleBot(token)
        self.limits_manager = LimitsManager() if HAS_LIMITS_MANAGER else None
        self.payment_system = PaymentSystem()
        self.user_states: Dict[int, Dict] = {}
        self.download_tasks: Dict[int, List[DownloadTask]] = {}
        self.download_queue = queue.Queue()
        self.active_downloads: Dict[int, int] = {}  # user_id -> count
        
        # فایل‌های موجود
        self.available_files = self.load_available_files()
        
        # مدیران
        self.admins = self.load_admins()
        
        # آمار سیستم
        self.system_stats = {
            'total_downloads': 0,
            'total_users': 0,
            'total_size': 0,
            'start_time': datetime.now()
        }
        
        # شروع workerها
        self._start_download_workers(5)  # 5 worker همزمان
        self._start_maintenance_worker()
        self._start_notification_worker()
        
        # تنظیم هندلرها
        self.setup_handlers()
        
        logger.info("🤖 AdvancedLimitedBot initialized")
    
    def load_available_files(self) -> List[Dict]:
        """بارگذاری فایل‌های موجود"""
        files_file = Path("data/files.json")
        if files_file.exists():
            with open(files_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # فایل‌های پیش‌فرض
        files = [
            {
                'id': '1',
                'name': 'آموزش پایتون مقدماتی.pdf',
                'size_mb': 5,
                'category': 'آموزشی',
                'tags': ['پایتون', 'برنامه‌نویسی', 'آموزش'],
                'downloads': 0,
                'premium_only': False
            },
            {
                'id': '2',
                'name': 'کتاب طراحی رابط کاربری.mp4',
                'size_mb': 150,
                'category': 'آموزشی',
                'tags': ['UI/UX', 'طراحی', 'ویدیو'],
                'downloads': 0,
                'premium_only': True
            },
            {
                'id': '3',
                'name': 'مجموعه آهنگ‌های جدید ۱۴۰۳.zip',
                'size_mb': 250,
                'category': 'موزیک',
                'tags': ['آهنگ', 'ایرانی', 'جدید'],
                'downloads': 0,
                'premium_only': False
            },
            {
                'id': '4',
                'name': 'نرم‌افزار ادوبی فتوشاپ ۲۰۲۴.rar',
                'size_mb': 1800,
                'category': 'نرم‌افزار',
                'tags': ['فتوشاپ', 'گرافیک', 'ادوبی'],
                'downloads': 0,
                'premium_only': True
            },
            {
                'id': '5',
                'name': 'مقاله علمی هوش مصنوعی.docx',
                'size_mb': 3,
                'category': 'علمی',
                'tags': ['هوش مصنوعی', 'مقاله', 'تحقیق'],
                'downloads': 0,
                'premium_only': False
            }
        ]
        
        # ذخیره فایل‌ها
        files_file.parent.mkdir(exist_ok=True, parents=True)
        with open(files_file, 'w', encoding='utf-8') as f:
            json.dump(files, f, indent=2, ensure_ascii=False)
        
        return files
    
    def load_admins(self) -> List[int]:
        """بارگذاری لیست ادمین‌ها"""
        admins_file = Path("config/admins.json")
        if admins_file.exists():
            with open(admins_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return [123456789]  # آیدی پیش‌فرض
    
    def _start_download_workers(self, num_workers: int = 3):
        """شروع workerها برای مدیریت دانلود همزمان"""
        def download_worker(worker_id: int):
            logger.info(f"Download worker {worker_id} started")
            while True:
                try:
                    task = self.download_queue.get()
                    if task is None:  # سیگنال خاتمه
                        break
                    
                    user_id, file_id, file_info, message_id = task
                    
                    # پردازش دانلود
                    self._process_download_task(
                        user_id, file_id, file_info, message_id, worker_id
                    )
                    
                    self.download_queue.task_done()
                    
                except Exception as e:
                    logger.error(f"Download worker {worker_id} error: {e}")
        
        for i in range(num_workers):
            thread = threading.Thread(
                target=download_worker,
                args=(i,),
                daemon=True,
                name=f"DownloadWorker-{i}"
            )
            thread.start()
        
        logger.info(f"✅ Started {num_workers} download workers")
    
    def _start_maintenance_worker(self):
        """شروع worker نگهداری سیستم"""
        def maintenance_worker():
            while True:
                try:
                    time.sleep(3600)  # هر ساعت
                    self._perform_maintenance()
                except Exception as e:
                    logger.error(f"Maintenance worker error: {e}")
                    time.sleep(60)
        
        thread = threading.Thread(
            target=maintenance_worker,
            daemon=True,
            name="MaintenanceWorker"
        )
        thread.start()
        logger.info("✅ Maintenance worker started")
    
    def _start_notification_worker(self):
        """شروع worker اطلاع‌رسانی"""
        def notification_worker():
            while True:
                try:
                    time.sleep(300)  # هر 5 دقیقه
                    self._send_notifications()
                except Exception as e:
                    logger.error(f"Notification worker error: {e}")
                    time.sleep(60)
        
        thread = threading.Thread(
            target=notification_worker,
            daemon=True,
            name="NotificationWorker"
        )
        thread.start()
        logger.info("✅ Notification worker started")
    
    def _perform_maintenance(self):
        """انجام عملیات نگهداری"""
        try:
            # پاکسازی وضعیت‌های قدیمی
            current_time = time.time()
            users_to_remove = []
            
            for user_id, state in self.user_states.items():
                last_activity = state.get('last_activity', 0)
                if current_time - last_activity > 24 * 3600:  # 24 ساعت
                    users_to_remove.append(user_id)
            
            for user_id in users_to_remove:
                del self.user_states[user_id]
            
            if users_to_remove:
                logger.info(f"Cleaned {len(users_to_remove)} inactive users")
            
            # ذخیره آمار
            self._save_system_stats()
            
        except Exception as e:
            logger.error(f"Maintenance error: {e}")
    
    def _send_notifications(self):
        """ارسال اطلاعیه‌های دوره‌ای"""
        # اینجا می‌توان اطلاعیه‌های مختلف ارسال کرد
        pass
    
    def _save_system_stats(self):
        """ذخیره آمار سیستم"""
        stats_file = Path("data/system_stats.json")
        stats_file.parent.mkdir(exist_ok=True, parents=True)
        
        stats = {
            **self.system_stats,
            'uptime': str(datetime.now() - self.system_stats['start_time']),
            'active_users': len(self.user_states),
            'queue_size': self.download_queue.qsize(),
            'timestamp': datetime.now().isoformat()
        }
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False, default=str)
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات"""
        
        # Command handlers
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            self.handle_start(message)
        
        @self.bot.message_handler(commands=['help'])
        def help_handler(message):
            self.handle_help(message)
        
        @self.bot.message_handler(commands=['stats'])
        def stats_handler(message):
            self.handle_stats(message)
        
        @self.bot.message_handler(commands=['files'])
        def files_handler(message):
            self.handle_files(message)
        
        @self.bot.message_handler(commands=['admin'])
        def admin_handler(message):
            self.handle_admin(message)
        
        @self.bot.message_handler(commands=['upgrade'])
        def upgrade_handler(message):
            self.handle_upgrade(message)
        
        # Text message handlers
        @self.bot.message_handler(func=lambda m: m.text == '📥 دانلود فایل')
        def download_menu_handler(message):
            self.show_download_menu(message.chat.id)
        
        @self.bot.message_handler(func=lambda m: m.text == '📊 آمار من')
        def my_stats_handler(message):
            self.show_user_stats(message.chat.id)
        
        @self.bot.message_handler(func=lambda m: m.text == '💎 ارتقا حساب')
        def upgrade_menu_handler(message):
            self.show_upgrade_menu(message.chat.id)
        
        @self.bot.message_handler(func=lambda m: m.text == '📁 فایل‌های من')
        def my_files_handler(message):
            self.show_my_files(message.chat.id)
        
        @self.bot.message_handler(func=lambda m: m.text == '⚙️ تنظیمات')
        def settings_handler(message):
            self.show_settings(message.chat.id)
        
        @self.bot.message_handler(func=lambda m: m.text == '🏠 برگشت به منو')
        def back_to_menu_handler(message):
            self.show_main_menu(message.chat.id)
        
        # Callback query handlers
        @self.bot.callback_query_handler(func=lambda call: True)
        def callback_query_handler(call):
            self.handle_callback_query(call)
    
    def handle_start(self, message):
        """هندلر دستور /start"""
        user_id = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        
        # ثبت کاربر
        self._register_user(user_id, username)
        
        # ارسال خوشآمدگویی
        welcome_text = self._get_welcome_message(user_id)
        
        # ارسال عکس یا استیکر
        try:
            self.bot.send_sticker(
                message.chat.id,
                "CAACAgIAAxkBAAIBbWbXmXGqVPRBvN74tc5TZzG4LtWlAAJ8FgACr_ohSQw3-FXmPJ8vNAQ"
            )
        except:
            pass
        
        self.bot.send_message(
            message.chat.id,
            welcome_text,
            parse_mode='HTML',
            reply_markup=self._create_main_menu_keyboard(user_id)
        )
    
    def _register_user(self, user_id: int, username: str):
        """ثبت کاربر جدید"""
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                'username': username,
                'join_date': datetime.now().isoformat(),
                'total_downloads': 0,
                'total_size': 0,
                'last_activity': time.time(),
                'last_download': None,
                'favorite_files': [],
                'settings': {
                    'notifications': True,
                    'auto_delete': False,
                    'language': 'fa'
                }
            }
            
            if self.limits_manager:
                self.limits_manager.increment_global_usage(LimitType.USER_COUNT)
            
            self.system_stats['total_users'] += 1
            
            logger.info(f"New user registered: {user_id} ({username})")
    
    def _get_welcome_message(self, user_id: int) -> str:
        """دریافت پیام خوشآمدگویی"""
        subscription = self.payment_system.get_user_subscription(user_id)
        
        if subscription:
            tier = subscription['tier']
            days_left = subscription['days_left']
            
            if tier == 'premium':
                return (
                    f"✨ <b>خوش آمدید کاربر پریمیوم!</b>\n\n"
                    f"👤 شناسه: <code>{user_id}</code>\n"
                    f"💎 سطح: <b>پریمیوم</b>\n"
                    f"⏳ اعتبار: {days_left} روز باقیمانده\n\n"
                    f"✅ شما به تمام امکانات ویژه دسترسی دارید:\n"
                    f"• دانلود نامحدود\n• سرعت بالا\n• فایل‌های VIP\n• پشتیبانی ویژه\n\n"
                    f"از امکانات ربات لذت ببرید! 🚀"
                )
            elif tier == 'vip':
                return (
                    f"👑 <b>خوش آمدید کاربر VIP!</b>\n\n"
                    f"👤 شناسه: <code>{user_id}</code>\n"
                    f"💎 سطح: <b>VIP</b>\n"
                    f"⏳ اعتبار: {days_left} روز باقیمانده\n\n"
                    f"🎯 شما کاربر ویژه ما هستید:\n"
                    f"• دانلود نامحدود با سرعت بسیار بالا\n"
                    f"• دسترسی به تمام فایل‌ها\n"
                    f"• اولویت در صف دانلود\n"
                    f"• پشتیبانی VIP 24/7\n\n"
                    f"از اعتماد شما متشکریم! 💎"
                )
        
        # کاربر رایگان
        return (
            f"👋 <b>به ربات دانلود ما خوش آمدید!</b>\n\n"
            f"👤 شناسه: <code>{user_id}</code>\n"
            f"🎯 سطح: <b>رایگان</b>\n\n"
            f"📊 <b>امکانات حساب رایگان:</b>\n"
            f"• ۱۰ دانلود روزانه\n"
            f"• حداکثر ۵۰۰MB حجم فایل\n"
            f"• ۳ دانلود همزمان\n"
            f"• پشتیبانی پایه\n\n"
            f"💎 برای دسترسی به امکانات بیشتر، حساب خود را ارتقا دهید.\n"
            f"برای شروع از دکمه‌های زیر استفاده کنید:"
        )
    
    def _create_main_menu_keyboard(self, user_id: int):
        """ایجاد کیبورد منوی اصلی"""
        subscription = self.payment_system.get_user_subscription(user_id)
        tier = subscription['tier'] if subscription else 'free'
        
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        
        if tier == 'free':
            keyboard.row('📥 دانلود فایل (۱۰/روز)')
            keyboard.row('📊 آمار من', '💎 ارتقا حساب')
            keyboard.row('ℹ️ راهنما', '📞 پشتیبانی')
        elif tier == 'premium':
            keyboard.row('📥 دانلود فایل (۵۰/روز)')
            keyboard.row('📊 آمار من', '📁 فایل‌های من')
            keyboard.row('⚙️ تنظیمات', '📞 پشتیبانی')
            keyboard.row('🏆 وضعیت پریمیوم')
        else:  # vip
            keyboard.row('📥 دانلود فایل (نامحدود)')
            keyboard.row('📊 آمار من', '📁 فایل‌های من')
            keyboard.row('⚙️ تنظیمات', '👑 پنل VIP')
            keyboard.row('⭐ امتیاز من')
        
        return keyboard
    
    def handle_help(self, message):
        """هندلر دستور /help"""
        help_text = (
            "📚 <b>راهنمای ربات</b>\n\n"
            "• برای مشاهده لیست فایل‌ها از /files استفاده کنید\n"
            "• برای دانلود روی فایل مورد نظر کلیک کنید\n"
            "• برای مشاهده آمار از /stats استفاده کنید\n"
            "• برای ارتقا حساب از /upgrade استفاده کنید\n\n"
            "🎯 <b>دستورات اصلی:</b>\n"
            "/start - شروع ربات\n"
            "/help - این راهنما\n"
            "/stats - آمار کاربر\n"
            "/files - لیست فایل‌ها\n"
            "/admin - پنل مدیریت (فقط ادمین)\n\n"
            "📞 <b>پشتیبانی:</b>\n"
            "برای گزارش مشکل یا سوال با آیدی @support در ارتباط باشید."
        )
        
        self.bot.send_message(message.chat.id, help_text, parse_mode='HTML')
    
    def handle_stats(self, message):
        """هندلر دستور /stats"""
        self.show_user_stats(message.chat.id)
    
    def show_user_stats(self, chat_id: int):
        """نمایش آمار کاربر"""
        user_id = chat_id
        
        if user_id not in self.user_states:
            self.bot.send_message(chat_id, "⛔ شما ثبت‌نام نکرده‌اید. /start را بزنید.")
            return
        
        user_data = self.user_states[user_id]
        subscription = self.payment_system.get_user_subscription(user_id)
        
        # به‌روزرسانی آخرین فعالیت
        user_data['last_activity'] = time.time()
        
        # جمع‌آوری آمار
        stats_text = self._create_stats_text(user_id, user_data, subscription)
        
        # ایجاد keyboard اضافی
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("🔄 به‌روزرسانی آمار", callback_data="refresh_stats"),
            types.InlineKeyboardButton("📊 نمودارها", callback_data="show_charts")
        )
        
        if not subscription or subscription['tier'] == 'free':
            keyboard.add(types.InlineKeyboardButton(
                "💎 ارتقا حساب", callback_data="upgrade_from_stats"
            ))
        
        self.bot.send_message(
            chat_id,
            stats_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
    
    def _create_stats_text(self, user_id: int, user_data: Dict, subscription: Optional[Dict]) -> str:
        """ایجاد متن آمار"""
        tier = subscription['tier'] if subscription else 'free'
        days_joined = (datetime.now() - datetime.fromisoformat(user_data['join_date'])).days
        
        # محاسبه محدودیت‌ها
        limits_info = ""
        if self.limits_manager:
            for limit_type in [LimitType.DAILY_DOWNLOADS, LimitType.TOTAL_DOWNLOADS, 
                             LimitType.DOWNLOAD_SIZE, LimitType.CONCURRENT_DOWNLOADS]:
                result = self.limits_manager.check_user_limit(user_id, limit_type)
                if result:
                    limit_name = self._get_limit_name(limit_type)
                    limits_info += (
                        f"• {limit_name}: {result['used']}/{result['limit']} "
                        f"({result['remaining']} باقیمانده)\n"
                    )
        
        stats_text = (
            f"📊 <b>آمار حساب کاربری</b>\n\n"
            f"👤 شناسه: <code>{user_id}</code>\n"
            f"🏷️ سطح: <b>{tier.upper()}</b>\n"
            f"📅 عضو شده: {days_joined} روز پیش\n\n"
            f"📥 <b>آمار دانلود:</b>\n"
            f"• کل دانلود‌ها: {user_data['total_downloads']}\n"
            f"• کل حجم: {user_data['total_size'] / 1024:.2f} GB\n"
            f"• آخرین دانلود: {self._format_date(user_data.get('last_download'))}\n\n"
        )
        
        if limits_info:
            stats_text += f"🎯 <b>محدودیت‌ها:</b>\n{limits_info}\n"
        
        if subscription:
            stats_text += (
                f"💎 <b>اشتراک:</b>\n"
                f"• شروع: {self._format_date(subscription['start_date'])}\n"
                f"• پایان: {self._format_date(subscription['end_date'])}\n"
                f"• باقیمانده: {subscription['days_left']} روز\n"
            )
        
        stats_text += f"\n🕒 به‌روزرسانی: {datetime.now().strftime('%H:%M:%S')}"
        
        return stats_text
    
    def _get_limit_name(self, limit_type: LimitType) -> str:
        """نام فارسی محدودیت"""
        names = {
            LimitType.DAILY_DOWNLOADS: "📥 دانلود روزانه",
            LimitType.TOTAL_DOWNLOADS: "📦 کل دانلود‌ها",
            LimitType.DOWNLOAD_SIZE: "💾 حجم فایل",
            LimitType.CONCURRENT_DOWNLOADS: "⚡ دانلود همزمان",
            LimitType.BANDWIDTH: "🌐 پهنای باند",
            LimitType.API_REQUESTS: "🔁 درخواست‌ها"
        }
        return names.get(limit_type, limit_type.value)
    
    def _format_date(self, date_str: Optional[str]) -> str:
        """فرمت تاریخ"""
        if not date_str:
            return "ندارد"
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y/%m/%d %H:%M")
        except:
            return date_str
    
    def handle_files(self, message):
        """هندلر دستور /files"""
        self.show_download_menu(message.chat.id)
    
    def show_download_menu(self, chat_id: int):
        """نمایش منوی دانلود"""
        user_id = chat_id
        
        # بررسی محدودیت کاربران کل
        if self.limits_manager:
            global_limit = self.limits_manager.check_global_limit(LimitType.USER_COUNT)
            if not global_limit['allowed']:
                self.bot.send_message(
                    chat_id,
                    "⛔ ربات به حداکثر ظرفیت کاربران رسیده است.\n"
                    "لطفاً چند ساعت دیگر تلاش کنید.",
                    reply_markup=self._create_main_menu_keyboard(user_id)
                )
                return
        
        # فیلتر فایل‌ها بر اساس سطح کاربر
        subscription = self.payment_system.get_user_subscription(user_id)
        tier = subscription['tier'] if subscription else 'free'
        
        available_files = []
        for file in self.available_files:
            if not file.get('premium_only') or tier in ['premium', 'vip']:
                available_files.append(file)
        
        if not available_files:
            self.bot.send_message(
                chat_id,
                "📭 در حال حاضر فایلی برای دانلود موجود نیست.",
                reply_markup=self._create_main_menu_keyboard(user_id)
            )
            return
        
        # ایجاد keyboard برای فایل‌ها
        keyboard = types.InlineKeyboardMarkup(row_width=1)
        
        for file in available_files[:10]:  # فقط 10 فایل اول
            file_size = self._format_size(file['size_mb'] * 1024 * 1024)
            premium_tag = " 👑" if file.get('premium_only') else ""
            
            keyboard.add(types.InlineKeyboardButton(
                f"📁 {file['name']} ({file_size}){premium_tag}",
                callback_data=f"file_{file['id']}"
            ))
        
        # دکمه‌های اضافی
        keyboard.row(
            types.InlineKeyboardButton("🔍 جستجو", callback_data="search_files"),
            types.InlineKeyboardButton("📁 همه فایل‌ها", callback_data="all_files")
        )
        
        if tier == 'free':
            keyboard.row(types.InlineKeyboardButton(
                "💎 مشاهده فایل‌های پریمیوم", callback_data="premium_files"
            ))
        
        keyboard.row(types.InlineKeyboardButton(
            "🏠 برگشت به منو", callback_data="back_to_menu"
        ))
        
        self.bot.send_message(
            chat_id,
            f"📁 <b>لیست فایل‌ها</b>\n\n"
            f"🔍 تعداد فایل‌ها: {len(available_files)}\n"
            f"💎 سطح حساب: {tier.upper()}\n\n"
            f"برای دانلود روی فایل مورد نظر کلیک کنید:",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    
    def _format_size(self, bytes_count: int) -> str:
        """فرمت اندازه فایل"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_count < 1024:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.1f} TB"
    
    def handle_callback_query(self, call):
        """هندلر کلیک دکمه‌ها"""
        user_id = call.from_user.id
        data = call.data
        
        try:
            if data == "refresh_stats":
                self.refresh_stats(user_id, call.message.message_id)
            elif data == "show_charts":
                self.show_charts(user_id)
            elif data == "upgrade_from_stats":
                self.show_upgrade_menu(user_id)
            elif data == "search_files":
                self.ask_for_search(user_id)
            elif data == "all_files":
                self.show_all_files(user_id)
            elif data == "premium_files":
                self.show_premium_files(user_id)
            elif data == "back_to_menu":
                self.show_main_menu(user_id)
            elif data.startswith("file_"):
                file_id = data.replace("file_", "")
                self.handle_file_selection(user_id, file_id, call.message.message_id)
            elif data.startswith("download_"):
                file_id = data.replace("download_", "")
                self.start_download(user_id, file_id, call.id)
            elif data.startswith("cancel_"):
                task_id = data.replace("cancel_", "")
                self.cancel_download(user_id, task_id, call.id)
            elif data == "admin_stats":
                self.show_admin_stats(user_id)
            elif data == "admin_users":
                self.show_admin_users(user_id)
            elif data == "admin_limits":
                self.show_admin_limits(user_id)
            elif data == "admin_system":
                self.show_admin_system(user_id)
            elif data.startswith("upgrade_"):
                tier = data.replace("upgrade_", "")
                self.process_upgrade(user_id, tier, call.id)
            
            # پاسخ به کلیک
            self.bot.answer_callback_query(call.id)
            
        except Exception as e:
            logger.error(f"Callback error: {e}")
            self.bot.answer_callback_query(call.id, "❌ خطا در پردازش درخواست")
    
    def handle_file_selection(self, user_id: int, file_id: str, message_id: int):
        """هندلر انتخاب فایل"""
        file_info = self._get_file_info(file_id)
        if not file_info:
            self.bot.send_message(user_id, "❌ فایل مورد نظر یافت نشد.")
            return
        
        # بررسی محدودیت‌ها
        if self.limits_manager:
            # بررسی حجم فایل
            size_check = self.limits_manager.check_user_limit(
                user_id, LimitType.DOWNLOAD_SIZE, file_info['size_mb']
            )
            
            if not size_check['allowed']:
                self.bot.send_message(
                    user_id,
                    f"⛔ حجم فایل بیشتر از محدودیت شما است.\n"
                    f"📊 محدودیت شما: {size_check['limit']}MB\n"
                    f"📁 حجم فایل: {file_info['size_mb']}MB\n\n"
                    f"💎 برای دانلود فایل‌های بزرگتر، حساب خود را ارتقا دهید."
                )
                return
            
            # بررسی دانلود روزانه
            daily_check = self.limits_manager.check_user_limit(
                user_id, LimitType.DAILY_DOWNLOADS
            )
            
            if not daily_check['allowed']:
                self.bot.send_message(
                    user_id,
                    f"⛔ محدودیت دانلود روزانه شما تکمیل شده است.\n"
                    f"📊 استفاده شده: {daily_check['used']}/{daily_check['limit']}\n"
                    f"⏰ ریست: {daily_check['next_reset'] or 'فردا'}\n\n"
                    f"💎 برای دانلود بیشتر، حساب خود را ارتقا دهید."
                )
                return
        
        # نمایش اطلاعات فایل با دکمه دانلود
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                f"📥 دانلود ({file_info['size_mb']}MB)",
                callback_data=f"download_{file_id}"
            ),
            types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_files")
        )
        
        file_text = (
            f"📁 <b>اطلاعات فایل</b>\n\n"
            f"📝 نام: {file_info['name']}\n"
            f"💾 حجم: {file_info['size_mb']} MB\n"
            f"🏷️ دسته‌بندی: {file_info['category']}\n"
            f"🏆 سطح: {'پریمیوم 👑' if file_info.get('premium_only') else 'همه کاربران'}\n"
            f"📊 دانلود شده: {file_info.get('downloads', 0)} بار\n\n"
            f"📌 برچسب‌ها: {' '.join([f'#{tag}' for tag in file_info.get('tags', [])])}\n\n"
        )
        
        if self.limits_manager:
            daily_check = self.limits_manager.check_user_limit(
                user_id, LimitType.DAILY_DOWNLOADS
            )
            file_text += f"📥 دانلود امروز: {daily_check['used']}/{daily_check['limit']}\n"
        
        self.bot.edit_message_text(
            file_text,
            chat_id=user_id,
            message_id=message_id,
            parse_mode='HTML',
            reply_markup=keyboard
        )
    
    def start_download(self, user_id: int, file_id: str, callback_id: str):
        """شروع دانلود"""
        file_info = self._get_file_info(file_id)
        if not file_info:
            self.bot.answer_callback_query(callback_id, "❌ فایل یافت نشد")
            return
        
        # بررسی محدودیت‌ها نهایی
        if self.limits_manager:
            checks = [
                (LimitType.DAILY_DOWNLOADS, 1, "محدودیت دانلود روزانه"),
                (LimitType.TOTAL_DOWNLOADS, 1, "محدودیت کل دانلود"),
                (LimitType.DOWNLOAD_SIZE, file_info['size_mb'], "محدودیت حجم فایل"),
                (LimitType.CONCURRENT_DOWNLOADS, 1, "محدودیت دانلود همزمان"),
            ]
            
            for limit_type, value, message in checks:
                check_result = self.limits_manager.check_user_limit(user_id, limit_type, value)
                if not check_result['allowed']:
                    self.bot.answer_callback_query(
                        callback_id,
                        f"⛔ {message}: {check_result['used']}/{check_result['limit']}"
                    )
                    return
        
        # ارسال پیام شروع دانلود
        msg = self.bot.send_message(
            user_id,
            f"⏳ <b>در حال شروع دانلود...</b>\n\n"
            f"📁 فایل: {file_info['name']}\n"
            f"💾 حجم: {file_info['size_mb']} MB\n"
            f"📊 موقعیت در صف: {self.download_queue.qsize() + 1}\n\n"
            f"لطفاً منتظر بمانید...",
            parse_mode='HTML'
        )
        
        # اضافه کردن به صف
        self.download_queue.put((user_id, file_id, file_info, msg.message_id))
        
        # افزایش محدودیت‌ها
        if self.limits_manager:
            self.limits_manager.increment_user_usage(user_id, LimitType.DAILY_DOWNLOADS)
            self.limits_manager.increment_user_usage(user_id, LimitType.TOTAL_DOWNLOADS)
            self.limits_manager.increment_user_usage(user_id, LimitType.DOWNLOAD_SIZE, file_info['size_mb'])
            self.limits_manager.increment_user_usage(user_id, LimitType.CONCURRENT_DOWNLOADS)
        
        # به‌روزرسانی آمار فایل
        file_info['downloads'] = file_info.get('downloads', 0) + 1
        self._save_available_files()
        
        # به‌روزرسانی آمار کاربر
        if user_id in self.user_states:
            self.user_states[user_id]['total_downloads'] += 1
            self.user_states[user_id]['total_size'] += file_info['size_mb'] * 1024 * 1024
            self.user_states[user_id]['last_download'] = datetime.now().isoformat()
            self.user_states[user_id]['last_activity'] = time.time()
        
        # به‌روزرسانی آمار سیستم
        self.system_stats['total_downloads'] += 1
        self.system_stats['total_size'] += file_info['size_mb']
        
        self.bot.answer_callback_query(callback_id, "✅ در صف دانلود قرار گرفت")
    
    def _process_download_task(self, user_id: int, file_id: str, 
                             file_info: dict, message_id: int, worker_id: int):
        """پردازش دانلود"""
        try:
            # به‌روزرسانی وضعیت
            self.bot.edit_message_text(
                f"⏬ <b>در حال دانلود...</b>\n\n"
                f"📁 فایل: {file_info['name']}\n"
                f"💾 حجم: {file_info['size_mb']} MB\n"
                f"👷‍♂️ Worker: #{worker_id + 1}\n\n"
                f"🔄 در حال اتصال...",
                chat_id=user_id,
                message_id=message_id,
                parse_mode='HTML'
            )
            
            # شبیه‌سازی دانلود
            total_size = file_info['size_mb'] * 1024 * 1024  # به بایت
            chunk_size = 1024 * 1024  # 1MB
            downloaded = 0
            
            # زمان‌سنج
            start_time = time.time()
            
            while downloaded < total_size:
                # محاسبه پیشرفت
                progress = (downloaded / total_size) * 100
                elapsed = time.time() - start_time
                speed = downloaded / elapsed if elapsed > 0 else 0
                eta = (total_size - downloaded) / speed if speed > 0 else 0
                
                # ایجاد progress bar
                progress_bar = self._create_progress_bar(progress)
                
                # به‌روزرسانی پیام
                if int(progress) % 10 == 0 or downloaded == 0:  # هر 10٪
                    self.bot.edit_message_text(
                        f"⏬ <b>در حال دانلود...</b>\n\n"
                        f"📁 فایل: {file_info['name']}\n"
                        f"💾 حجم: {self._format_size(downloaded)} / {self._format_size(total_size)}\n"
                        f"📊 پیشرفت: {progress:.1f}%\n"
                        f"{progress_bar}\n\n"
                        f"⚡ سرعت: {self._format_size(speed)}/s\n"
                        f"⏱️ زمان: {int(elapsed)}s / ETA: {int(eta)}s\n"
                        f"👷‍♂️ Worker: #{worker_id + 1}",
                        chat_id=user_id,
                        message_id=message_id,
                        parse_mode='HTML'
                    )
                
                # شبیه‌سازی دانلود
                chunk = min(chunk_size, total_size - downloaded)
                downloaded += chunk
                
                # تأخیر برای شبیه‌سازی
                time.sleep(0.05)  # سرعت 20MB/s
            
            # تکمیل دانلود
            elapsed = time.time() - start_time
            avg_speed = total_size / elapsed if elapsed > 0 else 0
            
            # ایجاد فایل شبیه‌سازی شده (در واقعیت فایل دانلود می‌شود)
            # و ارسال آن به کاربر
            
            self.bot.edit_message_text(
                f"✅ <b>دانلود تکمیل شد!</b>\n\n"
                f"📁 فایل: {file_info['name']}\n"
                f"💾 حجم: {self._format_size(total_size)}\n"
                f"⏱️ زمان: {elapsed:.1f} ثانیه\n"
                f"⚡ سرعت متوسط: {self._format_size(avg_speed)}/s\n\n"
                f"🎉 فایل با موفقیت دانلود شد.\n"
                f"برای دانلود مجدد از منوی اصلی استفاده کنید.",
                chat_id=user_id,
                message_id=message_id,
                parse_mode='HTML'
            )
            
            # کاهش محدودیت دانلود همزمان
            if self.limits_manager:
                self.limits_manager.increment_user_usage(
                    user_id, LimitType.CONCURRENT_DOWNLOADS, -1
                )
            
            logger.info(f"Download completed: user={user_id}, file={file_info['name']}")
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            
            # برگرداندن محدودیت‌ها در صورت خطا
            if self.limits_manager:
                self.limits_manager.increment_user_usage(user_id, LimitType.DAILY_DOWNLOADS, -1)
                self.limits_manager.increment_user_usage(user_id, LimitType.TOTAL_DOWNLOADS, -1)
                self.limits_manager.increment_user_usage(user_id, LimitType.DOWNLOAD_SIZE, -file_info['size_mb'])
                self.limits_manager.increment_user_usage(user_id, LimitType.CONCURRENT_DOWNLOADS, -1)
            
            self.bot.edit_message_text(
                f"❌ <b>خطا در دانلود</b>\n\n"
                f"📁 فایل: {file_info['name']}\n"
                f"💾 حجم: {file_info['size_mb']} MB\n\n"
                f"خطا: {str(e)[:100]}\n\n"
                f"لطفاً دوباره تلاش کنید.",
                chat_id=user_id,
                message_id=message_id,
                parse_mode='HTML'
            )
    
    def _create_progress_bar(self, percentage: float, length: int = 20) -> str:
        """ایجاد progress bar"""
        filled = int(length * percentage / 100)
        bar = '█' * filled + '░' * (length - filled)
        return f"[{bar}]"
    
    def handle_admin(self, message):
        """هندلر دستور /admin"""
        user_id = message.from_user.id
        
        if user_id not in self.admins:
            self.bot.send_message(user_id, "⛔ دسترسی denied!")
            return
        
        self.show_admin_panel(user_id)
    
    def show_admin_panel(self, user_id: int):
        """نمایش پنل مدیریت"""
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        keyboard.add(
            types.InlineKeyboardButton("📊 آمار سیستم", callback_data="admin_stats"),
            types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users")
        )
        
        keyboard.add(
            types.InlineKeyboardButton("⚙️ محدودیت‌ها", callback_data="admin_limits"),
            types.InlineKeyboardButton("💻 وضعیت سیستم", callback_data="admin_system")
        )
        
        keyboard.add(
            types.InlineKeyboardButton("📁 مدیریت فایل‌ها", callback_data="admin_files"),
            types.InlineKeyboardButton("💰 مالی", callback_data="admin_finance")
        )
        
        keyboard.add(
            types.InlineKeyboardButton("📈 گزارش‌ها", callback_data="admin_reports"),
            types.InlineKeyboardButton("🚫 بن کاربران", callback_data="admin_ban")
        )
        
        self.bot.send_message(
            user_id,
            "👨‍💼 <b>پنل مدیریت</b>\n\n"
            "لطفاً بخش مورد نظر را انتخاب کنید:",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    
    def show_admin_stats(self, user_id: int):
        """نمایش آمار سیستم"""
        uptime = datetime.now() - self.system_stats['start_time']
        
        # جمع‌آوری آمار
        stats_text = (
            f"📊 <b>آمار کلی سیستم</b>\n\n"
            f"⏰ آپتایم: {str(uptime).split('.')[0]}\n"
            f"👥 کاربران: {self.system_stats['total_users']}\n"
            f"📥 کل دانلود‌ها: {self.system_stats['total_downloads']}\n"
            f"💾 کل حجم: {self.system_stats['total_size'] / 1024:.2f} GB\n"
            f"📁 فایل‌ها: {len(self.available_files)}\n\n"
            f"⚙️ <b>وضعیت فعلی:</b>\n"
            f"• کاربران آنلاین: {len([u for u, d in self.user_states.items() 
                                   if time.time() - d['last_activity'] < 300])}\n"
            f"• دانلود فعال: {sum(self.active_downloads.values())}\n"
            f"• صف دانلود: {self.download_queue.qsize()}\n"
            f"• حافظه: {self._get_memory_usage():.1f} MB\n\n"
            f"🕒 به‌روزرسانی: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # آمار tier
        # (در نسخه کامل از دیتابیس خوانده می‌شود)
        
        self.bot.send_message(user_id, stats_text, parse_mode='HTML')
    
    def _get_memory_usage(self) -> float:
        """دریافت میزان استفاده از حافظه"""
        import os
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024  # MB
    
    def handle_upgrade(self, message):
        """هندلر دستور /upgrade"""
        self.show_upgrade_menu(message.chat.id)
    
    def show_upgrade_menu(self, chat_id: int):
        """نمایش منوی ارتقا"""
        user_id = chat_id
        subscription = self.payment_system.get_user_subscription(user_id)
        
        if subscription:
            current_tier = subscription['tier']
            days_left = subscription['days_left']
            
            self.bot.send_message(
                chat_id,
                f"💎 <b>وضعیت اشتراک شما</b>\n\n"
                f"🏷️ سطح فعلی: <b>{current_tier.upper()}</b>\n"
                f"⏳ اعتبار: {days_left} روز باقیمانده\n"
                f"📅 پایان: {self._format_date(subscription['end_date'])}\n\n"
                f"برای تمدید یا ارتقا، گزینه مورد نظر را انتخاب کنید:",
                parse_mode='HTML',
                reply_markup=self._create_upgrade_keyboard(current_tier)
            )
        else:
            self.bot.send_message(
                chat_id,
                "💎 <b>ارتقا حساب کاربری</b>\n\n"
                "در حال حاضر شما از حساب <b>رایگان</b> استفاده می‌کنید.\n"
                "با ارتقا حساب، به امکانات ویژه دسترسی پیدا کنید:",
                parse_mode='HTML',
                reply_markup=self._create_upgrade_keyboard('free')
            )
    
    def _create_upgrade_keyboard(self, current_tier: str) -> types.InlineKeyboardMarkup:
        """ایجاد کیبورد ارتقا"""
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        
        if current_tier == 'free':
            keyboard.add(
                types.InlineKeyboardButton(
                    "💎 پریمیوم - ماهانه ۵۰ هزار تومان",
                    callback_data="upgrade_premium"
                ),
                types.InlineKeyboardButton(
                    "👑 VIP - ماهانه ۱۵۰ هزار تومان",
                    callback_data="upgrade_vip"
                )
            )
        elif current_tier == 'premium':
            keyboard.add(
                types.InlineKeyboardButton(
                    "🔄 تمدید پریمیوم - ۵۰ هزار تومان",
                    callback_data="renew_premium"
                ),
                types.InlineKeyboardButton(
                    "⬆️ ارتقا به VIP - ۱۰۰ هزار تومان",
                    callback_data="upgrade_to_vip"
                )
            )
        elif current_tier == 'vip':
            keyboard.add(
                types.InlineKeyboardButton(
                    "🔄 تمدید VIP - ۱۵۰ هزار تومان",
                    callback_data="renew_vip"
                )
            )
        
        keyboard.add(
            types.InlineKeyboardButton("ℹ️ مقایسه پلن‌ها", callback_data="compare_plans"),
            types.InlineKeyboardButton("🏠 برگشت", callback_data="back_to_menu")
        )
        
        return keyboard
    
    def process_upgrade(self, user_id: int, tier: str, callback_id: str):
        """پردازش درخواست ارتقا"""
        # تعیین قیمت
        prices = {
            'premium': 50000,
            'vip': 150000,
            'renew_premium': 50000,
            'renew_vip': 150000,
            'upgrade_to_vip': 100000  # ارتقا از پریمیوم به VIP
        }
        
        if tier not in prices:
            self.bot.answer_callback_query(callback_id, "❌ گزینه نامعتبر")
            return
        
        amount = prices[tier]
        
        # ایجاد درخواست پرداخت
        payment = self.payment_system.create_payment(user_id, tier, amount)
        
        # نمایش اطلاعات پرداخت
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "💳 پرداخت آنلاین",
                url=f"https://payment.example.com/pay/{payment['transaction_id']}"
            ),
            types.InlineKeyboardButton(
                "✅ تایید پرداخت",
                callback_data=f"verify_{payment['transaction_id']}"
            )
        )
        
        self.bot.send_message(
            user_id,
            f"💰 <b>صورتحساب پرداخت</b>\n\n"
            f"🏷️ پلن: <b>{tier.upper()}</b>\n"
            f"💵 مبلغ: {amount:,} تومان\n"
            f"📋 شماره تراکنش: <code>{payment['transaction_id']}</code>\n\n"
            f"برای پرداخت روی دکمه زیر کلیک کنید:\n"
            f"پس از پرداخت، روی 'تایید پرداخت' کلیک کنید.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        
        self.bot.answer_callback_query(callback_id, "✅ درخواست پرداخت ایجاد شد")
    
    def _get_file_info(self, file_id: str) -> Optional[Dict]:
        """دریافت اطلاعات فایل"""
        for file in self.available_files:
            if file['id'] == file_id:
                return file
        return None
    
    def _save_available_files(self):
        """ذخیره لیست فایل‌ها"""
        files_file = Path("data/files.json")
        with open(files_file, 'w', encoding='utf-8') as f:
            json.dump(self.available_files, f, indent=2, ensure_ascii=False)
    
    def show_main_menu(self, chat_id: int):
        """نمایش منوی اصلی"""
        user_id = chat_id
        welcome_text = self._get_welcome_message(user_id)
        
        self.bot.send_message(
            chat_id,
            welcome_text,
            parse_mode='HTML',
            reply_markup=self._create_main_menu_keyboard(user_id)
        )
    
    def start(self):
        """شروع ربات"""
        logger.info("🚀 ربات با محدودیت شروع به کار کرد...")
        
        try:
            self.bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            time.sleep(5)
            self.start()  # تلاش مجدد

def main():
    """تابع اصلی اجرا"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Advanced Telegram Bot with Limits System')
    parser.add_argument('--token', required=True, help='Telegram Bot Token from @BotFather')
    parser.add_argument('--config', default='config/bot_config.json', help='Config file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    # تنظیم سطح لاگ
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("Debug mode enabled")
    
    # بارگذاری config
    config_path = Path(args.config)
    if not config_path.exists():
        logger.warning(f"Config file not found: {args.config}, using defaults")
    
    # ایجاد دایرکتوری‌ها
    Path("data").mkdir(exist_ok=True)
    Path("config").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    
    # ایجاد و اجرای ربات
    try:
        bot = AdvancedLimitedBot(args.token)
        logger.info("🤖 Bot instance created successfully")
        bot.start()
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
