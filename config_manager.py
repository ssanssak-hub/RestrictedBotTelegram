#!/usr/bin/env python3
# config_manager.py - مدیریت فایل تنظیمات ربات

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class BotConfig:
    """کلاس تنظیمات ربات"""
    token: str
    api_id: int = 0
    api_hash: str = ""
    admins: list = None
    welcome_message: str = ""
    
    def __post_init__(self):
        if self.admins is None:
            self.admins = []

@dataclass
class LimitsConfig:
    """کلاس تنظیمات محدودیت‌ها"""
    daily_downloads: int = 10
    max_file_size_mb: int = 500
    concurrent_downloads: int = 3
    bandwidth_gb_per_month: int = 10

@dataclass 
class DatabaseConfig:
    """کلاس تنظیمات دیتابیس"""
    type: str = "sqlite"
    path: str = "data/database.db"
    backup_interval_hours: int = 24

class ConfigManager:
    """مدیریت فایل‌های تنظیمات"""
    
    def __init__(self, config_path: str = "config/bot_config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.default_config = self._get_default_config()
        self.load_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """تنظیمات پیش‌فرض"""
        return {
            "bot": {
                "enabled": True,
                "token": "",
                "admins": [],
                "welcome_message": "👋 به ربات ما خوش آمدید!"
            },
            "limits": {
                "daily_downloads": 10,
                "max_file_size_mb": 500,
                "concurrent_downloads": 3
            },
            "database": {
                "type": "sqlite",
                "path": "data/database.db"
            }
        }
    
    def load_config(self) -> bool:
        """بارگذاری تنظیمات از فایل"""
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file not found: {self.config_path}")
                self.create_default_config()
                return False
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            # اعتبارسنجی ساختار
            self._validate_config()
            
            # ادغام با پیش‌فرض‌ها
            self._merge_with_defaults()
            
            logger.info(f"Config loaded successfully from {self.config_path}")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            self.create_default_config()
            return False
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return False
    
    def create_default_config(self):
        """ایجاد فایل config با مقادیر پیش‌فرض"""
        try:
            self.config_path.parent.mkdir(exist_ok=True, parents=True)
            
            self.config = self.default_config.copy()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Default config created at {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error creating default config: {e}")
            raise
    
    def _validate_config(self):
        """اعتبارسنجی تنظیمات"""
        required_sections = ['bot', 'limits']
        
        for section in required_sections:
            if section not in self.config:
                logger.warning(f"Missing required section: {section}")
                self.config[section] = self.default_config.get(section, {})
        
        # اعتبارسنجی token
        if 'bot' in self.config:
            bot_config = self.config['bot']
            if not bot_config.get('token'):
                logger.warning("Bot token is not set!")
    
    def _merge_with_defaults(self):
        """ادغام با مقادیر پیش‌فرض"""
        for section, default_values in self.default_config.items():
            if section not in self.config:
                self.config[section] = default_values
            else:
                if isinstance(default_values, dict):
                    for key, value in default_values.items():
                        if key not in self.config[section]:
                            self.config[section][key] = value
    
    def save_config(self):
        """ذخیره تنظیمات در فایل"""
        try:
            # ایجاد backup
            self._create_backup()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Config saved to {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
    
    def _create_backup(self):
        """ایجاد backup از فایل config"""
        if not self.config_path.exists():
            return
        
        backup_dir = self.config_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"bot_config_{timestamp}.json"
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as src:
                config_data = src.read()
            
            with open(backup_file, 'w', encoding='utf-8') as dst:
                dst.write(config_data)
            
            # حذف backup‌های قدیمی (بیش از 7 روز)
            self._clean_old_backups(backup_dir)
            
        except Exception as e:
            logger.error(f"Error creating config backup: {e}")
    
    def _clean_old_backups(self, backup_dir: Path, max_age_days: int = 7):
        """پاکسازی backup‌های قدیمی"""
        import time
        current_time = time.time()
        
        for backup_file in backup_dir.glob("bot_config_*.json"):
            file_age = current_time - backup_file.stat().st_mtime
            if file_age > max_age_days * 24 * 3600:
                try:
                    backup_file.unlink()
                    logger.debug(f"Removed old backup: {backup_file}")
                except Exception as e:
                    logger.error(f"Error removing old backup: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """دریافت مقدار از config"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """تنظیم مقدار در config"""
        keys = key.split('.')
        config_ref = self.config
        
        for k in keys[:-1]:
            if k not in config_ref:
                config_ref[k] = {}
            config_ref = config_ref[k]
        
        config_ref[keys[-1]] = value
    
    def update_bot_token(self, token: str):
        """به‌روزرسانی توکن ربات"""
        self.set('bot.token', token)
        self.save_config()
        logger.info("Bot token updated")
    
    def add_admin(self, admin_id: int):
        """افزودن ادمین"""
        admins = self.get('bot.admins', [])
        if admin_id not in admins:
            admins.append(admin_id)
            self.set('bot.admins', admins)
            self.save_config()
            logger.info(f"Admin added: {admin_id}")
    
    def remove_admin(self, admin_id: int):
        """حذف ادمین"""
        admins = self.get('bot.admins', [])
        if admin_id in admins:
            admins.remove(admin_id)
            self.set('bot.admins', admins)
            self.save_config()
            logger.info(f"Admin removed: {admin_id}")
    
    def update_limit(self, limit_name: str, value: int):
        """به‌روزرسانی محدودیت"""
        self.set(f'limits.{limit_name}', value)
        self.save_config()
        logger.info(f"Limit {limit_name} updated to {value}")
    
    def get_bot_config(self) -> BotConfig:
        """دریافت تنظیمات ربات به صورت object"""
        return BotConfig(
            token=self.get('bot.token', ''),
            api_id=self.get('bot.api_id', 0),
            api_hash=self.get('bot.api_hash', ''),
            admins=self.get('bot.admins', []),
            welcome_message=self.get('bot.welcome_message', '')
        )
    
    def get_limits_config(self) -> LimitsConfig:
        """دریافت تنظیمات محدودیت‌ها"""
        return LimitsConfig(
            daily_downloads=self.get('limits.tiers.free.daily_downloads', 10),
            max_file_size_mb=self.get('limits.tiers.free.max_file_size_mb', 500),
            concurrent_downloads=self.get('limits.tiers.free.concurrent_downloads', 3),
            bandwidth_gb_per_month=self.get('limits.tiers.free.bandwidth_gb_per_month', 10)
        )
    
    def get_database_config(self) -> DatabaseConfig:
        """دریافت تنظیمات دیتابیس"""
        return DatabaseConfig(
            type=self.get('database.type', 'sqlite'),
            path=self.get('database.path', 'data/database.db'),
            backup_interval_hours=self.get('database.backup.interval_hours', 24)
        )
    
    def validate_required_fields(self) -> list:
        """اعتبارسنجی فیلدهای ضروری"""
        errors = []
        
        # بررسی token
        token = self.get('bot.token')
        if not token or token == 'YOUR_BOT_TOKEN_HERE':
            errors.append("Bot token is not set or is default")
        
        # بررسی admins
        admins = self.get('bot.admins', [])
        if not admins:
            errors.append("No admins specified")
        
        return errors
    
    def get_config_hash(self) -> str:
        """دریافت hash از config برای تشخیص تغییرات"""
        config_str = json.dumps(self.config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()
    
    def reload(self):
        """بارگذاری مجدد config از فایل"""
        return self.load_config()

# Singleton instance
config_manager = ConfigManager()

# Helper functions
def get_config() -> Dict[str, Any]:
    """دریافت config"""
    return config_manager.config

def get_setting(key: str, default: Any = None) -> Any:
    """دریافت تنظیم"""
    return config_manager.get(key, default)

def update_setting(key: str, value: Any):
    """به‌روزرسانی تنظیم"""
    config_manager.set(key, value)
    config_manager.save_config()

if __name__ == "__main__":
    # تست config manager
    manager = ConfigManager()
    
    print("📋 Config loaded successfully!")
    print(f"✅ Token: {'*' * 10 if manager.get('bot.token') else 'NOT SET'}")
    print(f"✅ Admins: {manager.get('bot.admins', [])}")
    print(f"✅ Daily downloads: {manager.get('limits.tiers.free.daily_downloads')}")
    
    # اعتبارسنجی
    errors = manager.validate_required_fields()
    if errors:
        print(f"⚠️  Warnings: {errors}")

# config.py - فایل تنظیمات
import os
from pathlib import Path

# توکن ربات
TOKEN = os.getenv("BOT_TOKEN", "توکن_ربات_شما")

# اطلاعات API تلگرام
API_ID = int(os.getenv("API_ID", 123456))
API_HASH = os.getenv("API_HASH", "your_api_hash_here")
BOT_USERNAME = os.getenv("BOT_USERNAME", "username_bot")

# ادمین‌ها (آیدی عددی)
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

# کلید رمزنگاری
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "default_key_32_chars_long_here!")

# تنظیمات Redis (برای کش)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_DB = int(os.getenv("REDIS_DB", 0))

# تنظیمات Webhook (اختیاری)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT = int(os.getenv("PORT", 8443))
WEBHOOK_LISTEN = os.getenv("WEBHOOK_LISTEN", "0.0.0.0")

# محدودیت‌ها
MAX_DOWNLOAD_LIMIT = int(os.getenv("MAX_DOWNLOAD_LIMIT", 50))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", 500))
DAILY_DOWNLOAD_LIMIT = int(os.getenv("DAILY_DOWNLOAD_LIMIT", 20))

# مسیرهای فایل
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / "database" / "telegram_bot.db"
LOGS_PATH = BASE_DIR / "logs"
DOWNLOAD_PATH = BASE_DIR / "downloads"
EXPORTS_PATH = BASE_DIR / "exports"
ACCOUNTS_PATH = BASE_DIR / "accounts"

# ایجاد دایرکتوری‌ها
for path in [DATABASE_PATH.parent, LOGS_PATH, DOWNLOAD_PATH, EXPORTS_PATH, ACCOUNTS_PATH]:
    path.mkdir(parents=True, exist_ok=True)
