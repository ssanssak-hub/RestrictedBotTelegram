#!/usr/bin/env python3
# config_loader.py - بارگذاری و اعتبارسنجی کانفیگ

import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class SessionManagerConfig:
    """کانفیگ session_manager"""
    base_dir: Path
    max_sessions_per_user: int
    session_lifetime_hours: int
    encryption_enabled: bool
    backup_count: int
    # ... سایر فیلدها

@dataclass
class SessionMonitorConfig:
    """کانفیگ session_monitor"""
    check_interval_seconds: int
    alerting_enabled: bool
    system_thresholds: Dict[str, float]
    # ... سایر فیلدها

class ConfigLoader:
    """بارگذاری و اعتبارسنجی کانفیگ"""
    
    def __init__(self, config_path: Path = Path("session_config.json")):
        self.config_path = config_path
        self.config_data = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """بارگذاری کانفیگ از فایل"""
        if not self.config_path.exists():
            logger.warning(f"Config file not found: {self.config_path}")
            return self._get_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # اعتبارسنجی نسخه
            if config.get('config_version') != '3.0.0':
                logger.warning(f"Config version mismatch. Expected 3.0.0, got {config.get('config_version')}")
                
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON config: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise
    
    def get_session_manager_config(self) -> SessionManagerConfig:
        """استخراج تنظیمات session_manager"""
        sm_settings = self.config_data.get('session_manager_settings', {})
        
        return SessionManagerConfig(
            base_dir=Path(sm_settings.get('base_directory', 'secure_sessions')),
            max_sessions_per_user=sm_settings.get('max_sessions_per_user', 5),
            session_lifetime_hours=sm_settings.get('session_lifetime_hours', 168),
            encryption_enabled=sm_settings.get('encryption', {}).get('enabled', True),
            backup_count=sm_settings.get('backup', {}).get('count', 10),
            # ... سایر فیلدها
        )
    
    def get_session_monitor_config(self) -> SessionMonitorConfig:
        """استخراج تنظیمات session_monitor"""
        monitor_settings = self.config_data.get('session_monitor_settings', {})
        
        return SessionMonitorConfig(
            check_interval_seconds=monitor_settings.get('monitoring', {}).get('check_interval_seconds', 300),
            alerting_enabled=monitor_settings.get('alerting', {}).get('enabled', True),
            system_thresholds=monitor_settings.get('system_thresholds', {}),
            # ... سایر فیلدها
        )
    
    def get_environment_overrides(self) -> Dict[str, Any]:
        """دریافت overrideهای محیطی"""
        env = self.config_data.get('environment', 'production')
        overrides = self.config_data.get('environment_specific_overrides', {}).get(env, {})
        return overrides
    
    def apply_environment_overrides(self):
        """اعمال overrideهای محیطی"""
        overrides = self.get_environment_overrides()
        
        # اعمال overrideها به config_data
        for key_path, value in overrides.items():
            self._set_nested_value(self.config_data, key_path, value)
    
    def _set_nested_value(self, obj: Dict, key_path: str, value: Any):
        """تنظیم مقدار تو در تو"""
        keys = key_path.split('.')
        current = obj
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _get_default_config(self) -> Dict[str, Any]:
        """کانفیگ پیش‌فرض"""
        return {
            "config_version": "3.0.0",
            "environment": "development",
            "session_manager_settings": {
                "base_directory": "secure_sessions",
                "max_sessions_per_user": 3,
                "encryption": {"enabled": False},
                "backup": {"enabled": False}
            },
            "session_monitor_settings": {
                "monitoring": {"enabled": False},
                "alerting": {"enabled": False}
            }
        }
    
    def save_config(self, config: Optional[Dict] = None):
        """ذخیره کانفیگ"""
        if config is None:
            config = self.config_data
        
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info(f"Config saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

# تابع کمکی برای استفاده آسان
def load_config() -> ConfigLoader:
    """بارگذاری کانفیگ"""
    loader = ConfigLoader()
    loader.apply_environment_overrides()
    return loader
