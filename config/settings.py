#config/settings.py
"""
مدیریت هوشمند تنظیمات سیستم
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum
import yaml
from pydantic import BaseModel, validator, Field
import tomli

class TransferStrategy(str, Enum):
    """استراتژی‌های انتقال"""
    SINGLE = "single"
    MULTI_CONNECTION = "multi_connection"
    STREAMING = "streaming"
    ADAPTIVE = "adaptive"

class CompressionAlgorithm(str, Enum):
    """الگوریتم‌های فشرده‌سازی"""
    BROTLI = "brotli"
    ZSTD = "zstd"
    LZ4 = "lz4"
    GZIP = "gzip"
    NONE = "none"

class CacheStrategy(str, Enum):
    """استراتژی‌های کش"""
    LRU = "lru"
    LFU = "lfu"
    ARC = "arc"
    MRU = "mru"

class SpeedSettings(BaseModel):
    """تنظیمات اصلی سیستم"""
    
    # بخش دانلود
    download: dict = Field(default_factory=lambda: {
        'chunk_size_mb': Field(5, ge=0.1, le=50, description="سایز chunk بر حسب مگابایت"),
        'max_connections': Field(16, ge=1, le=64, description="حداکثر اتصالات همزمان"),
        'buffer_size_mb': Field(10, ge=1, le=100, description="سایز بافر"),
        'timeout_seconds': Field(30, ge=5, le=300),
        'retry_attempts': Field(3, ge=0, le=10),
        'resume_enabled': True,
        'strategy': TransferStrategy.ADAPTIVE,
        'prefetch_enabled': True,
        'prefetch_size_mb': 5,
    })
    
    # بخش آپلود
    upload: dict = Field(default_factory=lambda: {
        'chunk_size_mb': Field(2, ge=0.1, le=20),
        'parallel_uploads': Field(5, ge=1, le=20),
        'compression': {
            'enabled': True,
            'algorithm': CompressionAlgorithm.BROTLI,
            'level': Field(6, ge=1, le=11),
            'min_size_mb': 1,
            'extensions': ['.txt', '.log', '.json', '.xml', '.html', '.csv']
        },
        'timeout_seconds': 60,
        'resume_enabled': True,
        'encryption_enabled': False,
    })
    
    # فشرده‌سازی
    compression: dict = Field(default_factory=lambda: {
        'enabled': True,
        'default_algorithm': CompressionAlgorithm.ZSTD,
        'adaptive_compression': True,
        'min_compression_ratio': 0.8,
    })
    
    # کش
    caching: dict = Field(default_factory=lambda: {
        'enabled': True,
        'strategy': CacheStrategy.LRU,
        'memory_cache_mb': Field(100, ge=10, le=1024),
        'disk_cache_gb': Field(5, ge=1, le=100),
        'ttl_seconds': 3600,
        'cleanup_interval_minutes': 60,
        'persistent_cache': True,
        'cache_directory': "./cache",
    })
    
    # شبکه
    network: dict = Field(default_factory=lambda: {
        'tcp_fast_open': True,
        'tcp_no_delay': True,
        'keep_alive': True,
        'keep_alive_idle': 60,
        'keep_alive_interval': 30,
        'max_retries': 3,
        'connection_pool_size': 20,
        'dns_cache_ttl': 300,
        'proxy_enabled': False,
        'proxy_url': None,
        'bandwidth_throttling_mbps': 0,  # 0 = unlimited
    })
    
    # عملکرد
    performance: dict = Field(default_factory=lambda: {
        'thread_pool_size': Field(16, ge=1, le=64),
        'io_bound_threads': Field(8, ge=1, le=32),
        'cpu_bound_threads': Field(4, ge=1, le=16),
        'max_memory_mb': Field(512, ge=64, le=4096),
        'gc_threshold': (700, 10, 10),
        'enable_jit': False,
        'async_workers': 100,
    })
    
    # CDN
    cdn: dict = Field(default_factory=lambda: {
        'enabled': False,
        'servers': [],
        'strategy': 'round_robin',
        'cache_ttl': 3600,
        'geo_routing': True,
        'failover_enabled': True,
    })
    
    # مانیتورینگ
    monitoring: dict = Field(default_factory=lambda: {
        'update_interval_ms': 500,
        'history_size': 1000,
        'enable_metrics': True,
        'metrics_port': 9090,
        'alerting_enabled': True,
        'slow_transfer_threshold_mbps': 1.0,
        'enable_speed_graph': True,
        'graph_points': 100,
    })
    
    # هوش مصنوعی
    ai: dict = Field(default_factory=lambda: {
        'enabled': True,
        'model_path': './models/speed_predictor.onnx',
        'training_enabled': False,
        'prediction_confidence': 0.8,
        'adaptive_learning': True,
    })
    
    # امنیت
    security: dict = Field(default_factory=lambda: {
        'ssl_verify': True,
        'certificate_pinning': False,
        'encryption_enabled': False,
        'encryption_algorithm': 'chacha20-poly1305',
        'max_file_size_mb': 1024,
        'allowed_extensions': ['.*'],  # همه مجاز
        'blocked_extensions': ['.exe', '.bat', '.sh'],
    })
    
    @validator('download')
    def validate_download(cls, v):
        if v['chunk_size_mb'] * v['max_connections'] > 500:  # 500MB total buffer
            raise ValueError('Total buffer size too large')
        return v
    
    @validator('network')
    def validate_proxy(cls, v):
        if v['proxy_enabled'] and not v['proxy_url']:
            raise ValueError('Proxy URL required when proxy is enabled')
        return v
    
    @validator('security')
    def validate_security(cls, v):
        if v['encryption_enabled'] and not v['encryption_algorithm']:
            raise ValueError('Encryption algorithm required when encryption is enabled')
        return v

class ConfigManager:
    """مدیریت هوشمند پیکربندی"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_config_file()
        self.settings = self.load_settings()
        self.watcher = None
        self._setup_config_watcher()
    
    def _find_config_file(self) -> Path:
        """یافتن فایل پیکربندی"""
        possible_paths = [
            Path('config/settings.json'),
            Path('config/settings.yaml'),
            Path('config/settings.toml'),
            Path('settings.json'),
            Path('~/.speed_system/config.json').expanduser(),
        ]
        
        for path in possible_paths:
            if path.exists():
                return path
        
        # ایجاد فایل پیش‌فرض
        default_path = Path('config/settings.json')
        default_path.parent.mkdir(exist_ok=True)
        self._create_default_config(default_path)
        return default_path
    
    def _create_default_config(self, path: Path):
        """ایجاد پیکربندی پیش‌فرض"""
        default_settings = SpeedSettings()
        self.save_settings(default_settings.dict(), path)
    
    def load_settings(self) -> SpeedSettings:
        """بارگذاری تنظیمات"""
        if not self.config_path.exists():
            return SpeedSettings()
        
        with open(self.config_path, 'r') as f:
            if self.config_path.suffix == '.json':
                data = json.load(f)
            elif self.config_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(f)
            elif self.config_path.suffix == '.toml':
                data = tomli.load(f)
            else:
                raise ValueError(f'Unsupported config format: {self.config_path.suffix}')
        
        return SpeedSettings(**data)
    
    def save_settings(self, settings: Dict[str, Any], path: Optional[Path] = None):
        """ذخیره تنظیمات"""
        save_path = path or self.config_path
        save_path.parent.mkdir(exist_ok=True)
        
        if save_path.suffix == '.json':
            with open(save_path, 'w') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        elif save_path.suffix in ['.yaml', '.yml']:
            with open(save_path, 'w') as f:
                yaml.dump(settings, f, allow_unicode=True)
        elif save_path.suffix == '.toml':
            with open(save_path, 'w') as f:
                import tomli_w
                tomli_w.dump(settings, f)
    
    def _setup_config_watcher(self):
        """رصد تغییرات فایل پیکربندی"""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler
            
            class ConfigHandler(FileSystemEventHandler):
                def __init__(self, callback):
                    self.callback = callback
                
                def on_modified(self, event):
                    if event.src_path == str(self.config_path):
                        self.callback()
            
            self.observer = Observer()
            handler = ConfigHandler(self.reload_config)
            self.observer.schedule(handler, str(self.config_path.parent))
            self.observer.start()
            
        except ImportError:
            pass  # watchdog not installed
    
    def reload_config(self):
        """بارگذاری مجدد تنظیمات"""
        try:
            self.settings = self.load_settings()
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")
    
    def get_optimized_settings(self, file_size: int, network_type: str = "unknown") -> Dict[str, Any]:
        """دریافت تنظیمات بهینه برای شرایط خاص"""
        base_settings = self.settings.dict()
        
        # بهینه‌سازی بر اساس حجم فایل
        if file_size < 10 * 1024 * 1024:  # < 10MB
            base_settings['download']['chunk_size_mb'] = 1
            base_settings['download']['max_connections'] = 4
            base_settings['upload']['chunk_size_mb'] = 1
        elif file_size < 100 * 1024 * 1024:  # < 100MB
            base_settings['download']['chunk_size_mb'] = 2
            base_settings['download']['max_connections'] = 8
            base_settings['upload']['chunk_size_mb'] = 2
        else:  # > 100MB
            base_settings['download']['chunk_size_mb'] = 5
            base_settings['download']['max_connections'] = 16
            base_settings['upload']['chunk_size_mb'] = 5
        
        # بهینه‌سازی بر اساس نوع شبکه
        if network_type == "mobile":
            base_settings['download']['max_connections'] = 4
            base_settings['network']['keep_alive_idle'] = 30
            base_settings['compression']['enabled'] = True
        elif network_type == "satellite":
            base_settings['download']['chunk_size_mb'] = 10
            base_settings['download']['max_connections'] = 2
            base_settings['network']['timeout_seconds'] = 120
        
        return base_settings
    
    def validate_all(self) -> List[str]:
        """اعتبارسنجی تمام تنظیمات"""
        errors = []
        
        try:
            self.settings = SpeedSettings(**self.settings.dict())
        except Exception as e:
            errors.append(str(e))
        
        return errors

# نمونه singleton
config_manager = ConfigManager()
