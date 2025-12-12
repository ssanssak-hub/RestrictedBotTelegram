#!/usr/bin/env python3
# speed_monitor.py - نمایش سرعت دانلود/آپلود در لحظه

import asyncio
import time
import json
import math
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import threading
from queue import Queue
import psutil

logger = logging.getLogger(__name__)

@dataclass
class SpeedData:
    """داده‌های سرعت"""
    timestamp: float
    bytes_transferred: int
    total_bytes: int
    transfer_type: str  # 'download' یا 'upload'
    speed_bps: float = 0  # بیت بر ثانیه
    speed_kbps: float = 0  # کیلوبیت بر ثانیه
    speed_mbps: float = 0  # مگابیت بر ثانیه
    progress_percent: float = 0  # درصد پیشرفت
    eta_seconds: float = 0  # زمان تخمینی باقیمانده
    remaining_bytes: int = 0  # بایت باقیمانده

class RealTimeSpeedMonitor:
    """مانیتور سرعت real-time"""
    
    def __init__(self, update_interval: float = 0.5):  # هر 0.5 ثانیه
        self.update_interval = update_interval
        self.active_transfers: Dict[str, Dict] = {}  # transfer_id -> transfer_data
        self.speed_history: Dict[str, List[SpeedData]] = {}
        self.callbacks: Dict[str, List[Callable]] = {}  # transfer_id -> [callbacks]
        self.lock = threading.RLock()
        
        # شروع thread مانیتور
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info(f"RealTimeSpeedMonitor started with {update_interval}s interval")
    
    def _monitor_loop(self):
        """حلقه اصلی مانیتورینگ"""
        while True:
            try:
                with self.lock:
                    for transfer_id, transfer_data in list(self.active_transfers.items()):
                        self._update_transfer_speed(transfer_id, transfer_data)
                
                time.sleep(self.update_interval)
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                time.sleep(1)
    
    def _update_transfer_speed(self, transfer_id: str, transfer_data: Dict):
        """به‌روزرسانی سرعت انتقال"""
        try:
            current_time = time.time()
            elapsed = current_time - transfer_data['last_update_time']
            
            if elapsed <= 0:
                return
            
            # محاسبه سرعت آنی
            bytes_since_last = transfer_data['current_bytes'] - transfer_data['last_bytes']
            instant_speed_bps = bytes_since_last / elapsed
            
            # به‌روزرسانی داده‌ها
            transfer_data['last_bytes'] = transfer_data['current_bytes']
            transfer_data['last_update_time'] = current_time
            
            # محاسبه سرعت متوسط
            total_elapsed = current_time - transfer_data['start_time']
            average_speed_bps = transfer_data['current_bytes'] / total_elapsed if total_elapsed > 0 else 0
            
            # ایجاد SpeedData
            total_bytes = transfer_data['total_bytes']
            current_bytes = transfer_data['current_bytes']
            remaining_bytes = max(0, total_bytes - current_bytes)
            
            # محاسبه ETA
            eta_seconds = remaining_bytes / average_speed_bps if average_speed_bps > 0 else 0
            
            speed_data = SpeedData(
                timestamp=current_time,
                bytes_transferred=current_bytes,
                total_bytes=total_bytes,
                transfer_type=transfer_data['type'],
                speed_bps=instant_speed_bps,
                speed_kbps=instant_speed_bps / 1024,
                speed_mbps=instant_speed_bps / (1024 * 1024),
                progress_percent=(current_bytes / total_bytes * 100) if total_bytes > 0 else 0,
                eta_seconds=eta_seconds,
                remaining_bytes=remaining_bytes
            )
            
            # ذخیره در تاریخچه
            if transfer_id not in self.speed_history:
                self.speed_history[transfer_id] = []
            
            self.speed_history[transfer_id].append(speed_data)
            
            # حفظ فقط آخرین 1000 رکورد
            if len(self.speed_history[transfer_id]) > 1000:
                self.speed_history[transfer_id] = self.speed_history[transfer_id][-1000:]
            
            # فراخوانی callbackها
            if transfer_id in self.callbacks:
                for callback in self.callbacks[transfer_id]:
                    try:
                        callback(speed_data)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
            
        except Exception as e:
            logger.error(f"Update speed error: {e}")
    
    def register_transfer(
        self,
        transfer_id: str,
        transfer_type: str,
        total_bytes: int,
        callback: Optional[Callable] = None
    ):
        """ثبت انتقال جدید"""
        with self.lock:
            self.active_transfers[transfer_id] = {
                'type': transfer_type,
                'total_bytes': total_bytes,
                'current_bytes': 0,
                'start_time': time.time(),
                'last_update_time': time.time(),
                'last_bytes': 0
            }
            
            if callback:
                if transfer_id not in self.callbacks:
                    self.callbacks[transfer_id] = []
                self.callbacks[transfer_id].append(callback)
            
            logger.info(f"Transfer registered: {transfer_id} ({transfer_type})")
    
    def update_transfer_progress(
        self,
        transfer_id: str,
        bytes_transferred: int,
        total_bytes: Optional[int] = None
    ):
        """به‌روزرسانی پیشرفت انتقال"""
        with self.lock:
            if transfer_id not in self.active_transfers:
                logger.warning(f"Transfer not found: {transfer_id}")
                return
            
            transfer_data = self.active_transfers[transfer_id]
            transfer_data['current_bytes'] = bytes_transferred
            
            if total_bytes is not None:
                transfer_data['total_bytes'] = total_bytes
    
    def complete_transfer(self, transfer_id: str):
        """تکمیل انتقال"""
        with self.lock:
            if transfer_id in self.active_transfers:
                del self.active_transfers[transfer_id]
                
                # پاکسازی تاریخچه قدیمی بعد از 1 ساعت
                threading.Timer(3600, self._cleanup_history, args=[transfer_id]).start()
                
                logger.info(f"Transfer completed: {transfer_id}")
    
    def _cleanup_history(self, transfer_id: str):
        """پاکسازی تاریخچه"""
        with self.lock:
            if transfer_id in self.speed_history:
                del self.speed_history[transfer_id]
    
    def get_transfer_stats(self, transfer_id: str) -> Optional[Dict]:
        """دریافت آمار انتقال"""
        with self.lock:
            if transfer_id not in self.active_transfers:
                return None
            
            transfer_data = self.active_transfers[transfer_id]
            current_time = time.time()
            elapsed = current_time - transfer_data['start_time']
            
            # محاسبه سرعت
            speed_bps = transfer_data['current_bytes'] / elapsed if elapsed > 0 else 0
            
            return {
                'transfer_id': transfer_id,
                'type': transfer_data['type'],
                'total_bytes': transfer_data['total_bytes'],
                'transferred_bytes': transfer_data['current_bytes'],
                'progress_percent': (transfer_data['current_bytes'] / transfer_data['total_bytes'] * 100) 
                                  if transfer_data['total_bytes'] > 0 else 0,
                'speed_bps': speed_bps,
                'speed_kbps': speed_bps / 1024,
                'speed_mbps': speed_bps / (1024 * 1024),
                'elapsed_seconds': elapsed,
                'estimated_total_seconds': transfer_data['total_bytes'] / speed_bps if speed_bps > 0 else 0,
                'eta_seconds': max(0, (transfer_data['total_bytes'] - transfer_data['current_bytes']) / speed_bps) 
                             if speed_bps > 0 else 0
            }
    
    def get_speed_graph_data(self, transfer_id: str, points: int = 100) -> Dict:
        """دریافت داده‌های نمودار سرعت"""
        with self.lock:
            if transfer_id not in self.speed_history:
                return {'timestamps': [], 'speeds': []}
            
            history = self.speed_history[transfer_id]
            
            if len(history) == 0:
                return {'timestamps': [], 'speeds': []}
            
            # نمونه‌برداری برای تعداد نقاط مشخص
            step = max(1, len(history) // points)
            sampled = history[::step]
            
            timestamps = [data.timestamp - history[0].timestamp for data in sampled]
            speeds_kbps = [data.speed_kbps for data in sampled]
            
            return {
                'timestamps': timestamps,
                'speeds_kbps': speeds_kbps,
                'avg_speed_kbps': sum(speeds_kbps) / len(speeds_kbps) if speeds_kbps else 0,
                'max_speed_kbps': max(speeds_kbps) if speeds_kbps else 0,
                'min_speed_kbps': min(speeds_kbps) if speeds_kbps else 0
            }
    
    def format_speed_text(self, speed_data: SpeedData) -> str:
        """قالب‌بندی متن سرعت برای نمایش"""
        # تبدیل واحدها
        if speed_data.speed_mbps >= 1:
            speed_text = f"{speed_data.speed_mbps:.2f} MB/s"
        elif speed_data.speed_kbps >= 1:
            speed_text = f"{speed_data.speed_kbps:.2f} KB/s"
        else:
            speed_text = f"{speed_data.speed_bps:.0f} B/s"
        
        # تبدیل حجم
        transferred_mb = speed_data.bytes_transferred / (1024 * 1024)
        total_mb = speed_data.total_bytes / (1024 * 1024)
        
        # فرمت زمان ETA
        if speed_data.eta_seconds < 60:
            eta_text = f"{speed_data.eta_seconds:.0f} ثانیه"
        elif speed_data.eta_seconds < 3600:
            minutes = speed_data.eta_seconds / 60
            eta_text = f"{minutes:.0f} دقیقه"
        else:
            hours = speed_data.eta_seconds / 3600
            eta_text = f"{hours:.1f} ساعت"
        
        return speed_text, transferred_mb, total_mb, eta_text

class TelegramSpeedDisplay:
    """نمایش سرعت در تلگرام"""
    
    def __init__(self, bot):
        self.bot = bot
        self.speed_monitor = RealTimeSpeedMonitor(update_interval=0.5)
        self.user_messages: Dict[str, Dict] = {}  # transfer_id -> {chat_id, message_id}
        self.update_tasks: Dict[str, asyncio.Task] = {}
        
        logger.info("TelegramSpeedDisplay initialized")
    
    async def start_monitoring(
        self,
        chat_id: int,
        transfer_id: str,
        transfer_type: str,
        total_bytes: int,
        file_name: str = ""
    ):
        """شروع مانیتورینگ و نمایش"""
        # ثبت انتقال
        self.speed_monitor.register_transfer(
            transfer_id=transfer_id,
            transfer_type=transfer_type,
            total_bytes=total_bytes,
            callback=lambda data: asyncio.create_task(
                self._update_display(transfer_id, data)
            )
        )
        
        # ارسال پیام اولیه
        initial_message = await self._create_initial_message(
            chat_id, transfer_type, file_name, total_bytes
        )
        
        # ذخیره اطلاعات پیام
        self.user_messages[transfer_id] = {
            'chat_id': chat_id,
            'message_id': initial_message.message_id,
            'file_name': file_name,
            'last_update': time.time()
        }
        
        # شروع task به‌روزرسانی
        self.update_tasks[transfer_id] = asyncio.create_task(
            self._periodic_update(transfer_id)
        )
        
        logger.info(f"Started monitoring for {transfer_id} in chat {chat_id}")
    
    async def _create_initial_message(
        self,
        chat_id: int,
        transfer_type: str,
        file_name: str,
        total_bytes: int
    ):
        """ایجاد پیام اولیه"""
        total_mb = total_bytes / (1024 * 1024)
        
        if transfer_type == 'download':
            emoji = "📥"
            action = "دانلود"
        else:
            emoji = "📤"
            action = "آپلود"
        
        message_text = (
            f"{emoji} <b>{action} شروع شد</b>\n\n"
            f"📁 فایل: <code>{file_name[:50]}</code>\n"
            f"💾 حجم: {total_mb:.2f} MB\n"
            f"⏳ در حال آماده‌سازی...\n\n"
            f"<i>لطفاً منتظر بمانید...</i>"
        )
        
        return await self.bot.send_message(
            chat_id,
            message_text,
            parse_mode='HTML'
        )
    
    async def _update_display(self, transfer_id: str, speed_data: SpeedData):
        """به‌روزرسانی نمایش"""
        if transfer_id not in self.user_messages:
            return
        
        try:
            message_info = self.user_messages[transfer_id]
            chat_id = message_info['chat_id']
            message_id = message_info['message_id']
            
            # ایجاد متن به‌روزشده
            update_text = await self._create_update_text(
                transfer_id, speed_data, message_info['file_name']
            )
            
            # ویرایش پیام
            await self.bot.edit_message_text(
                update_text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='HTML'
            )
            
            # به‌روزرسانی زمان آخرین update
            message_info['last_update'] = time.time()
            
        except Exception as e:
            logger.error(f"Update display error: {e}")
    
    async def _create_update_text(
        self,
        transfer_id: str,
        speed_data: SpeedData,
        file_name: str
    ) -> str:
        """ایجاد متن به‌روزشده"""
        # فرمت سرعت
        speed_text, transferred_mb, total_mb, eta_text = \
            self.speed_monitor.format_speed_text(speed_data)
        
        # انتخاب emoji بر اساس سرعت
        if speed_data.speed_mbps > 5:
            speed_emoji = "⚡"
        elif speed_data.speed_mbps > 1:
            speed_emoji = "🚀"
        else:
            speed_emoji = "🐢"
        
        # انتخاب emoji نوع انتقال
        if speed_data.transfer_type == 'download':
            action_emoji = "📥"
            action_text = "دانلود"
        else:
            action_emoji = "📤"
            action_text = "آپلود"
        
        # ایجاد progress bar
        progress_bar = self._create_progress_bar(speed_data.progress_percent)
        
        # محاسبه زمان سپری شده
        stats = self.speed_monitor.get_transfer_stats(transfer_id)
        elapsed_seconds = stats['elapsed_seconds'] if stats else 0
        
        if elapsed_seconds < 60:
            elapsed_text = f"{elapsed_seconds:.0f} ثانیه"
        elif elapsed_seconds < 3600:
            elapsed_minutes = elapsed_seconds / 60
            elapsed_text = f"{elapsed_minutes:.0f} دقیقه"
        else:
            elapsed_hours = elapsed_seconds / 3600
            elapsed_text = f"{elapsed_hours:.1f} ساعت"
        
        # ساختن متن
        text = (
            f"{action_emoji} <b>{action_text}</b>\n\n"
            f"📁 فایل: <code>{file_name[:50]}</code>\n"
            f"📊 پیشرفت: {speed_data.progress_percent:.1f}%\n"
            f"{progress_bar}\n\n"
            f"💾 حجم: {transferred_mb:.2f} / {total_mb:.2f} MB\n"
            f"{speed_emoji} سرعت: <b>{speed_text}</b>\n"
            f"⏱️ زمان سپری شده: {elapsed_text}\n"
            f"⏳ زمان باقیمانده: {eta_text}\n\n"
        )
        
        # اضافه کردن اطلاعات اضافی برای فایل‌های بزرگ
        if total_mb > 100:
            graph_data = self.speed_monitor.get_speed_graph_data(transfer_id, 5)
            if graph_data['avg_speed_kbps'] > 0:
                avg_speed = graph_data['avg_speed_kbps'] / 1024
                text += f"📈 سرعت متوسط: {avg_speed:.2f} MB/s\n"
        
        return text
    
    def _create_progress_bar(self, percentage: float, length: int = 10) -> str:
        """ایجاد progress bar"""
        filled_length = int(length * percentage / 100)
        bar = '█' * filled_length + '░' * (length - filled_length)
        return f"[{bar}]"
    
    async def _periodic_update(self, transfer_id: str):
        """به‌روزرسانی دوره‌ای"""
        try:
            while transfer_id in self.user_messages:
                await asyncio.sleep(2)  # هر 2 ثانیه
                
                # بررسی اگر انتقال هنوز فعال است
                if transfer_id not in self.speed_monitor.active_transfers:
                    break
                
                # بررسی زمان آخرین update
                message_info = self.user_messages[transfer_id]
                if time.time() - message_info['last_update'] > 5:
                    # به‌روزرسانی دستی
                    stats = self.speed_monitor.get_transfer_stats(transfer_id)
                    if stats:
                        speed_data = SpeedData(
                            timestamp=time.time(),
                            bytes_transferred=stats['transferred_bytes'],
                            total_bytes=stats['total_bytes'],
                            transfer_type=stats['type'],
                            speed_bps=stats['speed_bps'],
                            speed_kbps=stats['speed_kbps'],
                            speed_mbps=stats['speed_mbps'],
                            progress_percent=stats['progress_percent'],
                            eta_seconds=stats['eta_seconds'],
                            remaining_bytes=stats['total_bytes'] - stats['transferred_bytes']
                        )
                        await self._update_display(transfer_id, speed_data)
        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Periodic update error: {e}")
    
    async def complete_monitoring(
        self,
        transfer_id: str,
        success: bool = True,
        error_message: str = ""
    ):
        """پایان مانیتورینگ"""
        try:
            if transfer_id not in self.user_messages:
                return
            
            # توقف task به‌روزرسانی
            if transfer_id in self.update_tasks:
                self.update_tasks[transfer_id].cancel()
                del self.update_tasks[transfer_id]
            
            # تکمیل انتقال در مانیتور
            self.speed_monitor.complete_transfer(transfer_id)
            
            # ارسال پیام نهایی
            message_info = self.user_messages[transfer_id]
            chat_id = message_info['chat_id']
            message_id = message_info['message_id']
            file_name = message_info['file_name']
            
            final_text = await self._create_final_message(
                file_name, success, error_message
            )
            
            await self.bot.edit_message_text(
                final_text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='HTML'
            )
            
            # پاکسازی
            del self.user_messages[transfer_id]
            
            logger.info(f"Monitoring completed for {transfer_id}")
            
        except Exception as e:
            logger.error(f"Complete monitoring error: {e}")
    
    async def _create_final_message(
        self,
        file_name: str,
        success: bool,
        error_message: str
    ) -> str:
        """ایجاد پیام نهایی"""
        if success:
            return (
                f"✅ <b>عملیات تکمیل شد</b>\n\n"
                f"📁 فایل: <code>{file_name}</code>\n"
                f"🎉 با موفقیت انجام شد!\n\n"
                f"<i>برای دانلود/آپلود بعدی آماده هستید.</i>"
            )
        else:
            return (
                f"❌ <b>خطا در عملیات</b>\n\n"
                f"📁 فایل: <code>{file_name}</code>\n"
                f"⚠️ خطا: {error_message}\n\n"
                f"<i>لطفاً دوباره تلاش کنید.</i>"
            )
    
    def get_transfer_info(self, transfer_id: str) -> Optional[Dict]:
        """دریافت اطلاعات انتقال"""
        if transfer_id in self.user_messages:
            return self.user_messages[transfer_id].copy()
        return None

class SpeedDisplayBot:
    """ربات با نمایش سرعت real-time"""
    
    def __init__(self, token: str):
        self.bot = telebot.TeleBot(token)
        self.speed_display = TelegramSpeedDisplay(self.bot)
        self.active_transfers: Dict[int, str] = {}  # user_id -> transfer_id
        
        self.setup_handlers()
    
    def setup_handlers(self):
        @self.bot.message_handler(commands=['start'])
        async def start_handler(message):
            await self.send_welcome(message.chat.id)
        
        @self.bot.message_handler(content_types=['document'])
        async def document_handler(message):
            await self.handle_document(message)
        
        @self.bot.message_handler(commands=['speedtest'])
        async def speedtest_handler(message):
            await self.run_speed_test(message.chat.id)
    
    async def send_welcome(self, chat_id: int):
        """ارسال پیام خوشآمدگویی"""
        welcome_text = (
            "👋 به ربات نمایش سرعت خوش آمدید!\n\n"
            "با این ربات می‌توانید:\n"
            "📥 فایل‌ها را با نمایش سرعت زنده دانلود کنید\n"
            "📤 فایل‌ها را با نمایش سرعت زنده آپلود کنید\n"
            "📊 سرعت اینترنت خود را تست کنید\n\n"
            "برای شروع، یک فایل ارسال کنید یا از /speedtest استفاده کنید."
        )
        
        await self.bot.send_message(chat_id, welcome_text)
    
    async def handle_document(self, message):
        """مدیریت فایل ارسالی"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        document = message.document
        
        # دریافت اطلاعات فایل
        file_name = document.file_name
        file_size = document.file_size
        
        # ایجاد ID انتقال
        transfer_id = f"upload_{user_id}_{int(time.time())}"
        
        # شروع مانیتورینگ
        await self.speed_display.start_monitoring(
            chat_id=chat_id,
            transfer_id=transfer_id,
            transfer_type='upload',
            total_bytes=file_size,
            file_name=file_name
        )
        
        # ذخیره انتقال فعال
        self.active_transfers[user_id] = transfer_id
        
        # شبیه‌سازی آپلود با به‌روزرسانی پیشرفت
        asyncio.create_task(
            self.simulate_upload(transfer_id, user_id, file_size)
        )
    
    async def simulate_upload(self, transfer_id: str, user_id: int, total_size: int):
        """شبیه‌سازی آپلود با به‌روزرسانی پیشرفت"""
        try:
            chunk_size = 1024 * 1024  # 1MB
            total_chunks = total_size // chunk_size + 1
            
            for chunk_num in range(total_chunks):
                # محاسبه بایت‌های انتقال داده شده
                transferred = min((chunk_num + 1) * chunk_size, total_size)
                
                # به‌روزرسانی مانیتور
                self.speed_display.speed_monitor.update_transfer_progress(
                    transfer_id, transferred
                )
                
                # تأخیر شبیه‌سازی
                await asyncio.sleep(0.1)
            
            # تکمیل انتقال
            await self.speed_display.complete_monitoring(transfer_id, success=True)
            
            # پاکسازی
            if user_id in self.active_transfers:
                del self.active_transfers[user_id]
            
        except Exception as e:
            logger.error(f"Simulate upload error: {e}")
            await self.speed_display.complete_monitoring(
                transfer_id, success=False, error_message=str(e)
            )
    
    async def run_speed_test(self, chat_id: int):
        """اجرای تست سرعت"""
        test_id = f"speedtest_{chat_id}_{int(time.time())}"
        
        # ارسال پیام شروع تست
        start_msg = await self.bot.send_message(
            chat_id,
            "🧪 <b>تست سرعت شروع شد</b>\n\n"
            "در حال اندازه‌گیری سرعت دانلود و آپلود...\n"
            "لطفاً چند ثانیه صبر کنید.",
            parse_mode='HTML'
        )
        
        # اجرای تست سرعت
        results = await self.perform_speed_test(test_id, chat_id)
        
        # ارسال نتایج
        result_text = self.format_speed_test_results(results)
        
        await self.bot.edit_message_text(
            result_text,
            chat_id=chat_id,
            message_id=start_msg.message_id,
            parse_mode='HTML'
        )
    
    async def perform_speed_test(self, test_id: str, chat_id: int) -> Dict:
        """انجام تست سرعت"""
        import random
        
        # شبیه‌سازی تست
        download_speed_mbps = random.uniform(5, 50)
        upload_speed_mbps = random.uniform(2, 20)
        ping_ms = random.randint(10, 100)
        
        # ایجاد نمودار سرعت تست
        speed_points = []
        for i in range(10):
            speed_points.append({
                'time': i,
                'download': download_speed_mbps * (0.8 + random.random() * 0.4),
                'upload': upload_speed_mbps * (0.8 + random.random() * 0.4)
            })
        
        return {
            'download_mbps': download_speed_mbps,
            'upload_mbps': upload_speed_mbps,
            'ping_ms': ping_ms,
            'server': 'Iran - Tehran',
            'isp': 'مشخص نشده',
            'speed_points': speed_points
        }
    
    def format_speed_test_results(self, results: Dict) -> str:
        """قالب‌بندی نتایج تست سرعت"""
        # ارزیابی سرعت
        def evaluate_speed(speed_mbps: float, type_: str) -> str:
            if type_ == 'download':
                if speed_mbps > 20:
                    return "عالی 🚀"
                elif speed_mbps > 10:
                    return "خوب 👍"
                elif speed_mbps > 5:
                    return "متوسط 📶"
                else:
                    return "ضعیف 🐌"
            else:  # upload
                if speed_mbps > 10:
                    return "عالی 🚀"
                elif speed_mbps > 5:
                    return "خوب 👍"
                elif speed_mbps > 2:
                    return "متوسط 📶"
                else:
                    return "ضعیف 🐌"
        
        download_eval = evaluate_speed(results['download_mbps'], 'download')
        upload_eval = evaluate_speed(results['upload_mbps'], 'upload')
        
        # ارزیابی پینگ
        if results['ping_ms'] < 30:
            ping_eval = "عالی 🎯"
        elif results['ping_ms'] < 60:
            ping_eval = "خوب 👍"
        elif results['ping_ms'] < 100:
            ping_eval = "متوسط ⏱️"
        else:
            ping_eval = "ضعیف 🐌"
        
        # ساخت متن نتایج
        text = (
            "📊 <b>نتایج تست سرعت</b>\n\n"
            f"🌐 سرور: {results['server']}\n"
            f"📡 ISP: {results['isp']}\n\n"
            f"📥 <b>دانلود:</b> {results['download_mbps']:.2f} Mbps\n"
            f"   وضعیت: {download_eval}\n\n"
            f"📤 <b>آپلود:</b> {results['upload_mbps']:.2f} Mbps\n"
            f"   وضعیت: {upload_eval}\n\n"
            f"⏱️ <b>پینگ:</b> {results['ping_ms']} ms\n"
            f"   وضعیت: {ping_eval}\n\n"
            f"<i>تست در {datetime.now().strftime('%H:%M')} انجام شد</i>"
        )
        
        return text
    
    async def start(self):
        """شروع ربات"""
        logger.info("SpeedDisplayBot started")
        await self.bot.polling(none_stop=True)

# نمونه استفاده
async def main():
    """تابع اصلی"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Speed Display Bot')
    parser.add_argument('--token', required=True, help='Bot token')
    
    args = parser.parse_args()
    
    bot = SpeedDisplayBot(args.token)
    await bot.start()

if __name__ == "__main__":
    asyncio.run(main())
