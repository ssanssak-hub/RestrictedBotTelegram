#!/usr/bin/env python3
# config_server.py - مدیریت تنظیمات از سرور

import os
import json
import requests
import hashlib
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import secrets
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

@dataclass
class ServerConfig:
    """تنظیمات سرور"""
    config_url: str
    auth_token: str
    refresh_interval: int = 300  # 5 دقیقه
    cache_enabled: bool = True
    cache_path: str = ".config_cache"
    encryption_key: Optional[str] = None

class ConfigFetcher:
    """دریافت تنظیمات از سرور"""
    
    def __init__(self, server_config: ServerConfig):
        self.server_config = server_config
        self.config_cache: Dict[str, Any] = {}
        self.last_fetch: Optional[datetime] = None
        self.cipher = self._init_cipher()
        
        # ایجاد پوشه کش
        os.makedirs(self.server_config.cache_path, exist_ok=True)
        
        logger.info("ConfigFetcher initialized")
    
    def _init_cipher(self) -> Optional[Fernet]:
        """راه‌اندازی رمزگذاری"""
        if not self.server_config.encryption_key:
            return None
        
        try:
            # تولید کلید از رمز عبور
            password = self.server_config.encryption_key.encode()
            salt = b'telegram_bot_salt'  # باید امن‌تر باشد
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            return Fernet(key)
        except Exception as e:
            logger.error(f"Cipher init error: {e}")
            return None
    
    def _encrypt_data(self, data: str) -> str:
        """رمزگذاری داده‌ها"""
        if not self.cipher:
            return data
        
        try:
            encrypted = self.cipher.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Encryption error: {e}")
            return data
    
    def _decrypt_data(self, encrypted_data: str) -> str:
        """رمزگشایی داده‌ها"""
        if not self.cipher:
            return encrypted_data
        
        try:
            decoded = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = self.cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption error: {e}")
            return encrypted_data
    
    def _get_cache_key(self, config_type: str) -> str:
        """تولید کلید کش"""
        return hashlib.md5(f"{config_type}_{self.server_config.auth_token}".encode()).hexdigest()
    
    def _load_from_cache(self, config_type: str) -> Optional[Dict]:
        """بارگذاری از کش"""
        if not self.server_config.cache_enabled:
            return None
        
        cache_key = self._get_cache_key(config_type)
        cache_file = os.path.join(self.server_config.cache_path, f"{cache_key}.json")
        
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # بررسی تاریخ انقضا
                cached_at = datetime.fromisoformat(cache_data.get('cached_at', '2000-01-01'))
                if datetime.now() - cached_at < timedelta(seconds=self.server_config.refresh_interval):
                    logger.debug(f"Loading {config_type} from cache")
                    return cache_data['data']
        
        except Exception as e:
            logger.error(f"Cache load error: {e}")
        
        return None
    
    def _save_to_cache(self, config_type: str, data: Dict):
        """ذخیره در کش"""
        if not self.server_config.cache_enabled:
            return
        
        cache_key = self._get_cache_key(config_type)
        cache_file = os.path.join(self.server_config.cache_path, f"{cache_key}.json")
        
        try:
            cache_data = {
                'config_type': config_type,
                'data': data,
                'cached_at': datetime.now().isoformat(),
                'hash': hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"Saved {config_type} to cache")
        
        except Exception as e:
            logger.error(f"Cache save error: {e}")
    
    def fetch_config(self, config_type: str, force_refresh: bool = False) -> Dict:
        """دریافت تنظیمات از سرور"""
        # بررسی کش
        if not force_refresh:
            cached = self._load_from_cache(config_type)
            if cached:
                self.config_cache[config_type] = cached
                return cached
        
        try:
            # درخواست به سرور
            headers = {
                'Authorization': f'Bearer {self.server_config.auth_token}',
                'User-Agent': 'TelegramBot/1.0',
                'Content-Type': 'application/json'
            }
            
            params = {
                'type': config_type,
                'timestamp': datetime.now().isoformat(),
                'hash': self._generate_request_hash()
            }
            
            response = requests.get(
                f"{self.server_config.config_url}/config",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # رمزگشایی اگر نیاز باشد
                if data.get('encrypted', False):
                    data['data'] = json.loads(self._decrypt_data(data['data']))
                
                # ذخیره در کش
                self._save_to_cache(config_type, data)
                
                # ذخیره در حافظه
                self.config_cache[config_type] = data
                self.last_fetch = datetime.now()
                
                logger.info(f"Successfully fetched {config_type} from server")
                return data
            
            else:
                logger.error(f"Server responded with {response.status_code}")
                # بازگرداندون کش در صورت خطا
                cached = self._load_from_cache(config_type)
                if cached:
                    logger.warning(f"Using cached {config_type} due to server error")
                    return cached
                else:
                    raise Exception(f"Server error: {response.status_code}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching config: {e}")
            
            # استفاده از کش در صورت خطای شبکه
            cached = self._load_from_cache(config_type)
            if cached:
                logger.warning(f"Using cached {config_type} due to network error")
                return cached
            else:
                raise Exception(f"Network error: {e}")
    
    def _generate_request_hash(self) -> str:
        """تولید hash برای امنیت درخواست"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        secret = self.server_config.auth_token
        return hashlib.sha256(f"{timestamp}{secret}".encode()).hexdigest()[:16]
    
    def get_all_configs(self) -> Dict[str, Dict]:
        """دریافت همه تنظیمات"""
        config_types = ['bot', 'userbot', 'database', 'limits', 'security', 'speed']
        all_configs = {}
        
        for config_type in config_types:
            try:
                config = self.fetch_config(config_type)
                all_configs[config_type] = config
            except Exception as e:
                logger.error(f"Failed to fetch {config_type}: {e}")
        
        return all_configs
    
    def validate_configs(self, configs: Dict) -> bool:
        """اعتبارسنجی تنظیمات"""
        required_fields = {
            'bot': ['token', 'admins', 'webhook_url'],
            'database': ['type', 'connection_string'],
            'security': ['encryption_key', 'allowed_ips']
        }
        
        for config_type, fields in required_fields.items():
            if config_type in configs:
                config_data = configs[config_type].get('data', {})
                
                for field in fields:
                    if field not in config_data:
                        logger.error(f"Missing required field {field} in {config_type}")
                        return False
        
        return True
    
    def check_for_updates(self) -> Dict[str, bool]:
        """بررسی بروزرسانی‌ها"""
        updates = {}
        
        for config_type in self.config_cache.keys():
            try:
                # دریافت نسخه فعلی از کش
                cached_hash = None
                cache_file = os.path.join(
                    self.server_config.cache_path,
                    f"{self._get_cache_key(config_type)}.json"
                )
                
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        cache_data = json.load(f)
                    cached_hash = cache_data.get('hash')
                
                # دریافت نسخه جدید
                new_config = self.fetch_config(config_type, force_refresh=True)
                new_hash = hashlib.md5(
                    json.dumps(new_config, sort_keys=True).encode()
                ).hexdigest()
                
                updates[config_type] = (cached_hash != new_hash)
                
                if updates[config_type]:
                    logger.info(f"Update available for {config_type}")
            
            except Exception as e:
                logger.error(f"Update check error for {config_type}: {e}")
                updates[config_type] = False
        
        return updates

class EnvironmentConfig:
    """مدیریت تنظیمات از Environment Variables"""
    
    @staticmethod
    def load_from_env() -> ServerConfig:
        """بارگذاری تنظیمات از متغیرهای محیطی"""
        # خواندن از env (برای Render, Heroku, Railway, etc.)
        config_url = os.getenv('CONFIG_SERVER_URL')
        auth_token = os.getenv('CONFIG_AUTH_TOKEN')
        encryption_key = os.getenv('CONFIG_ENCRYPTION_KEY')
        
        if not config_url or not auth_token:
            logger.warning("Environment variables not set, using defaults")
            
            # مقادیر پیش‌فرض برای توسعه
            config_url = "https://config.yourdomain.com/api"
            auth_token = "development_token_123"
        
        return ServerConfig(
            config_url=config_url,
            auth_token=auth_token,
            refresh_interval=int(os.getenv('CONFIG_REFRESH_INTERVAL', '300')),
            cache_enabled=os.getenv('CONFIG_CACHE_ENABLED', 'true').lower() == 'true',
            cache_path=os.getenv('CONFIG_CACHE_PATH', '.config_cache'),
            encryption_key=encryption_key
        )
    
    @staticmethod
    def load_secrets() -> Dict[str, Any]:
        """بارگذاری secrets از env"""
        secrets = {
            'bot_token': os.getenv('BOT_TOKEN'),
            'api_id': os.getenv('API_ID'),
            'api_hash': os.getenv('API_HASH'),
            'admin_id': os.getenv('ADMIN_ID'),
            'webhook_url': os.getenv('WEBHOOK_URL'),
            'webhook_secret': os.getenv('WEBHOOK_SECRET'),
            'database_url': os.getenv('DATABASE_URL'),
            'redis_url': os.getenv('REDIS_URL'),
            'encryption_key': os.getenv('ENCRYPTION_KEY'),
            'jwt_secret': os.getenv('JWT_SECRET'),
            'cdn_url': os.getenv('CDN_URL'),
            'sentry_dsn': os.getenv('SENTRY_DSN'),
            'monitoring_url': os.getenv('MONITORING_URL')
        }
        
        # اعتبارسنجی secrets ضروری
        required_secrets = ['bot_token', 'api_id', 'api_hash']
        missing = [key for key in required_secrets if not secrets[key]]
        
        if missing:
            logger.error(f"Missing required secrets: {missing}")
            raise ValueError(f"Required secrets missing: {missing}")
        
        return secrets

class ConfigManager:
    """مدیریت مرکزی تنظیمات"""
    
    def __init__(self, use_server_config: bool = True):
        self.use_server_config = use_server_config
        
        if use_server_config:
            # استفاده از سرور تنظیمات
            server_config = EnvironmentConfig.load_from_env()
            self.fetcher = ConfigFetcher(server_config)
        else:
            # استفاده از فایل‌های محلی (برای توسعه)
            self.fetcher = None
        
        # بارگذاری secrets
        self.secrets = EnvironmentConfig.load_secrets()
        
        # تنظیمات بارگذاری شده
        self.configs: Dict[str, Dict] = {}
        self.last_update_check: Optional[datetime] = None
        
        logger.info("ConfigManager initialized")
    
    async def initialize(self):
        """مقداردهی اولیه"""
        if self.use_server_config and self.fetcher:
            try:
                # دریافت همه تنظیمات از سرور
                self.configs = self.fetcher.get_all_configs()
                
                # اعتبارسنجی
                if not self.fetcher.validate_configs(self.configs):
                    logger.error("Config validation failed")
                    raise ValueError("Invalid configuration")
                
                logger.info("✅ Configs loaded from server")
                
            except Exception as e:
                logger.error(f"Failed to load configs from server: {e}")
                logger.warning("Falling back to environment variables")
                self._load_from_env_fallback()
        else:
            # استفاده از env
            self._load_from_env_fallback()
        
        # تنظیم متغیرهای محیطی
        self._set_environment_variables()
    
    def _load_from_env_fallback(self):
        """بارگذاری fallback از env"""
        self.configs = {
            'bot': {
                'data': {
                    'token': self.secrets['bot_token'],
                    'api_id': int(self.secrets['api_id']),
                    'api_hash': self.secrets['api_hash'],
                    'admins': [int(self.secrets['admin_id'])] if self.secrets['admin_id'] else [],
                    'webhook_url': self.secrets['webhook_url'],
                    'webhook_secret': self.secrets['webhook_secret']
                }
            },
            'database': {
                'data': {
                    'type': 'postgres' if 'postgres' in (self.secrets.get('database_url') or '') else 'sqlite',
                    'connection_string': self.secrets.get('database_url', 'sqlite:///data/bot.db'),
                    'pool_size': 20,
                    'max_overflow': 10
                }
            },
            'security': {
                'data': {
                    'encryption_key': self.secrets.get('encryption_key', 'default_key_change_me'),
                    'jwt_secret': self.secrets.get('jwt_secret', 'jwt_secret_change_me'),
                    'allowed_ips': [],
                    'rate_limit_per_minute': 60
                }
            }
        }
        
        logger.info("✅ Configs loaded from environment")
    
    def _set_environment_variables(self):
        """تنظیم متغیرهای محیطی از تنظیمات"""
        # تنظیم توکن ربات
        if 'bot' in self.configs:
            bot_token = self.configs['bot']['data'].get('token')
            if bot_token and not os.getenv('BOT_TOKEN'):
                os.environ['BOT_TOKEN'] = bot_token
        
        # تنظیم webhook URL
        if 'bot' in self.configs:
            webhook_url = self.configs['bot']['data'].get('webhook_url')
            if webhook_url and not os.getenv('WEBHOOK_URL'):
                os.environ['WEBHOOK_URL'] = webhook_url
    
    def get_config(self, config_type: str, key: str = None, default: Any = None) -> Any:
        """دریافت مقدار تنظیم"""
        if config_type not in self.configs:
            if self.use_server_config and self.fetcher:
                try:
                    self.configs[config_type] = self.fetcher.fetch_config(config_type)
                except:
                    return default
            else:
                return default
        
        config_data = self.configs[config_type].get('data', {})
        
        if key is None:
            return config_data
        
        # پشتیبانی از dot notation: 'database.connection_string'
        if '.' in key:
            keys = key.split('.')
            value = config_data
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        else:
            return config_data.get(key, default)
    
    def get_secret(self, key: str) -> Optional[str]:
        """دریافت secret"""
        return self.secrets.get(key)
    
    async def refresh_configs(self):
        """بروزرسانی تنظیمات"""
        if not self.use_server_config or not self.fetcher:
            return
        
        try:
            # بررسی بروزرسانی‌ها
            updates = self.fetcher.check_for_updates()
            
            for config_type, has_update in updates.items():
                if has_update:
                    # دریافت تنظیمات جدید
                    new_config = self.fetcher.fetch_config(config_type, force_refresh=True)
                    self.configs[config_type] = new_config
                    
                    logger.info(f"Refreshed config: {config_type}")
                    
                    # اطلاع به سیستم‌های دیگر
                    await self._notify_config_change(config_type)
        
        except Exception as e:
            logger.error(f"Refresh configs error: {e}")
    
    async def _notify_config_change(self, config_type: str):
        """اعلان تغییر تنظیمات"""
        # اینجا می‌توانید سیستم‌های دیگر را مطلع کنید
        # مثلاً restart workerها یا reload modules
        pass
    
    def save_config_locally(self, path: str = "config_backup.json"):
        """ذخیره تنظیمات به صورت محلی (برای بک‌آپ)"""
        try:
            backup_data = {
                'configs': self.configs,
                'secrets': {k: '***HIDDEN***' if 'key' in k.lower() or 'token' in k.lower() else v 
                           for k, v in self.secrets.items()},
                'backup_time': datetime.now().isoformat(),
                'source': 'server' if self.use_server_config else 'environment'
            }
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Config backup saved to {path}")
            return True
        
        except Exception as e:
            logger.error(f"Save config error: {e}")
            return False
    
    def export_for_deployment(self) -> Dict[str, Any]:
        """خروجی برای deployment"""
        deployment_config = {
            'environment_variables': {
                'BOT_TOKEN': self.get_config('bot', 'token'),
                'API_ID': self.get_config('bot', 'api_id'),
                'API_HASH': self.get_config('bot', 'api_hash'),
                'ADMIN_ID': self.get_config('bot', 'admins')[0] if self.get_config('bot', 'admins') else '',
                'WEBHOOK_URL': self.get_config('bot', 'webhook_url'),
                'DATABASE_URL': self.get_config('database', 'connection_string'),
                'CONFIG_SERVER_URL': os.getenv('CONFIG_SERVER_URL', ''),
                'CONFIG_AUTH_TOKEN': '***SECRET***'
            },
            'runtime_config': {
                'bot_settings': self.get_config('bot'),
                'database_settings': self.get_config('database'),
                'security_settings': self.get_config('security')
            },
            'metadata': {
                'last_updated': datetime.now().isoformat(),
                'config_source': 'server' if self.use_server_config else 'env',
                'hash': hashlib.md5(
                    json.dumps(self.configs, sort_keys=True).encode()
                ).hexdigest()
            }
        }
        
        return deployment_config

# تابع کمکی برای استفاده آسان
async def create_config_manager() -> ConfigManager:
    """ایجاد Config Manager"""
    # تشخیص محیط اجرا
    is_production = os.getenv('ENVIRONMENT') == 'production'
    use_server_config = is_production or os.getenv('USE_CONFIG_SERVER', 'false').lower() == 'true'
    
    manager = ConfigManager(use_server_config=use_server_config)
    await manager.initialize()
    
    return manager

# نمونه استفاده
async def example_usage():
    """نمونه استفاده"""
    manager = await create_config_manager()
    
    # دریافت تنظیمات
    bot_token = manager.get_config('bot', 'token')
    admin_id = manager.get_config('bot', 'admins')[0]
    db_url = manager.get_config('database', 'connection_string')
    
    print(f"Bot Token: {bot_token[:10]}...")
    print(f"Admin ID: {admin_id}")
    print(f"Database: {db_url}")
    
    # ذخیره بک‌آپ
    manager.save_config_locally()
    
    # خروجی برای deployment
    deployment = manager.export_for_deployment()
    print(f"Deployment config generated with hash: {deployment['metadata']['hash']}")

if __name__ == "__main__":
    asyncio.run(example_usage())
