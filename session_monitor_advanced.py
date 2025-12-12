#!/usr/bin/env python3
# session_monitor_advanced.py - سیستم مانیتورینگ پیشرفته session‌ها
# Version: 2.0.0

import asyncio
import json
import logging
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
import psutil
import aiofiles
import threading
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import statistics
from config_loader import load_config
# تنظیمات لاگ پیشرفته
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - [%(levelname)s] - [Thread:%(thread)d] - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'session_monitor.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# مدل‌های داده
# ============================================

class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"

class AlertType(Enum):
    SYSTEM = "system"
    SESSION = "session"
    NETWORK = "network"
    SECURITY = "security"
    PERFORMANCE = "performance"

@dataclass
class Alert:
    level: AlertLevel
    type: AlertType
    message: str
    timestamp: datetime
    source: str
    data: Optional[Dict] = None
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None

@dataclass
class SystemMetrics:
    timestamp: datetime
    cpu_percent: float
    cpu_temp: Optional[float] = None
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    disk_percent: float
    disk_free_gb: float
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_sent_mb: float = 0.0
    network_recv_mb: float = 0.0
    processes_count: int = 0
    load_average: Optional[tuple] = None

@dataclass
class SessionMetrics:
    timestamp: datetime
    total_sessions: int
    active_sessions: int
    healthy_sessions: int
    warning_sessions: int
    critical_sessions: int
    avg_health_score: float
    error_rate: float
    avg_response_time: float
    total_requests: int
    failed_requests: int
    session_rotations_24h: int

@dataclass
class MonitorConfig:
    check_interval_seconds: int = 300
    metrics_retention_days: int = 7
    alert_retention_days: int = 30
    system_thresholds: Dict[str, float] = None
    session_thresholds: Dict[str, float] = None
    enable_real_time_alerts: bool = True
    alert_cooldown_seconds: int = 300
    max_metrics_in_memory: int = 10000
    enable_auto_remediation: bool = False
    
    def __post_init__(self):
        if self.system_thresholds is None:
            self.system_thresholds = {
                'cpu_critical': 90.0,
                'cpu_warning': 70.0,
                'memory_critical': 90.0,
                'memory_warning': 75.0,
                'disk_critical': 95.0,
                'disk_warning': 85.0,
                'temperature_critical': 85.0,
                'temperature_warning': 70.0
            }
        
        if self.session_thresholds is None:
            self.session_thresholds = {
                'error_rate_critical': 0.3,
                'error_rate_warning': 0.1,
                'health_score_critical': 30.0,
                'health_score_warning': 50.0,
                'response_time_critical': 10.0,
                'response_time_warning': 5.0,
                'inactive_session_days': 7,
                'old_session_days': 30
            }

# ============================================
# سیستم ذخیره‌سازی متریک‌ها
# ============================================

class MetricsStorage:
    """ذخیره‌سازی کارآمد متریک‌ها"""
    
    def __init__(self, storage_dir: Path = Path("monitor_data")):
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(exist_ok=True)
        
        # حافظه کش
        self.system_metrics_cache = deque(maxlen=1000)
        self.session_metrics_cache = deque(maxlen=1000)
        self.alerts_cache = deque(maxlen=500)
        
        # Thread pool برای عملیات I/O
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        self.lock = threading.RLock()
    
    async def store_system_metrics(self, metrics: SystemMetrics):
        """ذخیره متریک‌های سیستم"""
        self.system_metrics_cache.append(metrics)
        
        # ذخیره غیرهمزمان در فایل
        await asyncio.get_event_loop().run_in_executor(
            self.thread_pool,
            self._append_to_file,
            "system_metrics.json",
            asdict(metrics)
        )
    
    async def store_session_metrics(self, metrics: SessionMetrics):
        """ذخیره متریک‌های session"""
        self.session_metrics_cache.append(metrics)
        
        await asyncio.get_event_loop().run_in_executor(
            self.thread_pool,
            self._append_to_file,
            "session_metrics.json",
            asdict(metrics)
        )
    
    async def store_alert(self, alert: Alert):
        """ذخیره هشدار"""
        self.alerts_cache.append(alert)
        
        await asyncio.get_event_loop().run_in_executor(
            self.thread_pool,
            self._append_to_file,
            "alerts.json",
            asdict(alert)
        )
    
    def _append_to_file(self, filename: str, data: Dict):
        """اضافه کردن داده به فایل (thread-safe)"""
        filepath = self.storage_dir / filename
        with self.lock:
            try:
                # خواندن داده‌های موجود
                existing_data = []
                if filepath.exists():
                    with open(filepath, 'r', encoding='utf-8') as f:
                        try:
                            existing_data = json.load(f)
                            if not isinstance(existing_data, list):
                                existing_data = []
                        except json.JSONDecodeError:
                            existing_data = []
                
                # اضافه کردن داده جدید
                existing_data.append(data)
                
                # حفظ فقط داده‌های اخیر
                if filename == "alerts.json":
                    max_items = 10000
                else:
                    max_items = 50000
                
                if len(existing_data) > max_items:
                    existing_data = existing_data[-max_items:]
                
                # ذخیره
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, indent=2, default=str, ensure_ascii=False)
                
            except Exception as e:
                logger.error(f"Failed to write to {filename}: {e}")
    
    async def get_recent_metrics(self, hours: int = 24) -> Dict:
        """دریافت متریک‌های اخیر"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        system_metrics = [
            m for m in self.system_metrics_cache
            if m.timestamp >= cutoff_time
        ]
        
        session_metrics = [
            m for m in self.session_metrics_cache
            if m.timestamp >= cutoff_time
        ]
        
        return {
            'system': system_metrics,
            'session': session_metrics,
            'alerts': list(self.alerts_cache)[-100:]  # آخرین 100 هشدار
        }
    
    async def cleanup_old_data(self, retention_days: int = 7):
        """پاکسازی داده‌های قدیمی"""
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        for filename in ["system_metrics.json", "session_metrics.json", "alerts.json"]:
            await self._cleanup_file(filename, cutoff_date)
    
    async def _cleanup_file(self, filename: str, cutoff_date: datetime):
        """پاکسازی فایل"""
        filepath = self.storage_dir / filename
        if not filepath.exists():
            return
        
        await asyncio.get_event_loop().run_in_executor(
            self.thread_pool,
            self._cleanup_file_sync,
            filepath,
            cutoff_date
        )
    
    def _cleanup_file_sync(self, filepath: Path, cutoff_date: datetime):
        """پاکسازی همزمان فایل"""
        with self.lock:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # فیلتر داده‌های قدیمی
                filtered_data = []
                for item in data:
                    timestamp_str = item.get('timestamp')
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(
                                timestamp_str.replace('Z', '+00:00')
                            )
                            if timestamp >= cutoff_date:
                                filtered_data.append(item)
                        except (ValueError, AttributeError):
                            filtered_data.append(item)
                    else:
                        filtered_data.append(item)
                
                # ذخیره داده‌های فیلتر شده
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(filtered_data, f, indent=2, default=str, ensure_ascii=False)
                
                logger.info(f"Cleaned up {filepath}: {len(data)} -> {len(filtered_data)} items")
                
            except Exception as e:
                logger.error(f"Failed to cleanup {filepath}: {e}")

# ============================================
# سیستم هشدار هوشمند
# ============================================

class SmartAlertSystem:
    """سیستم هشدار هوشمند با قابلیت یادگیری"""
    
    def __init__(self, config: MonitorConfig):
        self.config = config
        self.storage = MetricsStorage()
        self.active_alerts = {}
        self.alert_cooldowns = {}
        self.alert_handlers = []
        
        # آستانه‌های پویا
        self.dynamic_thresholds = config.system_thresholds.copy()
        self.learning_rate = 0.1
        
    def register_handler(self, handler: Callable):
        """ثبت handler برای هشدارها"""
        self.alert_handlers.append(handler)
    
    async def check_system_alerts(self, metrics: SystemMetrics) -> List[Alert]:
        """بررسی هشدارهای سیستم"""
        alerts = []
        
        # بررسی CPU
        if metrics.cpu_percent >= self.dynamic_thresholds['cpu_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SYSTEM,
                message=f"CPU usage critical: {metrics.cpu_percent:.1f}%",
                source="system_monitor",
                data={"cpu_percent": metrics.cpu_percent}
            ))
        elif metrics.cpu_percent >= self.dynamic_thresholds['cpu_warning']:
            alerts.append(self._create_alert(
                level=AlertLevel.WARNING,
                type=AlertType.SYSTEM,
                message=f"CPU usage high: {metrics.cpu_percent:.1f}%",
                source="system_monitor",
                data={"cpu_percent": metrics.cpu_percent}
            ))
        
        # بررسی حافظه
        if metrics.memory_percent >= self.dynamic_thresholds['memory_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SYSTEM,
                message=f"Memory usage critical: {metrics.memory_percent:.1f}%",
                source="system_monitor",
                data={"memory_percent": metrics.memory_percent}
            ))
        elif metrics.memory_percent >= self.dynamic_thresholds['memory_warning']:
            alerts.append(self._create_alert(
                level=AlertLevel.WARNING,
                type=AlertType.SYSTEM,
                message=f"Memory usage high: {metrics.memory_percent:.1f}%",
                source="system_monitor",
                data={"memory_percent": metrics.memory_percent}
            ))
        
        # بررسی دما
        if metrics.cpu_temp and metrics.cpu_temp >= self.dynamic_thresholds['temperature_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SYSTEM,
                message=f"CPU temperature critical: {metrics.cpu_temp:.1f}°C",
                source="system_monitor",
                data={"cpu_temp": metrics.cpu_temp}
            ))
        
        # بررسی دیسک
        if metrics.disk_percent >= self.dynamic_thresholds['disk_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SYSTEM,
                message=f"Disk usage critical: {metrics.disk_percent:.1f}%",
                source="system_monitor",
                data={"disk_percent": metrics.disk_percent}
            ))
        
        return await self._filter_cooldown_alerts(alerts)
    
    async def check_session_alerts(self, metrics: SessionMetrics) -> List[Alert]:
        """بررسی هشدارهای session"""
        alerts = []
        
        # بررسی نرخ خطا
        if metrics.error_rate >= self.config.session_thresholds['error_rate_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SESSION,
                message=f"Session error rate critical: {metrics.error_rate:.1%}",
                source="session_monitor",
                data={"error_rate": metrics.error_rate}
            ))
        
        # بررسی سلامت session‌ها
        if metrics.avg_health_score <= self.config.session_thresholds['health_score_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.CRITICAL,
                type=AlertType.SESSION,
                message=f"Average session health critical: {metrics.avg_health_score:.1f}",
                source="session_monitor",
                data={"avg_health_score": metrics.avg_health_score}
            ))
        
        # بررسی تعداد session‌های فعال
        if metrics.active_sessions == 0:
            alerts.append(self._create_alert(
                level=AlertLevel.EMERGENCY,
                type=AlertType.SESSION,
                message="No active sessions available",
                source="session_monitor",
                data={"active_sessions": metrics.active_sessions}
            ))
        elif metrics.active_sessions < 2:
            alerts.append(self._create_alert(
                level=AlertLevel.WARNING,
                type=AlertType.SESSION,
                message=f"Low number of active sessions: {metrics.active_sessions}",
                source="session_monitor",
                data={"active_sessions": metrics.active_sessions}
            ))
        
        # بررسی زمان پاسخ
        if metrics.avg_response_time >= self.config.session_thresholds['response_time_critical']:
            alerts.append(self._create_alert(
                level=AlertLevel.WARNING,
                type=AlertType.PERFORMANCE,
                message=f"High response time: {metrics.avg_response_time:.2f}s",
                source="session_monitor",
                data={"avg_response_time": metrics.avg_response_time}
            ))
        
        return await self._filter_cooldown_alerts(alerts)
    
    def _create_alert(self, level: AlertLevel, type: AlertType, 
                     message: str, source: str, data: Dict = None) -> Alert:
        """ایجاد هشدار"""
        return Alert(
            level=level,
            type=type,
            message=message,
            timestamp=datetime.now(),
            source=source,
            data=data or {}
        )
    
    async def _filter_cooldown_alerts(self, alerts: List[Alert]) -> List[Alert]:
        """فیلتر هشدارهای در cooldown"""
        filtered_alerts = []
        now = time.time()
        
        for alert in alerts:
            alert_key = f"{alert.source}:{alert.message[:50]}"
            
            if alert_key in self.alert_cooldowns:
                last_alert_time = self.alert_cooldowns[alert_key]
                if now - last_alert_time < self.config.alert_cooldown_seconds:
                    continue
            
            self.alert_cooldowns[alert_key] = now
            filtered_alerts.append(alert)
        
        return filtered_alerts
    
    async def process_alerts(self, alerts: List[Alert]):
        """پردازش هشدارها"""
        for alert in alerts:
            # ذخیره هشدار
            await self.storage.store_alert(alert)
            
            # ثبت در active alerts
            self.active_alerts[alert.message] = alert
            
            # فراخوانی handlers
            for handler in self.alert_handlers:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler failed: {e}")
            
            logger.log(
                logging.ERROR if alert.level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY]
                else logging.WARNING if alert.level == AlertLevel.WARNING
                else logging.INFO,
                f"ALERT [{alert.level.value}]: {alert.message}"
            )
    
    async def acknowledge_alert(self, alert_message: str, acknowledged_by: str):
        """تأیید هشدار"""
        if alert_message in self.active_alerts:
            alert = self.active_alerts[alert_message]
            alert.acknowledged = True
            alert.acknowledged_by = acknowledged_by
            alert.acknowledged_at = datetime.now()
            
            await self.storage.store_alert(alert)
            
            logger.info(f"Alert acknowledged by {acknowledged_by}: {alert_message}")
    
    async def update_dynamic_thresholds(self, recent_metrics: List[SystemMetrics]):
        """به‌روزرسانی آستانه‌های پویا"""
        if len(recent_metrics) < 100:
            return
        
        # محاسبه میانگین‌ها
        cpu_values = [m.cpu_percent for m in recent_metrics[-100:]]
        memory_values = [m.memory_percent for m in recent_metrics[-100:]]
        
        cpu_mean = statistics.mean(cpu_values)
        cpu_std = statistics.stdev(cpu_values) if len(cpu_values) > 1 else 0
        
        # تنظیم آستانه‌های پویا
        self.dynamic_thresholds['cpu_warning'] = min(
            self.config.system_thresholds['cpu_warning'],
            cpu_mean + 2 * cpu_std
        )
        
        logger.debug(f"Updated dynamic thresholds: CPU warning = {self.dynamic_thresholds['cpu_warning']:.1f}%")

# ============================================
# سیستم مانیتورینگ پیشرفته
# ============================================

class AdvancedSessionMonitor:
    """سیستم مانیتورینگ پیشرفته session‌ها"""
    
    def __init__(self, config: Optional[MonitorConfig] = None,
                 session_manager = None):
        
        self.config = config or MonitorConfig()
        self.session_manager = session_manager
        self.storage = MetricsStorage()
        self.alert_system = SmartAlertSystem(self.config)
        
        # وضعیت مانیتور
        self.is_running = False
        self.start_time = datetime.now()
        self.checks_performed = 0
        self.alerts_triggered = 0
        
        # منابع سیستم
        self.disk_io_last = None
        self.net_io_last = None
        self.last_check_time = None
        
        # ثبت handler برای هشدارها
        self.alert_system.register_handler(self._handle_alert)
        
        logger.info("AdvancedSessionMonitor initialized")
    
    async def _handle_alert(self, alert: Alert):
        """Handler برای پردازش هشدارها"""
        # می‌توانید اینجا اقدامات خاصی انجام دهید
        # مثلاً ارسال ایمیل، پیام تلگرام، etc.
        
        if alert.level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY]:
            # اقدامات فوری
            await self._emergency_actions(alert)
        
        elif alert.level == AlertLevel.WARNING and self.config.enable_auto_remediation:
            # اقدامات خودکار
            await self._auto_remediate(alert)
    
    async def _emergency_actions(self, alert: Alert):
        """اقدامات اضطراری"""
        if alert.type == AlertType.SESSION and "No active sessions" in alert.message:
            logger.critical("EMERGENCY: No active sessions! Attempting recovery...")
            
            if self.session_manager:
                try:
                    # تلاش برای ایجاد session جدید
                    await self.session_manager.create_session(
                        api_id=0,  # باید مقادیر واقعی استفاده شود
                        api_hash="",
                        user_id=0
                    )
                except Exception as e:
                    logger.error(f"Failed to create emergency session: {e}")
    
    async def _auto_remediate(self, alert: Alert):
        """رفع خودکار مشکلات"""
        if alert.type == AlertType.SYSTEM and "CPU usage high" in alert.message:
            # کاهش فشار روی CPU
            logger.info("Auto-remediation: Reducing monitoring intensity")
            self.config.check_interval_seconds = min(
                600,  # حداکثر 10 دقیقه
                self.config.check_interval_seconds + 60  # افزایش interval
            )
    
    async def start(self, background: bool = False):
        """شروع مانیتورینگ"""
        self.is_running = True
        self.start_time = datetime.now()
        
        if background:
            # اجرا در background
            asyncio.create_task(self._monitoring_loop())
        else:
            # اجرای مستقیم
            await self._monitoring_loop()
    
    async def stop(self):
        """توقف مانیتورینگ"""
        self.is_running = False
        logger.info("Monitor stopped")
    
    async def _monitoring_loop(self):
        """حلقه اصلی مانیتورینگ"""
        logger.info("Starting monitoring loop...")
        
        backoff = 1
        max_backoff = 60
        
        while self.is_running:
            try:
                await self.perform_check()
                backoff = 1  # reset backoff
                await asyncio.sleep(self.config.check_interval_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor check failed: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)  # exponential backoff
    
    async def perform_check(self):
        """انجام بررسی کامل"""
        self.checks_performed += 1
        check_start = datetime.now()
        
        try:
            # جمع‌آوری متریک‌های سیستم
            system_metrics = await self._collect_system_metrics()
            await self.storage.store_system_metrics(system_metrics)
            
            # جمع‌آوری متریک‌های session
            session_metrics = await self._collect_session_metrics()
            if session_metrics:
                await self.storage.store_session_metrics(session_metrics)
            
            # بررسی هشدارها
            system_alerts = await self.alert_system.check_system_alerts(system_metrics)
            if session_metrics:
                session_alerts = await self.alert_system.check_session_alerts(session_metrics)
                all_alerts = system_alerts + session_alerts
            else:
                all_alerts = system_alerts
            
            if all_alerts:
                await self.alert_system.process_alerts(all_alerts)
                self.alerts_triggered += len(all_alerts)
            
            # به‌روزرسانی آستانه‌های پویا
            recent_metrics = list(self.storage.system_metrics_cache)[-100:]
            if recent_metrics:
                await self.alert_system.update_dynamic_thresholds(recent_metrics)
            
            # پاکسازی داده‌های قدیمی (هر 24 ساعت)
            if self.checks_performed % (24 * 3600 // self.config.check_interval_seconds) == 0:
                await self.storage.cleanup_old_data(self.config.metrics_retention_days)
            
            check_duration = (datetime.now() - check_start).total_seconds()
            logger.debug(f"Check #{self.checks_performed} completed in {check_duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Check #{self.checks_performed} failed: {e}")
            raise
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """جمع‌آوری متریک‌های سیستم"""
        try:
            # CPU
            cpu_percent = await asyncio.get_event_loop().run_in_executor(
                None, lambda: psutil.cpu_percent(interval=0.5)
            )
            
            # حافظه
            memory = await asyncio.get_event_loop().run_in_executor(
                None, psutil.virtual_memory
            )
            
            # دیسک
            disk = await asyncio.get_event_loop().run_in_executor(
                None, lambda: psutil.disk_usage('/')
            )
            
            # دمای CPU (اگر در دسترس باشد)
            cpu_temp = None
            try:
                if hasattr(psutil, "sensors_temperatures"):
                    temps = await asyncio.get_event_loop().run_in_executor(
                        None, psutil.sensors_temperatures
                    )
                    if temps and 'coretemp' in temps:
                        cpu_temp = temps['coretemp'][0].current
            except:
                pass
            
            # I/O دیسک
            disk_io = await asyncio.get_event_loop().run_in_executor(
                None, psutil.disk_io_counters
            )
            
            disk_io_read_mb = 0.0
            disk_io_write_mb = 0.0
            
            if disk_io and self.disk_io_last:
                # محاسبه تفاضل
                read_diff = disk_io.read_bytes - self.disk_io_last.read_bytes
                write_diff = disk_io.write_bytes - self.disk_io_last.write_bytes
                
                if self.last_check_time:
                    time_diff = (datetime.now() - self.last_check_time).total_seconds()
                    if time_diff > 0:
                        disk_io_read_mb = (read_diff / time_diff) / (1024 * 1024)
                        disk_io_write_mb = (write_diff / time_diff) / (1024 * 1024)
            
            self.disk_io_last = disk_io
            
            # شبکه
            net_io = await asyncio.get_event_loop().run_in_executor(
                None, psutil.net_io_counters
            )
            
            net_sent_mb = 0.0
            net_recv_mb = 0.0
            
            if net_io and self.net_io_last:
                sent_diff = net_io.bytes_sent - self.net_io_last.bytes_sent
                recv_diff = net_io.bytes_recv - self.net_io_last.bytes_recv
                
                if self.last_check_time:
                    time_diff = (datetime.now() - self.last_check_time).total_seconds()
                    if time_diff > 0:
                        net_sent_mb = (sent_diff / time_diff) / (1024 * 1024)
                        net_recv_mb = (recv_diff / time_diff) / (1024 * 1024)
            
            self.net_io_last = net_io
            self.last_check_time = datetime.now()
            
            # تعداد processes
            processes = await asyncio.get_event_loop().run_in_executor(
                None, lambda: len(list(psutil.process_iter(['pid'])))
            )
            
            # load average
            load_avg = None
            try:
                load_avg = psutil.getloadavg()
            except:
                pass
            
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                cpu_temp=cpu_temp,
                memory_percent=memory.percent,
                memory_used_gb=memory.used / (1024**3),
                memory_available_gb=memory.available / (1024**3),
                disk_percent=disk.percent,
                disk_free_gb=disk.free / (1024**3),
                disk_io_read_mb=disk_io_read_mb,
                disk_io_write_mb=disk_io_write_mb,
                network_sent_mb=net_sent_mb,
                network_recv_mb=net_recv_mb,
                processes_count=processes,
                load_average=load_avg
            )
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_gb=0.0,
                memory_available_gb=0.0,
                disk_percent=0.0,
                disk_free_gb=0.0
            )
    
    async def _collect_session_metrics(self) -> Optional[SessionMetrics]:
        """جمع‌آوری متریک‌های session"""
        if not self.session_manager:
            return None
        
        try:
            # دریافت گزارش از session manager
            # این بخش باید با session manager واقعی شما تطبیق داده شود
            report = await self.session_manager.export_comprehensive_report()
            
            sessions = report.get('sessions', [])
            if not sessions:
                return None
            
            # محاسبه متریک‌ها
            total_sessions = len(sessions)
            
            # این بخش باید بر اساس ساختار گزارش شما تنظیم شود
            active_sessions = sum(1 for s in sessions if s.get('status') == 'active')
            healthy_sessions = sum(1 for s in sessions if s.get('health_score', 100) >= 70)
            warning_sessions = sum(1 for s in sessions if 30 <= s.get('health_score', 100) < 70)
            critical_sessions = sum(1 for s in sessions if s.get('health_score', 100) < 30)
            
            # محاسبه میانگین‌ها
            health_scores = [s.get('health_score', 100) for s in sessions]
            avg_health_score = sum(health_scores) / len(health_scores) if health_scores else 100.0
            
            error_counts = [s.get('error_count', 0) for s in sessions]
            request_counts = [s.get('requests_count', 1) for s in sessions]
            
            total_errors = sum(error_counts)
            total_requests = sum(request_counts)
            error_rate = total_errors / total_requests if total_requests > 0 else 0.0
            
            response_times = [s.get('avg_response_time', 0) for s in sessions if s.get('avg_response_time')]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0.0
            
            failed_requests = sum(s.get('failed_requests', 0) for s in sessions)
            
            # شمارش چرخش‌ها (بر اساس ساختار گزارش شما)
            rotation_history = report.get('rotation_history', [])
            rotations_24h = len([
                r for r in rotation_history 
                if datetime.fromisoformat(r['timestamp'].replace('Z', '+00:00')) > 
                   datetime.now() - timedelta(hours=24)
            ])
            
            return SessionMetrics(
                timestamp=datetime.now(),
                total_sessions=total_sessions,
                active_sessions=active_sessions,
                healthy_sessions=healthy_sessions,
                warning_sessions=warning_sessions,
                critical_sessions=critical_sessions,
                avg_health_score=avg_health_score,
                error_rate=error_rate,
                avg_response_time=avg_response_time,
                total_requests=total_requests,
                failed_requests=failed_requests,
                session_rotations_24h=rotations_24h
            )
            
        except Exception as e:
            logger.error(f"Failed to collect session metrics: {e}")
            return None
    
    async def get_dashboard_data(self, hours: int = 24) -> Dict:
        """دریافت داده‌های dashboard"""
        metrics = await self.storage.get_recent_metrics(hours)
        
        # محاسبه خلاصه
        if metrics['system']:
            latest_system = metrics['system'][-1]
        else:
            latest_system = None
        
        if metrics['session']:
            latest_session = metrics['session'][-1]
        else:
            latest_session = None
        
        # محاسبه trends
        trends = await self._calculate_trends(metrics)
        
        # وضعیت کلی
        overall_status = self._calculate_overall_status(latest_system, latest_session)
        
        return {
            'status': overall_status,
            'uptime': (datetime.now() - self.start_time).total_seconds(),
            'checks_performed': self.checks_performed,
            'alerts_triggered': self.alerts_triggered,
            'latest_system': latest_system,
            'latest_session': latest_session,
            'recent_alerts': metrics['alerts'],
            'trends': trends,
            'recommendations': await self._generate_recommendations(
                latest_system, latest_session, trends
            )
        }
    
    async def _calculate_trends(self, metrics: Dict) -> Dict:
        """محاسبه روندها"""
        trends = {}
        
        if len(metrics['system']) >= 2:
            system_data = metrics['system']
            
            # روند CPU
            cpu_values = [m.cpu_percent for m in system_data[-10:]]
            if len(cpu_values) >= 2:
                trends['cpu_trend'] = 'increasing' if cpu_values[-1] > cpu_values[0] else 'decreasing'
                trends['cpu_change'] = cpu_values[-1] - cpu_values[0]
            
            # روند حافظه
            memory_values = [m.memory_percent for m in system_data[-10:]]
            if len(memory_values) >= 2:
                trends['memory_trend'] = 'increasing' if memory_values[-1] > memory_values[0] else 'decreasing'
                trends['memory_change'] = memory_values[-1] - memory_values[0]
        
        if len(metrics['session']) >= 2:
            session_data = metrics['session']
            
            # روند سلامت session
            health_values = [m.avg_health_score for m in session_data[-10:]]
            if len(health_values) >= 2:
                trends['health_trend'] = 'improving' if health_values[-1] > health_values[0] else 'declining'
                trends['health_change'] = health_values[-1] - health_values[0]
        
        return trends
    
    def _calculate_overall_status(self, system_metrics, session_metrics) -> str:
        """محاسبه وضعیت کلی"""
        if not system_metrics and not session_metrics:
            return "unknown"
        
        statuses = []
        
        if system_metrics:
            if system_metrics.cpu_percent > 90 or system_metrics.memory_percent > 90:
                statuses.append("critical")
            elif system_metrics.cpu_percent > 70 or system_metrics.memory_percent > 75:
                statuses.append("warning")
            else:
                statuses.append("healthy")
        
        if session_metrics:
            if session_metrics.active_sessions == 0:
                statuses.append("critical")
            elif session_metrics.avg_health_score < 30:
                statuses.append("critical")
            elif session_metrics.avg_health_score < 50:
                statuses.append("warning")
            else:
                statuses.append("healthy")
        
        if "critical" in statuses:
            return "critical"
        elif "warning" in statuses:
            return "warning"
        else:
            return "healthy"
    
    async def _generate_recommendations(self, system_metrics, session_metrics, trends) -> List[Dict]:
        """تولید توصیه‌ها"""
        recommendations = []
        
        if system_metrics:
            # توصیه‌های سیستم
            if system_metrics.memory_percent > 80:
                recommendations.append({
                    'priority': 'high',
                    'category': 'system',
                    'action': 'free_up_memory',
                    'message': 'حافظه سیستم در سطح بالایی است',
                    'details': 'برنامه‌های غیرضروری را ببندید یا حافظه سیستم را افزایش دهید'
                })
            
            if system_metrics.disk_percent > 85:
                recommendations.append({
                    'priority': 'high',
                    'category': 'system',
                    'action': 'cleanup_disk',
                    'message': 'فضای دیسک در حال اتمام است',
                    'details': 'فایل‌های موقت و لاگ‌های قدیمی را پاک کنید'
                })
        
        if session_metrics:
            # توصیه‌های session
            if session_metrics.active_sessions < 2:
                recommendations.append({
                    'priority': 'critical',
                    'category': 'session',
                    'action': 'create_backup_session',
                    'message': 'تنها یک session فعال وجود دارد',
                    'details': 'برای افزونگی، حداقل یک session پشتیبان ایجاد کنید'
                })
            
            if session_metrics.avg_health_score < 40:
                recommendations.append({
                    'priority': 'high',
                    'category': 'session',
                    'action': 'investigate_sessions',
                    'message': 'سلامت session‌ها پایین است',
                    'details': 'session‌های مشکل‌دار را بررسی و ترمیم کنید'
                })
            
            if session_metrics.error_rate > 0.2:
                recommendations.append({
                    'priority': 'medium',
                    'category': 'session',
                    'action': 'rotate_problematic_sessions',
                    'message': 'نرخ خطای session‌ها بالا است',
                    'details': 'session‌های پرخطا را چرخش دهید'
                })
        
        # توصیه‌های بر اساس روند
        if trends.get('cpu_trend') == 'increasing' and trends.get('cpu_change', 0) > 10:
            recommendations.append({
                'priority': 'medium',
                'category': 'trend',
                'action': 'monitor_cpu_trend',
                'message': 'مصرف CPU در حال افزایش است',
                'details': 'برنامه‌های جدید یا نشتی حافظه را بررسی کنید'
            })
        
        return recommendations
    
    async def generate_report(self, report_type: str = "summary", 
                            output_format: str = "json") -> Any:
        """تولید گزارش"""
        
        if report_type == "summary":
            data = await self.get_dashboard_data(hours=24)
            
        elif report_type == "detailed":
            data = {
                'dashboard': await self.get_dashboard_data(hours=72),
                'system_metrics': list(self.storage.system_metrics_cache)[-100:],
                'session_metrics': list(self.storage.session_metrics_cache)[-100:],
                'recent_alerts': list(self.storage.alerts_cache)[-50:],
                'config': asdict(self.config)
            }
        
        elif report_type == "health":
            data = await self._generate_health_report()
        
        else:
            raise ValueError(f"Unknown report type: {report_type}")
        
        if output_format == "json":
            return json.dumps(data, indent=2, default=str, ensure_ascii=False)
        
        elif output_format == "html":
            return await self._generate_html_report(data, report_type)
        
        else:
            return data
    
    async def _generate_health_report(self) -> Dict:
        """تولید گزارش سلامت"""
        dashboard = await self.get_dashboard_data(hours=24)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'overall_health': dashboard['status'],
            'score': self._calculate_health_score(dashboard),
            'components': {
                'system': self._evaluate_system_health(dashboard.get('latest_system')),
                'sessions': self._evaluate_session_health(dashboard.get('latest_session')),
                'alerts': self._evaluate_alert_health(dashboard.get('recent_alerts', [])),
                'trends': self._evaluate_trend_health(dashboard.get('trends', {}))
            },
            'checks': {
                'total_checks': self.checks_performed,
                'failed_checks': 0,  # باید از logs محاسبه شود
                'success_rate': 100.0  # باید محاسبه شود
            }
        }
    
    def _calculate_health_score(self, dashboard: Dict) -> float:
        """محاسبه امتیاز سلامت"""
        score = 100.0
        
        # کسر بر اساس وضعیت
        if dashboard['status'] == 'critical':
            score -= 40
        elif dashboard['status'] == 'warning':
            score -= 20
        
        # کسر بر اساس تعداد هشدارها
        alert_count = len(dashboard.get('recent_alerts', []))
        score -= min(alert_count * 5, 30)
        
        # کسر بر اساس روندهای منفی
        trends = dashboard.get('trends', {})
        if trends.get('cpu_trend') == 'increasing' and trends.get('cpu_change', 0) > 15:
            score -= 10
        if trends.get('memory_trend') == 'increasing' and trends.get('memory_change', 0) > 10:
            score -= 10
        
        return max(0.0, min(100.0, score))
    
    def _evaluate_system_health(self, system_metrics) -> Dict:
        """ارزیابی سلامت سیستم"""
        if not system_metrics:
            return {'status': 'unknown', 'score': 0}
        
        score = 100.0
        
        if system_metrics.cpu_percent > 90:
            score -= 40
        elif system_metrics.cpu_percent > 70:
            score -= 20
        
        if system_metrics.memory_percent > 90:
            score -= 40
        elif system_metrics.memory_percent > 75:
            score -= 20
        
        if system_metrics.disk_percent > 95:
            score -= 30
        elif system_metrics.disk_percent > 85:
            score -= 15
        
        status = "healthy" if score >= 70 else "warning" if score >= 40 else "critical"
        
        return {
            'status': status,
            'score': score,
            'critical_metrics': [
                m for m in [
                    'cpu_percent' if system_metrics.cpu_percent > 80 else None,
                    'memory_percent' if system_metrics.memory_percent > 80 else None,
                    'disk_percent' if system_metrics.disk_percent > 90 else None
                ] if m is not None
            ]
        }
    
    def _evaluate_session_health(self, session_metrics) -> Dict:
        """ارزیابی سلامت session‌ها"""
        if not session_metrics:
            return {'status': 'unknown', 'score': 0}
        
        score = 100.0
        
        if session_metrics.active_sessions == 0:
            score -= 60
        elif session_metrics.active_sessions < 2:
            score -= 30
        
        if session_metrics.avg_health_score < 30:
            score -= 40
        elif session_metrics.avg_health_score < 50:
            score -= 20
        
        if session_metrics.error_rate > 0.3:
            score -= 30
        elif session_metrics.error_rate > 0.1:
            score -= 15
        
        status = "healthy" if score >= 70 else "warning" if score >= 40 else "critical"
        
        return {
            'status': status,
            'score': score,
            'critical_metrics': [
                m for m in [
                    'active_sessions' if session_metrics.active_sessions < 2 else None,
                    'health_score' if session_metrics.avg_health_score < 40 else None,
                    'error_rate' if session_metrics.error_rate > 0.2 else None
                ] if m is not None
            ]
        }
    
    def _evaluate_alert_health(self, recent_alerts: List) -> Dict:
        """ارزیابی سلامت بر اساس هشدارها"""
        if not recent_alerts:
            return {'status': 'healthy', 'score': 100, 'critical_alerts': 0, 'warning_alerts': 0}
        
        critical_alerts = len([a for a in recent_alerts if a.get('level') in ['critical', 'emergency']])
        warning_alerts = len([a for a in recent_alerts if a.get('level') == 'warning'])
        
        score = 100.0 - (critical_alerts * 20) - (warning_alerts * 10)
        score = max(0.0, score)
        
        status = "healthy" if score >= 70 else "warning" if score >= 40 else "critical"
        
        return {
            'status': status,
            'score': score,
            'critical_alerts': critical_alerts,
            'warning_alerts': warning_alerts
        }
    
    def _evaluate_trend_health(self, trends: Dict) -> Dict:
        """ارزیابی سلامت بر اساس روندها"""
        if not trends:
            return {'status': 'unknown', 'score': 100}
        
        score = 100.0
        
        negative_trends = 0
        if trends.get('cpu_trend') == 'increasing' and trends.get('cpu_change', 0) > 10:
            negative_trends += 1
        if trends.get('memory_trend') == 'increasing' and trends.get('memory_change', 0) > 5:
            negative_trends += 1
        if trends.get('health_trend') == 'declining' and trends.get('health_change', 0) < -10:
            negative_trends += 2
        
        score -= negative_trends * 10
        
        status = "healthy" if score >= 80 else "warning" if score >= 60 else "critical"
        
        return {
            'status': status,
            'score': score,
            'negative_trends': negative_trends
        }
    
    async def _generate_html_report(self, data: Dict, report_type: str) -> str:
        """تولید گزارش HTML"""
        # پیاده‌سازی ساده‌تر از نسخه اصلی
        html_template = """
        <!DOCTYPE html>
        <html dir="rtl">
        <head>
            <meta charset="UTF-8">
            <title>گزارش مانیتورینگ Session</title>
            <style>
                body { font-family: Tahoma, sans-serif; margin: 20px; }
                .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }
                .status-healthy { color: #4caf50; }
                .status-warning { color: #ff9800; }
                .status-critical { color: #f44336; }
                .card { border: 1px solid #ddd; border-radius: 5px; padding: 15px; margin: 10px 0; }
                table { width: 100%; border-collapse: collapse; margin: 10px 0; }
                th, td { padding: 10px; text-align: right; border: 1px solid #ddd; }
                th { background: #f5f5f5; }
                .recommendation { padding: 10px; margin: 5px 0; border-right: 4px solid; }
                .priority-high { border-color: #f44336; background: #ffebee; }
                .priority-medium { border-color: #ff9800; background: #fff3e0; }
                .priority-low { border-color: #4caf50; background: #e8f5e9; }
            </style>
        </head>
        <body>
            <div class="header">
                <h1>📊 گزارش مانیتورینگ Session</h1>
                <p>تاریخ تولید: {timestamp}</p>
                <p>وضعیت کلی: <span class="status-{overall_status}">{overall_status_fa}</span></p>
            </div>
            
            {content}
        </body>
        </html>
        """
        
        # ترجمه وضعیت به فارسی
        status_map = {
            'healthy': 'سالم',
            'warning': 'هشدار',
            'critical': 'بحرانی',
            'unknown': 'نامشخص'
        }
        
        if report_type == "summary":
            overall_status = data['status']
            content = f"""
            <div class="card">
                <h2>📈 آمار کلی</h2>
                <p>مدت فعالیت: {data['uptime']:.0f} ثانیه</p>
                <p>تعداد بررسی‌ها: {data['checks_performed']}</p>
                <p>هشدارهای فعال: {data['alerts_triggered']}</p>
            </div>
            
            <div class="card">
                <h2>🎯 توصیه‌ها</h2>
                {self._generate_recommendations_html(data.get('recommendations', []))}
            </div>
            """
        
        else:
            overall_status = data.get('overall_health', 'unknown')
            content = "<h2>گزارش تفصیلی</h2>"
        
        overall_status_fa = status_map.get(overall_status, overall_status)
        
        return html_template.format(
            timestamp=datetime.now().isoformat(),
            overall_status=overall_status,
            overall_status_fa=overall_status_fa,
            content=content
        )
    
    def _generate_recommendations_html(self, recommendations: List[Dict]) -> str:
        """تولید HTML برای توصیه‌ها"""
        if not recommendations:
            return "<p>✅ هیچ توصیه‌ای در حال حاضر وجود ندارد.</p>"
        
        html = ""
        for rec in recommendations:
            priority_class = f"priority-{rec['priority']}"
            html += f"""
            <div class="recommendation {priority_class}">
                <strong>{rec['message']}</strong>
                <p>{rec['details']}</p>
                <small>دسته: {rec['category']} | اقدام: {rec['action']}</small>
            </div>
            """
        
        return html

# ============================================
# تابع اصلی و CLI
# ============================================

async def create_monitor(config: Optional[MonitorConfig] = None,
                        session_manager = None) -> AdvancedSessionMonitor:
    """ایجاد instance از مانیتور"""
    monitor = AdvancedSessionMonitor(config=config, session_manager=session_manager)
    return monitor

async def main():
    """تابع اصلی"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='سیستم مانیتورینگ پیشرفته session‌ها',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
مثال‌ها:
  %(prog)s --daemon              # اجرا به عنوان سرویس
  %(prog)s --report summary      # تولید گزارش خلاصه
  %(prog)s --interval 60         # بررسی هر 60 ثانیه
  %(prog)s --report health --format html  # گزارش سلامت HTML
        """
    )
    
    parser.add_argument('--daemon', action='store_true',
                       help='اجرا به عنوان سرویس')
    parser.add_argument('--interval', type=int, default=300,
                       help='فاصله بررسی به ثانیه (پیش‌فرض: 300)')
    parser.add_argument('--report', choices=['summary', 'detailed', 'health'],
                       help='تولید گزارش و خروج')
    parser.add_argument('--format', choices=['json', 'html', 'text'],
                       default='json', help='فرمت گزارش')
    parser.add_argument('--hours', type=int, default=24,
                       help='ساعت‌های گذشته برای تحلیل')
    parser.add_argument('--config', type=str,
                       help='فایل تنظیمات JSON')
    parser.add_argument('--verbose', '-v', action='count', default=0,
                       help='افزایش سطح جزئیات لاگ')
    
    args = parser.parse_args()
    
    # تنظیم سطح لاگ
    if args.verbose >= 2:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.verbose >= 1:
        logging.getLogger().setLevel(logging.INFO)
    
    # بارگذاری تنظیمات
    config = MonitorConfig(check_interval_seconds=args.interval)
    
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                # می‌توانید تنظیمات را اعمال کنید
                logger.info(f"Loaded config from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
    
    # ایجاد مانیتور
    monitor = await create_monitor(config=config)
    
    try:
        if args.daemon:
            # اجرا به عنوان سرویس
            logger.info("Starting monitor daemon...")
            
            # ثبت handler برای سیگنال‌ها
            def signal_handler(signum, frame):
                logger.info(f"Received signal {signum}, shutting down...")
                asyncio.create_task(monitor.stop())
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            await monitor.start(background=False)
            
        elif args.report:
            # تولید گزارش
            logger.info(f"Generating {args.report} report...")
            
            # انجام یک بررسی اولیه
            await monitor.perform_check()
            
            # تولید گزارش
            report = await monitor.generate_report(
                report_type=args.report,
                output_format=args.format
            )
            
            if args.format == "json":
                print(report)
            elif args.format == "html":
                # ذخیره HTML در فایل
                filename = f"report_{args.report}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                async with aiofiles.open(filename, 'w', encoding='utf-8') as f:
                    await f.write(report)
                print(f"✅ گزارش ذخیره شد: {filename}")
            else:
                print(report)
            
            await monitor.stop()
            
        else:
            # اجرای یکبار
            logger.info("Performing single check...")
            await monitor.perform_check()
            
            dashboard = await monitor.get_dashboard_data()
            print(json.dumps(dashboard, indent=2, default=str, ensure_ascii=False))
            
            await monitor.stop()
    
    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user")
        await monitor.stop()
    
    except Exception as e:
        logger.error(f"Monitor failed: {e}")
        await monitor.stop()
        raise

if __name__ == "__main__":
    asyncio.run(main())
