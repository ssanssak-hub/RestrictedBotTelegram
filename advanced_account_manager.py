#advanced_account_manager.py
#!/usr/bin/env python3
"""
🔐 سیستم مدیریت پیشرفته اکانت تلگرام
ویژگی‌ها:
1. رمزنگاری AES-256 برای sessions و داده‌های حساس
2. سیستم چند اکانتی با load balancing
3. تشخیص ناهنجاری و امنیت پیشرفته
4. API REST برای مدیریت اکانت‌ها
5. مانیتورینگ real-time و alerting
6. Backup خودکار و recovery
7. پشتیبانی از proxy و TOR
8. Webhook برای رویدادها
"""

import asyncio
import json
import logging
import sys
import signal
import secrets
import hashlib
import base64
import re
import getpass
import sqlite3
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from enum import Enum
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import pickle
import zlib

# ========== کتابخانه‌های ضروری ==========
try:
    
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes, hmac
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    print("⚠️ برای رمزنگاری پیشرفته: pip install cryptography")

try:
    from telethon import TelegramClient, functions, types
    from telethon.sessions import SQLiteSession, StringSession
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
        FloodWaitError,
        AuthKeyDuplicatedError,
        PhoneCodeExpiredError,
        ApiIdInvalidError
    )
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False
    print("❌ Telethon ضروری است: pip install telethon")

try:
    import aiohttp
    from aiohttp import web
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    print("⚠️ برای API سرور: pip install aiohttp")
    
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    print("⚠️ برای مانیتورینگ: pip install psutil")

# ========== تنظیمات لاگ پیشرفته ==========

class ColorFormatter(logging.Formatter):
    """فرمت رنگی برای لاگ‌ها"""
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[41m',
        'RESET': '\033[0m'
    }
    
    def format(self, record):
        log_message = super().format(record)
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        return f"{color}{log_message}{self.COLORS['RESET']}"

def setup_logging(debug: bool = False):
    """تنظیم سیستم لاگ‌گیری"""
    log_level = logging.DEBUG if debug else logging.INFO
    
    # ایجاد دایرکتوری logs
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # فرمت لاگ
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    color_formatter = ColorFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    handlers = []
    
    # Console handler با رنگ
    console = logging.StreamHandler()
    console.setFormatter(color_formatter)
    handlers.append(console)
    
    # File handler
    file_handler = logging.FileHandler(
        log_dir / f"account_manager_{datetime.now().strftime('%Y%m%d')}.log",
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)
    
    # Error file handler
    error_handler = logging.FileHandler(
        log_dir / "errors.log",
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    handlers.append(error_handler)
    
    # تنظیم root logger
    logging.basicConfig(
        level=log_level,
        handlers=handlers,
        force=True
    )
    
    # تنظیم سطح لاگ برای کتابخانه‌های دیگر
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

logger = setup_logging()

# ========== مدل‌های داده ==========

class AccountStatus(Enum):
    """وضعیت اکانت"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"
    FLOOD_WAIT = "flood_wait"
    NEED_VERIFICATION = "need_verification"
    EXPIRED = "expired"

class LoginMethod(Enum):
    """روش ورود"""
    PHONE_CODE = "phone_code"
    PASSWORD = "password"
    QR_CODE = "qr_code"
    BOT_TOKEN = "bot_token"

@dataclass
class AccountInfo:
    """اطلاعات کامل اکانت"""
    account_id: str
    session_name: str
    user_id: int
    username: Optional[str]
    first_name: str
    last_name: Optional[str]
    phone: str
    phone_hash: str
    is_bot: bool = False
    is_premium: bool = False
    status: AccountStatus = AccountStatus.ACTIVE
    login_method: LoginMethod = LoginMethod.PHONE_CODE
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    total_messages: int = 0
    total_downloads: int = 0
    security_score: int = 100  # امتیاز امنیتی 0-100
    
    def to_dict(self) -> Dict:
        """تبدیل به دیکشنری"""
        data = asdict(self)
        data['status'] = self.status.value
        data['login_method'] = self.login_method.value
        data['created_at'] = self.created_at.isoformat()
        data['last_login'] = self.last_login.isoformat() if self.last_login else None
        data['last_activity'] = self.last_activity.isoformat() if self.last_activity else None
        return data

@dataclass
class LoginAttempt:
    """لاگ تلاش ورود"""
    attempt_id: str
    phone: str
    timestamp: datetime
    success: bool
    method: LoginMethod
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    error_message: Optional[str] = None
    response_time: Optional[float] = None

# ========== سیستم رمزنگاری پیشرفته ==========

class AdvancedEncryption:
    """سیستم رمزنگاری پیشرفته با چند لایه امنیتی"""
    
    def __init__(self, master_key: Optional[str] = None):
        if not HAS_CRYPTOGRAPHY:
            raise ImportError("کتابخانه cryptography ضروری است")
        
        if master_key:
            # استفاده از کلید اصلی
            self.master_key = self._derive_key(master_key.encode(), b'telegram_master_salt')
        else:
            # تولید کلید تصادفی
            self.master_key = secrets.token_bytes(32)
        
        # کلیدهای مختلف برای اهداف مختلف
        self.session_key = self._derive_key(self.master_key, b'session_encryption')
        self.data_key = self._derive_key(self.master_key, b'data_encryption')
        self.auth_key = self._derive_key(self.master_key, b'auth_hmac')
        
        # ایجاد cipherها
        self.session_cipher = AESGCM(self.session_key)
        self.data_cipher = AESGCM(self.data_key)
        
        logger.info("سیستم رمزنگاری پیشرفته راه‌اندازی شد")
    
    def _derive_key(self, password: bytes, salt: bytes, iterations: int = 100000) -> bytes:
        """استخراج کلید با PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=iterations
        )
        return kdf.derive(password)
    
    def encrypt_session(self, session_data: bytes) -> Dict[str, str]:
        """رمزنگاری session با احراز هویت"""
        nonce = secrets.token_bytes(12)
        
        # رمزنگاری
        ciphertext = self.session_cipher.encrypt(
            nonce,
            session_data,
            associated_data=b'session_encryption'
        )
        
        # HMAC برای احراز هویت
        h = hmac.HMAC(self.auth_key, hashes.SHA256())
        h.update(nonce + ciphertext)
        tag = h.finalize()
        
        return {
            'nonce': base64.b64encode(nonce).decode(),
            'ciphertext': base64.b64encode(ciphertext).decode(),
            'tag': base64.b64encode(tag).decode(),
            'version': '2.0',
            'timestamp': datetime.now().isoformat()
        }
    
    def decrypt_session(self, encrypted_data: Dict[str, str]) -> Optional[bytes]:
        """رمزگشایی و احراز هویت session"""
        try:
            nonce = base64.b64decode(encrypted_data['nonce'])
            ciphertext = base64.b64decode(encrypted_data['ciphertext'])
            tag = base64.b64decode(encrypted_data['tag'])
            
            # بررسی HMAC
            h = hmac.HMAC(self.auth_key, hashes.SHA256())
            h.update(nonce + ciphertext)
            h.verify(tag)
            
            # رمزگشایی
            plaintext = self.session_cipher.decrypt(
                nonce,
                ciphertext,
                associated_data=b'session_encryption'
            )
            
            return plaintext
            
        except Exception as e:
            logger.error(f"خطا در رمزگشایی session: {e}")
            return None
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """رمزنگاری داده‌های حساس"""
        nonce = secrets.token_bytes(12)
        ciphertext = self.data_cipher.encrypt(
            nonce,
            data.encode('utf-8'),
            associated_data=None
        )
        
        # ترکیب nonce + ciphertext
        encrypted = nonce + ciphertext
        return base64.b64encode(encrypted).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> Optional[str]:
        """رمزگشایی داده‌های حساس"""
        try:
            encrypted_bytes = base64.b64decode(encrypted_data)
            nonce = encrypted_bytes[:12]
            ciphertext = encrypted_bytes[12:]
            
            plaintext = self.data_cipher.decrypt(
                nonce,
                ciphertext,
                associated_data=None
            )
            
            return plaintext.decode('utf-8')
        except Exception as e:
            logger.error(f"خطا در رمزگشایی داده: {e}")
            return None

# ========== سیستم تشخیص ناهنجاری ==========

class AnomalyDetector:
    """تشخیص رفتارهای غیرعادی و حملات"""
    
    def __init__(self):
        self.login_patterns: Dict[str, List[datetime]] = {}
        self.failed_attempts: Dict[str, int] = {}
        self.geo_locations: Dict[str, List[str]] = {}
        self.device_fingerprints: Dict[str, List[str]] = {}
        self.lock = Lock()
        
        # الگوهای حمله شناخته شده
        self.malicious_patterns = {
            'rapid_logins': 5,  # بیش از 5 لاگین در دقیقه
            'multiple_failures': 3,  # بیش از 3 شکست متوالی
            'geo_hopping': 2,  # تغییر مکان جغرافیایی سریع
            'device_changes': 3  # تغییر دستگاه مکرر
        }
    
    def analyze_login_attempt(self, attempt: LoginAttempt) -> Dict[str, Any]:
        """تحلیل تلاش ورود برای تشخیص ناهنجاری"""
        anomalies = []
        risk_score = 0
        
        with self.lock:
            phone = attempt.phone
            
            # 1. بررسی rate limiting
            if phone not in self.login_patterns:
                self.login_patterns[phone] = []
            
            # حذف لاگین‌های قدیمی
            cutoff = datetime.now() - timedelta(minutes=1)
            self.login_patterns[phone] = [
                t for t in self.login_patterns[phone] if t > cutoff
            ]
            
            # اضافه کردن لاگین فعلی
            self.login_patterns[phone].append(attempt.timestamp)
            
            # بررسی تعداد لاگین‌های سریع
            if len(self.login_patterns[phone]) > self.malicious_patterns['rapid_logins']:
                anomalies.append("rapid_login_attempts")
                risk_score += 30
            
            # 2. بررسی شکست‌های متوالی
            if not attempt.success:
                self.failed_attempts[phone] = self.failed_attempts.get(phone, 0) + 1
                
                if self.failed_attempts[phone] > self.malicious_patterns['multiple_failures']:
                    anomalies.append("multiple_failed_attempts")
                    risk_score += 40
            else:
                self.failed_attempts[phone] = 0
            
            # 3. بررسی جغرافیا (اگر IP موجود باشد)
            if attempt.ip_address:
                if phone not in self.geo_locations:
                    self.geo_locations[phone] = []
                
                # استخراج کشور از IP (شبیه‌سازی)
                country = self._ip_to_country(attempt.ip_address)
                self.geo_locations[phone].append(country)
                
                # بررسی تغییرات سریع جغرافیایی
                if len(self.geo_locations[phone]) > 1:
                    unique_countries = len(set(self.geo_locations[phone][-3:]))
                    if unique_countries > self.malicious_patterns['geo_hopping']:
                        anomalies.append("suspicious_geo_hopping")
                        risk_score += 30
        
        return {
            'has_anomalies': len(anomalies) > 0,
            'anomalies': anomalies,
            'risk_score': min(risk_score, 100),
            'recommendation': self._get_recommendation(anomalies, risk_score)
        }
    
    def _ip_to_country(self, ip: str) -> str:
        """تبدیل IP به کشور (شبیه‌سازی)"""
        # در پروژه واقعی از GeoIP database استفاده کنید
        return "IR"  # شبیه‌سازی
    
    def _get_recommendation(self, anomalies: List[str], risk_score: int) -> str:
        """پیشنهادات امنیتی براساس ریسک"""
        if risk_score >= 70:
            return "BLOCK_IMMEDIATE"
        elif risk_score >= 50:
            return "REQUIRE_2FA"
        elif risk_score >= 30:
            return "REQUIRE_CAPTCHA"
        else:
            return "ALLOW"

# ========== سیستم مانیتورینگ real-time ==========

class AccountMonitor:
    """مانیتورینگ real-time اکانت‌ها"""
    
    def __init__(self):
        self.account_metrics: Dict[str, Dict] = {}
        self.alerts: List[Dict] = []
        self.metrics_history: Dict[str, List] = {}
        self.last_check = datetime.now()
        self.lock = Lock()
        
        # آستانه‌های هشدار
        self.alert_thresholds = {
            'inactive_hours': 24,
            'flood_wait_count': 3,
            'login_failures': 5,
            'memory_usage_mb': 500,
            'api_errors': 10
        }
    
    async def monitor_account(self, account_id: str, client: TelegramClient) -> Dict:
        """مانیتورینگ وضعیت اکانت"""
        metrics = {
            'timestamp': datetime.now(),
            'is_connected': client.is_connected(),
            'last_seen': None,
            'unread_count': 0,
            'memory_usage': self._get_memory_usage(),
            'api_latency': await self._check_api_latency(client),
            'is_online': await self._check_online_status(client)
        }
        
        with self.lock:
            self.account_metrics[account_id] = metrics
            
            # ذخیره تاریخچه
            if account_id not in self.metrics_history:
                self.metrics_history[account_id] = []
            
            self.metrics_history[account_id].append(metrics)
            
            # حفظ فقط 100 رکورد آخر
            if len(self.metrics_history[account_id]) > 100:
                self.metrics_history[account_id] = self.metrics_history[account_id][-100:]
            
            # بررسی هشدارها
            await self._check_alerts(account_id, metrics)
        
        return metrics
    
    async def _check_api_latency(self, client: TelegramClient) -> float:
        """بررسی تأخیر API"""
        import time
        
        try:
            start = time.time()
            await client.get_me()
            end = time.time()
            return end - start
        except:
            return -1
    
    async def _check_online_status(self, client: TelegramClient) -> bool:
        """بررسی وضعیت آنلاین"""
        try:
            me = await client.get_me()
            return me.status is not None
        except:
            return False
    
    def _get_memory_usage(self) -> float:
        """مصرف حافظه"""
        import psutil
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024  # MB
        except:
            return 0
    
    async def _check_alerts(self, account_id: str, metrics: Dict):
        """بررسی و ایجاد هشدار"""
        alerts = []
        
        # بررسی اتصال
        if not metrics['is_connected']:
            alerts.append({
                'type': 'DISCONNECTED',
                'account_id': account_id,
                'message': 'اکانت قطع شده است',
                'severity': 'HIGH'
            })
        
        # بررسی تأخیر API
        if metrics['api_latency'] > 5.0:  # بیش از 5 ثانیه
            alerts.append({
                'type': 'HIGH_LATENCY',
                'account_id': account_id,
                'message': f'تأخیر API بالا: {metrics["api_latency"]:.2f}s',
                'severity': 'MEDIUM'
            })
        
        # بررسی مصرف حافظه
        if metrics['memory_usage'] > self.alert_thresholds['memory_usage_mb']:
            alerts.append({
                'type': 'HIGH_MEMORY',
                'account_id': account_id,
                'message': f'مصرف حافظه بالا: {metrics["memory_usage"]:.2f}MB',
                'severity': 'MEDIUM'
            })
        
        # ذخیره هشدارها
        if alerts:
            self.alerts.extend(alerts)
            logger.warning(f"هشدار برای اکانت {account_id}: {alerts}")

# ========== سیستم مدیریت اکانت پیشرفته ==========

class AdvancedAccountManager:
    """مدیریت پیشرفته اکانت‌های تلگرام"""
    
    def __init__(self, base_dir: Path = Path("accounts"), 
                 encryption_key: Optional[str] = None,
                 api_id: Optional[int] = None,
                 api_hash: Optional[str] = None):
        
        self.base_dir = base_dir
        self.api_id = api_id
        self.api_hash = api_hash
        
        # ایجاد دایرکتوری‌ها
        self.directories = {
            'sessions': base_dir / "sessions",
            'encrypted': base_dir / "encrypted",
            'backups': base_dir / "backups",
            'logs': base_dir / "logs",
            'temp': base_dir / "temp",
            'exports': base_dir / "exports"
        }
        
        for name, path in self.directories.items():
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        # سیستم‌های اصلی
        self.encryption = AdvancedEncryption(encryption_key) if HAS_CRYPTOGRAPHY else None
        self.anomaly_detector = AnomalyDetector()
        self.monitor = AccountMonitor()
        self.database = AccountDatabase(base_dir / "accounts.db")
        
        # کش اکانت‌های فعال
        self.active_accounts: Dict[str, Dict] = {}
        self.account_pool = ThreadPoolExecutor(max_workers=10)
        self.locks: Dict[str, Lock] = {}
        
        # Webhook برای رویدادها
        self.webhook_url = None
        self.webhook_secret = secrets.token_urlsafe(32)
        
        # تنظیمات proxy
        self.proxy_settings = None
        
        logger.info("مدیریت اکانت پیشرفته راه‌اندازی شد")
    
    # ========== سیستم ورود پیشرفته ==========
    
    async def login_with_phone_advanced(
        self,
        phone: str,
        session_name: Optional[str] = None,  # ✅ باید Optional باشد
        use_proxy: bool = False,
        enable_2fa: bool = True,
        device_info: Optional[Dict] = None
    ) -> Tuple[bool, Optional[TelegramClient], Optional[str]]:
        """ورود پیشرفته با شماره تلفن"""
        
        # اعتبارسنجی شماره
        if not self._validate_phone_number(phone):
            return False, None, "شماره تلفن نامعتبر"
        
        # بررسی امنیتی اولیه
        security_check = await self._pre_login_security_check(phone)
        if not security_check['allowed']:
            return False, None, security_check['reason']
        
        # ایجاد نام session
        if not session_name:
            session_name = self._generate_session_name(phone)
        
        session_path = self.directories['sessions'] / f"{session_name}.session"
        
        # تنظیمات دستگاه
        if not device_info:
            device_info = self._get_default_device_info()
        
        try:
            # ایجاد کلاینت با تنظیمات پیشرفته
            client = await self._create_advanced_client(
                session_path=session_path,
                device_info=device_info,
                use_proxy=use_proxy
            )
            
            # لاگ تلاش ورود
            attempt = LoginAttempt(
                attempt_id=secrets.token_hex(8),
                phone=phone,
                timestamp=datetime.now(),
                success=False,
                method=LoginMethod.PHONE_CODE,
                ip_address=self._get_client_ip(),
                user_agent="AdvancedAccountManager/2.0"
            )
            
            # بررسی session موجود
            if await client.is_user_authorized():
                logger.info(f"Session موجود برای {phone}")
                attempt.success = True
                await self._log_login_attempt(attempt)
                
                # بارگذاری اطلاعات اکانت
                account_info = await self._load_or_create_account(client, phone, session_name)
                return True, client, account_info.account_id
            
            # درخواست کد تأیید
            logger.info(f"درخواست کد برای {phone}")
            
            try:
                sent = await client.send_code_request(phone)
                phone_code_hash = sent.phone_code_hash
                
                # ارسال webhook برای درخواست کد
                await self._send_webhook('code_requested', {
                    'phone': phone,
                    'session_name': session_name,
                    'timestamp': datetime.now().isoformat()
                })
                
            except FloodWaitError as e:
                logger.warning(f"Flood wait: {e.seconds} seconds")
                attempt.error_message = f"Flood wait {e.seconds}s"
                await self._log_login_attempt(attempt)
                
                # ذخیره flood wait در دیتابیس
                await self.database.update_account_status(
                    session_name, AccountStatus.FLOOD_WAIT, e.seconds
                )
                
                return False, None, f"لطفاً {e.seconds} ثانیه صبر کنید"
            
            # دریافت کد از کاربر (چند روش)
            code = await self._get_verification_code_interactive(phone)
            if code.lower() == 'resend':
                return await self.login_with_phone_advanced(
                    phone, session_name, use_proxy, enable_2fa, device_info
                )
            
            # تلاش برای ورود با کد
            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash
                )
                
                logger.info(f"ورود موفق با کد برای {phone}")
                attempt.success = True
                
            except SessionPasswordNeededError:
                # نیاز به رمز دو مرحله‌ای
                if enable_2fa:
                    password = await self._get_2fa_password_secure()
                    
                    try:
                        await client.sign_in(password=password)
                        attempt.method = LoginMethod.PASSWORD
                        attempt.success = True
                        logger.info(f"ورود موفق با 2FA برای {phone}")
                    except Exception as e:
                        attempt.error_message = str(e)
                        await self._log_login_attempt(attempt)
                        return False, None, f"رمز دو مرحله‌ای نامعتبر: {e}"
                else:
                    return False, None, "اکانت نیاز به رمز دو مرحله‌ای دارد"
            
            except PhoneCodeInvalidError:
                attempt.error_message = "کد تأیید نامعتبر"
                await self._log_login_attempt(attempt)
                return False, None, "کد تأیید نامعتبر"
            
            except PhoneCodeExpiredError:
                attempt.error_message = "کد تأیید منقضی شده"
                await self._log_login_attempt(attempt)
                return False, None, "کد تأیید منقضی شده. لطفاً دوباره تلاش کنید"
            
            # تأیید نهایی ورود
            if await client.is_user_authorized():
                attempt.response_time = (datetime.now() - attempt.timestamp).total_seconds()
                await self._log_login_attempt(attempt)
                
                # تحلیل ناهنجاری
                anomaly_result = self.anomaly_detector.analyze_login_attempt(attempt)
                
                if anomaly_result['has_anomalies']:
                    logger.warning(f"ناهنجاری تشخیص داده شد: {anomaly_result}")
                    
                    # اقدامات امنیتی براساس سطح ریسک
                    if anomaly_result['risk_score'] >= 70:
                        await client.disconnect()
                        return False, None, "ورود مسدود شد (ریسک امنیتی بالا)"
                
                # ایجاد/بارگذاری اطلاعات اکانت
                account_info = await self._load_or_create_account(client, phone, session_name)
                
                # ذخیره session رمزنگاری شده
                if self.encryption:
                    await self._encrypt_and_save_session(session_path, session_name)
                
                # شروع مانیتورینگ
                asyncio.create_task(
                    self.monitor.monitor_account(account_info.account_id, client)
                )
                
                # ارسال webhook برای ورود موفق
                await self._send_webhook('login_successful', {
                    'account_id': account_info.account_id,
                    'phone': phone,
                    'session_name': session_name,
                    'timestamp': datetime.now().isoformat(),
                    'risk_score': anomaly_result.get('risk_score', 0)
                })
                
                return True, client, account_info.account_id
            
            return False, None, "ورود ناموفق"
            
        except ApiIdInvalidError:
            return False, None, "API ID یا Hash نامعتبر"
        except Exception as e:
            logger.error(f"خطای ناشناخته در ورود: {e}")
            return False, None, f"خطای سیستمی: {str(e)}"
    
    async def login_with_qr(self) -> Tuple[bool, Optional[TelegramClient], Optional[str]]:
        """ورود با QR Code - متد اصلی"""
        try:
            session_name = self._generate_session_name("qr_login")
            session_path = self.directories['sessions'] / f"{session_name}.session"
            
            client = TelegramClient(
                session=str(session_path),
                api_id=self.api_id,
                api_hash=self.api_hash
            )
            
            await client.connect()
            
            # ایجاد QR Code
            qr_login = await client.qr_login()
            
            print("\n" + "="*50)
            print("📱 لطفاً QR Code زیر را با تلگرام اسکن کنید:")
            print("="*50)
            print(qr_login.url)
            print("\n⏳ منتظر تأیید... (30 ثانیه)")
            
            # انتظار برای تأیید
            try:
                await asyncio.wait_for(qr_login.wait(), timeout=30)
                
                if await client.is_user_authorized():
                    me = await client.get_me()
                    
                    # ایجاد اطلاعات اکانت
                    account_info = await self._create_account_info(
                        client, me.phone, session_name, LoginMethod.QR_CODE
                    )
                    
                    logger.info(f"ورود QR موفق برای {me.phone}")
                    return True, client, account_info.account_id
                
            except asyncio.TimeoutError:
                return False, None, "زمان اسکن QR Code به پایان رسید"
            
            return False, None, "ورود با QR ناموفق"
            
        except Exception as e:
            logger.error(f"خطا در ورود QR: {e}")
            return False, None, f"خطا در ورود QR: {str(e)}"
    
    async def login_with_qr_code(self) -> Tuple[bool, Optional[TelegramClient], Optional[str]]:
        """ورود با QR Code - سازگار با main.py"""
        return await self.login_with_qr()
    
    # ========== سیستم چند اکانتی ==========
    
    async def create_account_pool(self, accounts: List[Dict]) -> Dict[str, TelegramClient]:
        """ایجاد استخر اکانت برای load balancing"""
        account_pool = {}
        
        for account_config in accounts:
            phone = account_config.get('phone')
            session_name = account_config.get('session_name')
            
            if phone and session_name:
                success, client, account_id = await self.login_with_phone_advanced(
                    phone=phone,
                    session_name=session_name,
                    use_proxy=account_config.get('use_proxy', False)
                )
                
                if success and client:
                    account_pool[account_id] = client
        
        logger.info(f"استخر اکانت با {len(account_pool)} اکانت ایجاد شد")
        return account_pool
    
    async def get_account_for_task(self, task_type: str) -> Optional[TelegramClient]:
        """دریافت اکانت مناسب برای task خاص"""
        # الگوریتم load balancing هوشمند
        available_accounts = []
        
        for account_id, account_data in self.active_accounts.items():
            client = account_data.get('client')
            metrics = account_data.get('metrics', {})
            
            if client and client.is_connected():
                # بررسی workload اکانت
                workload = metrics.get('workload', 0)
                api_latency = metrics.get('api_latency', 0)
                
                if workload < 5 and api_latency < 3.0:  # آستانه‌ها
                    available_accounts.append((account_id, client, workload))
        
        if not available_accounts:
            return None
        
        # انتخاب اکانت با کمترین workload
        available_accounts.sort(key=lambda x: x[2])
        selected_account = available_accounts[0]
        
        # به‌روزرسانی workload
        account_id, client, _ = selected_account
        if account_id in self.active_accounts:
            self.active_accounts[account_id]['workload'] = \
                self.active_accounts[account_id].get('workload', 0) + 1
        
        return client
    
    # ========== مدیریت session ==========
    
    async def backup_account(self, account_id: str, 
                           backup_type: str = "full") -> Optional[Path]:
        """تهیه backup از اکانت"""
        try:
            if account_id not in self.active_accounts:
                return None
            
            account_data = self.active_accounts[account_id]
            session_name = account_data.get('session_name')
            
            if not session_name:
                return None
            
            # مسیر فایل‌های session
            session_file = self.directories['sessions'] / f"{session_name}.session"
            encrypted_file = self.directories['encrypted'] / f"{session_name}.enc"
            
            # ایجاد فایل backup
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = self.directories['backups'] / f"{session_name}_{timestamp}.backup"
            
            backup_data = {
                'account_id': account_id,
                'session_name': session_name,
                'backup_type': backup_type,
                'timestamp': timestamp,
                'files': {}
            }
            
            # backup از فایل session
            if session_file.exists():
                with open(session_file, 'rb') as f:
                    session_data = f.read()
                
                backup_data['files']['session'] = base64.b64encode(session_data).decode()
            
            # backup از فایل رمزنگاری شده
            if encrypted_file.exists():
                with open(encrypted_file, 'rb') as f:
                    encrypted_data = f.read()
                
                backup_data['files']['encrypted'] = base64.b64encode(encrypted_data).decode()
            
            # ذخیره backup
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            # فشرده‌سازی
            compressed_file = await self._compress_backup(backup_file)
            
            logger.info(f"Backup ایجاد شد: {compressed_file}")
            return compressed_file
            
        except Exception as e:
            logger.error(f"خطا در backup: {e}")
            return None
    
    async def restore_account(self, backup_file: Path) -> bool:
        """بازیابی اکانت از backup"""
        try:
            # decompress فایل
            decompressed_file = await self._decompress_backup(backup_file)
            
            with open(decompressed_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            session_name = backup_data.get('session_name')
            
            # بازیابی session
            if 'session' in backup_data['files']:
                session_data = base64.b64decode(backup_data['files']['session'])
                session_file = self.directories['sessions'] / f"{session_name}.session"
                
                with open(session_file, 'wb') as f:
                    f.write(session_data)
            
            # بازیابی فایل رمزنگاری شده
            if 'encrypted' in backup_data['files']:
                encrypted_data = base64.b64decode(backup_data['files']['encrypted'])
                encrypted_file = self.directories['encrypted'] / f"{session_name}.enc"
                
                with open(encrypted_file, 'wb') as f:
                    f.write(encrypted_data)
            
            logger.info(f"اکانت {session_name} بازیابی شد")
            return True
            
        except Exception as e:
            logger.error(f"خطا در بازیابی: {e}")
            return False
    
    async def export_account(self, account_id: str, 
                           password: str) -> Optional[Path]:
        """خروجی گرفتن از اکانت با رمز"""
        try:
            if account_id not in self.active_accounts:
                return None
            
            account_data = self.active_accounts[account_id]
            client = account_data.get('client')
            
            if not client:
                return None
            
            # ایجاد session string
            session_string = await client.session.save()
            
            # رمزنگاری با رمز کاربر
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
            from cryptography.hazmat.primitives import hashes
            
            salt = secrets.token_bytes(16)
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000
            )
            key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
            
            cipher = Fernet(key)
            encrypted_session = cipher.encrypt(session_string.encode())
            
            # ایجاد فایل export
            export_data = {
                'version': '1.0',
                'export_date': datetime.now().isoformat(),
                'salt': base64.b64encode(salt).decode(),
                'encrypted_session': base64.b64encode(encrypted_session).decode(),
                'account_info': account_data.get('info', {})
            }
            
            export_file = self.directories['exports'] / f"{account_id}_{datetime.now().strftime('%Y%m%d')}.export"
            
            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2)
            
            return export_file
            
        except Exception as e:
            logger.error(f"خطا در export: {e}")
            return None
    
    # ========== امنیت و مانیتورینگ ==========
    
    async def security_audit(self, account_id: str) -> Dict[str, Any]:
        """بررسی امنیتی اکانت"""
        if account_id not in self.active_accounts:
            return {'status': 'error', 'message': 'اکانت یافت نشد'}
        
        account_data = self.active_accounts[account_id]
        security_report = {
            'account_id': account_id,
            'timestamp': datetime.now().isoformat(),
            'checks': [],
            'score': 0,
            'recommendations': []
        }
        
        # 1. بررسی session
        session_check = await self._check_session_security(account_data)
        security_report['checks'].append(session_check)
        
        # 2. بررسی فعالیت‌های مشکوک
        activity_check = await self._check_suspicious_activity(account_id)
        security_report['checks'].append(activity_check)
        
        # 3. بررسی تنظیمات امنیتی
        settings_check = await self._check_security_settings(account_data)
        security_report['checks'].append(settings_check)
        
        # محاسبه امتیاز
        total_score = sum(check.get('score', 0) for check in security_report['checks'])
        security_report['score'] = total_score // len(security_report['checks'])
        
        # تولید پیشنهادات
        if security_report['score'] < 50:
            security_report['recommendations'].append("فعال‌سازی 2FA فوری")
        if security_report['score'] < 70:
            security_report['recommendations'].append("تغییر رمز session")
        
        return security_report
    
    async def rotate_session_key(self, account_id: str) -> bool:
        """تغییر کلید session برای امنیت بیشتر"""
        try:
            if account_id not in self.active_accounts:
                return False
            
            account_data = self.active_accounts[account_id]
            session_name = account_data.get('session_name')
            
            if not session_name:
                return False
            
            session_file = self.directories['sessions'] / f"{session_name}.session"
            
            if session_file.exists():
                # پشتیبان‌گیری
                backup = await self.backup_account(account_id, "pre_rotation")
                
                # حذف session قدیمی
                session_file.unlink()
                
                # ایجاد session جدید
                client = account_data.get('client')
                if client:
                    await client.disconnect()
                    
                    # اتصال مجدد برای ایجاد session جدید
                    await client.connect()
                    
                    # ذخیره session جدید
                    if self.encryption:
                        await self._encrypt_and_save_session(session_file, session_name)
                    
                    logger.info(f"کلید session برای {account_id} تغییر کرد")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"خطا در تغییر کلید: {e}")
            return False

    async def _check_session_security(self, account_data: Dict) -> Dict[str, Any]:
        """بررسی امنیت session"""
        try:
            client = account_data.get('client')
            if not client:
                return {'check': 'session', 'score': 0, 'message': 'کلاینت وجود ندارد'}
            
            session_file = self.directories['sessions'] / f"{account_data.get('session_name')}.session"
            encrypted_file = self.directories['encrypted'] / f"{account_data.get('session_name')}.enc"
            
            score = 50  # امتیاز پایه
            
            # بررسی وجود session رمزنگاری شده
            if encrypted_file.exists():
                score += 30
            
            # بررسی تاریخ‌چه session
            if session_file.exists():
                import os
                file_age = datetime.now().timestamp() - os.path.getmtime(session_file)
                if file_age < 86400:  # کمتر از 24 ساعت
                    score += 20
            
            return {
                'check': 'session_security',
                'score': min(score, 100),
                'message': f'امتیاز امنیت session: {score}/100'
            }
        except Exception as e:
            return {'check': 'session', 'score': 0, 'message': f'خطا: {str(e)}'}
    
    async def _check_suspicious_activity(self, account_id: str) -> Dict[str, Any]:
        """بررسی فعالیت‌های مشکوک"""
        try:
            # اینجا می‌توانید لاگ‌ها را از دیتابیس بررسی کنید
            score = 80  # امتیاز اولیه
            
            # شبیه‌سازی: اگر account_id شامل 'test' باشد، امتیاز کم کنید
            if 'test' in account_id.lower():
                score -= 30
            
            return {
                'check': 'suspicious_activity',
                'score': max(score, 0),
                'message': f'امتیاز فعالیت: {score}/100'
            }
        except Exception as e:
            return {'check': 'activity', 'score': 0, 'message': f'خطا: {str(e)}'}
    
    async def _check_security_settings(self, account_data: Dict) -> Dict[str, Any]:
        """بررسی تنظیمات امنیتی"""
        try:
            score = 70  # امتیاز اولیه
            info = account_data.get('info', {})
            
            # بررسی 2FA
            if info.get('login_method') == LoginMethod.PASSWORD.value:
                score += 20
            
            # بررسی اکانت پریمیوم
            if info.get('is_premium'):
                score += 10
            
            return {
                'check': 'security_settings',
                'score': min(score, 100),
                'message': f'امتیاز تنظیمات: {score}/100'
            }
        except Exception as e:
            return {'check': 'settings', 'score': 0, 'message': f'خطا: {str(e)}'}    
    
    # ========== API و Webhook ==========
    
    async def start_api_server(self, host: str = "127.0.0.1", 
                             port: int = 8080):
        """شروع API سرور"""
        if not HAS_AIOHTTP:
            logger.error("aiohttp برای API سرور نیاز است")
            return
        
        app = web.Application()
        
        # تعریف routes
        app.router.add_get('/api/accounts', self.handle_list_accounts)
        app.router.add_post('/api/accounts/login', self.handle_login)
        app.router.add_delete('/api/accounts/{account_id}', self.handle_logout)
        app.router.add_get('/api/accounts/{account_id}/status', self.handle_status)
        app.router.add_post('/api/accounts/{account_id}/backup', self.handle_backup)
        app.router.add_post('/api/webhook', self.handle_webhook)
        
        # middleware برای احراز هویت
        app.middlewares.append(self.auth_middleware)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        
        await site.start()
        logger.info(f"API سرور شروع شد: http://{host}:{port}")
        
        return runner
    
    async def handle_list_accounts(self, request):
        """لیست اکانت‌ها"""
        accounts = []
        for account_id, data in self.active_accounts.items():
            accounts.append({
                'account_id': account_id,
                'session_name': data.get('session_name'),
                'phone': data.get('phone'),
                'status': data.get('status'),
                'metrics': data.get('metrics', {})
            })
        
        return web.json_response({
            'success': True,
            'count': len(accounts),
            'accounts': accounts
        })
    
    # ========== توابع کمکی ==========
    
    def _validate_phone_number(self, phone: str) -> bool:
        """اعتبارسنجی شماره تلفن"""
        patterns = [
            r'^\+[1-9]\d{1,14}$',  # E.164
            r'^\+98[1-9]\d{9}$',    # ایران
            r'^09[0-9]{9}$',        # ایران بدون +
        ]
        
        for pattern in patterns:
            if re.match(pattern, phone):
                return True
        
        return False
    
    async def _pre_login_security_check(self, phone: str) -> Dict[str, Any]:
        """بررسی امنیتی قبل از ورود"""
        # بررسی flood wait
        flood_status = await self.database.get_flood_wait_status(phone)
        if flood_status['in_flood']:
            return {
                'allowed': False,
                'reason': f"Flood wait: {flood_status['remaining']} ثانیه"
            }
        
        # بررسی تعداد تلاش‌های اخیر
        recent_attempts = await self.database.get_recent_login_attempts(phone, minutes=5)
        if len(recent_attempts) >= 3:
            return {
                'allowed': False,
                'reason': "تعداد تلاش‌ها بیش از حد مجاز"
            }
        
        return {'allowed': True, 'reason': None}
    
    def _generate_session_name(self, phone: str) -> str:
        """تولید نام session منحصر به فرد"""
        phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:8]
        timestamp = int(datetime.now().timestamp())
        random_part = secrets.token_hex(4)
        
        return f"acc_{phone_hash}_{timestamp}_{random_part}"
    
    async def _create_advanced_client(self, session_path: Path, 
                                    device_info: Dict,
                                    use_proxy: bool = False) -> TelegramClient:
        """ایجاد کلاینت پیشرفته"""
        proxy = None
        if use_proxy and self.proxy_settings:
            from telethon.network import connection
            proxy = (self.proxy_settings['type'],
                    self.proxy_settings['host'],
                    self.proxy_settings['port'])
        
        client = TelegramClient(
            session=str(session_path),
            api_id=self.api_id,
            api_hash=self.api_hash,
            device_model=device_info.get('device_model', 'Desktop'),
            system_version=device_info.get('system_version', '10.0'),
            app_version=device_info.get('app_version', '4.0'),
            lang_code='fa',
            system_lang_code='fa-IR',
            proxy=proxy,
            connection_retries=3,
            retry_delay=2,
            timeout=30,
            flood_sleep_threshold=60
        )
        
        return client
    
    async def _get_verification_code_interactive(self, phone: str) -> str:
        """دریافت کد تأیید به صورت تعاملی"""
        print(f"\n📨 کد تأیید به {phone} ارسال شد")
        print("🔢 کد ۵ رقمی را وارد کنید")
        print("🔄 برای ارسال مجدد: resend")
        print("❌ برای لغو: cancel")
        
        while True:
            code = input("\nکد تأیید: ").strip()
            
            if code.lower() == 'cancel':
                raise KeyboardInterrupt("ورود لغو شد")
            elif code.lower() == 'resend':
                return 'resend'
            elif re.match(r'^\d{5}$', code):
                return code
            else:
                print("❌ کد باید ۵ رقم باشد")
    
    async def _get_2fa_password_secure(self) -> str:
        """دریافت رمز دو مرحله‌ای به صورت امن"""
        print("\n🔐 این اکانت رمز دو مرحله‌ای دارد")
        
        while True:
            password = getpass.getpass("رمز دو مرحله‌ای: ").strip()
            
            if len(password) >= 6:
                return password
            else:
                print("❌ رمز باید حداقل ۶ کاراکتر باشد")
    
    async def _load_or_create_account(self, client: TelegramClient, 
                                    phone: str, session_name: str) -> AccountInfo:
        """بارگذاری یا ایجاد اطلاعات اکانت"""
        # بررسی وجود در دیتابیس
        existing = await self.database.get_account_by_session(session_name)
        
        if existing:
            account_info = AccountInfo(**existing)
        else:
            # ایجاد جدید
            me = await client.get_me()
            account_info = await self._create_account_info(
                client, phone, session_name, LoginMethod.PHONE_CODE
            )
            
            # ذخیره در دیتابیس
            await self.database.save_account(account_info)
        
        # به‌روزرسانی در حافظه
        self.active_accounts[account_info.account_id] = {
            'client': client,
            'info': account_info,
            'session_name': session_name,
            'phone': phone,
            'last_used': datetime.now(),
            'metrics': {},
            'workload': 0
        }
        
        return account_info
    
    async def _create_account_info(self, client: TelegramClient, phone: str,
                                 session_name: str, method: LoginMethod) -> AccountInfo:
        """ایجاد اطلاعات اکانت"""
        me = await client.get_me()
        
        return AccountInfo(
            account_id=secrets.token_hex(8),
            session_name=session_name,
            user_id=me.id,
            username=me.username,
            first_name=me.first_name,
            last_name=me.last_name,
            phone=phone,
            phone_hash=hashlib.sha256(phone.encode()).hexdigest(),
            is_bot=me.bot,
            is_premium=me.premium,
            status=AccountStatus.ACTIVE,
            login_method=method,
            last_login=datetime.now(),
            security_score=85  # امتیاز اولیه
        )
    
    async def _encrypt_and_save_session(self, session_path: Path, session_name: str):
        """رمزنگاری و ذخیره session"""
        if not self.encryption or not session_path.exists():
            return
        
        try:
            # خواندن session
            with open(session_path, 'rb') as f:
                session_data = f.read()
            
            # رمزنگاری
            encrypted_data = self.encryption.encrypt_session(session_data)
            
            # ذخیره
            encrypted_file = self.directories['encrypted'] / f"{session_name}.enc"
            with open(encrypted_file, 'w', encoding='utf-8') as f:
                json.dump(encrypted_data, f, indent=2)
            
            # حذف فایل اصلی
            session_path.unlink()
            
            logger.debug(f"Session رمزنگاری شد: {session_name}")
            
        except Exception as e:
            logger.error(f"خطا در رمزنگاری session: {e}")
    
    async def _send_webhook(self, event_type: str, data: Dict):
        """ارسال webhook"""
        if not self.webhook_url:
            return
        
        try:
            payload = {
                'event': event_type,
                'timestamp': datetime.now().isoformat(),
                'data': data,
                'signature': self._create_webhook_signature(data)
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as resp:
                    if resp.status != 200:
                        logger.warning(f"Webhook ارسال نشد: {resp.status}")
        
        except Exception as e:
            logger.error(f"خطا در ارسال webhook: {e}")
    
    def _create_webhook_signature(self, data: Dict) -> str:
        """ایجاد امضا برای webhook"""
        import hmac
        
        message = json.dumps(data, sort_keys=True).encode()
        signature = hmac.new(
            self.webhook_secret.encode(),
            message,
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def _get_client_ip(self) -> str:
        """دریافت IP کلاینت (شبیه‌سازی)"""
        # در پروژه واقعی از request IP استفاده کنید
        return "127.0.0.1"
    
    def _get_default_device_info(self) -> Dict:
        """اطلاعات پیش‌فرض دستگاه"""
        import platform
        
        return {
            'device_model': 'Desktop',
            'system_version': platform.version(),
            'app_version': '4.0.0',
            'platform': platform.platform(),
            'python_version': platform.python_version()
        }
    
    async def _compress_backup(self, backup_file: Path) -> Path:
        """فشرده‌سازی backup"""
        compressed_file = backup_file.with_suffix('.backup.gz')
        
        import gzip
        with open(backup_file, 'rb') as f_in:
            with gzip.open(compressed_file, 'wb') as f_out:
                f_out.write(f_in.read())
        
        backup_file.unlink()  # حذف فایل اصلی
        return compressed_file
    
    async def _decompress_backup(self, backup_file: Path) -> Path:
        """از حالت فشرده خارج کردن"""
        decompressed_file = backup_file.with_suffix('').with_suffix('.backup')
        
        import gzip
        with gzip.open(backup_file, 'rb') as f_in:
            with open(decompressed_file, 'wb') as f_out:
                f_out.write(f_in.read())
        
        return decompressed_file
    
    async def _log_login_attempt(self, attempt: LoginAttempt):
        """ذخیره لاگ تلاش ورود"""
        await self.database.log_login_attempt(attempt)

# ========== دیتابیس پیشرفته ==========

class AccountDatabase:
    """دیتابیس پیشرفته برای مدیریت اکانت‌ها"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = None
        self._initialize()
    
    def _initialize(self):
        """مقداردهی اولیه دیتابیس"""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._create_tables()
    
    def _create_tables(self):
        """ایجاد جداول دیتابیس"""
        cursor = self.conn.cursor()
        
        # جدول اکانت‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                account_id TEXT PRIMARY KEY,
                session_name TEXT UNIQUE,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                phone_hash TEXT,
                is_bot BOOLEAN,
                is_premium BOOLEAN,
                status TEXT,
                login_method TEXT,
                created_at TIMESTAMP,
                last_login TIMESTAMP,
                last_activity TIMESTAMP,
                total_messages INTEGER DEFAULT 0,
                total_downloads INTEGER DEFAULT 0,
                security_score INTEGER DEFAULT 100,
                metadata TEXT
            )
        ''')
        
        # جدول تلاش‌های ورود
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                attempt_id TEXT PRIMARY KEY,
                phone TEXT,
                timestamp TIMESTAMP,
                success BOOLEAN,
                method TEXT,
                ip_address TEXT,
                user_agent TEXT,
                error_message TEXT,
                response_time REAL
            )
        ''')
        
        # جدول flood wait
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS flood_waits (
                phone TEXT PRIMARY KEY,
                wait_until TIMESTAMP,
                wait_seconds INTEGER,
                reason TEXT
            )
        ''')
        
        # جدول آمار
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_stats (
                stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT,
                timestamp TIMESTAMP,
                is_connected BOOLEAN,
                api_latency REAL,
                memory_usage REAL,
                unread_count INTEGER,
                FOREIGN KEY (account_id) REFERENCES accounts (account_id)
            )
        ''')
        
        # ایندکس‌ها
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_phone ON accounts(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_attempts_phone ON login_attempts(phone)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_login_attempts_time ON login_attempts(timestamp)')
        
        self.conn.commit()
        
    async def update_account_status(self, session_name: str, status: AccountStatus, wait_seconds: int = 0):
        """به‌روزرسانی وضعیت اکانت"""
        try:
            cursor = self.conn.cursor()
            if status == AccountStatus.FLOOD_WAIT:
                # ذخیره flood wait
                wait_until = datetime.now() + timedelta(seconds=wait_seconds)
                cursor.execute('''
                    INSERT OR REPLACE INTO flood_waits (phone, wait_until, wait_seconds, reason)
                    VALUES (?, ?, ?, ?)
                ''', (session_name, wait_until, wait_seconds, 'flood_wait'))
            else:
                # به‌روزرسانی وضعیت اکانت
                cursor.execute('''
                    UPDATE accounts SET status = ? WHERE session_name = ?
                ''', (status.value, session_name))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"خطا در به‌روزرسانی وضعیت: {e}")
    
    async def get_flood_wait_status(self, phone: str) -> Dict[str, Any]:
        """بررسی وضعیت flood wait"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT wait_until FROM flood_waits WHERE phone = ?', (phone,))
            result = cursor.fetchone()
            
            if result:
                wait_until = datetime.fromisoformat(result[0])
                remaining = (wait_until - datetime.now()).seconds
                return {
                    'in_flood': remaining > 0,
                    'remaining': max(0, remaining)
                }
        except Exception as e:
            logger.error(f"خطا در بررسی flood wait: {e}")
        
        return {'in_flood': False, 'remaining': 0}
    
    async def get_recent_login_attempts(self, phone: str, minutes: int = 5) -> List[Dict]:
        """دریافت تلاش‌های ورود اخیر"""
        try:
            cursor = self.conn.cursor()
            cutoff = datetime.now() - timedelta(minutes=minutes)
            cursor.execute('''
                SELECT * FROM login_attempts 
                WHERE phone = ? AND timestamp > ?
                ORDER BY timestamp DESC
            ''', (phone, cutoff))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"خطا در دریافت تلاش‌های ورود: {e}")
            return []
    
    async def get_account_by_session(self, session_name: str) -> Optional[Dict]:
        """دریافت اکانت براساس session name"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT * FROM accounts WHERE session_name = ?', (session_name,))
            result = cursor.fetchone()
            
            if result:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, result))
        except Exception as e:
            logger.error(f"خطا در دریافت اکانت: {e}")
        
        return None
    
    async def save_account(self, account_info: AccountInfo):
        """ذخیره اکانت در دیتابیس"""
        try:
            cursor = self.conn.cursor()
            account_dict = account_info.to_dict()
            
            # تبدیل به tuple برای SQL
            values = tuple(account_dict.values())
            
            cursor.execute('''
                INSERT OR REPLACE INTO accounts 
                (account_id, session_name, user_id, username, first_name, last_name, 
                 phone, phone_hash, is_bot, is_premium, status, login_method, 
                 created_at, last_login, last_activity, total_messages, 
                 total_downloads, security_score, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', values)
            
            self.conn.commit()
            logger.debug(f"اکانت {account_info.account_id} ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره اکانت: {e}")
    
    async def log_login_attempt(self, attempt: LoginAttempt):
        """ذخیره لاگ تلاش ورود"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                INSERT INTO login_attempts 
                (attempt_id, phone, timestamp, success, method, ip_address, 
                 user_agent, error_message, response_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                attempt.attempt_id, attempt.phone, attempt.timestamp,
                attempt.success, attempt.method.value, attempt.ip_address,
                attempt.user_agent, attempt.error_message, attempt.response_time
            ))
            
            self.conn.commit()
        except Exception as e:
            logger.error(f"خطا در ذخیره لاگ ورود: {e}")

# ========== رابط خط فرمان ==========

class AdvancedCLI:
    """رابط خط فرمان پیشرفته"""
    
    def __init__(self, manager: AdvancedAccountManager):
        self.manager = manager
        self.running = True
    
    async def run(self):
        """اجرای رابط"""
        self._print_banner()
        
        while self.running:
            try:
                await self._show_main_menu()
            except KeyboardInterrupt:
                print("\n\n⚠️ عملیات لغو شد")
                continue
            except Exception as e:
                print(f"\n❌ خطا: {e}")
                logger.exception("CLI error")
    
    def _print_banner(self):
        """چاپ بنر"""
        banner = """
╔══════════════════════════════════════════════════════════╗
║   🔐 سیستم مدیریت پیشرفته اکانت تلگرام - نسخه حرفه‌ای   ║
║                   با ۱۵+ ویژگی امنیتی                     ║
╚══════════════════════════════════════════════════════════╝
        """
        print(banner)
    
    async def _show_main_menu(self):
        """نمایش منوی اصلی"""
        menu = """
┌──────────────────────────────────────────────────────┐
│                    منوی اصلی                          │
├──────────────────────────────────────────────────────┤
│ 1. 📱 ورود با شماره تلفن (پیشرفته)                  │
│ 2. 📷 ورود با QR Code                               │
│ 3. 📋 لیست اکانت‌های فعال                          │
│ 4. 🔍 بررسی وضعیت اکانت                            │
│ 5. 🛡️  بررسی امنیتی اکانت                          │
│ 6. 💾 Backup از اکانت                              │
│ 7. 🔄 بازیابی اکانت                                │
│ 8. 📤 Export اکانت                                 │
│ 9. 🚪 خروج از اکانت                                │
│ 10. 📊 آمار سیستم                                  │
│ 11. ⚙️  تنظیمات                                    │
│ 12. ❌ خروج از برنامه                              │
└──────────────────────────────────────────────────────┘
        """
        
        print(menu)
        choice = input("\n📝 انتخاب شما: ").strip()
        
        if choice == '1':
            await self.login_with_phone()
        elif choice == '2':
            await self.login_with_qr()
        elif choice == '3':
            await self.list_accounts()
        elif choice == '4':
            await self.check_account_status()
        elif choice == '5':
            await self.security_audit()
        elif choice == '6':
            await self.backup_account()
        elif choice == '7':
            await self.restore_account()
        elif choice == '8':
            await self.export_account()
        elif choice == '9':
            await self.logout_account()
        elif choice == '10':
            await self.system_stats()
        elif choice == '11':
            await self.settings()
        elif choice == '12':
            self.running = False
            print("\n👋 خروج از برنامه...")
        else:
            print("\n❌ انتخاب نامعتبر")
    
    async def login_with_phone(self):
        """ورود با شماره تلفن"""
        print("\n" + "═"*50)
        print("📱 ورود پیشرفته با شماره تلفن")
        print("═"*50)
        
        phone = input("شماره تلفن (با +98): ").strip()
        
        if not phone:
            print("❌ شماره تلفن الزامی است")
            return
        
        use_proxy = input("استفاده از proxy؟ (y/n): ").strip().lower() == 'y'
        enable_2fa = input("فعال‌سازی 2FA؟ (y/n): ").strip().lower() == 'y'
        
        print("\n⏳ در حال ورود...")
        
        success, client, account_id = await self.manager.login_with_phone_advanced(
            phone=phone,
            use_proxy=use_proxy,
            enable_2fa=enable_2fa
        )
        
        if success and client:
            print(f"\n✅ ورود موفق!")
            print(f"🆔 Account ID: {account_id}")
            
            # نمایش اطلاعات کاربر
            me = await client.get_me()
            print(f"\n👤 اطلاعات کاربر:")
            print(f"   نام: {me.first_name} {me.last_name or ''}")
            print(f"   یوزرنیم: @{me.username or 'ندارد'}")
            print(f"   شماره: {me.phone}")
            
            # پرسش برای عملیات بیشتر
            await self.post_login_menu(account_id, client)
        else:
            print(f"\n❌ ورود ناموفق: {account_id}")

# ========== تابع اصلی ==========

async def main():
    """تابع اصلی"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='سیستم مدیریت پیشرفته اکانت تلگرام',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
مثال‌ها:
  %(prog)s --interactive
  %(prog)s --login +989123456789
  %(prog)s --api --port 8080
  %(prog)s --config custom_config.json
        """
    )
    
    parser.add_argument('--interactive', action='store_true',
                       help='اجرای حالت تعاملی')
    parser.add_argument('--login', metavar='PHONE',
                       help='ورود مستقیم با شماره')
    parser.add_argument('--api', action='store_true',
                       help='شروع API سرور')
    parser.add_argument('--port', type=int, default=8080,
                       help='پورت API سرور')
    parser.add_argument('--config', default='config.json',
                       help='فایل تنظیمات')
    parser.add_argument('--debug', action='store_true',
                       help='حالت دیباگ')
    
    args = parser.parse_args()
    
    # تنظیم لاگ
    global logger
    logger = setup_logging(debug=args.debug)
    
    # بارگذاری config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ فایل config یافت نشد: {args.config}")
        return
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ خطا در خواندن config: {e}")
        return
    
    # ایجاد مدیر اکانت
    manager = AdvancedAccountManager(
        base_dir=Path(config.get('accounts_dir', 'accounts')),
        encryption_key=config.get('encryption_key'),
        api_id=config.get('api_id'),
        api_hash=config.get('api_hash')
    )
    
    # تنظیم proxy اگر وجود دارد
    if 'proxy' in config:
        manager.proxy_settings = config['proxy']
    
    # تنظیم webhook اگر وجود دارد
    if 'webhook_url' in config:
        manager.webhook_url = config['webhook_url']
    
    try:
        if args.api:
            # شروع API سرور
            print(f"\n🚀 شروع API سرور روی پورت {args.port}...")
            await manager.start_api_server(port=args.port)
            
            # اجرای نامحدود
            await asyncio.Future()
            
        elif args.interactive:
            # حالت تعاملی
            cli = AdvancedCLI(manager)
            await cli.run()
            
        elif args.login:
            # ورود مستقیم
            print(f"\n🔐 ورود برای {args.login}...")
            success, client, account_id = await manager.login_with_phone_advanced(
                phone=args.login
            )
            
            if success:
                print(f"✅ ورود موفق: {account_id}")
                if client:
                    await client.disconnect()
            else:
                print(f"❌ ورود ناموفق: {account_id}")
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\n\n👋 برنامه توسط کاربر متوقف شد")
    except Exception as e:
        print(f"\n💥 خطای سیستمی: {e}")
        logger.exception("Main error")
        sys.exit(1)

if __name__ == "__main__":
    # بررسی وابستگی‌ها
    if not HAS_TELETHON:
        print("❌ Telethon ضروری است: pip install telethon")
        sys.exit(1)
    
    # اجرا
    asyncio.run(main())
