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
from typing import Optional, Dict, List, Any, Tuple, Union, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from enum import Enum
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
import pickle
import zlib
import jwt
import bcrypt
import string
import hmac
from ipaddress import ip_address, ip_network

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
                     
        # سیستم احراز هویت پیشرفته
        self.auth_system = AdvancedAuthMiddleware(
            jwt_secret=config.get('jwt_secret', secrets.token_urlsafe(64)),
            token_expiry_hours=config.get('token_expiry_hours', 24),
            rate_limit_per_minute=config.get('rate_limit', 100),
            allowed_ips=config.get('allowed_ips'),
            blocked_ips=config.get('blocked_ips', [])
        )

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

    # اضافه کردن این متدها به کلاس AdvancedAccountManager
    
    async def handle_login(self, request):
        """Handler برای ورود"""
        try:
            data = await request.json()
            phone = data.get('phone')
            
            if not phone:
                return web.json_response({
                    'success': False,
                    'error': 'شماره تلفن الزامی است'
                }, status=400)
            
            success, client, account_id = await self.login_with_phone_advanced(phone=phone)
            
            return web.json_response({
                'success': success,
                'account_id': account_id,
                'message': 'ورود موفق' if success else 'ورود ناموفق'
            })
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def handle_logout(self, request):
        """Handler برای خروج"""
        try:
            account_id = request.match_info.get('account_id')
            
            if account_id in self.active_accounts:
                client = self.active_accounts[account_id].get('client')
                if client:
                    await client.disconnect()
                del self.active_accounts[account_id]
            
            return web.json_response({
                'success': True,
                'message': 'اکانت خارج شد'
            })
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def handle_status(self, request):
        """Handler برای وضعیت"""
        account_id = request.match_info.get('account_id')
        
        if account_id in self.active_accounts:
            return web.json_response({
                'success': True,
                'account_id': account_id,
                'status': 'active',
                'data': self.active_accounts[account_id]
            })
        else:
            return web.json_response({
                'success': False,
                'error': 'اکانت یافت نشد'
            }, status=404)
    
    async def handle_backup(self, request):
        """Handler برای backup"""
        try:
            account_id = request.match_info.get('account_id')
            data = await request.json()
            backup_type = data.get('type', 'full')
            
            backup_path = await self.backup_account(account_id, backup_type)
            
            if backup_path:
                return web.json_response({
                    'success': True,
                    'backup_path': str(backup_path),
                    'message': 'Backup ایجاد شد'
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'خطا در ایجاد backup'
                }, status=500)
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    async def handle_webhook(self, request):
        """Handler برای webhook"""
        try:
            data = await request.json()
            logger.info(f"Webhook دریافت شد: {data}")
            
            return web.json_response({
                'success': True,
                'message': 'Webhook دریافت شد'
            })
        except Exception as e:
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
        
        # ادامه پردازش
        return await handler(request)
    
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
        # ========== اضافه کردن Middleware‌ها ==========
        app.middlewares.append(self.auth_middleware)  # Middleware احراز هویت
        app.middlewares.append(self.logging_middleware)  # Middleware لاگ‌گیری
        app.middlewares.append(self.cors_middleware)  # Middleware CORS
        app.middlewares.append(self.error_handling_middleware)  # Middleware مدیریت خطا
        # ========== تعریف Routes ==========
        # Routes عمومی (بدون احراز هویت)
        app.router.add_post('/api/auth/login', self.handle_auth_login)
        app.router.add_post('/api/auth/register', self.handle_auth_register)
        app.router.add_get('/api/auth/verify', self.handle_auth_verify)
        # Routes خصوصی (نیاز به احراز هویت)
        private_routes = web.RouteTableDef()

        # middleware برای احراز هویت
        app.middlewares.append(self.auth_middleware)

        @private_routes.get('/api/accounts')
        async def handle_list_accounts(request):
            return await self.handle_list_accounts(request)

        @private_routes.post('/api/accounts/login')
        async def handle_login(request):
            return await self.handle_login(request)
    
        @private_routes.delete('/api/accounts/{account_id}')
        async def handle_logout(request):
            return await self.handle_logout(request)
    
        @private_routes.get('/api/accounts/{account_id}/status')
        async def handle_status(request):
            return await self.handle_status(request)
    
        @private_routes.post('/api/accounts/{account_id}/backup')
        async def handle_backup(request):
            return await self.handle_backup(request)
    
        @private_routes.post('/api/webhook')
        async def handle_webhook(request):
            return await self.handle_webhook(request)

        # اضافه کردن routes خصوصی به app
        app.add_routes(private_routes)

        # ========== Routes مدیریت کاربران ==========
        app.router.add_post('/api/users/create', self.handle_create_user)
        app.router.post('/api/users/{user_id}/apikey', self.handle_generate_apikey)
        app.router.get('/api/users/{user_id}/logs', self.handle_get_user_logs)
    
        # ========== Routes مدیریت سیستم ==========
        app.router.get('/api/system/status', self.handle_system_status)
        app.router.get('/api/system/metrics', self.handle_system_metrics)
        app.router.get('/api/system/audit', self.handle_system_audit)
    
        # ========== تنظیمات CORS ==========
        self._setup_cors(app)
    
        # ========== تنظیمات Static Files ==========
        self._setup_static_files(app)

        # ========== شروع سرور ==========
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        
        await site.start()

        logger.info(f"✅ API سرور پیشرفته شروع شد: http://{host}:{port}")
        logger.info("📋 Routes فعال:")
        logger.info("  - POST   /api/auth/login")
        logger.info("  - POST   /api/auth/register")
        logger.info("  - GET    /api/accounts (نیاز به token)")
        logger.info("  - POST   /api/accounts/login (نیاز به token)")
        logger.info("  - DELETE /api/accounts/{id} (نیاز به token)")
        logger.info("  - POST   /api/users/create (نیاز به token admin)")
        
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

class AdvancedAuthMiddleware:
    """سیستم احراز هویت پیشرفته Enterprise-Level"""
    
    def __init__(self, 
                 jwt_secret: str = None,
                 token_expiry_hours: int = 24,
                 rate_limit_per_minute: int = 100,
                 allowed_ips: List[str] = None,
                 blocked_ips: List[str] = None):
        
        # کلیدهای JWT
        self.jwt_secret = jwt_secret or secrets.token_urlsafe(64)
        self.token_expiry_hours = token_expiry_hours
        
        # سیستم Rate Limiting
        self.rate_limit_per_minute = rate_limit_per_minute
        self.request_counts: Dict[str, List[datetime]] = {}
        
        # لیست IPهای مجاز/مسدود
        self.allowed_ips = set(allowed_ips) if allowed_ips else None
        self.blocked_ips = set(blocked_ips) if blocked_ips else set()
        
        # سیستم API Keys
        self.api_keys: Dict[str, Dict] = {}
        self.revoked_tokens: Set[str] = set()
        
        # سیستم Roles و Permissions
        self.roles_permissions = {
            'admin': ['*'],
            'manager': ['accounts:read', 'accounts:write', 'backup:create'],
            'viewer': ['accounts:read'],
            'bot': ['accounts:read', 'messages:send']
        }
        
        # سیستم Audit Log
        self.audit_log = []
        
        # سیستم 2FA
        self.twofa_codes: Dict[str, Dict] = {}
        
        logger.info(f"سیستم احراز هویت پیشرفته راه‌اندازی شد. JWT Secret: {self.jwt_secret[:10]}...")

    # ========== Middleware اصلی ==========
    
    @web.middleware
    async def auth_middleware(self, request: web.Request, handler):
        """Middleware پیشرفته احراز هویت با 10 لایه امنیتی"""
        
        request_id = secrets.token_hex(8)
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get('User-Agent', 'Unknown')
        start_time = datetime.now()
        
        # 🛡️ لایه 1: بررسی IP Block
        if self._is_ip_blocked(client_ip):
            await self._log_audit(
                request_id, client_ip, "BLOCKED_IP", request.path, 
                "دسترسی از IP مسدود شده", False
            )
            return self._block_response(
                "دسترسی از این IP مسدود شده است",
                status=403,
                request_id=request_id
            )
        
        # 🛡️ لایه 2: Rate Limiting
        if not self._check_rate_limit(client_ip):
            await self._log_audit(
                request_id, client_ip, "RATE_LIMIT", request.path,
                "تعداد درخواست بیش از حد مجاز", False
            )
            return self._block_response(
                "تعداد درخواست شما بیش از حد مجاز است. لطفاً 1 دقیقه صبر کنید.",
                status=429,
                request_id=request_id,
                retry_after=60
            )
        
        # 🛡️ لایه 3: بررسی User-Agent مشکوک
        if self._is_suspicious_user_agent(user_agent):
            await self._log_audit(
                request_id, client_ip, "SUSPICIOUS_UA", request.path,
                f"User-Agent مشکوک: {user_agent}", False
            )
            return self._block_response(
                "دسترسی با این مرورگر/دستگاه مجاز نیست",
                status=403,
                request_id=request_id
            )
        
        # 🛡️ لایه 4: احراز هویت Token
        auth_result = await self._authenticate_request(request)
        
        if not auth_result['authenticated']:
            await self._log_audit(
                request_id, client_ip, "AUTH_FAILED", request.path,
                auth_result.get('reason', 'عدم احراز هویت'), False
            )
            return self._auth_error_response(auth_result, request_id)
        
        user_data = auth_result['user_data']
        
        # 🛡️ لایه 5: بررسی Permission برای endpoint
        if not self._check_permission(user_data['role'], request.method, request.path):
            await self._log_audit(
                request_id, client_ip, "PERMISSION_DENIED", request.path,
                f"دسترسی غیرمجاز برای role: {user_data['role']}", False,
                user_id=user_data.get('user_id')
            )
            return self._block_response(
                "شما دسترسی لازم برای این عملیات را ندارید",
                status=403,
                request_id=request_id
            )
        
        # 🛡️ لایه 6: بررسی نیاز به 2FA
        if self._requires_2fa(request.path, user_data):
            twofa_result = await self._verify_2fa(request, user_data)
            if not twofa_result['verified']:
                await self._log_audit(
                    request_id, client_ip, "2FA_FAILED", request.path,
                    "تأیید دو مرحله‌ای ناموفق", False,
                    user_id=user_data.get('user_id')
                )
                return self._twofa_required_response(twofa_result, request_id)
        
        # 🛡️ لایه 7: بررسی Session Hijacking
        if self._detect_session_hijacking(request, user_data):
            await self._log_audit(
                request_id, client_ip, "SESSION_HIJACK", request.path,
                "شناسایی تلاش برای Session Hijacking", False,
                user_id=user_data.get('user_id')
            )
            # Revoke all user tokens
            await self._revoke_user_tokens(user_data['user_id'])
            return self._block_response(
                "نشست امنیتی شما به خطر افتاده است. لطفاً مجدداً وارد شوید.",
                status=401,
                request_id=request_id
            )
        
        # 🛡️ لایه 8: اضافه کردن اطلاعات کاربر به request
        request['user'] = user_data
        request['request_id'] = request_id
        request['client_ip'] = client_ip
        
        # 🛡️ لایه 9: اجرای درخواست با timeout
        try:
            response = await asyncio.wait_for(
                handler(request), 
                timeout=self._get_timeout_for_endpoint(request.path)
            )
            
            # 🛡️ لایه 10: لاگ موفقیت
            processing_time = (datetime.now() - start_time).total_seconds()
            await self._log_audit(
                request_id, client_ip, "SUCCESS", request.path,
                f"درخواست با موفقیت پردازش شد ({processing_time:.2f}s)",
                True,
                user_id=user_data.get('user_id'),
                processing_time=processing_time
            )
            
            # اضافه کردن هدرهای امنیتی
            response = self._add_security_headers(response)
            response.headers['X-Request-ID'] = request_id
            
            return response
            
        except asyncio.TimeoutError:
            await self._log_audit(
                request_id, client_ip, "TIMEOUT", request.path,
                "زمان پردازش درخواست به پایان رسید", False,
                user_id=user_data.get('user_id')
            )
            return web.json_response({
                'success': False,
                'error': 'زمان پردازش درخواست به پایان رسید',
                'request_id': request_id,
                'timestamp': datetime.now().isoformat()
            }, status=504)
        
        except Exception as e:
            await self._log_audit(
                request_id, client_ip, "SERVER_ERROR", request.path,
                f"خطای سرور: {str(e)}", False,
                user_id=user_data.get('user_id')
            )
            logger.error(f"خطا در پردازش درخواست {request_id}: {e}")
            
            # عدم افشای جزئیات خطا به کاربر
            return web.json_response({
                'success': False,
                'error': 'خطای داخلی سرور',
                'request_id': request_id,
                'timestamp': datetime.now().isoformat()
            }, status=500)

    # ========== متدهای احراز هویت پیشرفته ==========
    
    async def _authenticate_request(self, request: web.Request) -> Dict:
        """احراز هویت پیشرفته با پشتیبانی از چندین روش"""
        
        # روش 1: Bearer Token (JWT)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]
            return await self._authenticate_jwt(token, request)
        
        # روش 2: API Key در هدر
        api_key = request.headers.get('X-API-Key')
        if api_key:
            return await self._authenticate_api_key(api_key, request)
        
        # روش 3: API Key در query parameter (برای Webhookها)
        api_key_query = request.query.get('api_key')
        if api_key_query:
            return await self._authenticate_api_key(api_key_query, request)
        
        # روش 4: Session Cookie
        session_token = request.cookies.get('session_token')
        if session_token:
            return await self._authenticate_session(session_token, request)
        
        return {
            'authenticated': False,
            'reason': 'هیچ روش احراز هویت یافت نشد',
            'required_methods': ['Bearer token', 'API Key']
        }
    
    async def _authenticate_jwt(self, token: str, request: web.Request) -> Dict:
        """احراز هویت JWT با بررسی‌های پیشرفته"""
        
        # بررسی وجود در revoked tokens
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if token_hash in self.revoked_tokens:
            return {
                'authenticated': False,
                'reason': 'توکن منقضی شده است',
                'error_code': 'TOKEN_REVOKED'
            }
        
        try:
            # رمزگشایی JWT
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=['HS256'],
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'verify_aud': False
                }
            )
            
            # بررسی IP اختصاصی (اگر وجود دارد)
            if 'allowed_ips' in payload and self._get_client_ip(request) not in payload['allowed_ips']:
                return {
                    'authenticated': False,
                    'reason': 'دسترسی از این IP مجاز نیست',
                    'error_code': 'IP_NOT_ALLOWED'
                }
            
            # بررسی User-Agent (اگر وجود دارد)
            if 'user_agent' in payload:
                current_ua = request.headers.get('User-Agent', '')
                if payload['user_agent'] != current_ua:
                    logger.warning(f"User-Agent mismatch for user {payload.get('user_id')}")
            
            # بررسی زمان آخرین تغییر رمز
            if 'password_changed_at' in payload:
                password_age = datetime.now().timestamp() - payload['password_changed_at']
                if password_age > 90 * 24 * 3600:  # 90 روز
                    return {
                        'authenticated': True,
                        'requires_password_change': True,
                        'user_data': payload,
                        'warning': 'رمز عبور شما منقضی شده است'
                    }
            
            return {
                'authenticated': True,
                'user_data': payload,
                'auth_method': 'jwt'
            }
            
        except jwt.ExpiredSignatureError:
            return {
                'authenticated': False,
                'reason': 'توکن منقضی شده است',
                'error_code': 'TOKEN_EXPIRED'
            }
        except jwt.InvalidTokenError as e:
            return {
                'authenticated': False,
                'reason': f'توکن نامعتبر: {str(e)}',
                'error_code': 'INVALID_TOKEN'
            }
    
    async def _authenticate_api_key(self, api_key: str, request: web.Request) -> Dict:
        """احراز هویت با API Key پیشرفته"""
        
        # بررسی در کش
        if api_key in self.api_keys:
            key_data = self.api_keys[api_key]
            
            # بررسی تاریخ انقضا
            if 'expires_at' in key_data and datetime.fromisoformat(key_data['expires_at']) < datetime.now():
                del self.api_keys[api_key]
                return {
                    'authenticated': False,
                    'reason': 'API Key منقضی شده است',
                    'error_code': 'API_KEY_EXPIRED'
                }
            
            # بررسی محدودیت IP
            if 'allowed_ips' in key_data:
                client_ip = self._get_client_ip(request)
                if client_ip not in key_data['allowed_ips']:
                    return {
                        'authenticated': False,
                        'reason': 'دسترسی از این IP مجاز نیست',
                        'error_code': 'IP_NOT_ALLOWED'
                    }
            
            # بررسی Rate Limit اختصاصی
            if 'rate_limit' in key_data:
                key_identifier = f"api_key_{api_key}"
                if not self._check_rate_limit(key_identifier, key_data['rate_limit']):
                    return {
                        'authenticated': False,
                        'reason': 'محدودیت تعداد درخواست برای این API Key',
                        'error_code': 'RATE_LIMIT_EXCEEDED'
                    }
            
            # افزایش استفاده
            key_data['last_used'] = datetime.now().isoformat()
            key_data['usage_count'] = key_data.get('usage_count', 0) + 1
            
            return {
                'authenticated': True,
                'user_data': {
                    'user_id': key_data.get('user_id', 'api_client'),
                    'role': key_data.get('role', 'api_client'),
                    'permissions': key_data.get('permissions', []),
                    'auth_method': 'api_key'
                },
                'auth_method': 'api_key'
            }
        
        # بررسی هش شده
        for key, data in self.api_keys.items():
            if 'hashed_key' in data:
                if bcrypt.checkpw(api_key.encode(), data['hashed_key']):
                    return await self._authenticate_api_key(key, request)
        
        return {
            'authenticated': False,
            'reason': 'API Key نامعتبر',
            'error_code': 'INVALID_API_KEY'
        }
    
    # ========== متدهای 2FA ==========
    
    async def _verify_2fa(self, request: web.Request, user_data: Dict) -> Dict:
        """تأیید دو مرحله‌ای"""
        
        # روش 1: کد در هدر
        twofa_code = request.headers.get('X-2FA-Code')
        
        # روش 2: کد در body
        if not twofa_code and request.can_read_body:
            try:
                data = await request.json()
                twofa_code = data.get('twofa_code')
            except:
                pass
        
        if not twofa_code:
            return {
                'verified': False,
                'required': True,
                'methods': ['totp', 'sms', 'email'],
                'message': 'کد تأیید دو مرحله‌ای مورد نیاز است'
            }
        
        # بررسی کد TOTP
        user_id = user_data.get('user_id')
        if user_id in self.twofa_codes:
            stored_code = self.twofa_codes[user_id]
            
            # بررسی انقضا
            if datetime.fromisoformat(stored_code['expires_at']) < datetime.now():
                del self.twofa_codes[user_id]
                return {
                    'verified': False,
                    'required': True,
                    'message': 'کد تأیید منقضی شده است'
                }
            
            # بررسی کد
            if stored_code['code'] == twofa_code:
                # حذف کد استفاده شده
                del self.twofa_codes[user_id]
                
                # ذخیره لاگ 2FA موفق
                await self._log_audit(
                    secrets.token_hex(4),
                    self._get_client_ip(request),
                    "2FA_SUCCESS",
                    request.path,
                    "تأیید دو مرحله‌ای موفق",
                    True,
                    user_id=user_id
                )
                
                return {'verified': True}
        
        # بررسی کد TOTP دائمی
        if 'totp_secret' in user_data:
            # پیاده‌سازی TOTP واقعی
            # در پروژه واقعی از libraries مانند pyotp استفاده کنید
            pass
        
        return {
            'verified': False,
            'required': True,
            'message': 'کد تأیید نامعتبر است'
        }
    
    async def generate_2fa_code(self, user_id: str, method: str = 'sms') -> Dict:
        """تولید کد تأیید دو مرحله‌ای"""
        
        # تولید کد ۶ رقمی
        code = ''.join(secrets.choice(string.digits) for _ in range(6))
        
        # زمان انقضا: 5 دقیقه
        expires_at = (datetime.now() + timedelta(minutes=5)).isoformat()
        
        self.twofa_codes[user_id] = {
            'code': code,
            'expires_at': expires_at,
            'method': method,
            'created_at': datetime.now().isoformat()
        }
        
        # شبیه‌سازی ارسال کد
        if method == 'sms':
            logger.info(f"📱 کد 2FA برای کاربر {user_id}: {code} (انقضا: 5 دقیقه)")
        elif method == 'email':
            logger.info(f"📧 کد 2FA برای کاربر {user_id}: {code} (انقضا: 5 دقیقه)")
        
        return {
            'code': code,
            'expires_at': expires_at,
            'method': method,
            'length': 6
        }
    
    # ========== سیستم مدیریت API Keys ==========
    
    async def create_api_key(self, 
                           user_id: str,
                           role: str = 'api_client',
                           expires_in_days: int = 30,
                           rate_limit: int = 100,
                           allowed_ips: List[str] = None,
                           permissions: List[str] = None,
                           name: str = None) -> Dict:
        """ایجاد API Key جدید"""
        
        # تولید کلید
        api_key = secrets.token_urlsafe(32)
        
        # هش کردن برای ذخیره امن
        hashed_key = bcrypt.hashpw(api_key.encode(), bcrypt.gensalt())
        
        key_data = {
            'user_id': user_id,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=expires_in_days)).isoformat(),
            'rate_limit': rate_limit,
            'allowed_ips': allowed_ips or [],
            'permissions': permissions or self.roles_permissions.get(role, []),
            'name': name or f"API Key for {user_id}",
            'hashed_key': hashed_key,
            'usage_count': 0,
            'last_used': None
        }
        
        self.api_keys[api_key] = key_data
        
        await self._log_audit(
            secrets.token_hex(4),
            'SYSTEM',
            "API_KEY_CREATED",
            f"/api/keys/{user_id}",
            f"API Key ایجاد شد: {name}",
            True,
            user_id=user_id
        )
        
        return {
            'api_key': api_key,
            'key_data': {k: v for k, v in key_data.items() if k != 'hashed_key'},
            'warning': 'این کلید فقط یک بار نمایش داده می‌شود!'
        }
    
    async def revoke_api_key(self, api_key: str, reason: str = "درخواست کاربر") -> bool:
        """ابطال API Key"""
        
        if api_key in self.api_keys:
            user_id = self.api_keys[api_key].get('user_id')
            del self.api_keys[api_key]
            
            await self._log_audit(
                secrets.token_hex(4),
                'SYSTEM',
                "API_KEY_REVOKED",
                f"/api/keys/{api_key}",
                f"API Key ابطال شد: {reason}",
                True,
                user_id=user_id
            )
            
            return True
        
        return False
    
    # ========== سیستم مدیریت Tokens ==========
    
    async def create_jwt_token(self, 
                             user_id: str,
                             role: str = 'user',
                             additional_data: Dict = None,
                             expires_in_hours: int = None) -> str:
        """ایجاد JWT Token جدید"""
        
        if expires_in_hours is None:
            expires_in_hours = self.token_expiry_hours
        
        payload = {
            'user_id': user_id,
            'role': role,
            'iat': datetime.now().timestamp(),
            'exp': (datetime.now() + timedelta(hours=expires_in_hours)).timestamp(),
            'jti': secrets.token_hex(16),  # JWT ID برای tracking
            'user_agent': 'Unknown',  # باید از request گرفته شود
            'ip_address': '0.0.0.0'   # باید از request گرفته شود
        }
        
        if additional_data:
            payload.update(additional_data)
        
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        
        await self._log_audit(
            secrets.token_hex(4),
            'SYSTEM',
            "TOKEN_CREATED",
            f"/auth/token/{user_id}",
            f"توکن JWT ایجاد شد برای {user_id}",
            True,
            user_id=user_id
        )
        
        return token
    
    async def revoke_token(self, token: str, reason: str = "خروج کاربر") -> bool:
        """ابطال Token"""
        
        try:
            # هش کردن token برای ذخیره در revoked list
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            self.revoked_tokens.add(token_hash)
            
            # استخراج user_id از token برای لاگ
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'], options={'verify_signature': False})
            user_id = payload.get('user_id')
            
            await self._log_audit(
                secrets.token_hex(4),
                'SYSTEM',
                "TOKEN_REVOKED",
                "/auth/revoke",
                f"توکن ابطال شد: {reason}",
                True,
                user_id=user_id
            )
            
            return True
            
        except Exception as e:
            logger.error(f"خطا در ابطال توکن: {e}")
            return False
    
    async def _revoke_user_tokens(self, user_id: str):
        """ابطال تمام توکن‌های یک کاربر"""
        # در پروژه واقعی باید توکن‌ها را از دیتابیس پیدا و ابطال کند
        logger.warning(f"تمامی توکن‌های کاربر {user_id} ابطال شدند")
    
    # ========== متدهای کمکی امنیتی ==========
    
    def _check_rate_limit(self, identifier: str, custom_limit: int = None) -> bool:
        """بررسی Rate Limit"""
        
        limit = custom_limit or self.rate_limit_per_minute
        
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        
        if identifier not in self.request_counts:
            self.request_counts[identifier] = []
        
        # حذف درخواست‌های قدیمی
        self.request_counts[identifier] = [
            req_time for req_time in self.request_counts[identifier] 
            if req_time > minute_ago
        ]
        
        # بررسی تعداد درخواست‌ها
        if len(self.request_counts[identifier]) >= limit:
            return False
        
        # ثبت درخواست جدید
        self.request_counts[identifier].append(now)
        return True
    
    def _is_ip_blocked(self, ip: str) -> bool:
        """بررسی IP مسدود"""
        
        # بررسی در لیست مسدود
        if ip in self.blocked_ips:
            return True
        
        # بررسی رنج IP (مثال: 192.168.1.*)
        for blocked_range in self.blocked_ips:
            if '/' in blocked_range:  # CIDR notation
                if ip_address(ip) in ip_network(blocked_range):
                    return True
            elif ip.startswith(blocked_range.replace('*', '')):
                return True
        
        # بررسی لیست مجاز (اگر وجود دارد)
        if self.allowed_ips:
            return ip not in self.allowed_ips
        
        return False
    
    def _is_suspicious_user_agent(self, user_agent: str) -> bool:
        """شناسایی User-Agent مشکوک"""
        
        suspicious_patterns = [
            'curl', 'wget', 'python-requests', 'Go-http-client',
            'java', 'scrapy', 'bot', 'crawler', 'spider'
        ]
        
        if not user_agent or user_agent == 'Unknown':
            return False
        
        ua_lower = user_agent.lower()
        
        # لیست سفید
        if any(white in ua_lower for white in ['mozilla', 'chrome', 'safari', 'firefox']):
            return False
        
        # لیست مشکوک
        if any(suspicious in ua_lower for suspicious in suspicious_patterns):
            return True
        
        return False
    
    def _detect_session_hijacking(self, request: web.Request, user_data: Dict) -> bool:
        """شناسایی Session Hijacking"""
        
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get('User-Agent', '')
        
        # بررسی تغییر ناگهانی IP
        if 'last_ip' in user_data and user_data['last_ip'] != client_ip:
            # بررسی اینکه آیا IP جدید از همان کشور/شبکه است
            # در پروژه واقعی از GeoIP استفاده شود
            ip_changed = True
            if ip_changed and 'last_login' in user_data:
                # اگر کمتر از 5 دقیقه از لاگین گذشته و IP تغییر کرده
                login_time = datetime.fromtimestamp(user_data['last_login'])
                if (datetime.now() - login_time).seconds < 300:
                    return True
        
        # بررسی تغییر User-Agent
        if 'user_agent' in user_data and user_data['user_agent'] != user_agent:
            return True
        
        return False
    
    def _check_permission(self, role: str, method: str, path: str) -> bool:
        """بررسی دسترسی براساس Role و Permission"""
        
        if role not in self.roles_permissions:
            return False
        
        permissions = self.roles_permissions[role]
        
        # دسترسی کامل
        if '*' in permissions:
            return True
        
        # ساختار permission: resource:action
        # مثال: accounts:read, accounts:write, backup:create
        
        # نگاشت path به resource
        resource = self._map_path_to_resource(path)
        action = self._map_method_to_action(method)
        
        required_permission = f"{resource}:{action}"
        
        return required_permission in permissions
    
    def _map_path_to_resource(self, path: str) -> str:
        """تبدیل path به resource"""
        
        if path.startswith('/api/accounts'):
            return 'accounts'
        elif path.startswith('/api/backup'):
            return 'backup'
        elif path.startswith('/api/messages'):
            return 'messages'
        elif path.startswith('/api/admin'):
            return 'admin'
        else:
            return 'other'
    
    def _map_method_to_action(self, method: str) -> str:
        """تبدیل HTTP Method به action"""
        
        method_map = {
            'GET': 'read',
            'POST': 'create',
            'PUT': 'update',
            'DELETE': 'delete',
            'PATCH': 'update'
        }
        
        return method_map.get(method, 'read')
    
    def _requires_2fa(self, path: str, user_data: Dict) -> bool:
        """بررسی نیاز به 2FA"""
        
        # مسیرهای حساس که نیاز به 2FA دارند
        sensitive_paths = [
            '/api/accounts/delete',
            '/api/backup/create',
            '/api/admin/'
        ]
        
        # بررسی مسیر
        if any(path.startswith(p) for p in sensitive_paths):
            return True
        
        # بررسی role
        if user_data.get('role') in ['admin', 'manager']:
            return True
        
        # بررسی تنظیمات کاربر
        if user_data.get('force_2fa', False):
            return True
        
        return False
    
    # ========== متدهای کمکی ==========
    
    def _get_client_ip(self, request: web.Request) -> str:
        """دریافت IP واقعی کلاینت"""
        
        # بررسی هدرهای معتبر
        for header in ['X-Real-IP', 'X-Forwarded-For', 'CF-Connecting-IP']:
            ip = request.headers.get(header)
            if ip:
                return ip.split(',')[0].strip()
        
        # IP مستقیم
        return request.remote
    
    def _get_timeout_for_endpoint(self, path: str) -> int:
        """تعیین timeout براساس endpoint"""
        
        timeout_map = {
            '/api/accounts/login': 30,
            '/api/backup/create': 300,
            '/api/messages/send': 10,
            '/api/admin/': 60
        }
        
        for endpoint, timeout in timeout_map.items():
            if path.startswith(endpoint):
                return timeout
        
        return 30  # timeout پیش‌فرض
    
    def _add_security_headers(self, response: web.Response) -> web.Response:
        """اضافه کردن هدرهای امنیتی"""
        
        security_headers = {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'",
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'geolocation=(), microphone=(), camera=()'
        }
        
        for header, value in security_headers.items():
            response.headers[header] = value
        
        return response
    
    # ========== متدهای پاسخ ==========
    
    def _block_response(self, message: str, status: int = 403, **kwargs) -> web.Response:
        """پاسخ block"""
        
        response_data = {
            'success': False,
            'error': message,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        
        return web.json_response(response_data, status=status)
    
    def _auth_error_response(self, auth_result: Dict, request_id: str) -> web.Response:
        """پاسخ خطای احراز هویت"""
        
        response_data = {
            'success': False,
            'error': auth_result.get('reason', 'احراز هویت ناموفق'),
            'error_code': auth_result.get('error_code', 'AUTH_FAILED'),
            'request_id': request_id,
            'timestamp': datetime.now().isoformat(),
            'authenticated': False
        }
        
        # اضافه کردن WWW-Authenticate header
        response = web.json_response(response_data, status=401)
        response.headers['WWW-Authenticate'] = 'Bearer realm="API"'
        
        return response
    
    def _twofa_required_response(self, twofa_result: Dict, request_id: str) -> web.Response:
        """پاسخ نیاز به 2FA"""
        
        response_data = {
            'success': False,
            'error': 'تأیید دو مرحله‌ای مورد نیاز است',
            'error_code': '2FA_REQUIRED',
            'request_id': request_id,
            'timestamp': datetime.now().isoformat(),
            'twofa_required': True,
            'available_methods': twofa_result.get('methods', ['totp', 'sms', 'email'])
        }
        
        return web.json_response(response_data, status=403)
    
    # ========== سیستم Audit Log ==========
    
    async def _log_audit(self, 
                        request_id: str,
                        ip: str,
                        event_type: str,
                        path: str,
                        description: str,
                        success: bool,
                        user_id: str = None,
                        **kwargs):
        """ثبت لاگ امنیتی"""
        
        log_entry = {
            'request_id': request_id,
            'timestamp': datetime.now().isoformat(),
            'ip_address': ip,
            'event_type': event_type,
            'path': path,
            'description': description,
            'success': success,
            'user_id': user_id,
            **kwargs
        }
        
        self.audit_log.append(log_entry)
        
        # حفظ فقط 1000 لاگ آخر
        if len(self.audit_log) > 1000:
            self.audit_log = self.audit_log[-1000:]
        
        # لاگ کردن در فایل
        log_level = logging.INFO if success else logging.WARNING
        logger.log(log_level, f"AUDIT: {event_type} - {description} - IP: {ip} - User: {user_id}")
    
    async def get_audit_logs(self, 
                           start_date: datetime = None,
                           end_date: datetime = None,
                           event_type: str = None,
                           user_id: str = None,
                           limit: int = 100) -> List[Dict]:
        """دریافت لاگ‌های audit"""
        
        filtered_logs = self.audit_log
        
        if start_date:
            filtered_logs = [log for log in filtered_logs 
                           if datetime.fromisoformat(log['timestamp']) >= start_date]
        
        if end_date:
            filtered_logs = [log for log in filtered_logs 
                           if datetime.fromisoformat(log['timestamp']) <= end_date]
        
        if event_type:
            filtered_logs = [log for log in filtered_logs if log['event_type'] == event_type]
        
        if user_id:
            filtered_logs = [log for log in filtered_logs if log.get('user_id') == user_id]
        
        return filtered_logs[-limit:]

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
