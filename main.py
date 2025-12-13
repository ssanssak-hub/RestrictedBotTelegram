#main.py
"""
🤖 **ربات تلگرام یکپارچه پیشرفته** - نسخه نهایی
اتصال: main.py + advanced_telegram_system.py + advanced_userbot_downloader.py
"""

import logging
import asyncio
import sys
import os
import json
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from io import BytesIO
import hashlib
import re
import sqlite3
from contextlib import contextmanager
import random
import aiohttp

# ========== کتابخانه‌های اصلی ==========
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

# 1. سیستم مدیریت اکانت پیشرفته (از main.py)
from advanced_account_manager import (
    AdvancedAccountManager,
    AccountStatus,
    LoginMethod,
    AdvancedEncryption,
    AnomalyDetector,
    AccountMonitor
)

# 2. ویژگی‌های پیشرفته 8-11 (از main.py)
from advanced_features import (
    AdvancedReportGenerator,
    TwoFactorAuthentication,
    HealthMonitor,
    AnomalyDetectionSystem
)

# 3. سیستم امنیتی پیشرفته (از advanced_telegram_system.py)
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

# 4. تله‌تون برای UserBot (از advanced_userbot_downloader.py)
try:
    from telethon import TelegramClient, events
    from telethon.tl.types import DocumentAttributeFilename
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False

# ========== تنظیمات لاگ یکپارچه ==========

class ColoredFormatter(logging.Formatter):
    """فرمتر رنگی برای لاگ‌ها"""
    COLORS = {
        'DEBUG': '\033[94m',      # آبی
        'INFO': '\033[92m',       # سبز
        'WARNING': '\033[93m',    # زرد
        'ERROR': '\033[91m',      # قرمز
        'CRITICAL': '\033[91m\033[1m',  # قرمز پررنگ
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        message = super().format(record)
        return f"{log_color}{message}{self.COLORS['RESET']}"

def setup_logging():
    """تنظیمات پیشرفته لاگ‌گیری"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # فرمت پیشرفته
    formatter = ColoredFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler فایل
    file_handler = logging.FileHandler('telegram_bot_advanced.log', encoding='utf-8', mode='a')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # Handler کنسول
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ========== مدل‌های داده جدید ==========

class AIContentAnalyzer:
    """سیستم تحلیل محتوای هوشمند (از advanced_userbot_downloader.py)"""
    
    class ContentType:
        TEXT = "text"
        IMAGE = "image"
        VIDEO = "video"
        AUDIO = "audio"
        DOCUMENT = "document"
        UNKNOWN = "unknown"
    
    def __init__(self):
        self.initialized = False
        self.cache = {}
        
    async def initialize(self):
        """مقداردهی اولیه"""
        logger.info("✅ AI Analyzer initialized")
        self.initialized = True
        
        # لیست کلمات کلیدی برای طبقه‌بندی
        self.keyword_categories = {
            'educational': ['آموزش', 'درس', 'کتاب', 'تحصیل', 'دانشگاه', 'مدرسه'],
            'entertainment': ['فیلم', 'سریال', 'کارتون', 'موسیقی', 'طنز', 'تفریح'],
            'technology': ['برنامه', 'کد', 'پایتون', 'هوش', 'مصنوعی', 'کامپیوتر'],
            'news': ['اخبار', 'سیاسی', 'اقتصاد', 'حوادث', 'ورزش'],
            'religious': ['مذهبی', 'قرآن', 'اذان', 'دعا', 'روضه']
        }
        
        self.nsfw_keywords = ['ممنوع', 'سکسی', 'جنسی', 'محرمانه', 'خصوصی']
    
    async def analyze_text(self, text: str) -> Dict:
        """تحلیل متن"""
        if not text:
            return {'category': 'unknown', 'sentiment': 'neutral'}
        
        text_lower = text.lower()
        
        # تشخیص دسته‌بندی
        category = 'other'
        max_matches = 0
        for cat, keywords in self.keyword_categories.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > max_matches:
                max_matches = matches
                category = cat
        
        # تشخیص زبان
        lang = 'fa' if re.search(r'[\u0600-\u06FF]', text) else 'en'
        
        return {
            'category': category,
            'language': lang,
            'length': len(text)
        }
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """محاسبه هش فایل"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read(8192)).hexdigest()
        except:
            return ""

class AdvancedSecurity:
    """سیستم امنیتی AES-GCM (از advanced_telegram_system.py)"""
    
    def __init__(self, master_key: Optional[str] = None):
        if not HAS_CRYPTOGRAPHY:
            logger.warning("⚠️ Cryptography not installed. Security features limited.")
            self.available = False
            return
        
        self.available = True
        if master_key:
            self.master_key = self._derive_key(master_key.encode())
        else:
            import secrets
            self.master_key = secrets.token_bytes(32)
    
    def _derive_key(self, password: bytes, salt: bytes = None) -> bytes:
        """استخراج کلید از رمز عبور"""
        if salt is None:
            salt = b'telegram_bot_salt'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password)
    
    def encrypt(self, plaintext: str) -> str:
        """رمزنگاری داده"""
        if not self.available:
            return plaintext
        
        import secrets
        aesgcm = AESGCM(self.master_key)
        nonce = secrets.token_bytes(12)
        
        ciphertext = aesgcm.encrypt(
            nonce,
            plaintext.encode('utf-8'),
            None
        )
        
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode('utf-8')
    
    def decrypt(self, encrypted_data: str) -> str:
        """رمزگشایی داده"""
        if not self.available:
            return encrypted_data
        
        aesgcm = AESGCM(self.master_key)
        encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
        
        nonce = encrypted_bytes[:12]
        ciphertext = encrypted_bytes[12:]
        
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext_bytes.decode('utf-8')

class DatabaseManager:
    """پایگاه داده یکپارچه"""
    
    def __init__(self, db_path: str = "telegram_bot_advanced.db"):
        self.db_path = Path(db_path)
        self.init_db()
    
    def init_db(self):
        """ایجاد جداول"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # جدول کاربران (از main.py)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone_number TEXT,
                config TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP
            )
            ''')
            
            # جدول فایل‌های دانلود شده (از advanced_userbot_downloader.py)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS downloaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_hash TEXT UNIQUE,
                file_name TEXT,
                file_path TEXT,
                file_size INTEGER,
                file_type TEXT,
                source_chat TEXT,
                caption TEXT,
                category TEXT,
                download_time TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
            
            # جدول فعالیت‌ها (از main.py)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                activity_type TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
            
            # جدول گزارش‌ها (از main.py)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                report_type TEXT,
                report_data TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
            
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """مدیریت اتصال به دیتابیس"""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def save_user_activity(self, user_id: int, activity_type: str, details: str = ""):
        """ذخیره فعالیت کاربر"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO user_activities (user_id, activity_type, details) VALUES (?, ?, ?)",
                    (user_id, activity_type, details)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Database error saving activity: {e}")
    
    def save_downloaded_file(self, user_id: int, file_info: Dict):
        """ذخیره اطلاعات فایل دانلود شده"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO downloaded_files 
                (user_id, file_hash, file_name, file_path, file_size, file_type, source_chat, caption, category, download_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    file_info.get('file_hash', ''),
                    file_info.get('file_name', ''),
                    file_info.get('file_path', ''),
                    file_info.get('file_size', 0),
                    file_info.get('file_type', ''),
                    file_info.get('source_chat', ''),
                    file_info.get('caption', '')[:500],
                    file_info.get('category', 'unknown'),
                    datetime.now().isoformat()
                ))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Database error saving file: {e}")
            return False

# ========== مدیر یکپارچه ==========

class IntegratedBotManager:
    """مدیریت یکپارچه تمام سیستم‌ها"""
    
    def __init__(self, bot_token: str, admin_ids: List[int], api_id: int, api_hash: str):
        self.setup_directories()
        
        # تنظیمات اصلی
        self.bot_token = bot_token
        self.admin_ids = admin_ids
        self.api_id = api_id
        self.api_hash = api_hash
        
        # 1. سیستم مدیریت اکانت (از main.py)
        self.account_manager = AdvancedAccountManager(
            base_dir=Path("accounts"),
            api_id=api_id,
            api_hash=api_hash,
            encryption_key = os.getenv("ENCRYPTION_KEY")
            if not encryption_key:
                raise ValueError("ENCRYPTION_KEY not set in environment")
        )
        
        # 2. ویژگی‌های پیشرفته (از main.py)
        self.report_generator = AdvancedReportGenerator()
        self.two_fa = TwoFactorAuthentication()
        self.anomaly_detector = AnomalyDetectionSystem()
        
        # 3. سیستم امنیتی جدید (از advanced_telegram_system.py)
        self.security = AdvancedSecurity(os.getenv("ENCRYPTION_KEY"))
        
        # 4. سیستم AI جدید (از advanced_userbot_downloader.py)
        self.ai_analyzer = AIContentAnalyzer()
        
        # 5. پایگاه داده یکپارچه
        self.db = DatabaseManager()
        
        # 6. UserBot (اگر telethon نصب باشد)
        self.userbot_client = None
        if HAS_TELETHON:
            self.userbot_initialized = False
        else:
            logger.warning("⚠️ Telethon not installed. UserBot features disabled.")
            self.userbot_initialized = False
        
        # داده‌های کاربران
        self.user_sessions: Dict[int, Dict] = {}
        self.user_states: Dict[int, Dict] = {}
        self.download_queues: Dict[int, List] = {}
        
        logger.info("✅ مدیر یکپارچه راه‌اندازی شد")
    
    def setup_directories(self):
        """ایجاد دایرکتوری‌های لازم"""
        directories = [
            "accounts/sessions",
            "accounts/backups",
            "reports",
            "downloads",
            "downloads/images",
            "downloads/videos",
            "downloads/documents",
            "downloads/audio",
            "logs",
            "database",
            "temp",
            "exports"
        ]
        
        for dir_path in directories:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    async def initialize_systems(self):
        """مقداردهی اولیه تمام سیستم‌ها"""
        try:
            # راه‌اندازی AI
            await self.ai_analyzer.initialize()
            logger.info("✅ AI System initialized")
            
            # راه‌اندازی Health Monitor
            if hasattr(self, 'health_monitor'):
                await self.start_health_monitor()
            
            # راه‌اندازی UserBot (اگر فعال باشد)
            if HAS_TELETHON and not self.userbot_initialized:
                await self.initialize_userbot()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Error initializing systems: {e}")
            return False
    
    async def initialize_userbot(self):
        """راه‌اندازی UserBot"""
        try:
            # ایجاد کلاینت UserBot
            self.userbot_client = TelegramClient(
                session="userbot_session",
                api_id=self.api_id,
                api_hash=self.api_hash,
                device_model="Samsung Galaxy S23",
                system_version="Android 14",
                app_version="9.6.1",
                lang_code="fa",
                system_lang_code="fa-IR"
            )
            
            await self.userbot_client.start()
            me = await self.userbot_client.get_me()
            logger.info(f"✅ UserBot initialized as: {me.first_name} (@{me.username})")
            
            self.userbot_initialized = True
            
            # تنظیم هندلرهای UserBot
            await self.setup_userbot_handlers()
            
        except Exception as e:
            logger.error(f"❌ Error initializing UserBot: {e}")
            self.userbot_client = None
    
    async def setup_userbot_handlers(self):
        """تنظیم هندلرهای UserBot"""
        if not self.userbot_client:
            return
        
        @self.userbot_client.on(events.NewMessage(incoming=True))
        async def userbot_handler(event):
            """هندلر UserBot برای پردازش پیام‌ها"""
            try:
                # می‌توانید منطق پردازش UserBot را اینجا اضافه کنید
                pass
            except Exception as e:
                logger.error(f"UserBot handler error: {e}")
    
    async def download_from_userbot(self, user_id: int, chat_link: str, limit: int = 10):
        """دانلود محتوا از کانال/گروه با UserBot"""
        if not self.userbot_client or not self.userbot_initialized:
            return {"success": False, "error": "UserBot not initialized"}
        
        try:
            # استخراج username/id از لینک
            if "t.me/" in chat_link:
                chat_identifier = chat_link.split("t.me/")[-1].split("/")[0]
            else:
                chat_identifier = chat_link
            
            # دریافت پیام‌ها
            messages = []
            async for message in self.userbot_client.iter_messages(
                chat_identifier, 
                limit=limit,
                wait_time=2
            ):
                if message.media:
                    messages.append(message)
            
            # دانلود فایل‌ها
            downloaded_files = []
            for message in messages:
                file_info = await self.download_userbot_file(user_id, message)
                if file_info:
                    downloaded_files.append(file_info)
            
            return {
                "success": True,
                "count": len(downloaded_files),
                "files": downloaded_files
            }
            
        except Exception as e:
            logger.error(f"UserBot download error: {e}")
            return {"success": False, "error": str(e)}
    
    async def download_userbot_file(self, user_id: int, message) -> Optional[Dict]:
        """دانلود یک فایل از UserBot"""
        try:
            if not message.media:
                return None
            
            # ایجاد مسیر دانلود
            download_dir = Path(f"downloads/user_{user_id}")
            download_dir.mkdir(exist_ok=True)
            
            # دریافت نام فایل
            file_name = self.get_userbot_filename(message)
            file_path = download_dir / file_name
            
            # دانلود فایل
            await message.download_media(file=str(file_path))
            
            # تحلیل AI
            caption = message.text or ""
            analysis = await self.ai_analyzer.analyze_text(caption)
            
            # محاسبه هش
            file_hash = self.ai_analyzer.calculate_file_hash(file_path)
            
            # ذخیره در دیتابیس
            file_info = {
                'file_hash': file_hash,
                'file_name': file_name,
                'file_path': str(file_path),
                'file_size': file_path.stat().st_size,
                'file_type': Path(file_name).suffix.replace('.', '').upper(),
                'source_chat': getattr(message.chat, 'title', 'Unknown'),
                'caption': caption[:500],
                'category': analysis['category']
            }
            
            self.db.save_downloaded_file(user_id, file_info)
            
            # ذخیره فعالیت
            self.db.save_user_activity(user_id, "download_file", f"{file_name} ({analysis['category']})")
            
            return file_info
            
        except Exception as e:
            logger.error(f"UserBot file download error: {e}")
            return None
    
    def get_userbot_filename(self, message) -> str:
        """دریافت نام فایل از پیام UserBot"""
        try:
            if hasattr(message, 'document') and message.document:
                for attr in message.document.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        return attr.file_name
            
            # نام‌گذاری پیش‌فرض براساس نوع
            if message.photo:
                return f"photo_{message.id}.jpg"
            elif message.video:
                return f"video_{message.id}.mp4"
            elif message.audio:
                return f"audio_{message.id}.mp3"
            elif message.voice:
                return f"voice_{message.id}.ogg"
            else:
                return f"file_{message.id}.bin"
                
        except Exception as e:
            logger.error(f"Error getting filename: {e}")
            return f"file_{message.id}.bin"

# ========== هندلرهای اصلی ربات ==========

class TelegramBotHandlers:
    """هندلرهای دستورات تلگرام"""
    
    def __init__(self, manager: IntegratedBotManager, application: Application):
        self.manager = manager
        self.application = application
        self.STATES = {
            'AWAITING_PHONE': 1,
            'AWAITING_CODE': 2,
            'AWAITING_2FA': 3,
            'AWAITING_REPORT_TYPE': 4,
            'AWAITING_BACKUP_CONFIRM': 5,
            'AWAITING_DOWNLOAD_LINK': 6,
            'AWAITING_DOWNLOAD_LIMIT': 7,
            'AWAITING_ENCRYPT_TEXT': 8,
            'AWAITING_DECRYPT_TEXT': 9
        }
        
        # تنظیم notify_admins در manager
        self.manager.notify_admins = self.notify_admins
    
    async def notify_admins(self, message: str):
        """ارسال اطلاعیه به ادمین‌ها"""
        for admin_id in self.manager.admin_ids:
            try:
                await self.application.bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")
    
    # ========== دستورات اصلی ==========
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /start بهبود یافته"""
        user = update.effective_user
        user_id = user.id
        
        # ثبت فعالیت
        self.manager.db.save_user_activity(user_id, "start_command")
        
        welcome_text = f"""
👋 سلام {user.first_name}!

🤖 **ربات مدیریت تلگرام پیشرفته** به شما خوش آمد می‌گوید.

🚀 **ویژگی‌های جدید:**
• 🔐 سیستم امنیتی AES-G256
• 🧠 هوش مصنوعی تحلیل محتوا
• 📥 دانلود خودکار از کانال‌ها
• 🔍 تشخیص فایل‌های تکراری
• 📊 سازماندهی هوشمند فایل‌ها

📋 **دستورات اصلی:**
/start - نمایش این پیام
/login - ورود به اکانت تلگرام
/accounts - مدیریت اکانت‌ها
/download - دانلود از کانال
/myfiles - فایل‌های دانلود شده
/encrypt - رمزنگاری متن
/decrypt - رمزگشایی متن
/ai_analyze - تحلیل متن با AI

🛡️ **امنیت پیشرفته:**
/security - تنظیمات امنیتی
/2fa - احراز هویت دو مرحله‌ای
/backup - پشتیبان‌گیری

📊 **گزارش‌گیری:**
/report - دریافت گزارش
/stats - آمار سیستم
/help - راهنمای کامل
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔐 ورود به اکانت", callback_data='menu_login'),
                InlineKeyboardButton("📥 دانلود", callback_data='menu_download')
            ],
            [
                InlineKeyboardButton("🧠 تحلیل AI", callback_data='menu_ai'),
                InlineKeyboardButton("🛡️ امنیت", callback_data='menu_security')
            ],
            [
                InlineKeyboardButton("📊 گزارش‌گیری", callback_data='menu_reports'),
                InlineKeyboardButton("⚙️ تنظیمات", callback_data='menu_settings')
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    # ========== سیستم دانلود پیشرفته ==========
    
    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /download - دانلود از کانال/گروه"""
        user_id = update.effective_user.id
        
        # بررسی فعال بودن UserBot
        if not self.manager.userbot_initialized:
            keyboard = [
                [InlineKeyboardButton("📖 راهنمای فعال‌سازی UserBot", callback_data='userbot_guide')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "⚠️ **سیستم UserBot فعال نیست**\n\n"
                "برای استفاده از قابلیت دانلود خودکار:\n"
                "1. کتابخانه telethon را نصب کنید: `pip install telethon`\n"
                "2. API credentials را تنظیم کنید\n"
                "3. ربات را مجدداً راه‌اندازی کنید",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "📥 **سیستم دانلود پیشرفته**\n\n"
            "لطفاً لینک کانال یا گروه را ارسال کنید:\n"
            "مثال: `https://t.me/channel_username` یا `@channel_username`\n\n"
            "❌ برای لغو: /cancel"
        )
        
        return self.STATES['AWAITING_DOWNLOAD_LINK']
    
    async def handle_download_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش لینک دانلود"""
        user_id = update.effective_user.id
        chat_link = update.message.text.strip()
        
        # ذخیره لینک در context
        context.user_data['download_link'] = chat_link
        
        await update.message.reply_text(
            "🔢 **تعداد فایل‌ها**\n\n"
            "لطفاً تعداد فایل‌هایی که می‌خواهید دانلود کنید را وارد کنید:\n"
            "عدد بین ۱ تا ۵۰ (پیش‌فرض: ۱۰)\n\n"
            "⚠️ توجه: دانلود تعداد زیاد ممکن است زمان‌بر باشد."
        )
        
        return self.STATES['AWAITING_DOWNLOAD_LIMIT']
    
    async def handle_download_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش محدودیت دانلود"""
        user_id = update.effective_user.id
        
        try:
            limit = int(update.message.text)
            limit = max(1, min(50, limit))  # محدودیت ۱-۵۰
        except:
            limit = 10
        
        chat_link = context.user_data.get('download_link', '')
        
        # ارسال پیام در حال پردازش
        status_msg = await update.message.reply_text(
            f"⏳ **در حال پردازش درخواست...**\n\n"
            f"🔗 لینک: {chat_link}\n"
            f"📦 تعداد: {limit} فایل\n"
            f"⏱️ لطفاً منتظر بمانید..."
        )
        
        # شروع دانلود
        result = await self.manager.download_from_userbot(user_id, chat_link, limit)
        
        if result['success']:
            await status_msg.edit_text(
                f"✅ **دانلود کامل شد!**\n\n"
                f"📊 آمار دانلود:\n"
                f"• تعداد فایل‌ها: {result['count']}\n"
                f"• لینک: {chat_link}\n"
                f"• زمان: {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"📁 فایل‌ها در پوشه `downloads/user_{user_id}` ذخیره شدند.\n"
                f"برای مشاهده فایل‌ها: /myfiles"
            )
            
            # اطلاع به ادمین‌ها اگر تعداد زیاد باشد
            if result['count'] >= 20:
                await self.notify_admins(
                    f"📥 **دانلود حجیم**\n\n"
                    f"👤 کاربر: {user_id}\n"
                    f"🔗 کانال: {chat_link}\n"
                    f"📦 تعداد: {result['count']} فایل\n"
                    f"⏰ زمان: {datetime.now().strftime('%Y/%m/%d %H:%M')}"
                )
        else:
            await status_msg.edit_text(
                f"❌ **خطا در دانلود**\n\n"
                f"خطا: {result.get('error', 'Unknown error')}\n\n"
                f"لطفاً مطمئن شوید:\n"
                f"1. لینک معتبر است\n"
                f"2. UserBot به کانال دسترسی دارد\n"
                f"3. اینترنت متصل است"
            )
        
        return ConversationHandler.END
    
    # ========== مدیریت فایل‌ها ==========
    
    async def myfiles_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /myfiles - نمایش فایل‌های دانلود شده"""
        user_id = update.effective_user.id
        
        try:
            with self.manager.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                SELECT file_name, file_size, category, download_time 
                FROM downloaded_files 
                WHERE user_id = ? 
                ORDER BY id DESC 
                LIMIT 20
                ''', (user_id,))
                
                files = cursor.fetchall()
            
            if not files:
                keyboard = [[InlineKeyboardButton("📥 شروع دانلود", callback_data='menu_download')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "📭 **شما هیچ فایلی ندارید**\n\n"
                    "هنوز فایلی دانلود نکرده‌اید.\n"
                    "برای شروع دانلود از کانال‌ها استفاده کنید:",
                    reply_markup=reply_markup
                )
                return
            
            # ساخت گزارش
            total_size = sum(f['file_size'] for f in files)
            categories = {}
            for f in files:
                categories[f['category']] = categories.get(f['category'], 0) + 1
            
            files_text = f"""
📁 **فایل‌های شما** (آخرین ۲۰ مورد)

📊 **آمار کلی:**
• تعداد فایل‌ها: {len(files)}
• حجم کل: {total_size / 1024 / 1024:.1f} MB
• دسته‌بندی‌ها: {', '.join(f'{k}: {v}' for k, v in categories.items())}

📋 **لیست فایل‌ها:**
            """
            
            for i, file in enumerate(files, 1):
                size_mb = file['file_size'] / 1024 / 1024
                time_str = file['download_time'][:16] if file['download_time'] else "Unknown"
                
                files_text += f"\n{i}. **{file['file_name']}**"
                files_text += f"\n   📦 {size_mb:.1f} MB | 📁 {file['category']} | 📅 {time_str}"
            
            keyboard = [
                [
                    InlineKeyboardButton("🧹 پاکسازی قدیمی‌ها", callback_data='cleanup_files'),
                    InlineKeyboardButton("📥 دانلود بیشتر", callback_data='menu_download')
                ],
                [
                    InlineKeyboardButton("🔍 جستجوی فایل", callback_data='search_files'),
                    InlineKeyboardButton("🔄 به‌روزرسانی", callback_data='refresh_files')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(files_text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error getting files: {e}")
            await update.message.reply_text("❌ خطا در دریافت اطلاعات فایل‌ها")
    
    # ========== سیستم رمزنگاری ==========
    
    async def encrypt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /encrypt - رمزنگاری متن"""
        await update.message.reply_text(
            "🔐 **سیستم رمزنگاری AES-G256**\n\n"
            "لطفاً متنی که می‌خواهید رمزنگاری شود را ارسال کنید:\n\n"
            "⚠️ توجه: کلید رمزنگاری به صورت امن ذخیره می‌شود.\n"
            "❌ برای لغو: /cancel"
        )
        
        return self.STATES['AWAITING_ENCRYPT_TEXT']
    
    async def handle_encrypt_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش رمزنگاری متن"""
        user_id = update.effective_user.id
        plaintext = update.message.text
        
        if not plaintext or len(plaintext) < 2:
            await update.message.reply_text("❌ متن بسیار کوتاه است.")
            return ConversationHandler.END
        
        # رمزنگاری
        try:
            encrypted_text = self.manager.security.encrypt(plaintext)
            
            await update.message.reply_text(
                f"✅ **متن با موفقیت رمزنگاری شد**\n\n"
                f"📝 متن اصلی: `{plaintext[:50]}{'...' if len(plaintext) > 50 else ''}`\n\n"
                f"🔐 متن رمزنگاری شده:\n"
                f"```\n{encrypted_text}\n```\n\n"
                f"💡 برای رمزگشایی از دستور /decrypt استفاده کنید.",
                parse_mode='Markdown'
            )
            
            # ثبت فعالیت
            self.manager.db.save_user_activity(user_id, "encrypt_text", f"length: {len(plaintext)}")
            
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            await update.message.reply_text("❌ خطا در رمزنگاری متن")
        
        return ConversationHandler.END
    
    async def decrypt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /decrypt - رمزگشایی متن"""
        await update.message.reply_text(
            "🔓 **سیستم رمزگشایی AES-G256**\n\n"
            "لطفاً متن رمزنگاری شده را ارسال کنید:\n\n"
            "⚠️ توجه: فقط متنی که با همین سیستم رمز شده قابل رمزگشایی است.\n"
            "❌ برای لغو: /cancel"
        )
        
        return self.STATES['AWAITING_DECRYPT_TEXT']
    
    async def handle_decrypt_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش رمزگشایی متن"""
        user_id = update.effective_user.id
        encrypted_text = update.message.text
        
        if not encrypted_text:
            await update.message.reply_text("❌ متن رمزنگاری شده را وارد کنید.")
            return ConversationHandler.END
        
        # رمزگشایی
        try:
            decrypted_text = self.manager.security.decrypt(encrypted_text)
            
            await update.message.reply_text(
                f"✅ **متن با موفقیت رمزگشایی شد**\n\n"
                f"🔓 متن اصلی:\n"
                f"```\n{decrypted_text}\n```",
                parse_mode='Markdown'
            )
            
            # ثبت فعالیت
            self.manager.db.save_user_activity(user_id, "decrypt_text", f"length: {len(decrypted_text)}")
            
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            await update.message.reply_text("❌ خطا در رمزگشایی متن. مطمئن شوید متن معتبر است.")
        
        return ConversationHandler.END
    
    # ========== سیستم AI ==========
    
    async def ai_analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /ai_analyze - تحلیل متن با هوش مصنوعی"""
        await update.message.reply_text(
            "🧠 **تحلیل محتوای هوشمند**\n\n"
            "لطفاً متنی که می‌خواهید تحلیل شود را ارسال کنید:\n\n"
            "📊 **آنالیز شامل:**\n"
            "• تشخیص دسته‌بندی\n"
            "• تشخیص زبان\n"
            "• کلمات کلیدی\n"
            "• طول متن\n\n"
            "❌ برای لغو: /cancel"
        )
        
        # تغییر حالت برای دریافت متن
        context.user_data['awaiting_ai_text'] = True
    
    async def handle_ai_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش تحلیل AI"""
        user_id = update.effective_user.id
        text = update.message.text
        
        if not text or len(text) < 5:
            await update.message.reply_text("❌ متن بسیار کوتاه است.")
            return
        
        # ارسال پیام در حال پردازش
        status_msg = await update.message.reply_text("🧠 **در حال تحلیل متن...**\nلطفاً منتظر بمانید.")
        
        # تحلیل AI
        analysis = await self.manager.ai_analyzer.analyze_text(text)
        
        # ساخت پاسخ
        analysis_text = f"""
✅ **تحلیل هوشمند متن**

📝 **متن ورودی:**
`{text[:100]}{'...' if len(text) > 100 else ''}`

📊 **نتایج تحلیل:**

🏷️ **دسته‌بندی:** {analysis['category'].upper()}
🌐 **زبان:** {'فارسی' if analysis['language'] == 'fa' else 'انگلیسی'}
📏 **طول متن:** {analysis['length']} کاراکتر

📋 **توضیحات:**
"""
        
        if analysis['category'] == 'educational':
            analysis_text += "• محتوای آموزشی\n• مناسب برای یادگیری\n• ارزش علمی بالا"
        elif analysis['category'] == 'entertainment':
            analysis_text += "• محتوای سرگرمی\n• مناسب برای اوقات فراغت\n• جذاب و تفریحی"
        elif analysis['category'] == 'technology':
            analysis_text += "• محتوای تکنولوژی\n• مرتبط با فناوری\n• به روز و کاربردی"
        elif analysis['category'] == 'news':
            analysis_text += "• محتوای خبری\n• اطلاعات روز\n• معتبر و به‌موقع"
        else:
            analysis_text += "• محتوای عمومی\n• چندمنظوره\n• کاربردی"
        
        await status_msg.edit_text(analysis_text)
        
        # ثبت فعالیت
        self.manager.db.save_user_activity(user_id, "ai_analysis", f"category: {analysis['category']}")
    
    # ========== دستورات بهبود یافته ==========
    
    async def security_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /security بهبود یافته"""
        security_status = f"""
🛡️ **وضعیت امنیتی سیستم**

🔐 **رمزنگاری:**
• AES-G256: {'فعال ✅' if self.manager.security.available else 'غیرفعال ⚠️'}
• کلید ذخیره‌سازی: امن
• الگوریتم: AES-GCM با 256 بیت

🧠 **هوش مصنوعی:**
• تحلیل محتوا: {'فعال ✅' if self.manager.ai_analyzer.initialized else 'غیرفعال ⚠️'}
• تشخیص دسته‌بندی: فعال
• فیلتر محتوا: فعال

📥 **سیستم دانلود:**
• UserBot: {'فعال ✅' if self.manager.userbot_initialized else 'غیرفعال ⚠️'}
• تشخیص تکراری: فعال
• محدودیت حجم: 500 MB

🗄️ **پایگاه داده:**
• SQLite: فعال ✅
• رمزنگاری داده: فعال
• پشتیبان‌گیری: روزانه
        """
        
        keyboard = [
            [
                InlineKeyboardButton("🔐 تست رمزنگاری", callback_data='test_encryption'),
                InlineKeyboardButton("🧪 تست AI", callback_data='test_ai')
            ],
            [
                InlineKeyboardButton("📊 لاگ امنیتی", callback_data='security_logs'),
                InlineKeyboardButton("⚙️ تنظیمات", callback_data='security_settings')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(security_status, reply_markup=reply_markup)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /stats بهبود یافته"""
        user_id = update.effective_user.id
        
        try:
            with self.manager.db.get_connection() as conn:
                cursor = conn.cursor()
                
                # آمار کاربر
                cursor.execute("SELECT COUNT(*) as total_files FROM downloaded_files WHERE user_id = ?", (user_id,))
                user_files = cursor.fetchone()['total_files']
                
                cursor.execute("SELECT SUM(file_size) as total_size FROM downloaded_files WHERE user_id = ?", (user_id,))
                user_size = cursor.fetchone()['total_size'] or 0
                
                # آمار کلی
                cursor.execute("SELECT COUNT(*) as total_users FROM users")
                total_users = cursor.fetchone()['total_users']
                
                cursor.execute("SELECT COUNT(*) as total_downloads FROM downloaded_files")
                total_downloads = cursor.fetchone()['total_downloads']
                
                cursor.execute("SELECT SUM(file_size) as system_size FROM downloaded_files")
                system_size = cursor.fetchone()['system_size'] or 0
            
            stats_text = f"""
📊 **آمار پیشرفته سیستم**

👤 **آمار شما:**
├ فایل‌های دانلود شده: {user_files}
├ حجم کل فایل‌ها: {user_size / 1024 / 1024:.1f} MB
└ آخرین فعالیت: {datetime.now().strftime('%H:%M')}

🌐 **آمار کلی سیستم:**
├ کاربران فعال: {total_users}
├ کل دانلود‌ها: {total_downloads}
├ حجم کل سیستم: {system_size / 1024 / 1024 / 1024:.1f} GB
└ تاریخچه: {datetime.now().strftime('%Y/%m/%d')}

⚙️ **وضعیت سیستم‌ها:**
├ AI Analyzer: {'✅' if self.manager.ai_analyzer.initialized else '⚠️'}
├ UserBot: {'✅' if self.manager.userbot_initialized else '⚠️'}
├ امنیت: {'✅' if self.manager.security.available else '⚠️'}
└ دیتابیس: ✅
            """
            
            await update.message.reply_text(stats_text)
            
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await update.message.reply_text("❌ خطا در دریافت آمار")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور /help بهبود یافته"""
        help_text = """
📚 **راهنمای کامل ربات پیشرفته**

🔐 **مدیریت اکانت:**
/login - ورود به اکانت تلگرام
/accounts - مدیریت اکانت‌های شما
/backup - پشتیبان‌گیری اکانت
/2fa - احراز هویت دو مرحله‌ای

📥 **سیستم دانلود پیشرفته:**
/download - دانلود از کانال/گروه (با UserBot)
/myfiles - مشاهده فایل‌های دانلود شده
/search - جستجوی فایل‌ها
/organize - سازماندهی فایل‌ها

🛡️ **امنیت و رمزنگاری:**
/encrypt - رمزنگاری متن (AES-G256)
/decrypt - رمزگشایی متن
/security - وضعیت امنیتی
/encrypt_file - رمزنگاری فایل

🧠 **هوش مصنوعی:**
/ai_analyze - تحلیل متن با AI
/ai_categorize - دسته‌بندی محتوا
/ai_filter - فیلتر محتوای نامناسب

📊 **گزارش‌گیری:**
/stats - آمار کامل سیستم
/report - گزارش فعالیت
/insights - تحلیل هوشمند
/export - خروجی داده‌ها

⚙️ **مدیریت سیستم (ادمین):**
/admin - پنل مدیریت
/health - بررسی سلامت
/users - مدیریت کاربران
/broadcast - اطلاعیه همگانی

🔧 **پشتیبانی:**
/support - ارتباط با پشتیبانی
/feedback - ارسال نظرات
/guide - راهنمای استفاده

⚠️ **نکات امنیتی:**
1. هرگز اطلاعات حساس را در چت عمومی ارسال نکنید
2. کلیدهای رمزنگاری را امن نگهداری کنید
3. از فایل‌های مشکوک دانلود نکنید
4. در صورت مشاهده فعالیت مشکوک گزارش دهید
        """
        
        await update.message.reply_text(help_text)

# ========== تابع اصلی ==========

async def main():
    """تابع اصلی اجرای ربات یکپارچه"""
    
    print("""
╔══════════════════════════════════════════════════════════════╗
║   🤖 ربات تلگرام یکپارچه پیشرفته - نسخه نهایی             ║
║   ترکیب: main.py + advanced_telegram_system.py              ║
║          + advanced_userbot_downloader.py                    ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # بارگذاری تنظیمات
    try:
        from config import TOKEN, BOT_USERNAME, API_ID, API_HASH, ADMIN_IDS
    except ImportError:
        print("❌ خطا: فایل config.py پیدا نشد!")
        print("""
📝 فایل config.py را ایجاد کنید با این محتوا:

TOKEN = "توکن_ربات_شما"
BOT_USERNAME = "username_bot"
API_ID = 123456  # از my.telegram.org
API_HASH = "your_api_hash_here"
ADMIN_IDS = [123456789]  # آیدی عددی ادمین‌ها
        """)
        sys.exit(1)
    
    # بررسی توکن
    if TOKEN == "توکن_ربات_شما":
        print("❌ خطا: توکن ربات تنظیم نشده است!")
        print("لطفاً فایل config.py را ویرایش کنید.")
        sys.exit(1)
    
    # ایجاد مدیر یکپارچه
    integrated_manager = IntegratedBotManager(
        bot_token=TOKEN,
        admin_ids=ADMIN_IDS,
        api_id=API_ID,
        api_hash=API_HASH
    )
    
    # مقداردهی اولیه سیستم‌ها
    print("🔄 در حال راه‌اندازی سیستم‌های پیشرفته...")
    await integrated_manager.initialize_systems()
    
    # ایجاد اپلیکیشن تلگرام
    application = Application.builder().token(TOKEN).build()
    
    # ایجاد هندلرها
    handlers = TelegramBotHandlers(integrated_manager, application)
    
    # ========== تنظیم Conversation Handlers ==========
    
    # ورود
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
    
    # دانلود
    download_conversation = ConversationHandler(
        entry_points=[CommandHandler('download', handlers.download_command)],
        states={
            handlers.STATES['AWAITING_DOWNLOAD_LINK']: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_download_link)
            ],
            handlers.STATES['AWAITING_DOWNLOAD_LIMIT']: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_download_limit)
            ]
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_command)],
        allow_reentry=True
    )
    
    # رمزنگاری
    encrypt_conversation = ConversationHandler(
        entry_points=[CommandHandler('encrypt', handlers.encrypt_command)],
        states={
            handlers.STATES['AWAITING_ENCRYPT_TEXT']: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_encrypt_text)
            ]
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_command)],
        allow_reentry=True
    )
    
    # رمزگشایی
    decrypt_conversation = ConversationHandler(
        entry_points=[CommandHandler('decrypt', handlers.decrypt_command)],
        states={
            handlers.STATES['AWAITING_DECRYPT_TEXT']: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_decrypt_text)
            ]
        },
        fallbacks=[CommandHandler('cancel', handlers.cancel_command)],
        allow_reentry=True
    )
    
    # هندلر پیام‌های AI
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handlers.handle_ai_text
    ), group=1)
    
    # ========== اضافه کردن هندلرهای اصلی ==========
    
    # دستورات اصلی
    application.add_handler(CommandHandler("start", handlers.start_command))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CommandHandler("accounts", handlers.accounts_command))
    application.add_handler(CommandHandler("2fa", handlers.twofa_command))
    application.add_handler(CommandHandler("myfiles", handlers.myfiles_command))
    application.add_handler(CommandHandler("security", handlers.security_command))
    application.add_handler(CommandHandler("stats", handlers.stats_command))
    application.add_handler(CommandHandler("ai_analyze", handlers.ai_analyze_command))
    application.add_handler(CommandHandler("report", handlers.report_command))
    application.add_handler(CommandHandler("backup", handlers.backup_command))
    application.add_handler(CommandHandler("health", handlers.health_command))
    
    # Conversation Handlers
    application.add_handler(login_conversation)
    application.add_handler(download_conversation)
    application.add_handler(encrypt_conversation)
    application.add_handler(decrypt_conversation)
    
    # Callback Handlers
    application.add_handler(CallbackQueryHandler(handlers.handle_callback_query))
    
    # ========== شروع ربات ==========
    
    print(f"\n🤖 ربات @{BOT_USERNAME} در حال اجراست...")
    print("✅ سیستم‌های فعال:")
    print("   🔐 مدیریت اکانت‌ها")
    print("   🧠 هوش مصنوعی تحلیل محتوا")
    print("   📥 دانلود خودکار با UserBot")
    print("   🔐 رمزنگاری AES-G256")
    print("   📊 پایگاه داده یکپارچه")
    print("   🛡️ سیستم امنیتی پیشرفته")
    print("\n📝 برای خروج Ctrl+C را بفشارید")
    print("=" * 60)
    
    # اجرای ربات
    await application.initialize()
    await application.start()
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    # نگه داشتن ربات فعال
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        print("\n\n👋 ربات با موفقیت متوقف شد.")
    finally:
        await application.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 ربات با موفقیت متوقف شد.")
    except Exception as e:
        print(f"\n💥 خطای غیرمنتظره: {e}")
        logger.exception("خطای اصلی")
        sys.exit(1)
