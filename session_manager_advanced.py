#!/usr/bin/env python3
# session_manager_advanced.py - سیستم مدیریت session ایمن و پیشرفته برای UserBot
# Version: 2.0.0

import asyncio
import json
import os
import hashlib
import secrets
import time
import re
import base64
import hmac
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pickle
import struct
import threading
from concurrent.futures import ThreadPoolExecutor
import aiofiles
import psutil
import socket
import uuid
from contextlib import asynccontextmanager

# تنظیمات لاگ پیشرفته
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - [%(levelname)s] - [Thread:%(thread)d] - %(message)s',
    handlers=[
        RotatingFileHandler(
            'secure_session_manager.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# مدل‌های داده (Data Models)
# ============================================

class SessionStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    ERROR = "error"
    PENDING = "pending"

class DeviceType(Enum):
    ANDROID = "android"
    IOS = "ios"
    DESKTOP = "desktop"
    WEB = "web"

@dataclass
class DeviceInfo:
    device_model: str
    system_version: str
    app_version: str
    lang_code: str = "en"
    system_lang_code: str = "en-US"
    device_type: DeviceType = DeviceType.ANDROID
    manufacturer: str = ""
    screen_resolution: str = "1080x1920"
    dpi: int = 420
    ram_size: int = 4096  # MB
    storage_size: int = 128  # GB
    cpu_cores: int = 8
    unique_id: str = ""

@dataclass
class LocationInfo:
    ip: str
    country: str
    city: str
    timezone: str = "UTC"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    isp: str = ""
    asn: str = ""
    proxy_type: Optional[str] = None

@dataclass
class SessionMetrics:
    requests_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    average_response_time: float = 0.0
    last_request_time: Optional[datetime] = None
    consecutive_errors: int = 0
    health_score: float = 100.0  # امتیاز سلامت (0-100)

@dataclass
class SessionConfig:
    max_sessions: int = 5
    session_lifetime_hours: int = 168  # 7 days
    auto_rotate: bool = True
    rotate_after_errors: int = 5
    rotate_after_requests: int = 1000
    backup_count: int = 10
    encryption_enabled: bool = True
    compression_enabled: bool = True
    geo_diversity: bool = True
    device_rotation: bool = True
    use_proxy_pool: bool = False
    enable_metrics: bool = True
    enable_health_check: bool = True
    session_timeout_seconds: int = 300
    max_concurrent_requests: int = 10
    rate_limit_per_minute: int = 60

# ============================================
# سیستم رمزنگاری پیشرفته
# ============================================

class AdvancedEncryption:
    """سیستم رمزنگاری پیشرفته با چند لایه امنیتی"""
    
    def __init__(self, master_key: Optional[str] = None):
        self.master_key = master_key or self._generate_master_key()
        self.derived_keys = {}
        
    @staticmethod
    def _generate_master_key() -> str:
        """تولید کلید اصلی از entropy سیستم"""
        system_entropy = str(psutil.cpu_percent()) + str(psutil.virtual_memory().available)
        process_entropy = str(os.getpid()) + str(threading.get_ident())
        time_entropy = str(time.time_ns())
        
        combined = system_entropy + process_entropy + time_entropy
        return hashlib.sha512(combined.encode()).hexdigest()
    
    def derive_key(self, salt: bytes, purpose: str = "session") -> bytes:
        """استخراج کلید از کلید اصلی با PBKDF2"""
        if purpose in self.derived_keys:
            return self.derived_keys[purpose]
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(self.master_key.encode())
        self.derived_keys[purpose] = key
        return key
    
    def encrypt_data(self, data: bytes, session_id: str) -> bytes:
        """رمزگذاری داده با AES-GCM"""
        salt = os.urandom(16)
        key = self.derive_key(salt, f"enc_{session_id}")
        
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        
        encrypted = aesgcm.encrypt(nonce, data, None)
        
        # ترکیب salt + nonce + encrypted
        result = salt + nonce + encrypted
        return base64.b64encode(result)
    
    def decrypt_data(self, encrypted_data: bytes, session_id: str) -> bytes:
        """رمزگشایی داده"""
        try:
            data = base64.b64decode(encrypted_data)
            salt = data[:16]
            nonce = data[16:28]
            ciphertext = data[28:]
            
            key = self.derive_key(salt, f"enc_{session_id}")
            aesgcm = AESGCM(key)
            
            return aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
    
    def create_hmac(self, data: bytes, session_id: str) -> str:
        """ایجاد HMAC برای احراز اصالت داده"""
        salt = os.urandom(16)
        key = self.derive_key(salt, f"hmac_{session_id}")
        
        h = hmac.new(key, data, hashlib.sha256)
        return base64.b64encode(salt + h.digest()).decode()

# ============================================
# سیستم تشخیص ناهنجاری (Anomaly Detection)
# ============================================

class AnomalyDetector:
    """سیستم تشخیص رفتار غیرعادی در session‌ها"""
    
    def __init__(self):
        self.behavior_profiles = {}
        self.anomaly_threshold = 0.8
        self.learning_rate = 0.1
        
    def create_profile(self, session_id: str, initial_behavior: Dict):
        """ایجاد پروفایل رفتاری برای session"""
        self.behavior_profiles[session_id] = {
            'request_patterns': initial_behavior.get('request_patterns', {}),
            'timing_stats': initial_behavior.get('timing_stats', {}),
            'geolocation_history': [],
            'device_consistency': True,
            'updated_at': datetime.now()
        }
    
    def detect_anomalies(self, session_id: str, current_behavior: Dict) -> List[str]:
        """تشخیص ناهنجاری‌های رفتاری"""
        if session_id not in self.behavior_profiles:
            return []
        
        profile = self.behavior_profiles[session_id]
        anomalies = []
        
        # بررسی الگوی درخواست‌ها
        request_anomaly = self._check_request_pattern(profile, current_behavior)
        if request_anomaly:
            anomalies.append(request_anomaly)
        
        # بررسی زمان‌بندی
        timing_anomaly = self._check_timing_anomaly(profile, current_behavior)
        if timing_anomaly:
            anomalies.append(timing_anomaly)
        
        # بررسی موقعیت جغرافیایی
        geo_anomaly = self._check_geolocation_anomaly(profile, current_behavior)
        if geo_anomaly:
            anomalies.append(geo_anomaly)
        
        # به‌روزرسانی پروفایل
        if not anomalies:
            self._update_profile(session_id, current_behavior)
        
        return anomalies
    
    def _check_request_pattern(self, profile: Dict, current: Dict) -> Optional[str]:
        """بررسی تغییرات ناگهانی در الگوی درخواست‌ها"""
        # پیاده‌سازی منطق تشخیص
        return None
    
    def _check_timing_anomaly(self, profile: Dict, current: Dict) -> Optional[str]:
        """بررسی انحراف در زمان‌بندی"""
        return None
    
    def _check_geolocation_anomaly(self, profile: Dict, current: Dict) -> Optional[str]:
        """بررسی جابجایی جغرافیایی غیرممکن"""
        return None
    
    def _update_profile(self, session_id: str, new_behavior: Dict):
        """به‌روزرساری تدریجی پروفایل"""
        pass

# ============================================
# سیستم مدیریت Session پیشرفته
# ============================================

class AdvancedSessionManager:
    """
    سیستم مدیریت session پیشرفته با قابلیت‌های:
    - رمزنگاری چندلایه
    - تشخیص ناهنجاری
    - مدیریت proxy پویا
    - مانیتورینگ سلامت
    - بازیابی خودکار
    - مقیاس‌پذیری
    """
    
    def __init__(self, 
                 base_dir: Path = Path("secure_sessions"),
                 config: Optional[SessionConfig] = None):
        
        self.base_dir = Path(base_dir)
        self.sessions_dir = self.base_dir / "sessions"
        self.backup_dir = self.base_dir / "backups"
        self.cache_dir = self.base_dir / "cache"
        self.logs_dir = self.base_dir / "logs"
        self.metadata_file = self.base_dir / "metadata.enc"
        
        # ایجاد ساختار پوشه‌ها
        self._create_directory_structure()
        
        # سیستم‌های اصلی
        self.encryption = AdvancedEncryption()
        self.config = config or SessionConfig()
        self.anomaly_detector = AnomalyDetector()
        
        # ذخیره‌سازی داده‌ها
        self.metadata = self._load_encrypted_metadata()
        self.active_connections = {}
        self.session_cache = {}
        self.rate_limiters = {}
        
        # مدیریت Thread و Async
        self.lock = asyncio.Lock()
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        self.health_check_task = None
        
        # مانیتورینگ
        self.metrics = {
            'total_requests': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'session_rotations': 0,
            'anomalies_detected': 0,
            'start_time': datetime.now()
        }
        
        # شروع سیستم
        self._start_health_monitor()
        logger.info(f"AdvancedSessionManager initialized at {self.base_dir}")
    
    def _create_directory_structure(self):
        """ایجاد ساختار پوشه‌های امن"""
        directories = [
            self.base_dir,
            self.sessions_dir,
            self.backup_dir,
            self.cache_dir,
            self.logs_dir,
            self.base_dir / "temp",
            self.base_dir / "reports"
        ]
        
        for directory in directories:
            directory.mkdir(exist_ok=True, parents=True)
            # تنظیم مجوزهای امنیتی
            if os.name != 'nt':  # غیر از ویندوز
                os.chmod(directory, 0o700)
    
    def _load_encrypted_metadata(self) -> Dict:
        """بارگذاری متادیتای رمزگذاری شده"""
        if not self.metadata_file.exists():
            return {
                'sessions': {},
                'active_sessions': [],
                'rotation_history': [],
                'error_stats': {},
                'user_mapping': {},
                'created_at': datetime.now().isoformat(),
                'version': '2.0.0'
            }
        
        try:
            async with aiofiles.open(self.metadata_file, 'rb') as f:
                encrypted_data = await f.read()
            
            decrypted = self.encryption.decrypt_data(encrypted_data, "metadata")
            return json.loads(decrypted.decode('utf-8'))
        
        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return self._load_encrypted_metadata()  # بازگشت به مقدار پیش‌فرض
    
    async def _save_encrypted_metadata(self):
        """ذخیره متادیتای رمزگذاری شده"""
        async with self.lock:
            try:
                data = json.dumps(self.metadata, ensure_ascii=False, default=str).encode('utf-8')
                encrypted = self.encryption.encrypt_data(data, "metadata")
                
                # ذخیره در فایل موقت و سپس جابجایی (atomic write)
                temp_file = self.metadata_file.with_suffix('.tmp')
                async with aiofiles.open(temp_file, 'wb') as f:
                    await f.write(encrypted)
                
                # جابجایی اتمی
                temp_file.replace(self.metadata_file)
                
            except Exception as e:
                logger.error(f"Failed to save metadata: {e}")
                await asyncio.sleep(1)
                await self._save_encrypted_metadata()  # تلاش مجدد
    
    def _generate_session_id(self) -> str:
        """تولید شناسه session منحصربه‌فرد"""
        timestamp = int(time.time() * 1000)
        random_bits = secrets.randbits(64)
        system_id = hashlib.md5(socket.gethostname().encode()).hexdigest()[:8]
        
        return f"ses_{timestamp}_{random_bits:016x}_{system_id}"
    
    def _generate_device_info(self, session_num: int = 0) -> DeviceInfo:
        """تولید اطلاعات دستگاه هوشمند"""
        android_devices = [
            DeviceInfo(
                device_model="Samsung Galaxy S24 Ultra",
                system_version="Android 14",
                app_version="10.5.0",
                device_type=DeviceType.ANDROID,
                manufacturer="Samsung",
                screen_resolution="1440x3088",
                dpi=500,
                ram_size=12000,
                storage_size=512,
                cpu_cores=8,
                unique_id=f"AND-{secrets.token_hex(8)}"
            ),
            DeviceInfo(
                device_model="Google Pixel 8 Pro",
                system_version="Android 14",
                app_version="10.4.2",
                device_type=DeviceType.ANDROID,
                manufacturer="Google",
                screen_resolution="1344x2992",
                dpi=489,
                ram_size=12000,
                storage_size=256,
                cpu_cores=9,
                unique_id=f"AND-{secrets.token_hex(8)}"
            ),
        ]
        
        ios_devices = [
            DeviceInfo(
                device_model="iPhone 15 Pro Max",
                system_version="iOS 17.2",
                app_version="10.5.1",
                device_type=DeviceType.IOS,
                manufacturer="Apple",
                screen_resolution="1290x2796",
                dpi=460,
                ram_size=8000,
                storage_size=512,
                cpu_cores=6,
                unique_id=f"IOS-{secrets.token_hex(8)}"
            ),
        ]
        
        if self.config.device_rotation:
            all_devices = android_devices + ios_devices
            return all_devices[session_num % len(all_devices)]
        
        return android_devices[0]
    
    def _generate_location_info(self) -> Optional[LocationInfo]:
        """تولید اطلاعات موقعیت جغرافیایی پویا"""
        if not self.config.geo_diversity:
            return None
        
        locations = [
            LocationInfo(
                ip=f"185.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}",
                country="Germany",
                city="Frankfurt",
                timezone="Europe/Berlin",
                latitude=50.1109,
                longitude=8.6821,
                isp="Deutsche Telekom",
                asn="AS3320"
            ),
            LocationInfo(
                ip=f"104.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}",
                country="USA",
                city="New York",
                timezone="America/New_York",
                latitude=40.7128,
                longitude=-74.0060,
                isp="DigitalOcean",
                asn="AS14061"
            ),
            LocationInfo(
                ip=f"5.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}",
                country="Iran",
                city="Tehran",
                timezone="Asia/Tehran",
                latitude=35.6892,
                longitude=51.3890,
                isp="Iran Telecommunication Company",
                asn="AS58224"
            ),
        ]
        
        return secrets.choice(locations)
    
    async def create_session(self, 
                           api_id: int, 
                           api_hash: str,
                           phone: Optional[str] = None,
                           user_id: Optional[int] = None,
                           custom_device: Optional[DeviceInfo] = None) -> Dict[str, Any]:
        """
        ایجاد session جدید با تمامی حفاظت‌ها
        """
        async with self.lock:
            try:
                # اعتبارسنجی اولیه
                await self._validate_create_request(api_id, api_hash, user_id)
                
                # تولید شناسه و مسیر
                session_id = self._generate_session_id()
                session_path = self.sessions_dir / f"{session_id}.ses"
                
                # اطلاعات session
                session_info = {
                    'session_id': session_id,
                    'path': str(session_path),
                    'api_id': api_id,
                    'api_hash': api_hash,
                    'phone': self._hash_phone(phone) if phone else None,
                    'user_id': user_id,
                    'created_at': datetime.now().isoformat(),
                    'last_used': None,
                    'status': SessionStatus.ACTIVE.value,
                    'device_info': asdict(custom_device or self._generate_device_info()),
                    'location_info': asdict(self._generate_location_info()) if self.config.geo_diversity else {},
                    'metrics': asdict(SessionMetrics()),
                    'tags': [],
                    'custom_data': {},
                    'security_flags': {
                        'requires_2fa': False,
                        'last_password_change': None,
                        'trusted_device': False
                    }
                }
                
                # ذخیره در متادیتا
                self.metadata['sessions'][session_id] = session_info
                
                # نگاشت کاربر
                if user_id:
                    if user_id not in self.metadata['user_mapping']:
                        self.metadata['user_mapping'][user_id] = []
                    self.metadata['user_mapping'][user_id].append(session_id)
                
                # ذخیره متادیتا
                await self._save_encrypted_metadata()
                
                # ایجاد پروفایل رفتاری
                self.anomaly_detector.create_profile(session_id, {})
                
                logger.info(f"Session created: {session_id} for user {user_id}")
                self.metrics['successful_operations'] += 1
                
                return session_info
                
            except Exception as e:
                logger.error(f"Failed to create session: {e}")
                self.metrics['failed_operations'] += 1
                raise
    
    async def _validate_create_request(self, api_id: int, api_hash: str, user_id: Optional[int]):
        """اعتبارسنجی درخواست ایجاد session"""
        
        # بررسی محدودیت تعداد session
        if user_id:
            user_sessions = self.metadata['user_mapping'].get(user_id, [])
            if len(user_sessions) >= self.config.max_sessions:
                raise ValueError(f"User {user_id} has reached maximum session limit")
        
        # بررسی فرمت api_id و api_hash
        if not isinstance(api_id, int) or api_id <= 0:
            raise ValueError("Invalid API ID")
        
        if not isinstance(api_hash, str) or len(api_hash) < 10:
            raise ValueError("Invalid API Hash")
    
    def _hash_phone(self, phone: str) -> str:
        """هش کردن شماره تلفن با salt"""
        salt = os.urandom(16)
        phone_bytes = phone.encode()
        
        # استفاده از PBKDF2 برای هش کردن
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        key = kdf.derive(phone_bytes)
        return base64.b64encode(salt + key).decode()
    
    async def rotate_sessions(self, force: bool = False, reason: str = "auto"):
        """
        چرخش هوشمند session‌ها با الگوریتم پیشرفته
        """
        async with self.lock:
            try:
                active_sessions = [
                    s for s in self.metadata['sessions'].values()
                    if s['status'] == SessionStatus.ACTIVE.value
                ]
                
                if not active_sessions:
                    logger.warning("No active sessions to rotate")
                    return
                
                # الگوریتم انتخاب session برای چرخش
                session_to_rotate = self._select_session_for_rotation(active_sessions)
                
                if not session_to_rotate:
                    logger.debug("No session needs rotation")
                    return
                
                session_id = session_to_rotate['session_id']
                
                # تغییر وضعیت session فعلی
                self.metadata['sessions'][session_id]['status'] = SessionStatus.INACTIVE.value
                self.metadata['sessions'][session_id]['rotated_at'] = datetime.now().isoformat()
                
                # پشتیبان‌گیری
                await self._backup_session_advanced(session_id)
                
                # انتخاب session جدید (یا ایجاد)
                new_session_id = await self._select_or_create_new_session(
                    session_to_rotate, 
                    active_sessions
                )
                
                # به‌روزرسانی متادیتا
                rotation_record = {
                    'timestamp': datetime.now().isoformat(),
                    'from_session': session_id,
                    'to_session': new_session_id,
                    'reason': reason,
                    'metrics_before': session_to_rotate.get('metrics', {}),
                    'triggered_by': 'system' if not force else 'manual'
                }
                
                self.metadata['rotation_history'].append(rotation_record)
                if len(self.metadata['rotation_history']) > 1000:
                    self.metadata['rotation_history'] = self.metadata['rotation_history'][-1000:]
                
                await self._save_encrypted_metadata()
                
                logger.info(f"Session rotated: {session_id} -> {new_session_id}")
                self.metrics['session_rotations'] += 1
                
                return new_session_id
                
            except Exception as e:
                logger.error(f"Session rotation failed: {e}")
                raise
    
    def _select_session_for_rotation(self, active_sessions: List[Dict]) -> Optional[Dict]:
        """الگوریتم انتخاب session برای چرخش"""
        
        now = datetime.now()
        selected_session = None
        highest_score = 0
        
        for session in active_sessions:
            score = 0
            
            # امتیاز بر اساس خطاها
            metrics = session.get('metrics', {})
            error_count = metrics.get('error_count', 0)
            if error_count >= self.config.rotate_after_errors:
                score += 50
            
            # امتیاز بر اساس تعداد درخواست‌ها
            requests_count = metrics.get('requests_count', 0)
            if requests_count >= self.config.rotate_after_requests:
                score += 30
            
            # امتیاز بر اساس عمر session
            created_at = datetime.fromisoformat(session['created_at'])
            age_hours = (now - created_at).total_seconds() / 3600
            if age_hours >= self.config.session_lifetime_hours:
                score += 40
            
            # امتیاز بر اساس سلامت
            health_score = metrics.get('health_score', 100)
            if health_score < 50:
                score += 60
            
            # انتخاب session با بالاترین امتیاز
            if score > highest_score:
                highest_score = score
                selected_session = session
        
        return selected_session if highest_score >= 30 else None
    
    async def _backup_session_advanced(self, session_id: str):
        """پشتیبان‌گیری پیشرفته از session"""
        try:
            session_info = self.metadata['sessions'].get(session_id)
            if not session_info:
                return
            
            session_path = Path(session_info['path'])
            if not session_path.exists():
                return
            
            # خواندن و رمزگذاری
            async with aiofiles.open(session_path, 'rb') as f:
                data = await f.read()
            
            encrypted = self.encryption.encrypt_data(data, session_id)
            
            # فشرده‌سازی
            if self.config.compression_enabled:
                compressed = zlib.compress(encrypted, level=9)
            else:
                compressed = encrypted
            
            # ذخیره پشتیبان با timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup_name = f"{session_id}_{timestamp}.backup"
            backup_path = self.backup_dir / backup_name
            
            async with aiofiles.open(backup_path, 'wb') as f:
                await f.write(compressed)
            
            # اضافه کردن metadata به پشتیبان
            backup_meta = {
                'session_id': session_id,
                'backup_time': timestamp,
                'size_bytes': len(compressed),
                'checksum': hashlib.sha256(compressed).hexdigest(),
                'encryption_version': '2.0'
            }
            
            meta_path = backup_path.with_suffix('.meta')
            async with aiofiles.open(meta_path, 'w') as f:
                await f.write(json.dumps(backup_meta, indent=2))
            
            # مدیریت تعداد پشتیبان‌ها
            await self._cleanup_old_backups(session_id)
            
            logger.debug(f"Backup created: {backup_name}")
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
    
    async def _cleanup_old_backups(self, session_id: str):
        """پاکسازی پشتیبان‌های قدیمی"""
        try:
            backups = list(self.backup_dir.glob(f"{session_id}_*.backup"))
            backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            if len(backups) > self.config.backup_count:
                for old_backup in backups[self.config.backup_count:]:
                    # حذف فایل پشتیبان و metadata مربوطه
                    old_backup.unlink()
                    meta_file = old_backup.with_suffix('.meta')
                    if meta_file.exists():
                        meta_file.unlink()
        
        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
    
    async def _select_or_create_new_session(self, old_session: Dict, active_sessions: List[Dict]) -> str:
        """انتخاب یا ایجاد session جدید"""
        
        # اولویت: انتخاب session غیرفعال موجود
        inactive_sessions = [
            s for s in self.metadata['sessions'].values()
            if s['status'] == SessionStatus.INACTIVE.value
            and s.get('user_id') == old_session.get('user_id')
        ]
        
        if inactive_sessions:
            # انتخاب session با کمترین خطا
            best_session = min(inactive_sessions, 
                             key=lambda x: x.get('metrics', {}).get('error_count', 0))
            best_session['status'] = SessionStatus.ACTIVE.value
            return best_session['session_id']
        
        # اگر session غیرفعالی نبود، ایجاد جدید
        new_session = await self.create_session(
            api_id=old_session['api_id'],
            api_hash=old_session['api_hash'],
            phone=None,  # شماره از session قدیمی خوانده می‌شود
            user_id=old_session.get('user_id')
        )
        
        return new_session['session_id']
    
    async def get_session(self, session_id: str, update_stats: bool = True) -> Optional[Dict]:
        """دریافت اطلاعات session با کش کردن"""
        
        # بررسی کش
        if session_id in self.session_cache:
            cached = self.session_cache[session_id]
            if time.time() - cached['timestamp'] < 30:  # 30 ثانیه کش
                return cached['data']
        
        # دریافت از متادیتا
        session_info = self.metadata['sessions'].get(session_id)
        if not session_info:
            return None
        
        # به‌روزرسانی آمار
        if update_stats:
            session_info['last_accessed'] = datetime.now().isoformat()
            if 'access_count' not in session_info:
                session_info['access_count'] = 0
            session_info['access_count'] += 1
            
            await self._save_encrypted_metadata()
        
        # ذخیره در کش
        self.session_cache[session_id] = {
            'data': session_info,
            'timestamp': time.time()
        }
        
        return session_info
    
    async def update_session_metrics(self, session_id: str, success: bool, 
                                   response_time: float = 0.0, 
                                   bytes_sent: int = 0, 
                                   bytes_received: int = 0):
        """به‌روزرسانی متریک‌های session"""
        async with self.lock:
            try:
                if session_id not in self.metadata['sessions']:
                    return
                
                session = self.metadata['sessions'][session_id]
                if 'metrics' not in session:
                    session['metrics'] = asdict(SessionMetrics())
                
                metrics = session['metrics']
                
                # به‌روزرسانی مقادیر
                metrics['requests_count'] += 1
                
                if success:
                    metrics['success_count'] += 1
                    metrics['consecutive_errors'] = 0
                else:
                    metrics['error_count'] += 1
                    metrics['consecutive_errors'] += 1
                
                metrics['total_bytes_sent'] += bytes_sent
                metrics['total_bytes_received'] += bytes_received
                
                # محاسبه میانگین زمان پاسخ
                if response_time > 0:
                    old_avg = metrics['average_response_time']
                    count = metrics['success_count']
                    metrics['average_response_time'] = (
                        (old_avg * (count - 1) + response_time) / count
                        if count > 1 else response_time
                    )
                
                metrics['last_request_time'] = datetime.now().isoformat()
                
                # محاسبه امتیاز سلامت
                metrics['health_score'] = self._calculate_health_score(metrics)
                
                # بررسی نیاز به چرخش
                if (metrics['consecutive_errors'] >= 3 or 
                    metrics['health_score'] < 30):
                    session['status'] = SessionStatus.ERROR.value
                    await self.rotate_sessions(reason="health_check")
                
                await self._save_encrypted_metadata()
                
            except Exception as e:
                logger.error(f"Failed to update metrics: {e}")
    
    def _calculate_health_score(self, metrics: Dict) -> float:
        """محاسبه امتیاز سلامت session"""
        score = 100.0
        
        # کاهش بر اساس خطاها
        error_ratio = metrics.get('error_count', 0) / max(metrics.get('requests_count', 1), 1)
        if error_ratio > 0.1:  # بیش از 10% خطا
            score -= 40
        
        # کاهش بر اساس خطاهای متوالی
        consecutive_errors = metrics.get('consecutive_errors', 0)
        score -= consecutive_errors * 10
        
        # کاهش بر اساس زمان پاسخ
        avg_response = metrics.get('average_response_time', 0)
        if avg_response > 5.0:  # بیش از 5 ثانیه
            score -= 20
        
        return max(0.0, min(100.0, score))
    
    async def validate_all_sessions(self) -> Dict[str, List]:
        """اعتبارسنجی کامل تمام session‌ها"""
        results = {
            'valid': [],
            'invalid': [],
            'warning': [],
            'needs_attention': []
        }
        
        for session_id, session_info in self.metadata['sessions'].items():
            try:
                # بررسی وجود فایل
                session_path = Path(session_info['path'])
                if not session_path.exists():
                    results['invalid'].append({
                        'session_id': session_id,
                        'reason': 'File not found'
                    })
                    continue
                
                # بررسی سایز فایل
                file_size = session_path.stat().st_size
                if file_size < 100:
                    results['warning'].append({
                        'session_id': session_id,
                        'reason': f'File too small ({file_size} bytes)'
                    })
                
                # بررسی سلامت متریک‌ها
                health_score = session_info.get('metrics', {}).get('health_score', 100)
                if health_score < 50:
                    results['needs_attention'].append({
                        'session_id': session_id,
                        'reason': f'Low health score: {health_score}'
                    })
                
                # بررسی تاریخ انقضا
                created_at = datetime.fromisoformat(session_info['created_at'])
                age_days = (datetime.now() - created_at).days
                if age_days > 30:
                    results['warning'].append({
                        'session_id': session_id,
                        'reason': f'Old session ({age_days} days)'
                    })
                
                results['valid'].append(session_id)
                
            except Exception as e:
                results['invalid'].append({
                    'session_id': session_id,
                    'reason': str(e)
                })
        
        return results
    
    def _start_health_monitor(self):
        """شروع مانیتورینگ سلامت سیستم"""
        async def monitor_health():
            while True:
                try:
                    await self._perform_health_check()
                    await asyncio.sleep(60)  # هر 1 دقیقه
                except Exception as e:
                    logger.error(f"Health monitor error: {e}")
                    await asyncio.sleep(10)
        
        # شروع task مانیتورینگ
        self.health_check_task = asyncio.create_task(monitor_health())
    
    async def _perform_health_check(self):
        """انجام بررسی سلامت سیستم"""
        try:
            # بررسی استفاده از حافظه
            process = psutil.Process()
            memory_usage = process.memory_percent()
            
            if memory_usage > 80:
                logger.warning(f"High memory usage: {memory_usage:.1f}%")
                
                # پاکسازی کش
                self._cleanup_cache()
            
            # بررسی فضای دیسک
            disk_usage = psutil.disk_usage(self.base_dir).percent
            if disk_usage > 90:
                logger.warning(f"High disk usage: {disk_usage:.1f}%")
                
                # پاکسازی پشتیبان‌های قدیمی
                await self._cleanup_old_data()
            
            # بررسی تعداد session‌ها
            total_sessions = len(self.metadata['sessions'])
            if total_sessions > 100:
                logger.info(f"Total sessions: {total_sessions}")
            
            # بررسی session‌های مشکل‌دار
            validation = await self.validate_all_sessions()
            if validation['needs_attention']:
                logger.warning(f"Sessions need attention: {len(validation['needs_attention'])}")
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
    
    def _cleanup_cache(self):
        """پاکسازی کش"""
        current_time = time.time()
        to_remove = []
        
        for session_id, cache_info in self.session_cache.items():
            if current_time - cache_info['timestamp'] > 300:  # 5 دقیقه
                to_remove.append(session_id)
        
        for session_id in to_remove:
            del self.session_cache[session_id]
    
    async def _cleanup_old_data(self):
        """پاکسازی داده‌های قدیمی"""
        try:
            # پاکسازی session‌های قدیمی
            for session_id, session_info in list(self.metadata['sessions'].items()):
                created_at = datetime.fromisoformat(session_info['created_at'])
                age_days = (datetime.now() - created_at).days
                
                if (age_days > 90 and 
                    session_info['status'] != SessionStatus.ACTIVE.value):
                    
                    # حذف فایل session
                    session_path = Path(session_info['path'])
                    if session_path.exists():
                        session_path.unlink()
                    
                    # حذف از متادیتا
                    del self.metadata['sessions'][session_id]
                    
                    logger.info(f"Cleaned up old session: {session_id}")
            
            await self._save_encrypted_metadata()
            
        except Exception as e:
            logger.error(f"Data cleanup failed: {e}")
    
    async def export_comprehensive_report(self, format_type: str = "json") -> Any:
        """خروجی گزارش جامع"""
        report = {
            'report_id': str(uuid.uuid4()),
            'generated_at': datetime.now().isoformat(),
            'system_info': {
                'version': '2.0.0',
                'base_directory': str(self.base_dir),
                'total_sessions': len(self.metadata['sessions']),
                'active_sessions': len([
                    s for s in self.metadata['sessions'].values()
                    if s['status'] == SessionStatus.ACTIVE.value
                ]),
                'total_users': len(self.metadata['user_mapping']),
                'uptime_seconds': (datetime.now() - self.metrics['start_time']).total_seconds()
            },
            'metrics': self.metrics.copy(),
            'sessions_summary': [],
            'health_status': 'healthy',
            'recommendations': []
        }
        
        # جمع‌آوری اطلاعات session‌ها
        for session_id, session_info in self.metadata['sessions'].items():
            session_summary = {
                'session_id': session_id,
                'status': session_info['status'],
                'created_at': session_info['created_at'],
                'last_used': session_info.get('last_used'),
                'health_score': session_info.get('metrics', {}).get('health_score', 100),
                'request_count': session_info.get('metrics', {}).get('requests_count', 0),
                'error_count': session_info.get('metrics', {}).get('error_count', 0),
                'device': session_info.get('device_info', {}).get('device_model', 'unknown'),
                'user_id': session_info.get('user_id')
            }
            report['sessions_summary'].append(session_summary)
        
        # محاسبه وضعیت سلامت
        avg_health = sum(
            s.get('metrics', {}).get('health_score', 100) 
            for s in self.metadata['sessions'].values()
        ) / max(len(self.metadata['sessions']), 1)
        
        if avg_health < 50:
            report['health_status'] = 'critical'
        elif avg_health < 70:
            report['health_status'] = 'warning'
        
        # تولید توصیه‌ها
        if report['health_status'] == 'critical':
            report['recommendations'].append(
                "🔴 فوری: برخی session‌ها در وضعیت بحرانی هستند. چرخش session‌ها را انجام دهید."
            )
        
        if len(self.metadata['sessions']) > 50:
            report['recommendations'].append(
                "⚠️ تعداد session‌ها زیاد است. پاکسازی session‌های قدیمی را در نظر بگیرید."
            )
        
        # ذخیره گزارش در فایل
        report_path = self.base_dir / "reports" / f"report_{report['report_id'][:8]}.json"
        async with aiofiles.open(report_path, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(report, indent=2, ensure_ascii=False))
        
        if format_type == "json":
            return report
        elif format_type == "html":
            return await self._generate_html_report(report)
        else:
            return json.dumps(report, indent=2)
    
    async def _generate_html_report(self, report: Dict) -> str:
        """تولید گزارش HTML"""
        html_template = """
        <!DOCTYPE html>
        <html dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>گزارش سیستم مدیریت Session</title>
            <style>
                body { font-family: Tahoma, sans-serif; margin: 20px; }
                .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
                .section { margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }
                .critical { background: #ffebee; border-color: #f44336; }
                .warning { background: #fff3e0; border-color: #ff9800; }
                .healthy { background: #e8f5e9; border-color: #4caf50; }
                table { width: 100%; border-collapse: collapse; }
                th, td { padding: 10px; text-align: right; border: 1px solid #ddd; }
                th { background: #f5f5f5; }
                .badge { padding: 3px 8px; border-radius: 10px; color: white; font-size: 12px; }
                .badge-success { background: #4caf50; }
                .badge-warning { background: #ff9800; }
                .badge-danger { background: #f44336; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 گزارش سیستم مدیریت Session</h1>
                <p>تاریخ تولید: {generated_at}</p>
            </div>
            
            <div class="section {health_class}">
                <h2>وضعیت سیستم: {health_status}</h2>
                <p>تعداد Session‌ها: {total_sessions} | کاربران: {total_users}</p>
            </div>
            
            <div class="section">
                <h2>📈 آمار کلی</h2>
                <table>
                    <tr>
                        <th>Session‌های فعال</th>
                        <th>چرخش‌های انجام شده</th>
                        <th>عملیات موفق</th>
                        <th>عملیات ناموفق</th>
                    </tr>
                    <tr>
                        <td>{active_sessions}</td>
                        <td>{rotations}</td>
                        <td>{success_ops}</td>
                        <td>{failed_ops}</td>
                    </tr>
                </table>
            </div>
            
            <div class="section">
                <h2>🎯 توصیه‌ها</h2>
                <ul>
                    {recommendations}
                </ul>
            </div>
        </body>
        </html>
        """
        
        # پر کردن template
        health_class = ""
        if report['health_status'] == 'critical':
            health_class = 'critical'
        elif report['health_status'] == 'warning':
            health_class = 'warning'
        else:
            health_class = 'healthy'
        
        recommendations_html = ""
        for rec in report['recommendations']:
            recommendations_html += f"<li>{rec}</li>"
        
        html_content = html_template.format(
            generated_at=report['generated_at'],
            health_class=health_class,
            health_status=report['health_status'],
            total_sessions=report['system_info']['total_sessions'],
            total_users=report['system_info']['total_users'],
            active_sessions=report['system_info']['active_sessions'],
            rotations=report['metrics'].get('session_rotations', 0),
            success_ops=report['metrics'].get('successful_operations', 0),
            failed_ops=report['metrics'].get('failed_operations', 0),
            recommendations=recommendations_html
        )
        
        return html_content
    
    @asynccontextmanager
    async def session_context(self, session_id: str):
        """
        Context Manager برای مدیریت ایمن session
        """
        session_info = await self.get_session(session_id)
        if not session_info:
            raise ValueError(f"Session not found: {session_id}")
        
        try:
            # ثبت شروع استفاده
            session_info['last_activity'] = datetime.now().isoformat()
            yield session_info
            
        except Exception as e:
            # ثبت خطا
            await self.update_session_metrics(
                session_id, 
                success=False, 
                response_time=0.0
            )
            raise
            
        finally:
            # ثبت پایان استفاده موفق
            await self.update_session_metrics(
                session_id, 
                success=True, 
                response_time=0.0  # می‌توانید زمان واقعی را محاسبه کنید
            )
    
    async def close(self):
        """بستن ایمن سیستم"""
        try:
            # توقف مانیتور سلامت
            if self.health_check_task:
                self.health_check_task.cancel()
                try:
                    await self.health_check_task
                except asyncio.CancelledError:
                    pass
            
            # ذخیره نهایی متادیتا
            await self._save_encrypted_metadata()
            
            # بستن thread pool
            self.thread_pool.shutdown(wait=True)
            
            logger.info("Session manager closed successfully")
            
        except Exception as e:
            logger.error(f"Error during close: {e}")

# ============================================
# Telethon Client Wrapper پیشرفته
# ============================================

class AdvancedTelethonWrapper:
    """Wrapper پیشرفته برای Telethon با قابلیت‌های اضافه"""
    
    def __init__(self, session_manager: AdvancedSessionManager):
        self.session_manager = session_manager
        self.clients = {}  # session_id -> client
        self.connection_pool = {}
        self.reconnect_attempts = {}
        
    async def get_client(self, session_id: str, auto_reconnect: bool = True):
        """دریافت کلاینت Telethon"""
        if session_id in self.clients:
            client = self.clients[session_id]
            if client.is_connected():
                return client
            elif auto_reconnect:
                await self.reconnect_client(session_id)
                return self.clients.get(session_id)
        
        # ایجاد کلاینت جدید
        client = await self.create_client(session_id)
        if client:
            self.clients[session_id] = client
            return client
        
        return None
    
    async def create_client(self, session_id: str):
        """ایجاد کلاینت Telethon جدید"""
        try:
            session_info = await self.session_manager.get_session(session_id)
            if not session_info:
                logger.error(f"Session not found: {session_id}")
                return None
            
            from telethon import TelegramClient
            from telethon.network import ConnectionTcpFull
            
            # تنظیمات اتصال پیشرفته
            client = TelegramClient(
                session=session_info['path'],
                api_id=session_info['api_id'],
                api_hash=session_info['api_hash'],
                device_model=session_info['device_info']['device_model'],
                system_version=session_info['device_info']['system_version'],
                app_version=session_info['device_info']['app_version'],
                lang_code=session_info['device_info']['lang_code'],
                system_lang_code=session_info['device_info']['system_lang_code'],
                connection=ConnectionTcpFull,
                use_ipv6=False,
                proxy=None,  # می‌توانید proxy اضافه کنید
                timeout=30,
                request_retries=3,
                connection_retries=3,
                auto_reconnect=True
            )
            
            # اتصال
            await client.connect()
            
            # بررسی اتصال
            if not await client.is_user_authorized():
                logger.warning(f"Session {session_id} is not authorized")
                return None
            
            logger.info(f"Telethon client created for session: {session_id}")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create client: {e}")
            await self.session_manager.update_session_metrics(
                session_id, 
                success=False
            )
            return None
    
    async def reconnect_client(self, session_id: str, max_attempts: int = 3):
        """اتصال مجدد کلاینت"""
        if session_id not in self.reconnect_attempts:
            self.reconnect_attempts[session_id] = 0
        
        attempts = self.reconnect_attempts[session_id]
        if attempts >= max_attempts:
            logger.error(f"Max reconnect attempts reached for {session_id}")
            return False
        
        try:
            # حذف کلاینت قدیمی
            if session_id in self.clients:
                try:
                    await self.clients[session_id].disconnect()
                except:
                    pass
                del self.clients[session_id]
            
            # ایجاد کلاینت جدید
            client = await self.create_client(session_id)
            if client:
                self.clients[session_id] = client
                self.reconnect_attempts[session_id] = 0
                return True
            else:
                self.reconnect_attempts[session_id] += 1
                return False
                
        except Exception as e:
            logger.error(f"Reconnect failed: {e}")
            self.reconnect_attempts[session_id] += 1
            return False
    
    async def execute_with_retry(self, session_id: str, coroutine_func: Callable, 
                               max_retries: int = 3, use_rotation: bool = True):
        """
        اجرای عملیات با قابلیت تلاش مجدد و چرخش خودکار
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                client = await self.get_client(session_id)
                if not client:
                    raise ConnectionError("Client not available")
                
                # اجرای عملیات
                start_time = time.time()
                result = await coroutine_func(client)
                response_time = time.time() - start_time
                
                # ثبت موفقیت
                await self.session_manager.update_session_metrics(
                    session_id,
                    success=True,
                    response_time=response_time
                )
                
                return result
                
            except Exception as e:
                last_error = e
                logger.error(f"Attempt {attempt + 1} failed: {e}")
                
                # ثبت خطا
                await self.session_manager.update_session_metrics(
                    session_id,
                    success=False
                )
                
                # تصمیم‌گیری برای اقدام بعدی
                should_rotate = any([
                    "FloodWaitError" in str(e),
                    "AuthKeyError" in str(e),
                    "SessionRevokedError" in str(e),
                    attempt >= 1 and use_rotation
                ])
                
                if should_rotate and attempt < max_retries - 1:
                    logger.info("Rotating session and retrying...")
                    
                    # چرخش session
                    new_session_id = await self.session_manager.rotate_sessions(
                        force=True,
                        reason=f"retry_after_error:{type(e).__name__}"
                    )
                    
                    if new_session_id and new_session_id != session_id:
                        session_id = new_session_id
                    
                    # تاخیر تصاعدی
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    # تاخیر قبل از تلاش مجدد
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1)
        
        raise last_error or Exception("All retry attempts failed")
    
    async def close_all(self):
        """بستن تمامی کلاینت‌ها"""
        for session_id, client in list(self.clients.items()):
            try:
                if client.is_connected():
                    await client.disconnect()
                del self.clients[session_id]
            except Exception as e:
                logger.error(f"Error closing client {session_id}: {e}")
        
        logger.info("All Telethon clients closed")

# ============================================
# سیستم Rate Limiting پیشرفته
# ============================================

class RateLimiter:
    """سیستم محدودیت نرخ درخواست"""
    
    def __init__(self, requests_per_minute: int = 60, burst_size: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self.request_logs = {}  # session_id -> [timestamps]
        self.lock = asyncio.Lock()
    
    async def check_rate_limit(self, session_id: str) -> Tuple[bool, float]:
        """بررسی محدودیت نرخ"""
        async with self.lock:
            now = time.time()
            
            if session_id not in self.request_logs:
                self.request_logs[session_id] = []
            
            # حذف درخواست‌های قدیمی (بیش از 1 دقیقه)
            cutoff_time = now - 60
            self.request_logs[session_id] = [
                t for t in self.request_logs[session_id] 
                if t > cutoff_time
            ]
            
            # بررسی burst
            if len(self.request_logs[session_id]) >= self.burst_size:
                # محاسبه زمان انتظار
                wait_time = 60 / self.requests_per_minute
                return False, wait_time
            
            # بررسی نرخ در دقیقه
            if len(self.request_logs[session_id]) >= self.requests_per_minute:
                oldest_request = min(self.request_logs[session_id])
                wait_time = 60 - (now - oldest_request)
                return False, max(wait_time, 0)
            
            # ثبت درخواست جدید
            self.request_logs[session_id].append(now)
            return True, 0
    
    def get_session_stats(self, session_id: str) -> Dict:
        """دریافت آمار Rate Limiting"""
        if session_id not in self.request_logs:
            return {
                'requests_last_minute': 0,
                'is_limited': False,
                'burst_available': self.burst_size
            }
        
        now = time.time()
        cutoff_time = now - 60
        recent_requests = [
            t for t in self.request_logs[session_id] 
            if t > cutoff_time
        ]
        
        return {
            'requests_last_minute': len(recent_requests),
            'is_limited': len(recent_requests) >= self.requests_per_minute,
            'burst_available': max(0, self.burst_size - len(recent_requests))
        }

# ============================================
# تابع اصلی و تست
# ============================================

async def create_advanced_session_manager(config: Optional[SessionConfig] = None) -> AdvancedSessionManager:
    """ایجاد instance از Session Manager پیشرفته"""
    manager = AdvancedSessionManager(config=config)
    
    # اعتبارسنجی اولیه
    validation = await manager.validate_all_sessions()
    if validation['invalid']:
        logger.warning(f"Found {len(validation['invalid'])} invalid sessions")
    
    # پاکسازی دوره‌ای
    await manager._cleanup_old_data()
    
    # تولید گزارش اولیه
    report = await manager.export_comprehensive_report()
    logger.info(f"System initialized. Health status: {report['health_status']}")
    
    return manager

async def example_usage():
    """مثال استفاده از سیستم"""
    
    # 1. ایجاد مدیر session
    config = SessionConfig(
        max_sessions=3,
        session_lifetime_hours=24,
        auto_rotate=True,
        backup_count=5
    )
    
    manager = await create_advanced_session_manager(config)
    
    try:
        # 2. ایجاد session جدید
        session_info = await manager.create_session(
            api_id=123456,
            api_hash="your_api_hash_here",
            phone="+1234567890",
            user_id=12345
        )
        
        session_id = session_info['session_id']
        print(f"✅ Session created: {session_id}")
        
        # 3. استفاده از context manager
        async with manager.session_context(session_id) as session:
            print(f"📱 Using session: {session['device_info']['device_model']}")
            
            # 4. ایجاد wrapper برای Telethon
            wrapper = AdvancedTelethonWrapper(manager)
            
            # 5. اجرای عملیات با retry
            try:
                result = await wrapper.execute_with_retry(
                    session_id,
                    lambda client: client.get_me(),
                    max_retries=3
                )
                print(f"👤 User: {result.username}")
                
            except Exception as e:
                print(f"❌ Operation failed: {e}")
        
        # 6. دریافت گزارش
        report = await manager.export_comprehensive_report("html")
        
        if isinstance(report, dict):
            print(f"📊 System health: {report['health_status']}")
            print(f"📈 Total sessions: {report['system_info']['total_sessions']}")
        
        # 7. اعتبارسنجی
        validation = await manager.validate_all_sessions()
        print(f"🔍 Valid sessions: {len(validation['valid'])}")
        
    finally:
        # 8. بستن ایمن
        await manager.close()
        print("🔒 System closed safely")

async def stress_test():
    """تست استرس سیستم"""
    manager = await create_advanced_session_manager()
    
    tasks = []
    for i in range(10):
        task = asyncio.create_task(
            manager.create_session(
                api_id=1000000 + i,
                api_hash=f"hash_{i}",
                user_id=i
            )
        )
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    successful = [r for r in results if not isinstance(r, Exception)]
    print(f"✅ Created {len(successful)} sessions")
    
    await manager.close()

if __name__ == "__main__":
    # اجرای مثال
    print("🚀 Starting Advanced Session Manager...")
    
    # انتخاب تست
    test_mode = "example"  # "example" یا "stress"
    
    if test_mode == "example":
        asyncio.run(example_usage())
    elif test_mode == "stress":
        asyncio.run(stress_test())
    
    print("✨ Test completed!")
