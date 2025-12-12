#core/monitor.py
"""
سیستم مانیتورینگ Real-time با AI
"""

import asyncio
import time
import json
import math
from typing import Dict, List, Optional, Callable, Any, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import logging
from pathlib import Path
import threading
from collections import deque, defaultdict
import statistics
from concurrent.futures import ThreadPoolExecutor
import psutil
import numpy as np
from prometheus_client import Counter, Gauge, Histogram, Summary, start_http_server
import msgpack

from .models.speed_data import SpeedData, TransferStats, NetworkMetrics
from .ai_predictor import AISpeedPredictor
from .network_analyzer import NetworkAnalyzer
from config.settings import config_manager

logger = logging.getLogger(__name__)

# متریک‌های Prometheus
METRICS = {
    'download_speed': Gauge('download_speed_mbps', 'Download speed in Mbps'),
    'upload_speed': Gauge('upload_speed_mbps', 'Upload speed in Mbps'),
    'active_transfers': Gauge('active_transfers', 'Number of active transfers'),
    'transfer_duration': Histogram('transfer_duration_seconds', 'Transfer duration'),
    'bytes_transferred': Counter('bytes_transferred_total', 'Total bytes transferred'),
    'transfer_errors': Counter('transfer_errors_total', 'Total transfer errors'),
    'cache_hits': Counter('cache_hits_total', 'Total cache hits'),
    'retry_attempts': Counter('retry_attempts_total', 'Total retry attempts'),
}

@dataclass
class TransferContext:
    """context کامل انتقال"""
    transfer_id: str
    user_id: str
    file_name: str
    file_size: int
    transfer_type: str
    start_time: float = field(default_factory=time.time)
    status: str = "pending"
    priority: int = 5  # 1-10
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Performance tracking
    speed_samples: List[float] = field(default_factory=list)
    error_count: int = 0
    retry_count: int = 0
    last_checkpoint: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class AdaptiveSpeedMonitor:
    """مانیتور سرعت تطبیقی با AI"""
    
    def __init__(self, config=None):
        self.config = config or config_manager.settings
        self.update_interval = self.config.monitoring['update_interval_ms'] / 1000
        
        # State management
        self.active_transfers: Dict[str, TransferContext] = {}
        self.transfer_history: Dict[str, List[SpeedData]] = defaultdict(deque)
        self.user_sessions: Dict[str, List[str]] = defaultdict(list)
        
        # Callback system
        self.callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self.global_callbacks: List[Callable] = []
        
        # Locks for thread safety
        self._transfer_lock = asyncio.Lock()
        self._callback_lock = asyncio.Lock()
        self._history_lock = asyncio.Lock()
        
        # AI and Analytics
        self.ai_predictor = AISpeedPredictor()
        self.network_analyzer = NetworkAnalyzer()
        
        # Performance optimization
        self.speed_buffer = deque(maxlen=100)
        self.avg_speeds = defaultdict(lambda: deque(maxlen=50))
        
        # Metrics exporter
        if self.config.monitoring['enable_metrics']:
            self._start_metrics_server()
        
        # Background tasks
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._analysis_task = asyncio.create_task(self._periodic_analysis())
        self._backup_task = asyncio.create_task(self._periodic_backup())
        
        logger.info(f"AdaptiveSpeedMonitor initialized with AI: {self.config.ai['enabled']}")
    
    def _start_metrics_server(self):
        """شروع سرور متریک‌ها"""
        try:
            start_http_server(self.config.monitoring['metrics_port'])
            logger.info(f"Metrics server started on port {self.config.monitoring['metrics_port']}")
        except Exception as e:
            logger.warning(f"Failed to start metrics server: {e}")
    
    async def register_transfer(
        self,
        transfer_id: str,
        user_id: str,
        file_name: str,
        file_size: int,
        transfer_type: str,
        priority: int = 5,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> TransferContext:
        """ثبت انتقال جدید با context کامل"""
        async with self._transfer_lock:
            # پیش‌بینی سرعت با AI
            predicted_speed = None
            if self.config.ai['enabled']:
                predicted_speed = await self.ai_predictor.predict_speed(
                    file_size=file_size,
                    user_id=user_id,
                    time_of_day=datetime.now().hour,
                    network_type=await self.network_analyzer.get_network_type()
                )
            
            context = TransferContext(
                transfer_id=transfer_id,
                user_id=user_id,
                file_name=file_name,
                file_size=file_size,
                transfer_type=transfer_type,
                priority=priority,
                tags=tags or set(),
                metadata=metadata or {}
            )
            
            if predicted_speed:
                context.metadata['predicted_speed_mbps'] = predicted_speed
            
            self.active_transfers[transfer_id] = context
            self.user_sessions[user_id].append(transfer_id)
            
            # ارسال event
            await self._emit_event('transfer_started', {
                'transfer_id': transfer_id,
                'user_id': user_id,
                'file_size': file_size,
                'predicted_speed': predicted_speed
            })
            
            METRICS['active_transfers'].inc()
            
            logger.info(f"Transfer registered: {transfer_id} ({transfer_type}), "
                       f"Predicted speed: {predicted_speed} Mbps")
            
            return context
    
    async def update_transfer_progress(
        self,
        transfer_id: str,
        bytes_transferred: int,
        total_bytes: Optional[int] = None,
        speed_bps: Optional[float] = None,
        network_metrics: Optional[NetworkMetrics] = None
    ) -> Optional[SpeedData]:
        """به‌روزرسانی پیشرفت با دقت بالا"""
        async with self._transfer_lock:
            if transfer_id not in self.active_transfers:
                logger.warning(f"Transfer not found: {transfer_id}")
                return None
            
            context = self.active_transfers[transfer_id]
            current_time = time.time()
            
            # محاسبه سرعت آنی اگر ارائه نشده
            if speed_bps is None and context.last_checkpoint:
                elapsed = current_time - context.last_checkpoint
                if elapsed > 0:
                    bytes_since_last = bytes_transferred - context.metadata.get('last_bytes', 0)
                    speed_bps = bytes_since_last / elapsed
            
            # ایجاد SpeedData
            if total_bytes is None:
                total_bytes = context.file_size
            
            remaining_bytes = max(0, total_bytes - bytes_transferred)
            progress_percent = (bytes_transferred / total_bytes * 100) if total_bytes > 0 else 0
            
            # محاسبه سرعت متوسط
            total_elapsed = current_time - context.start_time
            avg_speed_bps = bytes_transferred / total_elapsed if total_elapsed > 0 else 0
            
            # محاسبه ETA تطبیقی
            eta_seconds = self._calculate_adaptive_eta(
                bytes_transferred, total_bytes, context.speed_samples, avg_speed_bps
            )
            
            speed_data = SpeedData(
                timestamp=current_time,
                bytes_transferred=bytes_transferred,
                total_bytes=total_bytes,
                transfer_type=context.transfer_type,
                speed_bps=speed_bps or avg_speed_bps,
                speed_kbps=(speed_bps or avg_speed_bps) / 1024,
                speed_mbps=(speed_bps or avg_speed_bps) / (1024 * 1024),
                progress_percent=progress_percent,
                eta_seconds=eta_seconds,
                remaining_bytes=remaining_bytes,
                network_metrics=network_metrics,
                transfer_id=transfer_id,
                user_id=context.user_id
            )
            
            # ذخیره نمونه سرعت
            context.speed_samples.append(speed_bps or avg_speed_bps)
            
            # به‌روزرسانی تاریخچه
            async with self._history_lock:
                self.transfer_history[transfer_id].append(speed_data)
                
                # محدود کردن سایز تاریخچه
                max_history = self.config.monitoring['history_size']
                if len(self.transfer_history[transfer_id]) > max_history:
                    self.transfer_history[transfer_id].popleft()
            
            # به‌روزرسانی متریک‌ها
            if speed_data.transfer_type == 'download':
                METRICS['download_speed'].set(speed_data.speed_mbps)
            else:
                METRICS['upload_speed'].set(speed_data.speed_mbps)
            
            METRICS['bytes_transferred'].inc(bytes_transferred - context.metadata.get('last_bytes', 0))
            
            # به‌روزرسانی context
            context.metadata['last_bytes'] = bytes_transferred
            context.metadata['last_speed'] = speed_bps
            context.last_checkpoint = current_time
            
            # فراخوانی callbackها
            await self._execute_callbacks(transfer_id, speed_data)
            
            # یادگیری AI
            if self.config.ai['enabled'] and len(context.speed_samples) > 10:
                asyncio.create_task(
                    self.ai_predictor.update_model(
                        user_id=context.user_id,
                        actual_speed=speed_data.speed_mbps,
                        file_size=context.file_size,
                        network_metrics=network_metrics
                    )
                )
            
            return speed_data
    
    def _calculate_adaptive_eta(
        self,
        bytes_transferred: int,
        total_bytes: int,
        speed_samples: List[float],
        current_avg_speed: float
    ) -> float:
        """محاسبه ETA تطبیقی با AI"""
        if not speed_samples or current_avg_speed <= 0:
            return 0
        
        remaining_bytes = total_bytes - bytes_transferred
        
        # استفاده از چندین روش محاسبه
        methods = []
        
        # 1. سرعت فعلی
        if speed_samples:
            methods.append(remaining_bytes / speed_samples[-1])
        
        # 2. سرعت متوسط
        methods.append(remaining_bytes / current_avg_speed)
        
        # 3. سرعت وزنی (سرعت‌های اخیر وزن بیشتر)
        if len(speed_samples) >= 5:
            weighted_speeds = []
            weights = np.linspace(0.5, 1.0, len(speed_samples[-5:]))
            for speed, weight in zip(speed_samples[-5:], weights):
                weighted_speeds.append(speed * weight)
            weighted_avg = sum(weighted_speeds) / sum(weights)
            methods.append(remaining_bytes / weighted_avg)
        
        # 4. پیش‌بینی AI
        if self.config.ai['enabled'] and len(speed_samples) > 10:
            predicted_speed = self.ai_predictor.predict_future_speed(speed_samples)
            if predicted_speed > 0:
                methods.append(remaining_bytes / predicted_speed)
        
        # انتخاب بهترین ETA (کمترین مقدار محافظه‌کارانه)
        return max(methods) if methods else 0
    
    async def _execute_callbacks(self, transfer_id: str, speed_data: SpeedData):
        """اجرای callbackها به صورت موازی"""
        callbacks_to_execute = []
        
        async with self._callback_lock:
            # Callbackهای اختصاصی
            if transfer_id in self.callbacks:
                callbacks_to_execute.extend(self.callbacks[transfer_id])
            
            # Callbackهای جهانی
            callbacks_to_execute.extend(self.global_callbacks)
        
        # اجرای موازی
        if callbacks_to_execute:
            tasks = []
            for callback in callbacks_to_execute:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        tasks.append(callback(speed_data))
                    else:
                        # اجرا در thread pool برای blocking functions
                        tasks.append(
                            asyncio.get_event_loop().run_in_executor(
                                None, callback, speed_data
                            )
                        )
                except Exception as e:
                    logger.error(f"Callback preparation error: {e}")
            
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """ارسال event به listeners"""
        # اینجا می‌توان به سیستم event-driven مثل Redis/Kafka وصل شد
        logger.debug(f"Event emitted: {event_type} - {data}")
    
    async def complete_transfer(
        self,
        transfer_id: str,
        success: bool = True,
        error_message: str = "",
        final_stats: Optional[Dict[str, Any]] = None
    ):
        """تکمیل انتقال با آمار نهایی"""
        async with self._transfer_lock:
            if transfer_id not in self.active_transfers:
                return
            
            context = self.active_transfers[transfer_id]
            context.status = "completed" if success else "failed"
            
            # محاسبه آمار نهایی
            duration = time.time() - context.start_time
            avg_speed = context.file_size / duration if duration > 0 else 0
            
            # ذخیره آمار
            transfer_stats = TransferStats(
                transfer_id=transfer_id,
                user_id=context.user_id,
                file_name=context.file_name,
                file_size=context.file_size,
                transfer_type=context.transfer_type,
                duration_seconds=duration,
                avg_speed_mbps=avg_speed / (1024 * 1024),
                max_speed_mbps=max(context.speed_samples) / (1024 * 1024) if context.speed_samples else 0,
                min_speed_mbps=min(context.speed_samples) / (1024 * 1024) if context.speed_samples else 0,
                success=success,
                error_message=error_message,
                start_time=context.start_time,
                end_time=time.time(),
                retry_count=context.retry_count,
                tags=list(context.tags),
                metadata=context.metadata
            )
            
            # ذخیره در دیتابیس یا فایل
            await self._save_transfer_stats(transfer_stats)
            
            # ارسال event
            await self._emit_event('transfer_completed', {
                'transfer_id': transfer_id,
                'success': success,
                'duration': duration,
                'avg_speed_mbps': avg_speed / (1024 * 1024),
                'error': error_message
            })
            
            # به‌روزرسانی متریک‌ها
            METRICS['active_transfers'].dec()
            METRICS['transfer_duration'].observe(duration)
            
            if not success:
                METRICS['transfer_errors'].inc()
            
            # پاکسازی
            del self.active_transfers[transfer_id]
            
            # زمان‌بندی پاکسازی تاریخچه
            asyncio.create_task(self._schedule_history_cleanup(transfer_id))
            
            logger.info(f"Transfer completed: {transfer_id}, "
                       f"Success: {success}, "
                       f"Avg Speed: {avg_speed/(1024*1024):.2f} Mbps")
    
    async def _save_transfer_stats(self, stats: TransferStats):
        """ذخیره آمار انتقال"""
        try:
            stats_dir = Path("stats")
            stats_dir.mkdir(exist_ok=True)
            
            # ذخیره به صورت msgpack برای کارایی
            stats_file = stats_dir / f"{stats.transfer_id}.msgpack"
            with open(stats_file, 'wb') as f:
                packed = msgpack.packb(stats.to_dict(), use_bin_type=True)
                f.write(packed)
            
            # همچنین به صورت JSON برای خوانایی
            json_file = stats_dir / f"{stats.transfer_id}.json"
            with open(json_file, 'w') as f:
                json.dump(stats.to_dict(), f, indent=2, default=str)
                
        except Exception as e:
            logger.error(f"Failed to save transfer stats: {e}")
    
    async def _schedule_history_cleanup(self, transfer_id: str, delay_hours: int = 1):
        """زمان‌بندی پاکسازی تاریخچه"""
        await asyncio.sleep(delay_hours * 3600)
        
        async with self._history_lock:
            if transfer_id in self.transfer_history:
                del self.transfer_history[transfer_id]
    
    async def _periodic_cleanup(self):
        """پاکسازی دوره‌ای"""
        while True:
            await asyncio.sleep(300)  # هر 5 دقیقه
            
            try:
                async with self._transfer_lock:
                    now = time.time()
                    expired = []
                    
                    for transfer_id, context in self.active_transfers.items():
                        # حذف انتقال‌های متوقف شده (بیش از 1 ساعت)
                        if now - context.last_checkpoint > 3600:
                            expired.append(transfer_id)
                    
                    for transfer_id in expired:
                        await self.complete_transfer(
                            transfer_id,
                            success=False,
                            error_message="Transfer timeout"
                        )
                        
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")
    
    async def _periodic_analysis(self):
        """آنالیز دوره‌ای عملکرد"""
        while True:
            await asyncio.sleep(60)  # هر دقیقه
            
            try:
                # آنالیز شبکه
                network_health = await self.network_analyzer.analyze_network()
                
                # آنالیز عملکرد سیستم
                system_stats = self._get_system_stats()
                
                # ایجاد گزارش
                report = {
                    'timestamp': datetime.now().isoformat(),
                    'active_transfers': len(self.active_transfers),
                    'network_health': network_health,
                    'system_stats': system_stats,
                    'performance_score': self._calculate_performance_score(
                        network_health, system_stats
                    )
                }
                
                # ارسال هشدار اگر لازم باشد
                if report['performance_score'] < 0.7:
                    await self._send_alert(f"Performance degradation detected: {report['performance_score']:.2f}")
                
                logger.debug(f"System analysis report: {report}")
                
            except Exception as e:
                logger.error(f"Periodic analysis error: {e}")
    
    async def _periodic_backup(self):
        """بکاپ دوره‌ای"""
        while True:
            await asyncio.sleep(3600)  # هر ساعت
            
            try:
                backup_dir = Path("backups") / datetime.now().strftime("%Y%m%d_%H")
                backup_dir.mkdir(parents=True, exist_ok=True)
                
                # بکاپ تاریخچه
                async with self._history_lock:
                    history_file = backup_dir / "transfer_history.msgpack"
                    with open(history_file, 'wb') as f:
                        packed = msgpack.packb(
                            {k: list(v) for k, v in self.transfer_history.items()},
                            use_bin_type=True
                        )
                        f.write(packed)
                
                logger.info(f"Backup created at {backup_dir}")
                
            except Exception as e:
                logger.error(f"Periodic backup error: {e}")
    
    def _get_system_stats(self) -> Dict[str, Any]:
        """دریافت آمار سیستم"""
        return {
            'cpu_percent': psutil.cpu_percent(),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': psutil.disk_usage('/').percent,
            'network_io': psutil.net_io_counters()._asdict(),
            'active_threads': threading.active_count(),
        }
    
    def _calculate_performance_score(self, network_health: Dict, system_stats: Dict) -> float:
        """محاسبه نمره عملکرد"""
        scores = []
        
        # نمره شبکه
        if 'quality_score' in network_health:
            scores.append(network_health['quality_score'] * 0.4)
        
        # نمره CPU
        cpu_score = max(0, 1 - system_stats['cpu_percent'] / 100)
        scores.append(cpu_score * 0.3)
        
        # نمره Memory
        mem_score = max(0, 1 - system_stats['memory_percent'] / 100)
        scores.append(mem_score * 0.2)
        
        # نمره Disk
        disk_score = max(0, 1 - system_stats['disk_usage'] / 100)
        scores.append(disk_score * 0.1)
        
        return sum(scores)
    
    async def _send_alert(self, message: str):
        """ارسال هشدار"""
        # اینجا می‌توان به Telegram, Email, Slack, etc. وصل شد
        logger.warning(f"ALERT: {message}")
    
    # Public API methods
    async def get_transfer_stats(self, transfer_id: str) -> Optional[Dict[str, Any]]:
        """دریافت آمار انتقال"""
        async with self._transfer_lock:
            if transfer_id not in self.active_transfers:
                return None
            
            context = self.active_transfers[transfer_id]
            current_time = time.time()
            elapsed = current_time - context.start_time
            
            # محاسبه سرعت
            current_bytes = context.metadata.get('last_bytes', 0)
            avg_speed = current_bytes / elapsed if elapsed > 0 else 0
            
            # محاسبه پیشرفت
            progress = (current_bytes / context.file_size * 100) if context.file_size > 0 else 0
            
            return {
                'transfer_id': transfer_id,
                'user_id': context.user_id,
                'file_name': context.file_name,
                'file_size': context.file_size,
                'transfer_type': context.transfer_type,
                'progress_percent': progress,
                'transferred_bytes': current_bytes,
                'remaining_bytes': max(0, context.file_size - current_bytes),
                'elapsed_seconds': elapsed,
                'avg_speed_bps': avg_speed,
                'avg_speed_mbps': avg_speed / (1024 * 1024),
                'current_speed_bps': context.metadata.get('last_speed', 0),
                'status': context.status,
                'priority': context.priority,
                'tags': list(context.tags),
                'start_time': context.start_time,
                'estimated_completion': context.start_time + (
                    (context.file_size - current_bytes) / avg_speed if avg_speed > 0 else 0
                )
            }
    
    async def get_speed_graph_data(
        self,
        transfer_id: str,
        points: Optional[int] = None,
        time_range: Optional[tuple] = None
    ) -> Dict[str, Any]:
        """دریافت داده‌های نمودار پیشرفته"""
        async with self._history_lock:
            if transfer_id not in self.transfer_history:
                return {'error': 'Transfer not found'}
            
            history = list(self.transfer_history[transfer_id])
            
            if not history:
                return {'timestamps': [], 'speeds': []}
            
            # فیلتر بر اساس بازه زمانی
            if time_range:
                start_time, end_time = time_range
                history = [h for h in history if start_time <= h.timestamp <= end_time]
            
            # نمونه‌برداری هوشمند
            if points and len(history) > points:
                # الگوریتم نمونه‌برداری با حفظ نقاط مهم
                indices = self._smart_sampling_indices(history, points)
                history = [history[i] for i in indices]
            
            # استخراج داده‌ها
            timestamps = [h.timestamp - history[0].timestamp for h in history]
            speeds_kbps = [h.speed_kbps for h in history]
            progress = [h.progress_percent for h in history]
            
            # محاسبه آمار
            if speeds_kbps:
                speed_stats = {
                    'avg': statistics.mean(speeds_kbps),
                    'max': max(speeds_kbps),
                    'min': min(speeds_kbps),
                    'std': statistics.stdev(speeds_kbps) if len(speeds_kbps) > 1 else 0,
                    'percentiles': {
                        '25': np.percentile(speeds_kbps, 25),
                        '50': np.percentile(speeds_kbps, 50),
                        '75': np.percentile(speeds_kbps, 75),
                        '95': np.percentile(speeds_kbps, 95),
                    }
                }
            else:
                speed_stats = {}
            
            return {
                'timestamps': timestamps,
                'speeds_kbps': speeds_kbps,
                'progress_percent': progress,
                'speed_stats': speed_stats,
                'transfer_id': transfer_id,
                'data_points': len(history),
                'time_range': {
                    'start': history[0].timestamp,
                    'end': history[-1].timestamp,
                    'duration': history[-1].timestamp - history[0].timestamp
                }
            }
    
    def _smart_sampling_indices(self, data: List, target_points: int) -> List[int]:
        """نمونه‌برداری هوشمند با حفظ نقاط مهم"""
        n = len(data)
        if n <= target_points:
            return list(range(n))
        
        # انتخاب نقاط با تغییرات زیاد (حفظ peaks)
        indices = set()
        
        # همیشه اول و آخر
        indices.add(0)
        indices.add(n - 1)
        
        # محاسبه تغییرات
        changes = []
        for i in range(1, n):
            if hasattr(data[i], 'speed_kbps'):
                change = abs(data[i].speed_kbps - data[i-1].speed_kbps)
                changes.append((i, change))
        
        # انتخاب نقاط با بیشترین تغییر
        changes.sort(key=lambda x: x[1], reverse=True)
        for i, _ in changes[:target_points - 2]:
            indices.add(i)
        
        # پر کردن باقیمانده به صورت یکنواخت
        remaining = target_points - len(indices)
        if remaining > 0:
            step = n // (remaining + 1)
            for i in range(step, n, step):
                if i not in indices:
                    indices.add(i)
        
        return sorted(indices)
    
    async def register_callback(
        self,
        callback: Callable,
        transfer_id: Optional[str] = None
    ):
        """ثبت callback"""
        async with self._callback_lock:
            if transfer_id:
                if transfer_id not in self.callbacks:
                    self.callbacks[transfer_id] = []
                self.callbacks[transfer_id].append(callback)
            else:
                self.global_callbacks.append(callback)
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """دریافت نمای کلی سیستم"""
        async with self._transfer_lock:
            active_transfers = len(self.active_transfers)
            
            # آمار کاربران
            user_stats = {}
            for user_id, transfers in self.user_sessions.items():
                if transfers[-10:]:  # آخرین 10 انتقال
                    user_stats[user_id] = len(transfers[-10:])
            
            # آمار سرعت
            download_speeds = []
            upload_speeds = []
            
            for context in self.active_transfers.values():
                if context.speed_samples:
                    last_speed = context.speed_samples[-1] / (1024 * 1024)  # به Mbps
                    if context.transfer_type == 'download':
                        download_speeds.append(last_speed)
                    else:
                        upload_speeds.append(last_speed)
            
            return {
                'active_transfers': active_transfers,
                'unique_users': len(user_stats),
                'avg_download_speed': statistics.mean(download_speeds) if download_speeds else 0,
                'avg_upload_speed': statistics.mean(upload_speeds) if upload_speeds else 0,
                'total_throughput_mbps': (sum(download_speeds) + sum(upload_speeds)),
                'user_activity': user_stats,
                'system_health': self._get_system_stats(),
                'network_health': await self.network_analyzer.get_health_score(),
                'ai_enabled': self.config.ai['enabled'],
                'uptime_seconds': time.time() - getattr(self, '_start_time', time.time()),
                'timestamp': datetime.now().isoformat()
            }
    
    async def optimize_transfer(
        self,
        transfer_id: str,
        optimization_type: str = "auto"
    ) -> Dict[str, Any]:
        """بهینه‌سازی انتقال در حال اجرا"""
        async with self._transfer_lock:
            if transfer_id not in self.active_transfers:
                return {'error': 'Transfer not found'}
            
            context = self.active_transfers[transfer_id]
            
            # آنالیز شبکه
            network_analysis = await self.network_analyzer.analyze_network()
            
            # پیشنهادات بهینه‌سازی
            recommendations = []
            
            # تنظیمات بر اساس آنالیز شبکه
            if network_analysis.get('latency', 0) > 100:
                recommendations.append({
                    'type': 'connection',
                    'action': 'reduce_connections',
                    'reason': 'High latency detected',
                    'suggested_value': max(2, context.metadata.get('connections', 8) // 2)
                })
            
            if network_analysis.get('packet_loss', 0) > 0.05:
                recommendations.append({
                    'type': 'chunk',
                    'action': 'reduce_chunk_size',
                    'reason': 'High packet loss',
                    'suggested_value': max(256 * 1024, context.metadata.get('chunk_size', 1024 * 1024) // 2)
                })
            
            # تنظیمات بر اساس سرعت
            if context.speed_samples:
                avg_speed = statistics.mean(context.speed_samples[-10:]) if len(context.speed_samples) >= 10 else context.speed_samples[-1]
                
                if avg_speed < 1024 * 1024:  # کمتر از 1 Mbps
                    recommendations.append({
                        'type': 'compression',
                        'action': 'enable_compression',
                        'reason': 'Low speed detected',
                        'suggested_value': True
                    })
            
            # تنظیمات بر اساس حجم فایل
            if context.file_size > 100 * 1024 * 1024:  # بیشتر از 100MB
                recommendations.append({
                    'type': 'strategy',
                    'action': 'enable_resume',
                    'reason': 'Large file',
                    'suggested_value': True
                })
            
            # اگر AI فعال است، پیشنهادات AI
            if self.config.ai['enabled']:
                ai_recommendations = await self.ai_predictor.get_optimization_recommendations(
                    transfer_id=transfer_id,
                    context=context.to_dict(),
                    network_analysis=network_analysis
                )
                recommendations.extend(ai_recommendations)
            
            return {
                'transfer_id': transfer_id,
                'network_analysis': network_analysis,
                'recommendations': recommendations,
                'current_settings': context.metadata.get('settings', {}),
                'optimization_score': self._calculate_optimization_score(recommendations)
            }
    
    def _calculate_optimization_score(self, recommendations: List[Dict]) -> float:
        """محاسبه نمره بهینه‌سازی"""
        if not recommendations:
            return 1.0
        
        # هر recommendation بر اساس اهمیت وزن دارد
        weights = {
            'connection': 0.3,
            'chunk': 0.25,
            'compression': 0.2,
            'strategy': 0.15,
            'other': 0.1
        }
        
        score = 1.0
        for rec in recommendations:
            rec_type = rec.get('type', 'other')
            weight = weights.get(rec_type, 0.1)
            
            # هر recommendation کمی score را کاهش می‌دهد
            # (چون نشان‌دهنده نیاز به بهینه‌سازی است)
            score -= weight * 0.1
        
        return max(0.0, min(1.0, score))
    
    async def shutdown(self):
        """خاموش کردن graceful سیستم"""
        logger.info("Shutting down AdaptiveSpeedMonitor...")
        
        # لغو tasks
        self._cleanup_task.cancel()
        self._analysis_task.cancel()
        self._backup_task.cancel()
        
        try:
            await asyncio.gather(
                self._cleanup_task,
                self._analysis_task,
                self._backup_task,
                return_exceptions=True
            )
        except asyncio.CancelledError:
            pass
        
        # تکمیل انتقال‌های فعال
        async with self._transfer_lock:
            for transfer_id in list(self.active_transfers.keys()):
                await self.complete_transfer(
                    transfer_id,
                    success=False,
                    error_message="System shutdown"
                )
        
        logger.info("AdaptiveSpeedMonitor shutdown complete")

# Singleton instance
speed_monitor = AdaptiveSpeedMonitor()
