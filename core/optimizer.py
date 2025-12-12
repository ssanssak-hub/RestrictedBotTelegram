#core/optimizer.py
"""
سیستم بهینه‌سازی هوشمند انتقال با AI
"""

import asyncio
import aiohttp
import aiofiles
import concurrent.futures
from typing import List, Dict, Optional, Tuple, Any, Set, Union
import time
import json
import logging
from pathlib import Path
import threading
from collections import deque
import hashlib
import zlib
import lz4.frame
import brotli
import zstandard as zstd
from dataclasses import dataclass, field, asdict
from enum import Enum
import numpy as np
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
import base64
import os
import socket
import ssl
from urllib.parse import urlparse
import dns.resolver
import psutil

from .models.speed_data import SpeedData, TransferStats
from .ai_predictor import AISpeedPredictor
from .network_analyzer import NetworkAnalyzer
from config.settings import config_manager, SpeedSettings
from utils.cache_manager import CacheManager
from utils.encryption import EncryptionManager

logger = logging.getLogger(__name__)

class TransferStrategy(Enum):
    """استراتژی‌های انتقال"""
    SINGLE = "single"
    MULTI_CONNECTION = "multi_connection"
    ADAPTIVE = "adaptive"
    STREAMING = "streaming"
    TORRENT = "torrent"

class CompressionResult:
    """نتیجه فشرده‌سازی"""
    def __init__(self, compressed: bytes, original_size: int, ratio: float, algorithm: str):
        self.compressed = compressed
        self.original_size = original_size
        self.compressed_size = len(compressed)
        self.ratio = ratio
        self.algorithm = algorithm
    
    def to_dict(self) -> Dict:
        return {
            'compressed_size': self.compressed_size,
            'original_size': self.original_size,
            'ratio': self.ratio,
            'algorithm': self.algorithm,
            'saved_bytes': self.original_size - self.compressed_size
        }

@dataclass
class TransferOptimization:
    """بهینه‌سازی انتقال"""
    strategy: TransferStrategy
    chunk_size: int
    connections: int
    buffer_size: int
    compression_enabled: bool
    encryption_enabled: bool
    resume_enabled: bool
    priority: int
    estimated_speed: float  # Mbps
    confidence: float

class IntelligentSpeedOptimizer:
    """بهینه‌ساز هوشمند سرعت"""
    
    def __init__(self, config: Optional[SpeedSettings] = None):
        self.config = config or config_manager.settings
        self.cache_manager = CacheManager(self.config.caching)
        self.encryption_manager = EncryptionManager()
        self.ai_predictor = AISpeedPredictor()
        self.network_analyzer = NetworkAnalyzer()
        
        # Connection pools
        self.http_pool = aiohttp.ClientSession()
        self.ssl_context = self._create_ssl_context()
        
        # Thread pools
        self.io_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.performance['io_bound_threads'],
            thread_name_prefix="io_worker"
        )
        
        self.cpu_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.config.performance['cpu_bound_threads'],
            thread_name_prefix="cpu_worker"
        )
        
        # DNS cache
        self.dns_cache: Dict[str, Tuple[str, float]] = {}
        self.dns_cache_ttl = self.config.network['dns_cache_ttl']
        
        # Transfer queue with priority
        self.transfer_queue = asyncio.PriorityQueue()
        self.active_transfers: Dict[str, asyncio.Task] = {}
        self.transfer_results: Dict[str, Any] = {}
        
        # Performance monitoring
        self.performance_stats = {
            'total_downloaded': 0,
            'total_uploaded': 0,
            'avg_download_speed': 0,
            'avg_upload_speed': 0,
            'peak_download_speed': 0,
            'peak_upload_speed': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'compression_savings': 0,
            'total_errors': 0
        }
        
        # Adaptive learning
        self.learning_data = deque(maxlen=1000)
        
        # Start background tasks
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        self._monitor_task = asyncio.create_task(self._monitor_performance())
        self._dns_refresh_task = asyncio.create_task(self._refresh_dns_cache())
        
        # Circuit breaker
        self.circuit_breakers: Dict[str, Dict] = {}
        
        logger.info(f"IntelligentSpeedOptimizer initialized with {self.config.performance['thread_pool_size']} threads")
    
    def _create_ssl_context(self) -> Optional[ssl.SSLContext]:
        """ایجاد SSL context بهینه"""
        if not self.config.security['ssl_verify']:
            return None
        
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        
        # Optimization
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
        context.set_alpn_protocols(['h2', 'http/1.1'])
        
        # Certificate pinning
        if self.config.security['certificate_pinning']:
            # Load pinned certificates
            pass
        
        return context
    
    async def _resolve_dns(self, hostname: str) -> str:
        """حل DNS با کش"""
        now = time.time()
        
        if hostname in self.dns_cache:
            ip, expiry = self.dns_cache[hostname]
            if now < expiry:
                return ip
        
        try:
            # Try multiple DNS servers
            resolvers = ['8.8.8.8', '1.1.1.1', '9.9.9.9']
            for resolver in resolvers:
                try:
                    answers = dns.resolver.resolve(hostname, 'A')
                    ip = str(answers[0])
                    self.dns_cache[hostname] = (ip, now + self.dns_cache_ttl)
                    return ip
                except:
                    continue
            
            # Fallback to socket
            ip = socket.gethostbyname(hostname)
            self.dns_cache[hostname] = (ip, now + self.dns_cache_ttl)
            return ip
            
        except Exception as e:
            logger.warning(f"DNS resolution failed for {hostname}: {e}")
            return hostname
    
    async def download_file(
        self,
        url: str,
        destination: Path,
        progress_callback = None,
        priority: int = 5,
        optimization_hints: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        دانلود هوشمند فایل با بهینه‌سازی خودکار
        """
        transfer_id = f"dl_{hashlib.md5(url.encode()).hexdigest()[:8]}_{int(time.time())}"
        
        try:
            # بررسی circuit breaker
            if self._is_circuit_open(url):
                return {
                    'success': False,
                    'error': 'Circuit breaker open',
                    'transfer_id': transfer_id
                }
            
            # بهینه‌سازی خودکار
            optimization = await self._optimize_download(
                url, destination, priority, optimization_hints
            )
            
            # ثبت در صف
            task = asyncio.create_task(
                self._execute_download(
                    transfer_id, url, destination, optimization, progress_callback
                )
            )
            
            self.active_transfers[transfer_id] = task
            
            # بازگشت فوری
            return {
                'success': True,
                'transfer_id': transfer_id,
                'optimization': optimization.to_dict(),
                'estimated_time': self._estimate_download_time(optimization, destination),
                'queue_position': self.transfer_queue.qsize()
            }
            
        except Exception as e:
            logger.error(f"Download initiation failed: {e}")
            self._record_failure(url, str(e))
            
            return {
                'success': False,
                'error': str(e),
                'transfer_id': transfer_id
            }
    
    async def _optimize_download(
        self,
        url: str,
        destination: Path,
        priority: int,
        hints: Optional[Dict]
    ) -> TransferOptimization:
        """بهینه‌سازی خودکار دانلود"""
        
        # دریافت اطلاعات فایل
        file_info = await self._analyze_file(url, destination)
        
        # آنالیز شبکه
        network_analysis = await self.network_analyzer.analyze_network()
        
        # یادگیری از داده‌های تاریخی
        historical_data = await self._get_historical_data(url, file_info['size'])
        
        # پیش‌بینی AI
        if self.config.ai['enabled']:
            ai_prediction = await self.ai_predictor.predict_optimal_strategy(
                file_size=file_info['size'],
                network_conditions=network_analysis,
                historical_data=historical_data,
                hints=hints
            )
            
            strategy = TransferStrategy(ai_prediction.get('strategy', 'adaptive'))
            confidence = ai_prediction.get('confidence', 0.7)
            estimated_speed = ai_prediction.get('estimated_speed', 0)
            
        else:
            # بهینه‌سازی مبتنی بر قوانین
            strategy, confidence, estimated_speed = self._rule_based_optimization(
                file_info, network_analysis, priority
            )
        
        # محاسبه پارامترها
        chunk_size = self._calculate_optimal_chunk_size(
            file_info['size'], network_analysis, strategy
        )
        
        connections = self._calculate_optimal_connections(
            file_info['size'], network_analysis, strategy
        )
        
        # ایجاد بهینه‌سازی
        return TransferOptimization(
            strategy=strategy,
            chunk_size=chunk_size,
            connections=connections,
            buffer_size=self._calculate_buffer_size(chunk_size, connections),
            compression_enabled=self._should_compress(file_info),
            encryption_enabled=self.config.security['encryption_enabled'],
            resume_enabled=True,
            priority=priority,
            estimated_speed=estimated_speed,
            confidence=confidence
        )
    
    async def _execute_download(
        self,
        transfer_id: str,
        url: str,
        destination: Path,
        optimization: TransferOptimization,
        progress_callback
    ) -> Dict[str, Any]:
        """اجرای دانلود با استراتژی بهینه"""
        start_time = time.time()
        
        try:
            # بررسی کش
            cache_result = await self.cache_manager.get(url)
            if cache_result['hit']:
                self.performance_stats['cache_hits'] += 1
                
                await self._copy_from_cache(
                    cache_result['path'], destination, progress_callback
                )
                
                return {
                    'success': True,
                    'transfer_id': transfer_id,
                    'path': destination,
                    'size': cache_result['size'],
                    'time': time.time() - start_time,
                    'speed_mbps': cache_result['size'] / (time.time() - start_time) / (1024 * 1024),
                    'cached': True,
                    'checksum': cache_result['checksum'],
                    'optimization_used': optimization.to_dict()
                }
            
            self.performance_stats['cache_misses'] += 1
            
            # اجرای بر اساس استراتژی
            if optimization.strategy == TransferStrategy.SINGLE:
                result = await self._download_single(url, destination, optimization, progress_callback)
            
            elif optimization.strategy == TransferStrategy.MULTI_CONNECTION:
                result = await self._download_multi_connection(url, destination, optimization, progress_callback)
            
            elif optimization.strategy == TransferStrategy.ADAPTIVE:
                result = await self._download_adaptive(url, destination, optimization, progress_callback)
            
            elif optimization.strategy == TransferStrategy.STREAMING:
                result = await self._download_streaming(url, destination, optimization, progress_callback)
            
            else:
                result = {'success': False, 'error': f'Unknown strategy: {optimization.strategy}'}
            
            # ذخیره در کش
            if result['success']:
                await self.cache_manager.put(url, destination, result['checksum'])
                
                # به‌روزرسانی یادگیری
                await self._update_learning_data(
                    url=url,
                    strategy=optimization.strategy,
                    performance={
                        'speed': result.get('speed_mbps', 0),
                        'time': result.get('time', 0),
                        'success': True
                    }
                )
            
            # به‌روزرسانی آمار
            if result['success']:
                self._update_performance_stats('download', result['size'], result.get('time', 0))
            
            result['transfer_id'] = transfer_id
            result['optimization_used'] = optimization.to_dict()
            
            return result
            
        except Exception as e:
            logger.error(f"Download execution failed: {e}")
            self._record_failure(url, str(e))
            
            return {
                'success': False,
                'error': str(e),
                'transfer_id': transfer_id,
                'time': time.time() - start_time
            }
    
    async def _download_adaptive(
        self,
        url: str,
        destination: Path,
        optimization: TransferOptimization,
        progress_callback
    ) -> Dict[str, Any]:
        """دانلود تطبیقی با تغییر استراتژی در حین اجرا"""
        start_time = time.time()
        file_size = await self._get_file_size(url)
        
        if not file_size:
            return {'success': False, 'error': 'Cannot get file size'}
        
        # شروع با multi-connection
        initial_result = await self._download_multi_connection(
            url, destination, optimization, progress_callback
        )
        
        if not initial_result['success']:
            return initial_result
        
        # مانیتورینگ و تنظیم در حین اجرا
        monitor_task = asyncio.create_task(
            self._monitor_and_adjust(
                url, destination, optimization, progress_callback, file_size
            )
        )
        
        try:
            result = await monitor_task
            return result
        except asyncio.CancelledError:
            return {'success': False, 'error': 'Download cancelled'}
    
    async def _monitor_and_adjust(
        self,
        url: str,
        destination: Path,
        optimization: TransferOptimization,
        progress_callback,
        file_size: int
    ):
        """مانیتورینگ و تنظیم پارامترها در حین دانلود"""
        
        adaptation_interval = 5  # ثانیه
        last_adaptation = time.time()
        
        while True:
            await asyncio.sleep(1)
            
            # بررسی پیشرفت
            current_progress = await self._get_current_progress(destination)
            
            if current_progress >= file_size:
                break
            
            # تنظیم در بازه‌های زمانی
            if time.time() - last_adaptation >= adaptation_interval:
                last_adaptation = time.time()
                
                # آنالیز عملکرد
                performance = await self._analyze_current_performance(
                    url, destination, current_progress
                )
                
                # تنظیم پارامترها
                if performance['speed'] < optimization.estimated_speed * 0.5:
                    await self._adjust_parameters(
                        url, destination, optimization, performance
                    )
        
        # تکمیل دانلود
        checksum = await self._calculate_file_checksum(destination)
        
        return {
            'success': True,
            'path': destination,
            'size': file_size,
            'checksum': checksum
        }
    
    async def _adjust_parameters(
        self,
        url: str,
        destination: Path,
        optimization: TransferOptimization,
        performance: Dict
    ):
        """تنظیم پارامترها در حین اجرا"""
        
        # کاهش تعداد اتصالات اگر سرعت پایین است
        if performance['speed'] < optimization.estimated_speed * 0.3:
            optimization.connections = max(1, optimization.connections // 2)
        
        # افزایش chunk size اگر شبکه پایدار است
        if performance.get('stability', 1) > 0.9:
            optimization.chunk_size = min(
                optimization.chunk_size * 2,
                self.config.download['chunk_size_mb'] * 1024 * 1024
            )
        
        logger.info(f"Parameters adjusted: connections={optimization.connections}, "
                   f"chunk_size={optimization.chunk_size}")
    
    async def upload_file(
        self,
        source: Path,
        upload_url: str,
        progress_callback = None,
        priority: int = 5,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        آپلود هوشمند فایل
        """
        transfer_id = f"ul_{hashlib.md5(str(source).encode()).hexdigest()[:8]}_{int(time.time())}"
        
        try:
            # بررسی فایل
            if not source.exists():
                return {'success': False, 'error': 'File not found'}
            
            file_size = source.stat().st_size
            
            # بهینه‌سازی
            optimization = await self._optimize_upload(
                source, upload_url, file_size, priority, metadata
            )
            
            # اجرای آپلود
            result = await self._execute_upload(
                transfer_id, source, upload_url, optimization, progress_callback, metadata
            )
            
            # به‌روزرسانی آمار
            if result['success']:
                self._update_performance_stats('upload', file_size, result.get('time', 0))
            
            result['transfer_id'] = transfer_id
            result['optimization_used'] = optimization.to_dict()
            
            return result
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'transfer_id': transfer_id
            }
    
    async def _optimize_upload(
        self,
        source: Path,
        upload_url: str,
        file_size: int,
        priority: int,
        metadata: Optional[Dict]
    ) -> TransferOptimization:
        """بهینه‌سازی آپلود"""
        
        # آنالیز فایل
        file_analysis = await self._analyze_file_for_upload(source, metadata)
        
        # آنالیز شبکه
        network_analysis = await self.network_analyzer.analyze_network()
        
        # تعیین استراتژی
        if file_size < 5 * 1024 * 1024:  # کمتر از 5MB
            strategy = TransferStrategy.SINGLE
        elif file_size < 100 * 1024 * 1024:  # کمتر از 100MB
            strategy = TransferStrategy.MULTI_CONNECTION
        else:
            strategy = TransferStrategy.ADAPTIVE
        
        # محاسبه پارامترها
        chunk_size = self._calculate_upload_chunk_size(file_size, network_analysis)
        
        connections = min(
            self.config.upload['parallel_uploads'],
            max(2, file_size // (10 * 1024 * 1024))  # یک connection به ازای هر 10MB
        )
        
        # بررسی نیاز به فشرده‌سازی
        compression_enabled = (
            self.config.upload['compression']['enabled'] and
            file_size >= self.config.upload['compression']['min_size_mb'] * 1024 * 1024 and
            source.suffix in self.config.upload['compression']['extensions']
        )
        
        return TransferOptimization(
            strategy=strategy,
            chunk_size=chunk_size,
            connections=connections,
            buffer_size=self._calculate_buffer_size(chunk_size, connections),
            compression_enabled=compression_enabled,
            encryption_enabled=self.config.security['encryption_enabled'],
            resume_enabled=True,
            priority=priority,
            estimated_speed=network_analysis.get('upload_speed', 0),
            confidence=0.8
        )
    
    async def _execute_upload(
        self,
        transfer_id: str,
        source: Path,
        upload_url: str,
        optimization: TransferOptimization,
        progress_callback,
        metadata: Optional[Dict]
    ) -> Dict[str, Any]:
        """اجرای آپلود"""
        start_time = time.time()
        
        try:
            file_size = source.stat().st_size
            
            if optimization.strategy == TransferStrategy.SINGLE:
                result = await self._upload_single(
                    source, upload_url, optimization, progress_callback, metadata
                )
            else:
                result = await self._upload_multipart(
                    source, upload_url, optimization, progress_callback, metadata
                )
            
            if result['success']:
                result.update({
                    'time': time.time() - start_time,
                    'speed_mbps': file_size / (time.time() - start_time) / (1024 * 1024)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Upload execution failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'time': time.time() - start_time
            }
    
    async def _upload_multipart(
        self,
        source: Path,
        upload_url: str,
        optimization: TransferOptimization,
        progress_callback,
        metadata: Optional[Dict]
    ) -> Dict[str, Any]:
        """آپلود چند قسمتی"""
        
        # شروع آپلود
        upload_id = await self._initiate_multipart_upload(
            upload_url, source.name, source.stat().st_size, metadata
        )
        
        if not upload_id:
            return {'success': False, 'error': 'Failed to initiate upload'}
        
        try:
            # تقسیم فایل به chunkها
            chunks = await self._split_file_into_chunks(
                source, optimization.chunk_size, optimization.compression_enabled
            )
            
            # آپلود موازی chunkها
            upload_tasks = []
            for chunk_idx, chunk_data in enumerate(chunks):
                task = self._upload_chunk(
                    upload_url, upload_id, chunk_idx, chunk_data, progress_callback
                )
                upload_tasks.append(task)
            
            # محدودیت همزمانی
            semaphore = asyncio.Semaphore(optimization.connections)
            
            async def limited_upload(task):
                async with semaphore:
                    return await task
            
            results = await asyncio.gather(
                *[limited_upload(task) for task in upload_tasks],
                return_exceptions=True
            )
            
            # بررسی خطاها
            errors = []
            for result in results:
                if isinstance(result, Exception):
                    errors.append(str(result))
            
            if errors:
                await self._abort_multipart_upload(upload_url, upload_id)
                return {'success': False, 'error': f'Chunk errors: {errors}'}
            
            # تکمیل آپلود
            final_url = await self._complete_multipart_upload(
                upload_url, upload_id, len(chunks)
            )
            
            if not final_url:
                return {'success': False, 'error': 'Failed to complete upload'}
            
            return {
                'success': True,
                'url': final_url,
                'size': source.stat().st_size,
                'chunks': len(chunks),
                'upload_id': upload_id
            }
            
        except Exception as e:
            await self._abort_multipart_upload(upload_url, upload_id)
            raise
    
    async def _split_file_into_chunks(
        self,
        source: Path,
        chunk_size: int,
        compress: bool
    ) -> List[bytes]:
        """تقسیم فایل به chunkها با امکان فشرده‌سازی"""
        chunks = []
        
        async with aiofiles.open(source, 'rb') as f:
            while True:
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                
                if compress:
                    chunk = await self._compress_chunk(chunk)
                
                chunks.append(chunk)
        
        return chunks
    
    async def _compress_chunk(self, chunk: bytes) -> bytes:
        """فشرده‌سازی chunk"""
        algorithm = self.config.upload['compression']['algorithm']
        level = self.config.upload['compression']['level']
        
        if algorithm == 'brotli':
            return brotli.compress(chunk, quality=level)
        elif algorithm == 'zstd':
            cctx = zstd.ZstdCompressor(level=level)
            return cctx.compress(chunk)
        elif algorithm == 'lz4':
            return lz4.frame.compress(chunk, compression_level=level)
        elif algorithm == 'gzip':
            return zlib.compress(chunk, level=level)
        else:
            return chunk
    
    # Helper methods
    async def _analyze_file(self, url: str, destination: Path) -> Dict[str, Any]:
        """آنالیز فایل قبل از دانلود"""
        try:
            # دریافت headerها
            async with self.http_pool.head(url) as response:
                headers = response.headers
                
                file_size = int(headers.get('Content-Length', 0))
                content_type = headers.get('Content-Type', '')
                supports_range = 'Accept-Ranges' in headers or 'Content-Range' in headers
                
                return {
                    'size': file_size,
                    'type': content_type,
                    'supports_range': supports_range,
                    'headers': dict(headers)
                }
                
        except Exception as e:
            logger.warning(f"File analysis failed: {e}")
            return {'size': 0, 'type': 'unknown', 'supports_range': False}
    
    def _rule_based_optimization(
        self,
        file_info: Dict,
        network_analysis: Dict,
        priority: int
    ) -> Tuple[TransferStrategy, float, float]:
        """بهینه‌سازی مبتنی بر قوانین"""
        
        file_size = file_info['size']
        latency = network_analysis.get('latency', 0)
        bandwidth = network_analysis.get('bandwidth', 0)
        
        # تعیین استراتژی
        if file_size < 2 * 1024 * 1024:  # کمتر از 2MB
            strategy = TransferStrategy.SINGLE
            confidence = 0.9
        elif latency > 200 or bandwidth < 1 * 1024 * 1024:  # شبکه ضعیف
            strategy = TransferStrategy.SINGLE
            confidence = 0.8
        elif file_size > 100 * 1024 * 1024:  # فایل بزرگ
            strategy = TransferStrategy.MULTI_CONNECTION
            confidence = 0.85
        else:
            strategy = TransferStrategy.ADAPTIVE
            confidence = 0.7
        
        # تخمین سرعت
        if bandwidth > 0:
            estimated_speed = min(bandwidth / (1024 * 1024), 100)  # محدود به 100Mbps
        else:
            # تخمین بر اساس قوانین تجربی
            if latency < 50:
                estimated_speed = 50  # Mbps
            elif latency < 100:
                estimated_speed = 20
            elif latency < 200:
                estimated_speed = 10
            else:
                estimated_speed = 5
        
        return strategy, confidence, estimated_speed
    
    def _calculate_optimal_chunk_size(
        self,
        file_size: int,
        network_analysis: Dict,
        strategy: TransferStrategy
    ) -> int:
        """محاسبه سایز بهینه chunk"""
        
        base_chunk = self.config.download['chunk_size_mb'] * 1024 * 1024
        
        if strategy == TransferStrategy.SINGLE:
            return min(file_size, base_chunk)
        
        # تنظیم بر اساس شرایط شبکه
        latency = network_analysis.get('latency', 0)
        packet_loss = network_analysis.get('packet_loss', 0)
        
        if latency > 100:
            # کاهش chunk size برای شبکه‌های با تاخیر بالا
            return max(256 * 1024, base_chunk // 2)
        elif packet_loss > 0.1:
            # کاهش بیشتر برای packet loss بالا
            return max(128 * 1024, base_chunk // 4)
        else:
            # افزایش برای شبکه‌های پایدار
            return min(base_chunk * 2, 50 * 1024 * 1024)  # حداکثر 50MB
    
    def _calculate_optimal_connections(
        self,
        file_size: int,
        network_analysis: Dict,
        strategy: TransferStrategy
    ) -> int:
        """محاسبه تعداد بهینه اتصالات"""
        
        max_conn = self.config.download['max_connections']
        
        if strategy == TransferStrategy.SINGLE:
            return 1
        
        # محاسبه بر اساس حجم فایل
        base_connections = min(max_conn, max(2, file_size // (10 * 1024 * 1024)))
        
        # تنظیم بر اساس شبکه
        latency = network_analysis.get('latency', 0)
        
        if latency > 150:
            # کاهش اتصالات برای تاخیر بالا
            return max(2, base_connections // 2)
        else:
            return base_connections
    
    def _calculate_buffer_size(self, chunk_size: int, connections: int) -> int:
        """محاسبه سایز بافر"""
        return min(
            chunk_size * connections * 2,
            self.config.download['buffer_size_mb'] * 1024 * 1024
        )
    
    def _should_compress(self, file_info: Dict) -> bool:
        """بررسی نیاز به فشرده‌سازی"""
        if not self.config.compression['enabled']:
            return False
        
        # بررسی type فایل
        content_type = file_info.get('type', '').lower()
        
        if any(text_type in content_type for text_type in ['text', 'json', 'xml', 'javascript']):
            return True
        
        # بررسی بر اساس حجم
        if file_info['size'] < 1024 * 1024:  # کمتر از 1MB
            return False
        
        return self.config.compression['adaptive_compression']
    
    def _estimate_download_time(self, optimization: TransferOptimization, destination: Path) -> float:
        """تخمین زمان دانلود"""
        if optimization.estimated_speed <= 0:
            return 0
        
        if destination.exists():
            current_size = destination.stat().st_size
        else:
            current_size = 0
        
        remaining_size = max(0, getattr(destination, 'expected_size', 0) - current_size)
        
        return remaining_size / (optimization.estimated_speed * 1024 * 1024)
    
    async def _get_file_size(self, url: str) -> Optional[int]:
        """دریافت سایز فایل"""
        try:
            async with self.http_pool.head(url, allow_redirects=True) as response:
                if response.status == 200:
                    size = response.headers.get('Content-Length')
                    return int(size) if size else None
        except:
            pass
        return None
    
    async def _get_current_progress(self, destination: Path) -> int:
        """دریافت پیشرفت فعلی"""
        if destination.exists():
            return destination.stat().st_size
        return 0
    
    async def _analyze_current_performance(
        self,
        url: str,
        destination: Path,
        current_progress: int
    ) -> Dict[str, Any]:
        """آنالیز عملکرد فعلی"""
        # اینجا می‌توان سرعت، stability و دیگر متریک‌ها را محاسبه کرد
        return {
            'speed': 0,  # Mbps
            'stability': 0.9,
            'progress': current_progress
        }
    
    async def _get_historical_data(self, url: str, file_size: int) -> List[Dict]:
        """دریافت داده‌های تاریخی"""
        # جستجو در learning_data
        historical = []
        
        for data in self.learning_data:
            if data.get('url') == url or data.get('file_size') == file_size:
                historical.append(data)
        
        return historical[-10:]  # آخرین 10 رکورد
    
    async def _update_learning_data(self, url: str, strategy: TransferStrategy, performance: Dict):
        """به‌روزرسانی داده‌های یادگیری"""
        learning_entry = {
            'timestamp': time.time(),
            'url': url,
            'strategy': strategy.value,
            'performance': performance,
            'network_conditions': await self.network_analyzer.get_current_conditions()
        }
        
        self.learning_data.append(learning_entry)
    
    def _update_performance_stats(self, transfer_type: str, size: int, duration: float):
        """به‌روزرسانی آمار عملکرد"""
        if duration <= 0:
            return
        
        speed_mbps = size / duration / (1024 * 1024)
        
        if transfer_type == 'download':
            self.performance_stats['total_downloaded'] += size
            self.performance_stats['avg_download_speed'] = (
                self.performance_stats['avg_download_speed'] * 0.9 + speed_mbps * 0.1
            )
            self.performance_stats['peak_download_speed'] = max(
                self.performance_stats['peak_download_speed'], speed_mbps
            )
        else:
            self.performance_stats['total_uploaded'] += size
            self.performance_stats['avg_upload_speed'] = (
                self.performance_stats['avg_upload_speed'] * 0.9 + speed_mbps * 0.1
            )
            self.performance_stats['peak_upload_speed'] = max(
                self.performance_stats['peak_upload_speed'], speed_mbps
            )
    
    def _is_circuit_open(self, url: str) -> bool:
        """بررسی وضعیت circuit breaker"""
        hostname = urlparse(url).hostname
        if not hostname:
            return False
        
        if hostname in self.circuit_breakers:
            cb = self.circuit_breakers[hostname]
            
            if cb['state'] == 'open':
                # بررسی زمان بازگشایی
                if time.time() - cb['opened_at'] > cb['reset_timeout']:
                    cb['state'] = 'half_open'
                    cb['test_count'] = 0
                    return False
                return True
        
        return False
    
    def _record_failure(self, url: str, error: str):
        """ثبت خطا و به‌روزرسانی circuit breaker"""
        hostname = urlparse(url).hostname
        if not hostname:
            return
        
        if hostname not in self.circuit_breakers:
            self.circuit_breakers[hostname] = {
                'state': 'closed',
                'failure_count': 0,
                'success_count': 0,
                'opened_at': 0,
                'reset_timeout': 60,  # ثانیه
                'threshold': 5  # تعداد خطا برای باز شدن
            }
        
        cb = self.circuit_breakers[hostname]
        
        if cb['state'] == 'half_open':
            # در half-open، هر خطا باعث بازگشت به open می‌شود
            cb['state'] = 'open'
            cb['opened_at'] = time.time()
            cb['test_count'] = 0
        
        else:
            cb['failure_count'] += 1
            cb['success_count'] = max(0, cb['success_count'] - 1)
            
            if cb['failure_count'] >= cb['threshold']:
                cb['state'] = 'open'
                cb['opened_at'] = time.time()
                logger.warning(f"Circuit breaker opened for {hostname}")
    
    def _record_success(self, url: str):
        """ثبت موفقیت و به‌روزرسانی circuit breaker"""
        hostname = urlparse(url).hostname
        if not hostname:
            return
        
        if hostname in self.circuit_breakers:
            cb = self.circuit_breakers[hostname]
            
            if cb['state'] == 'half_open':
                cb['test_count'] += 1
                if cb['test_count'] >= 3:  # 3 موفقیت متوالی
                    cb['state'] = 'closed'
                    cb['failure_count'] = 0
                    cb['test_count'] = 0
            
            elif cb['state'] == 'closed':
                cb['success_count'] += 1
                cb['failure_count'] = max(0, cb['failure_count'] - 1)
    
    async def _periodic_cleanup(self):
        """پاکسازی دوره‌ای"""
        while True:
            await asyncio.sleep(300)  # هر 5 دقیقه
            
            try:
                # پاکسازی انتقال‌های کامل شده
                completed = []
                for transfer_id, task in self.active_transfers.items():
                    if task.done():
                        completed.append(transfer_id)
                
                for transfer_id in completed:
                    del self.active_transfers[transfer_id]
                
                # پاکسازی DNS cache قدیمی
                now = time.time()
                expired = []
                for hostname, (_, expiry) in self.dns_cache.items():
                    if now > expiry:
                        expired.append(hostname)
                
                for hostname in expired:
                    del self.dns_cache[hostname]
                
                # پاکسازی circuit breakers قدیمی
                expired_cb = []
                for hostname, cb in self.circuit_breakers.items():
                    if cb['state'] == 'open' and now - cb['opened_at'] > 3600:  # 1 ساعت
                        expired_cb.append(hostname)
                
                for hostname in expired_cb:
                    del self.circuit_breakers[hostname]
                
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")
    
    async def _monitor_performance(self):
        """مانیتورینگ عملکرد"""
        while True:
            await asyncio.sleep(60)  # هر دقیقه
            
            try:
                logger.info(
                    f"Performance Stats - "
                    f"Down: {self.performance_stats['avg_download_speed']:.2f}MB/s "
                    f"(peak: {self.performance_stats['peak_download_speed']:.2f}MB/s) | "
                    f"Up: {self.performance_stats['avg_upload_speed']:.2f}MB/s "
                    f"(peak: {self.performance_stats['peak_upload_speed']:.2f}MB/s) | "
                    f"Cache: {self.performance_stats['cache_hits']}/{self.performance_stats['cache_hits'] + self.performance_stats['cache_misses']} "
                    f"({self.performance_stats['cache_hits']/(self.performance_stats['cache_hits'] + self.performance_stats['cache_misses'] + 1)*100:.1f}%)"
                )
                
            except Exception as e:
                logger.error(f"Performance monitoring error: {e}")
    
    async def _refresh_dns_cache(self):
        """رفرش DNS cache"""
        while True:
            await asyncio.sleep(self.dns_cache_ttl)
            
            try:
                # رفرش آیتم‌های مهم
                important_hosts = []
                for transfer_id in self.active_transfers.keys():
                    # استخراج hostname از URLهای فعال
                    pass
                
            except Exception as e:
                logger.error(f"DNS cache refresh error: {e}")
    
    async def get_performance_report(self) -> Dict[str, Any]:
        """گزارش عملکرد"""
        return {
            'stats': self.performance_stats.copy(),
            'active_transfers': len(self.active_transfers),
            'queue_size': self.transfer_queue.qsize(),
            'circuit_breakers': len(self.circuit_breakers),
            'dns_cache_size': len(self.dns_cache),
            'learning_data_size': len(self.learning_data),
            'cache_stats': await self.cache_manager.get_stats(),
            'timestamp': time.time()
        }
    
    async def shutdown(self):
        """خاموش کردن graceful"""
        logger.info("Shutting down IntelligentSpeedOptimizer...")
        
        # لغو tasks
        self._cleanup_task.cancel()
        self._monitor_task.cancel()
        self._dns_refresh_task.cancel()
        
        try:
            await asyncio.gather(
                self._cleanup_task,
                self._monitor_task,
                self._dns_refresh_task,
                return_exceptions=True
            )
        except asyncio.CancelledError:
            pass
        
        # بستن connection pool
        await self.http_pool.close()
        
        # shutdown thread pools
        self.io_executor.shutdown(wait=True)
        self.cpu_executor.shutdown(wait=True)
        
        # ذخیره learning data
        await self._save_learning_data()
        
        logger.info("IntelligentSpeedOptimizer shutdown complete")
    
    async def _save_learning_data(self):
        """ذخیره داده‌های یادگیری"""
        try:
            learning_dir = Path("learning_data")
            learning_dir.mkdir(exist_ok=True)
            
            filename = learning_dir / f"learning_{int(time.time())}.json"
            with open(filename, 'w') as f:
                json.dump(list(self.learning_data), f, indent=2)
            
            logger.info(f"Learning data saved to {filename}")
            
        except Exception as e:
            logger.error(f"Failed to save learning data: {e}")

# Singleton instance
speed_optimizer = IntelligentSpeedOptimizer()
