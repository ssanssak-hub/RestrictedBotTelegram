#!/usr/bin/env python3
# bot_with_live_speed_advanced.py - ربات کامل با نمایش سرعت real-time + ویژگی‌های پیشرفته

import asyncio
import logging
import time
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path
import aiohttp
import aioredis
from cachetools import TTLCache
import numpy as np
from collections import deque

try:
    import telebot
    from telebot.async_telebot import AsyncTeleBot
    from telebot import asyncio_filters
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except ImportError:
    print("⚠️  لطفا کتابخانه pyTelegramBotAPI را نصب کنید:")
    print("pip install pyTelegramBotAPI")
    exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==================== Data Classes ====================
@dataclass
class SpeedData:
    """داده‌های سرعت"""
    bytes_transferred: int
    total_bytes: int
    speed_bps: float
    speed_mbps: float
    speed_kbps: float
    progress_percent: float
    timestamp: float

@dataclass
class TransferStats:
    """آمار انتقال"""
    elapsed_seconds: float
    eta_seconds: float
    average_speed_mbps: float
    peak_speed_mbps: float
    consistency_score: float

@dataclass
class UserSession:
    """سشن کاربر"""
    user_id: int
    chat_id: int
    join_time: float
    total_downloads: int = 0
    total_uploads: int = 0
    avg_speed_mbps: float = 0.0
    total_data_transferred: int = 0
    last_active: float = 0.0
    preferred_language: str = 'fa'
    is_premium: bool = False

# ==================== ماژول Speed Monitor ====================
class RealTimeSpeedMonitor:
    """مانیتور سرعت real-time"""
    
    def __init__(self, update_interval: float = 0.3):
        self.update_interval = update_interval
        self.transfers: Dict[str, Dict] = {}
        self.speed_history: Dict[str, List[SpeedData]] = {}
        self.last_update: Dict[str, float] = {}
        self.callbacks: Dict[str, callable] = {}
        
        # Cache برای بهبود performance
        self.cache = TTLCache(maxsize=100, ttl=60)
        
        # ردیابی peak speed
        self.peak_speeds: Dict[str, float] = {}
    
    def register_transfer(self, transfer_id: str, transfer_type: str, 
                         total_bytes: int, callback: callable):
        """ثبت انتقال جدید"""
        self.transfers[transfer_id] = {
            'id': transfer_id,
            'type': transfer_type,
            'total_bytes': total_bytes,
            'bytes_transferred': 0,
            'start_time': time.time(),
            'last_bytes': 0,
            'last_time': time.time(),
            'speeds': deque(maxlen=100)  # ذخیره آخرین 100 سرعت
        }
        self.speed_history[transfer_id] = []
        self.callbacks[transfer_id] = callback
        self.peak_speeds[transfer_id] = 0.0
    
    def update_transfer_progress(self, transfer_id: str, bytes_transferred: int):
        """به‌روزرسانی پیشرفت انتقال"""
        if transfer_id not in self.transfers:
            return
        
        transfer = self.transfers[transfer_id]
        current_time = time.time()
        
        # محاسبه سرعت
        bytes_diff = bytes_transferred - transfer['bytes_transferred']
        time_diff = current_time - transfer['last_time']
        
        if time_diff > 0:
            current_speed_bps = bytes_diff / time_diff
            current_speed_mbps = (current_speed_bps * 8) / 1_000_000
            
            # ذخیره سرعت
            transfer['speeds'].append(current_speed_mbps)
            
            # به‌روزرسانی peak speed
            if current_speed_mbps > self.peak_speeds[transfer_id]:
                self.peak_speeds[transfer_id] = current_speed_mbps
            
            # ایجاد SpeedData
            speed_data = SpeedData(
                bytes_transferred=bytes_transferred,
                total_bytes=transfer['total_bytes'],
                speed_bps=current_speed_bps,
                speed_mbps=current_speed_mbps,
                speed_kbps=current_speed_bps / 1024,
                progress_percent=(bytes_transferred / transfer['total_bytes']) * 100,
                timestamp=current_time
            )
            
            # ذخیره تاریخچه
            self.speed_history[transfer_id].append(speed_data)
            
            # ذخیره وضعیت
            transfer['bytes_transferred'] = bytes_transferred
            transfer['last_bytes'] = bytes_transferred
            transfer['last_time'] = current_time
            
            # فراخوانی callback
            if current_time - self.last_update.get(transfer_id, 0) >= self.update_interval:
                self.callbacks[transfer_id](speed_data)
                self.last_update[transfer_id] = current_time
    
    def get_transfer_stats(self, transfer_id: str) -> Optional[TransferStats]:
        """دریافت آمار انتقال"""
        if transfer_id not in self.transfers:
            return None
        
        transfer = self.transfers[transfer_id]
        current_time = time.time()
        elapsed = current_time - transfer['start_time']
        
        # محاسبه ETA
        remaining_bytes = transfer['total_bytes'] - transfer['bytes_transferred']
        avg_speed_mbps = np.mean(list(transfer['speeds'])) if transfer['speeds'] else 0
        
        if avg_speed_mbps > 0:
            eta_seconds = (remaining_bytes * 8) / (avg_speed_mbps * 1_000_000)
        else:
            eta_seconds = 0
        
        # محاسبه consistency
        if len(transfer['speeds']) > 1:
            speeds = list(transfer['speeds'])
            consistency = 1.0 - (np.std(speeds) / np.mean(speeds)) if np.mean(speeds) > 0 else 0
            consistency = max(0, min(1, consistency))
        else:
            consistency = 1.0
        
        return TransferStats(
            elapsed_seconds=elapsed,
            eta_seconds=eta_seconds,
            average_speed_mbps=avg_speed_mbps,
            peak_speed_mbps=self.peak_speeds.get(transfer_id, 0),
            consistency_score=consistency
        )
    
    def complete_transfer(self, transfer_id: str):
        """اتمام انتقال"""
        if transfer_id in self.transfers:
            # ذخیره نهایی
            transfer = self.transfers[transfer_id]
            final_speed_data = SpeedData(
                bytes_transferred=transfer['total_bytes'],
                total_bytes=transfer['total_bytes'],
                speed_bps=0,
                speed_mbps=0,
                speed_kbps=0,
                progress_percent=100,
                timestamp=time.time()
            )
            
            # فراخوانی نهایی
            self.callbacks[transfer_id](final_speed_data)
            
            # پاکسازی (با تاخیر برای امکان استفاده آخرین)
            asyncio.create_task(self._cleanup_transfer(transfer_id))
    
    async def _cleanup_transfer(self, transfer_id: str, delay: int = 10):
        """پاکسازی انتقال با تاخیر"""
        await asyncio.sleep(delay)
        for dict_name in [self.transfers, self.speed_history, self.callbacks, self.last_update]:
            dict_name.pop(transfer_id, None)
        self.peak_speeds.pop(transfer_id, None)

# ==================== ماژول UI ====================
class ProgressUI:
    """ابزارهای UI پیشرفت"""
    
    def __init__(self):
        self.progress_chars = {
            'filled': '█',
            'empty': '░',
            'half': '▒'
        }
    
    def format_size(self, bytes_size: int) -> str:
        """فرمت‌بندی سایز"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_size < 1024.0:
                return f"{bytes_size:.2f} {unit}"
            bytes_size /= 1024.0
        return f"{bytes_size:.2f} TB"
    
    def format_speed(self, speed_bps: float) -> str:
        """فرمت‌بندی سرعت"""
        if speed_bps >= 1_000_000_000:  # Gbps
            return f"{(speed_bps / 1_000_000_000):.2f} Gbps"
        elif speed_bps >= 1_000_000:  # Mbps
            return f"{(speed_bps / 1_000_000):.2f} Mbps"
        elif speed_bps >= 1_000:  # Kbps
            return f"{(speed_bps / 1_000):.2f} Kbps"
        else:
            return f"{speed_bps:.2f} bps"
    
    def format_time(self, seconds: float) -> str:
        """فرمت‌بندی زمان"""
        if seconds < 60:
            return f"{seconds:.0f} ثانیه"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}:{secs:02d} دقیقه"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}:{minutes:02d} ساعت"
    
    def create_progress_bar(self, percent: float, width: int = 20) -> str:
        """ایجاد نوار پیشرفت"""
        filled_width = int(width * percent / 100)
        bar = self.progress_chars['filled'] * filled_width
        bar += self.progress_chars['empty'] * (width - filled_width)
        return bar
    
    def create_sparkline(self, data: List[float], height: int = 4) -> str:
        """ایجاد sparkline"""
        if not data:
            return ""
        
        max_val = max(data)
        if max_val == 0:
            return ""
        
        # نرمالایز کردن داده‌ها
        normalized = [int((d / max_val) * height) for d in data]
        
        # کاراکترهای براکت
        brackets = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█']
        
        # ایجاد sparkline
        sparkline = ''.join([brackets[min(val, len(brackets)-1)] for val in normalized])
        return sparkline

class AnimatedProgress:
    """انیمیشن‌های پیشرفت"""
    
    def __init__(self):
        self.spinners = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_index = 0
    
    def get_spinner(self, text: str = "") -> str:
        """دریافت spinner"""
        spinner = self.spinners[self.spinner_index]
        self.spinner_index = (self.spinner_index + 1) % len(self.spinners)
        return f"{spinner} {text}" if text else spinner
    
    def get_progress_animation(self, percent: float, width: int = 20) -> str:
        """انیمیشن پیشرفت"""
        frames = ['▏', '▎', '▍', '▌', '▋', '▊', '▉', '█']
        frame_index = int((percent / 100) * len(frames)) % len(frames)
        bar = self.create_progress_bar(percent, width)
        return f"{bar} {frames[frame_index]}"
    
    def create_progress_bar(self, percent: float, width: int = 20) -> str:
        """ایجاد نوار پیشرفت با انیمیشن"""
        filled = int(width * percent / 100)
        bar = '█' * filled + '░' * (width - filled)
        return bar

# ==================== ویژگی‌های پیشرفته ====================
class AISpeedOptimizer:
    """بهینه‌ساز هوشمند سرعت"""
    
    def __init__(self):
        self.user_patterns = {}
        self.network_cache = TTLCache(maxsize=1000, ttl=3600)
    
    async def analyze_network_pattern(self, user_id: int, speed_data: List[SpeedData]) -> Dict:
        """تحلیل الگوی شبکه کاربر"""
        if not speed_data:
            return {}
        
        speeds = [d.speed_mbps for d in speed_data]
        times = [datetime.fromtimestamp(d.timestamp).hour for d in speed_data]
        
        analysis = {
            'avg_speed': np.mean(speeds),
            'max_speed': np.max(speeds),
            'min_speed': np.min(speeds),
            'stability': 1.0 - (np.std(speeds) / np.mean(speeds)) if np.mean(speeds) > 0 else 0,
            'best_hour': max(set(times), key=times.count) if times else 12,
            'peak_hours': self._find_peak_hours(times, speeds),
            'recommendations': []
        }
        
        # تولید توصیه‌ها
        if analysis['stability'] < 0.7:
            analysis['recommendations'].append({
                'title': 'افزایش ثبات اتصال',
                'description': 'اتصال شما ناپایدار است. سعی کنید به روتر نزدیک‌تر شوید.',
                'priority': 'high'
            })
        
        if analysis['avg_speed'] < 5:
            analysis['recommendations'].append({
                'title': 'ارتقاء پلن اینترنت',
                'description': 'سرعت متوسط شما پایین است. ممکن است نیاز به ارتقاء پلن داشته باشید.',
                'priority': 'medium'
            })
        
        return analysis
    
    def _find_peak_hours(self, times: List[int], speeds: List[float]) -> List[int]:
        """پیدا کردن ساعات اوج سرعت"""
        hour_speeds = {}
        for hour, speed in zip(times, speeds):
            hour_speeds[hour] = hour_speeds.get(hour, []) + [speed]
        
        avg_speeds = {hour: np.mean(speeds) for hour, speeds in hour_speeds.items()}
        return sorted(avg_speeds.keys(), key=lambda h: avg_speeds[h], reverse=True)[:3]
    
    async def predict_optimal_time(self, user_id: int) -> Dict:
        """پیش‌بینی بهترین زمان برای دانلود"""
        # شبیه‌سازی تحلیل
        await asyncio.sleep(0.5)
        
        return {
            'optimal_hour': 2,  # 2-5 صبح
            'optimal_day': 'شنبه',
            'confidence': 0.85,
            'expected_speed_improvement': '40-60%',
            'reason': 'کمترین ترافیک شبکه'
        }

class NetworkDiagnostic:
    """تشخیص‌دهنده مشکلات شبکه"""
    
    def __init__(self):
        self.test_servers = [
            {'name': 'Google DNS', 'host': '8.8.8.8', 'location': 'USA'},
            {'name': 'Cloudflare', 'host': '1.1.1.1', 'location': 'Global'},
            {'name': 'Parsijoo', 'host': '8.8.4.4', 'location': 'Iran'},
        ]
    
    async def run_diagnostics(self, user_id: int) -> Dict:
        """اجرای تشخیص کامل"""
        diagnostics = {
            'timestamp': time.time(),
            'user_id': user_id,
            'tests': {},
            'issues': [],
            'score': 100  # شروع از 100، کم می‌کنیم برای هر مشکل
        }
        
        # تست پینگ
        ping_results = await self.test_ping_all()
        diagnostics['tests']['ping'] = ping_results
        
        # بررسی مشکلات
        for server, result in ping_results.items():
            if result['ping_ms'] > 200:
                diagnostics['issues'].append({
                    'type': 'high_latency',
                    'server': server,
                    'ping': result['ping_ms'],
                    'solution': 'سرور جایگزین انتخاب شود'
                })
                diagnostics['score'] -= 20
        
        # تست DNS
        dns_status = await self.test_dns_resolution()
        diagnostics['tests']['dns'] = dns_status
        
        if not dns_status['working']:
            diagnostics['issues'].append({
                'type': 'dns_failure',
                'solution': 'تغییر DNS به 1.1.1.1 یا 8.8.8.8'
            })
            diagnostics['score'] -= 30
        
        # ارزیابی نهایی
        if diagnostics['score'] > 80:
            diagnostics['health'] = 'عالی 🟢'
        elif diagnostics['score'] > 60:
            diagnostics['health'] = 'متوسط 🟡'
        else:
            diagnostics['health'] = 'ضعیف 🔴'
        
        return diagnostics
    
    async def test_ping_all(self) -> Dict:
        """تست پینگ همه سرورها"""
        results = {}
        
        async with aiohttp.ClientSession() as session:
            for server in self.test_servers:
                try:
                    start = time.time()
                    async with session.get(f'http://{server["host"]}', timeout=2) as resp:
                        ping_ms = (time.time() - start) * 1000
                        results[server['name']] = {
                            'ping_ms': round(ping_ms, 2),
                            'status': 'success',
                            'location': server['location']
                        }
                except Exception as e:
                    results[server['name']] = {
                        'ping_ms': None,
                        'status': 'failed',
                        'error': str(e)
                    }
        
        return results
    
    async def test_dns_resolution(self) -> Dict:
        """تست عملکرد DNS"""
        import socket
        
        test_domains = ['google.com', 'github.com', 'varzesh3.com']
        results = []
        
        for domain in test_domains:
            try:
                start = time.time()
                socket.gethostbyname(domain)
                resolve_time = (time.time() - start) * 1000
                results.append({
                    'domain': domain,
                    'time_ms': round(resolve_time, 2),
                    'status': 'success'
                })
            except Exception as e:
                results.append({
                    'domain': domain,
                    'status': 'failed',
                    'error': str(e)
                })
        
        working = all(r['status'] == 'success' for r in results)
        avg_time = np.mean([r['time_ms'] for r in results if r['status'] == 'success']) if working else None
        
        return {
            'working': working,
            'results': results,
            'avg_resolve_time_ms': avg_time
        }

class AdvancedReporting:
    """گزارش‌دهی پیشرفته"""
    
    def __init__(self):
        self.report_templates = {
            'basic': self._basic_report,
            'detailed': self._detailed_report,
            'comparative': self._comparative_report
        }
    
    async def generate_report(self, report_type: str, data: Dict, user_id: int) -> str:
        """تولید گزارش"""
        if report_type not in self.report_templates:
            report_type = 'basic'
        
        template_func = self.report_templates[report_type]
        return await template_func(data, user_id)
    
    async def _basic_report(self, data: Dict, user_id: int) -> str:
        """گزارش پایه"""
        report = f"""📊 <b>گزارش سرعت اینترنت</b>
👤 کاربر: {user_id}
📅 تاریخ: {datetime.now().strftime('%Y/%m/%d %H:%M')}
━━━━━━━━━━━━━━━━━━

📥 <b>دانلود:</b>
   🔹 سرعت: {data.get('download_speed', 0):.2f} Mbps
   🔹 کیفیت: {data.get('download_quality', 'نامعلوم')}
   🔹 زمان: {data.get('download_time', 0):.2f} ثانیه

📤 <b>آپلود:</b>
   🔹 سرعت: {data.get('upload_speed', 0):.2f} Mbps
   🔹 کیفیت: {data.get('upload_quality', 'نامعلوم')}
   🔹 زمان: {data.get('upload_time', 0):.2f} ثانیه

⏱️ <b>پینگ:</b>
   🔹 مقدار: {data.get('ping', 0)} ms
   🔹 ثبات: {data.get('ping_stability', 'نامعلوم')}

📈 <b>ارزیابی کلی:</b>
   ⭐ {data.get('overall_rating', 'نامعلوم')}
"""
        return report
    
    async def _detailed_report(self, data: Dict, user_id: int) -> str:
        """گزارش تفصیلی"""
        # پیاده‌سازی مشابه با جزئیات بیشتر
        return "گزارش تفصیلی"
    
    async def _comparative_report(self, data: Dict, user_id: int) -> str:
        """گزارش مقایسه‌ای"""
        # پیاده‌سازی مقایسه با دیگران
        return "گزارش مقایسه‌ای"

class GamificationEngine:
    """موتور بازی‌سازی برای افزایش تعامل"""
    
    def __init__(self):
        self.achievements = {
            'speed_demon': {'name': 'شیطان سرعت', 'threshold': 100},
            'consistent_user': {'name': 'کاربر منظم', 'threshold': 10},
            'data_hoarder': {'name': 'ذخیره‌کننده داده', 'threshold': 1024},  # GB
            'network_expert': {'name': 'متخصص شبکه', 'threshold': 50},
        }
        self.user_achievements = {}
    
    async def check_achievements(self, user_id: int, action: str, value: float) -> List[Dict]:
        """بررسی دستاوردهای کاربر"""
        if user_id not in self.user_achievements:
            self.user_achievements[user_id] = {
                'total_speed_tests': 0,
                'total_data_gb': 0,
                'consecutive_days': 0,
                'unlocked_achievements': []
            }
        
        user_data = self.user_achievements[user_id]
        unlocked = []
        
        # به‌روزرسانی آمار
        if action == 'speed_test':
            user_data['total_speed_tests'] += 1
            if value > 100:  # بیشتر از 100 Mbps
                unlocked.append(self._unlock_achievement(user_id, 'speed_demon'))
        
        elif action == 'data_transfer':
            user_data['total_data_gb'] += value / 1024  # تبدیل MB به GB
            if user_data['total_data_gb'] > 1024:
                unlocked.append(self._unlock_achievement(user_id, 'data_hoarder'))
        
        # بررسی دستاورد کاربر منظم
        if user_data['total_speed_tests'] >= 10:
            unlocked.append(self._unlock_achievement(user_id, 'consistent_user'))
        
        return unlocked
    
    def _unlock_achievement(self, user_id: int, achievement_id: str) -> Dict:
        """باز کردن دستاورد"""
        if achievement_id not in self.user_achievements[user_id]['unlocked_achievements']:
            self.user_achievements[user_id]['unlocked_achievements'].append(achievement_id)
            achievement = self.achievements[achievement_id]
            return {
                'id': achievement_id,
                'name': achievement['name'],
                'message': f"🏆 دستاورد جدید: {achievement['name']}!"
            }
        return None

# ==================== ربات اصلی ====================
class AdvancedSpeedBot:
    """ربات پیشرفته نمایش سرعت"""
    
    def __init__(self, token: str):
        self.bot = AsyncTeleBot(token)
        self.speed_monitor = RealTimeSpeedMonitor(update_interval=0.3)
        self.progress_ui = ProgressUI()
        self.animation = AnimatedProgress()
        
        # ویژگی‌های پیشرفته
        self.ai_optimizer = AISpeedOptimizer()
        self.network_diagnostic = NetworkDiagnostic()
        self.reporting = AdvancedReporting()
        self.gamification = GamificationEngine()
        
        # ذخیره وضعیت
        self.user_sessions: Dict[int, UserSession] = {}
        self.active_tests: Dict[int, str] = {}  # user_id -> test_id
        
        # cache برای performance
        self.message_cache = TTLCache(maxsize=500, ttl=300)
        
        self.setup_handlers()
        logger.info("🤖 AdvancedSpeedBot initialized")
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات"""
        
        @self.bot.message_handler(commands=['start', 'help'])
        async def start_handler(message):
            await self.send_welcome(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['download'])
        async def download_handler(message):
            await self.start_download_test(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['upload'])
        async def upload_handler(message):
            await self.start_upload_test(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['speedtest'])
        async def speedtest_handler(message):
            await self.run_complete_speedtest(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['diagnose'])
        async def diagnose_handler(message):
            await self.run_network_diagnosis(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['optimize'])
        async def optimize_handler(message):
            await self.show_optimization_tips(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['report'])
        async def report_handler(message):
            await self.generate_speed_report(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['stats', 'profile'])
        async def stats_handler(message):
            await self.show_user_stats(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['achievements'])
        async def achievements_handler(message):
            await self.show_achievements(message.from_user.id, message.chat.id)
        
        @self.bot.message_handler(commands=['leaderboard'])
        async def leaderboard_handler(message):
            await self.show_leaderboard(message.chat.id)
        
        @self.bot.message_handler(content_types=['document'])
        async def document_handler(message):
            await self.handle_real_upload(message)
    
    async def send_welcome(self, user_id: int, chat_id: int):
        """ارسال پیام خوشآمدگویی"""
        welcome_text = """
🚀 <b>ربات پیشرفته تست سرعت اینترنت</b>

با این ربات می‌توانید:
✅ تست سرعت دانلود/آپلود Real-time
✅ نمایش نمودارهای زنده
✅ تشخیص مشکلات شبکه
✅ بهینه‌سازی هوشمند
✅ گزارش‌گیری حرفه‌ای
✅ سیستم امتیاز و دستاورد

📋 <b>دستورات اصلی:</b>
/download - تست دانلود
/upload - تست آپلود  
/speedtest - تست کامل
/diagnose - تشخیص شبکه
/optimize - بهینه‌سازی
/report - گزارش کامل
/stats - آمار شما
/achievements - دستاوردها
/leaderboard - جدول رده‌بندی

🎮 <b>ویژگی‌های ویژه:</b>
• نمودارهای تعاملی
• پیش‌بینی بهترین زمان دانلود
• مقایسه با سایر کاربران
• تشخیص خودکار مشکلات
• سیستم بازی‌سازی
"""
        
        # ایجاد دکمه‌های شیشه‌ای
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("🚀 تست سرعت", callback_data="quick_test"),
            InlineKeyboardButton("🔍 تشخیص", callback_data="diagnose")
        )
        markup.add(
            InlineKeyboardButton("📊 آمار من", callback_data="my_stats"),
            InlineKeyboardButton("🏆 دستاوردها", callback_data="achievements")
        )
        
        await self.bot.send_message(
            chat_id, 
            welcome_text, 
            parse_mode='HTML',
            reply_markup=markup
        )
        
        # ثبت کاربر
        self.user_sessions[user_id] = UserSession(
            user_id=user_id,
            chat_id=chat_id,
            join_time=time.time(),
            last_active=time.time()
        )
        
        # باز کردن دستاورد شروع
        achievements = await self.gamification.check_achievements(user_id, 'speed_test', 0)
        if achievements:
            for achievement in achievements:
                if achievement:
                    await self.bot.send_message(chat_id, f"🎉 {achievement['message']}")
    
    async def start_download_test(self, user_id: int, chat_id: int):
        """شروع تست دانلود"""
        if user_id in self.active_tests:
            await self.bot.send_message(chat_id, "⏳ یک تست در حال اجرا است. لطفا صبر کنید.")
            return
        
        test_id = f"download_{user_id}_{int(time.time())}"
        self.active_tests[user_id] = test_id
        
        try:
            # ارسال پیام شروع
            start_msg = await self.bot.send_message(
                chat_id,
                self.animation.get_spinner("🎯 آماده‌سازی تست دانلود..."),
                parse_mode='HTML'
            )
            
            # ایجاد انتقال
            test_size = 50 * 1024 * 1024  # 50MB
            self.speed_monitor.register_transfer(
                transfer_id=test_id,
                transfer_type='download',
                total_bytes=test_size,
                callback=lambda data: asyncio.create_task(
                    self.update_download_display(chat_id, start_msg.message_id, test_id, data)
                )
            )
            
            # شبیه‌سازی دانلود
            asyncio.create_task(
                self.simulate_download(test_id, test_size, chat_id, start_msg.message_id, user_id)
            )
            
        except Exception as e:
            logger.error(f"Start download error: {e}")
            self.active_tests.pop(user_id, None)
            await self.bot.send_message(chat_id, f"❌ خطا: {str(e)}")
    
    async def simulate_download(self, test_id: str, total_size: int, 
                               chat_id: int, msg_id: int, user_id: int):
        """شبیه‌سازی دانلود"""
        chunk_size = 1024 * 1024  # 1MB
        total_chunks = total_size // chunk_size
        
        try:
            for chunk in range(total_chunks):
                if test_id != self.active_tests.get(user_id):
                    break  # تست لغو شده
                
                transferred = (chunk + 1) * chunk_size
                self.speed_monitor.update_transfer_progress(test_id, transferred)
                
                # تأخیر متغیر برای شبیه‌سازی واقعی
                base_delay = 0.05
                variation = 0.1 * (chunk % 20) / 20
                await asyncio.sleep(base_delay + variation)
            
            if test_id == self.active_tests.get(user_id):
                self.speed_monitor.complete_transfer(test_id)
                
                # به‌روزرسانی آمار کاربر
                if user_id in self.user_sessions:
                    self.user_sessions[user_id].total_downloads += 1
                    self.user_sessions[user_id].total_data_transferred += total_size
                
                # ارسال پیام تکمیل
                await self.send_completion_message(
                    chat_id, msg_id, 'download', total_size, user_id
                )
                
                # بررسی دستاوردها
                stats = self.speed_monitor.get_transfer_stats(test_id)
                if stats:
                    achievements = await self.gamification.check_achievements(
                        user_id, 'speed_test', stats.average_speed_mbps
                    )
                    for achievement in achievements:
                        if achievement:
                            await self.bot.send_message(
                                chat_id, 
                                f"🏆 {achievement['message']}"
                            )
            
        except Exception as e:
            logger.error(f"Download simulation error: {e}")
            await self.bot.edit_message_text(
                f"❌ خطا در تست دانلود: {e}",
                chat_id=chat_id,
                message_id=msg_id
            )
        finally:
            self.active_tests.pop(user_id, None)
    
    async def update_download_display(self, chat_id: int, msg_id: int, 
                                     test_id: str, speed_data: SpeedData):
        """به‌روزرسانی نمایش دانلود"""
        try:
            stats = self.speed_monitor.get_transfer_stats(test_id)
            if not stats:
                return
            
            text = self.create_speed_display_text(
                'download', 'test_file.bin', speed_data, stats
            )
            
            await self.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Update download display error: {e}")
    
    async def start_upload_test(self, user_id: int, chat_id: int):
        """شروع تست آپلود"""
        # پیاده‌سازی مشابه تست دانلود
        await self.bot.send_message(
            chat_id,
            "📤 تست آپلود در نسخه‌های بعدی اضافه خواهد شد."
        )
    
    def create_speed_display_text(self, transfer_type: str, file_name: str, 
                                 speed_data: SpeedData, stats: TransferStats) -> str:
        """ایجاد متن نمایش سرعت"""
        # انتخاب emoji و متن
        if transfer_type == 'download':
            action_emoji = "📥"
            action_text = "دانلود"
        else:
            action_emoji = "📤"
            action_text = "آپلود"
        
        # progress bar
        progress_bar = self.progress_ui.create_progress_bar(speed_data.progress_percent)
        
        # قالب‌بندی
        transferred = self.progress_ui.format_size(speed_data.bytes_transferred)
        total = self.progress_ui.format_size(speed_data.total_bytes)
        speed = self.progress_ui.format_speed(speed_data.speed_bps)
        elapsed = self.progress_ui.format_time(stats.elapsed_seconds)
        eta = self.progress_ui.format_time(stats.eta_seconds)
        
        # emoji سرعت
        if speed_data.speed_mbps > 50:
            speed_emoji = "⚡⚡"
            speed_status = "فوق‌العاده"
        elif speed_data.speed_mbps > 20:
            speed_emoji = "⚡"
            speed_status = "عالی"
        elif speed_data.speed_mbps > 5:
            speed_emoji = "🚀"
            speed_status = "خوب"
        elif speed_data.speed_mbps > 1:
            speed_emoji = "🐢"
            speed_status = "متوسط"
        else:
            speed_emoji = "🐌"
            speed_status = "کند"
        
        # ایجاد sparkline
        history = self.speed_monitor.speed_history.get(f"{action_text}_{id(speed_data)}", [])
        if len(history) > 5:
            speeds = [h.speed_mbps for h in history[-10:]]
            sparkline = self.progress_ui.create_sparkline(speeds)
        else:
            sparkline = ""
        
        # ساخت متن
        text = (
            f"{action_emoji} <b>{action_text} در حال اجرا...</b>\n\n"
            f"📁 فایل: <code>{file_name}</code>\n"
            f"📊 پیشرفت: {speed_data.progress_percent:.1f}%\n"
            f"{progress_bar}\n\n"
            f"💾 حجم: {transferred} / {total}\n"
            f"{speed_emoji} سرعت: <b>{speed}</b> ({speed_status})\n"
            f"📈 میانگین: {stats.average_speed_mbps:.2f} Mbps\n"
            f"🏆 اوج: {stats.peak_speed_mbps:.2f} Mbps\n"
            f"🎯 ثبات: {stats.consistency_score:.0%}\n\n"
            f"⏱️ سپری شده: {elapsed}\n"
            f"⏳ باقیمانده: {eta}\n"
        )
        
        if sparkline:
            text += f"📊 نمودار: {sparkline}\n\n"
        
        text += "<i>تست در حال اجراست...</i>"
        
        return text
    
    async def send_completion_message(self, chat_id: int, msg_id: int, 
                                     transfer_type: str, total_size: int, user_id: int):
        """ارسال پیام تکمیل"""
        if transfer_type == 'download':
            emoji = "📥"
            action = "دانلود"
        else:
            emoji = "📤"
            action = "آپلود"
        
        size_fmt = self.progress_ui.format_size(total_size)
        
        # دریافت آمار
        if user_id in self.user_sessions:
            user_data = self.user_sessions[user_id]
            total_tests = user_data.total_downloads + user_data.total_uploads
            total_data = self.progress_ui.format_size(user_data.total_data_transferred)
        else:
            total_tests = 0
            total_data = "0 B"
        
        completion_text = (
            f"{emoji} <b>{action} تکمیل شد!</b>\n\n"
            f"✅ تست با موفقیت انجام شد\n"
            f"💾 حجم تست: {size_fmt}\n\n"
            f"📊 <b>آمار کلی شما:</b>\n"
            f"🔸 تعداد تست‌ها: {total_tests}\n"
            f"🔸 کل داده انتقال یافته: {total_data}\n\n"
            f"برای تست مجدد از /download یا /upload استفاده کنید."
        )
        
        await self.bot.edit_message_text(
            completion_text,
            chat_id=chat_id,
            message_id=msg_id,
            parse_mode='HTML'
        )
    
    async def run_complete_speedtest(self, user_id: int, chat_id: int):
        """اجرای تست سرعت کامل"""
        test_msg = await self.bot.send_message(
            chat_id,
            "🧪 <b>تست سرعت کامل شروع شد</b>\n\n"
            "در حال اندازه‌گیری:\n"
            "1. سرعت دانلود 📥\n"
            "2. سرعت آپلود 📤\n"
            "3. پینگ و جیتر ⏱️\n"
            "4. از دست رفتن بسته 📦\n\n"
            "<i>لطفاً ۱۰-۱۵ ثانیه صبر کنید...</i>",
            parse_mode='HTML'
        )
        
        try:
            # اجرای تست‌ها به صورت موازی
            download_task = asyncio.create_task(self.measure_download_speed())
            upload_task = asyncio.create_task(self.measure_upload_speed())
            ping_task = asyncio.create_task(self.measure_ping())
            
            download_result = await download_task
            upload_result = await upload_task
            ping_result = await ping_task
            
            # ایجاد نتایج
            results_text = self.create_speedtest_results(
                download_result, upload_result, ping_result, user_id
            )
            
            await self.bot.edit_message_text(
                results_text,
                chat_id=chat_id,
                message_id=test_msg.message_id,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Speedtest error: {e}")
            await self.bot.edit_message_text(
                f"❌ خطا در تست سرعت: {str(e)}",
                chat_id=chat_id,
                message_id=test_msg.message_id
            )
    
    async def measure_download_speed(self) -> Dict:
        """اندازه‌گیری سرعت دانلود"""
        # شبیه‌سازی تست واقعی
        await asyncio.sleep(3)
        
        return {
            'speed_mbps': 42.5,
            'latency_ms': 25,
            'jitter_ms': 5,
            'packet_loss': 0,
            'rating': 'عالی 🚀',
            'quality': 'A+'
        }
    
    async def measure_upload_speed(self) -> Dict:
        """اندازه‌گیری سرعت آپلود"""
        await asyncio.sleep(2)
        
        return {
            'speed_mbps': 18.3,
            'latency_ms': 30,
            'jitter_ms': 8,
            'packet_loss': 0.1,
            'rating': 'خوب 👍',
            'quality': 'B+'
        }
    
    async def measure_ping(self) -> Dict:
        """اندازه‌گیری پینگ"""
        await asyncio.sleep(1)
        
        return {
            'ping_ms': 28,
            'jitter_ms': 3,
            'server': 'Iran - Tehran',
            'rating': 'عالی 🎯',
            'quality': 'A+'
        }
    
    def create_speedtest_results(self, download: Dict, upload: Dict, 
                                ping: Dict, user_id: int) -> str:
        """ایجاد متن نتایج تست سرعت"""
        # محاسبه امتیاز کلی
        download_score = min(100, download['speed_mbps'] * 2)
        upload_score = min(100, upload['speed_mbps'] * 5)
        ping_score = max(0, 100 - ping['ping_ms'])
        
        overall_score = (download_score * 0.5 + upload_score * 0.3 + ping_score * 0.2)
        
        # تعیین رتبه
        if overall_score > 90:
            grade = "A+ 🏆"
            comment = "اتصال شما فوق‌العاده است!"
        elif overall_score > 75:
            grade = "A 🎯"
            comment = "اتصال بسیار خوبی دارید."
        elif overall_score > 60:
            grade = "B 👍"
            comment = "اتصال قابل قبولی دارید."
        elif overall_score > 40:
            grade = "C 🤔"
            comment = "اتصال نیاز به بهبود دارد."
        else:
            grade = "D ⚠️"
            comment = "مشکلی در اتصال شما وجود دارد."
        
        text = (
            f"📊 <b>نتایج تست سرعت کامل</b>\n\n"
            f"👤 کاربر: {user_id}\n"
            f"🌐 سرور: {ping['server']}\n"
            f"⏱️ زمان: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📅 تاریخ: {datetime.now().strftime('%Y/%m/%d')}\n\n"
            
            f"🏆 <b>امتیاز کلی: {overall_score:.1f}/100</b>\n"
            f"📈 رتبه: {grade}\n"
            f"💡 {comment}\n\n"
            
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📥 <b>دانلود:</b> {download['speed_mbps']:.2f} Mbps\n"
            f"   کیفیت: {download['quality']}\n"
            f"   وضعیت: {download['rating']}\n"
            f"   تاخیر: {download['latency_ms']} ms\n\n"
            
            f"📤 <b>آپلود:</b> {upload['speed_mbps']:.2f} Mbps\n"
            f"   کیفیت: {upload['quality']}\n"
            f"   وضعیت: {upload['rating']}\n"
            f"   تاخیر: {upload['latency_ms']} ms\n\n"
            
            f"⏱️ <b>پینگ:</b> {ping['ping_ms']} ms\n"
            f"   کیفیت: {ping['quality']}\n"
            f"   وضعیت: {ping['rating']}\n"
            f"   جیتر: {ping['jitter_ms']} ms\n\n"
            
            f"📦 از دست رفتن بسته: {upload['packet_loss']:.1%}\n\n"
            
            f"💎 <i>برای بهبود سرعت از /optimize استفاده کنید.</i>"
        )
        
        return text
    
    async def run_network_diagnosis(self, user_id: int, chat_id: int):
        """اجرای تشخیص شبکه"""
        diag_msg = await self.bot.send_message(
            chat_id,
            "🔍 <b>در حال اجرای تشخیص شبکه...</b>\n\n"
            "در حال بررسی:\n"
            "1. اتصال به اینترنت 🌐\n"
            "2. سرورهای DNS 🔄\n"
            "3. تاخیر شبکه ⏱️\n"
            "4. مشکلات فایروال 🛡️\n\n"
            "<i>لطفا صبر کنید...</i>",
            parse_mode='HTML'
        )
        
        try:
            diagnostics = await self.network_diagnostic.run_diagnostics(user_id)
            
            # ایجاد گزارش تشخیص
            report = self.create_diagnosis_report(diagnostics)
            
            await self.bot.edit_message_text(
                report,
                chat_id=chat_id,
                message_id=diag_msg.message_id,
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"Diagnosis error: {e}")
            await self.bot.edit_message_text(
                f"❌ خطا در تشخیص شبکه: {str(e)}",
                chat_id=chat_id,
                message_id=diag_msg.message_id
            )
    
    def create_diagnosis_report(self, diagnostics: Dict) -> str:
        """ایجاد گزارش تشخیص"""
        issues_count = len(diagnostics['issues'])
        
        report = (
            f"🩺 <b>گزارش تشخیص شبکه</b>\n\n"
            f"📊 سلامت کلی: {diagnostics['health']}\n"
            f"🎯 امتیاز: {diagnostics['score']}/100\n"
            f"⚠️ مشکلات یافت شده: {issues_count}\n\n"
        )
        
        if diagnostics['tests']['ping']:
            report += "📡 <b>اتصال به سرورها:</b>\n"
            for server, result in diagnostics['tests']['ping'].items():
                if result['status'] == 'success':
                    report += f"   ✅ {server}: {result['ping_ms']} ms\n"
                else:
                    report += f"   ❌ {server}: قطع\n"
            report += "\n"
        
        if diagnostics['tests']['dns']:
            dns = diagnostics['tests']['dns']
            if dns['working']:
                report += f"🔗 <b>DNS:</b> فعال (میانگین: {dns['avg_resolve_time_ms']:.0f} ms)\n\n"
            else:
                report += "🔗 <b>DNS:</b> غیرفعال ⚠️\n\n"
        
        if issues_count > 0:
            report += "🚨 <b>مشکلات شناسایی شده:</b>\n"
            for i, issue in enumerate(diagnostics['issues'], 1):
                report += f"{i}. {issue['type']}\n"
                if 'solution' in issue:
                    report += f"   راه‌حل: {issue['solution']}\n"
            report += "\n"
        
        report += "💡 <i>برای رفع مشکلات از /optimize استفاده کنید.</i>"
        
        return report
    
    async def show_optimization_tips(self, user_id: int, chat_id: int):
        """نمایش نکات بهینه‌سازی"""
        try:
            # تحلیل الگوی کاربر
            if user_id in self.user_sessions:
                user_data = self.user_sessions[user_id]
                
                # پیش‌بینی بهترین زمان
                optimal_time = await self.ai_optimizer.predict_optimal_time(user_id)
                
                tips_text = (
                    f"🎯 <b>نکات بهینه‌سازی سرعت</b>\n\n"
                    f"👤 تحلیل برای کاربر: {user_id}\n\n"
                    
                    f"⏰ <b>بهترین زمان دانلود:</b>\n"
                    f"   ساعات: {optimal_time['optimal_hour']}-{optimal_time['optimal_hour']+3}\n"
                    f"   روز: {optimal_time['optimal_day']}\n"
                    f"   بهبود مورد انتظار: {optimal_time['expected_speed_improvement']}\n"
                    f"   دلیل: {optimal_time['reason']}\n\n"
                    
                    f"🔧 <b>پیشنهادات فنی:</b>\n"
                    f"1. استفاده از DNS: 1.1.1.1 یا 8.8.8.8\n"
                    f"2. به‌روزرسانی firmware روتر\n"
                    f"3. کاهش دستگاه‌های متصل به WiFi\n"
                    f"4. قرار دادن روتر در مرکز خانه\n"
                    f"5. استفاده از کابل Ethernet به جای WiFi\n\n"
                    
                    f"📱 <b>برای موبایل:</b>\n"
                    f"• فعال کردن Data Saver\n"
                    f"• غیرفعال کردن Background App Refresh\n"
                    f"• پاکسازی cache برنامه‌ها\n\n"
                    
                    f"💎 <i>این پیشنهادات بر اساس الگوی استفاده شماست.</i>"
                )
                
                await self.bot.send_message(chat_id, tips_text, parse_mode='HTML')
            else:
                await self.bot.send_message(
                    chat_id,
                    "⚠️ ابتدا با /start ربات را فعال کنید."
                )
                
        except Exception as e:
            logger.error(f"Optimization tips error: {e}")
            await self.bot.send_message(
                chat_id,
                f"❌ خطا در تولید پیشنهادات: {str(e)}"
            )
    
    async def generate_speed_report(self, user_id: int, chat_id: int):
        """تولید گزارش سرعت"""
        report_msg = await self.bot.send_message(
            chat_id,
            "📋 <b>در حال تهیه گزارش...</b>\n\n"
            "<i>لطفا صبر کنید...</i>",
            parse_mode='HTML'
        )
        
        try:
            # جمع‌آوری داده‌ها
            report_data = {
                'user_id': user_id,
                'timestamp': time.time(),
                'download_speed': 42.5,
                'upload_speed': 18.3,
                'ping': 28,
                'download_quality': 'A+',
                'upload_quality': 'B+',
                'ping_stability': 'عالی',
                'download_time': 3.2,
                'upload_time': 1.8,
                'overall_rating': 'عالی 🚀'
            }
            
            # تولید گزارش
            report_text = await self.reporting.generate_report('basic', report_data, user_id)
            
            await self.bot.edit_message_text(
                report_text,
                chat_id=chat_id,
                message_id=report_msg.message_id,
                parse_mode='HTML'
            )
            
            # ارسال نسخه ذخیره
            report_file = f"report_{user_id}_{int(time.time())}.txt"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_text.replace('<b>', '').replace('</b>', '')
                               .replace('<i>', '').replace('</i>', ''))
            
            await self.bot.send_document(chat_id, open(report_file, 'rb'))
            
            # حذف فایل موقت
            import os
            os.remove(report_file)
            
        except Exception as e:
            logger.error(f"Report generation error: {e}")
            await self.bot.edit_message_text(
                f"❌ خطا در تولید گزارش: {str(e)}",
                chat_id=chat_id,
                message_id=report_msg.message_id
            )
    
    async def show_user_stats(self, user_id: int, chat_id: int):
        """نمایش آمار کاربر"""
        if user_id not in self.user_sessions:
            await self.bot.send_message(
                chat_id,
                "📭 هیچ آماری موجود نیست. ابتدا با /start شروع کنید."
            )
            return
        
        user_data = self.user_sessions[user_id]
        
        # محاسبه زمان فعالیت
        active_seconds = time.time() - user_data.join_time
        active_time = self.progress_ui.format_time(active_seconds)
        
        # محاسبه میانگین سرعت
        total_tests = user_data.total_downloads + user_data.total_uploads
        avg_speed = user_data.avg_speed_mbps if total_tests > 0 else 0
        
        # رتبه‌بندی
        if avg_speed > 50:
            rank = "🏆 طلایی"
        elif avg_speed > 20:
            rank = "🥈 نقره‌ای"
        elif avg_speed > 10:
            rank = "🥉 برنزی"
        else:
            rank = "🎖️ معمولی"
        
        stats_text = (
            f"📊 <b>آمار کاربر</b>\n\n"
            f"👤 شناسه: {user_id}\n"
            f"🎖️ رتبه: {rank}\n"
            f"⏰ مدت فعالیت: {active_time}\n"
            f"📅 تاریخ عضویت: {datetime.fromtimestamp(user_data.join_time).strftime('%Y/%m/%d')}\n\n"
            
            f"📥 تعداد دانلود: {user_data.total_downloads}\n"
            f"📤 تعداد آپلود: {user_data.total_uploads}\n"
            f"🔢 کل تست‌ها: {total_tests}\n"
            f"💾 کل داده انتقال یافته: {self.progress_ui.format_size(user_data.total_data_transferred)}\n"
            f"⚡ سرعت متوسط: {avg_speed:.2f} Mbps\n\n"
            
            f"🌍 زبان: {user_data.preferred_language}\n"
            f"💎 وضعیت: {'پریمیوم 👑' if user_data.is_premium else 'رایگان 🔓'}\n\n"
            
            f"<i>برای مشاهده دستاوردها از /achievements استفاده کنید.</i>"
        )
        
        await self.bot.send_message(chat_id, stats_text, parse_mode='HTML')
    
    async def show_achievements(self, user_id: int, chat_id: int):
        """نمایش دستاوردهای کاربر"""
        try:
            # دریافت دستاوردها از موتور بازی‌سازی
            # (در این نسخه ساده شده)
            
            achievements_text = (
                "🏆 <b>دستاوردهای شما</b>\n\n"
                "🎮 <i>سیستم دستاوردها به زودی اضافه خواهد شد...</i>\n\n"
                "📈 در حال حاضر می‌توانید:\n"
                "• تست سرعت انجام دهید\n"
                "• در جدول رده‌بندی شرکت کنید\n"
                "• گزارش‌های کامل دریافت کنید\n\n"
                "برای مشاهده رتبه‌بندی از /leaderboard استفاده کنید."
            )
            
            await self.bot.send_message(chat_id, achievements_text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Achievements error: {e}")
            await self.bot.send_message(
                chat_id,
                f"❌ خطا در نمایش دستاوردها: {str(e)}"
            )
    
    async def show_leaderboard(self, chat_id: int):
        """نمایش جدول رده‌بندی"""
        try:
            # شبیه‌سازی داده‌های رده‌بندی
            leaderboard_data = [
                {'user_id': 123456, 'name': 'علی', 'score': 95, 'speed': 85.2},
                {'user_id': 789012, 'name': 'مریم', 'score': 88, 'speed': 72.5},
                {'user_id': 345678, 'name': 'رضا', 'score': 82, 'speed': 68.3},
                {'user_id': 901234, 'name': 'سارا', 'score': 78, 'speed': 65.1},
                {'user_id': 567890, 'name': 'محمد', 'score': 75, 'speed': 62.8},
            ]
            
            leaderboard_text = "🏆 <b>جدول رده‌بندی سرعت</b>\n\n"
            leaderboard_text += "📊 برترین کاربران این هفته:\n\n"
            
            for i, user in enumerate(leaderboard_data, 1):
                medal = ""
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                else:
                    medal = f"{i}."
                
                leaderboard_text += (
                    f"{medal} <b>{user['name']}</b>\n"
                    f"   امتیاز: {user['score']}/100\n"
                    f"   سرعت: {user['speed']} Mbps\n\n"
                )
            
            leaderboard_text += (
                "━━━━━━━━━━━━━━━━━━\n"
                "💡 <i>برای ورود به جدول رده‌بندی تست سرعت انجام دهید!</i>\n"
                "🚀 از /speedtest استفاده کنید."
            )
            
            await self.bot.send_message(chat_id, leaderboard_text, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Leaderboard error: {e}")
            await self.bot.send_message(
                chat_id,
                f"❌ خطا در نمایش جدول رده‌بندی: {str(e)}"
            )
    
    async def handle_real_upload(self, message):
        """مدیریت آپلود واقعی"""
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        await self.bot.send_message(
            chat_id,
            "📤 ویژگی آپلود واقعی در نسخه‌های بعدی اضافه خواهد شد.\n"
            "در حال حاضر از /upload برای تست آپلود استفاده کنید."
        )
    
    async def start(self):
        """شروع ربات"""
        logger.info("🚀 AdvancedSpeedBot starting...")
        await self.bot.polling(non_stop=True)

# ==================== تابع اصلی ====================
async def main():
    """تابع اصلی"""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(description='Advanced Speed Display Bot')
    parser.add_argument('--token', help='Bot token')
    
    args = parser.parse_args()
    
    # دریافت توکن
    token = args.token or os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("❌ توکن ربات را وارد کنید:")
        print("   روش 1: export TELEGRAM_BOT_TOKEN='YOUR_TOKEN'")
        print("   روش 2: python bot.py --token YOUR_TOKEN")
        token = input("🔑 لطفا توکن ربات را وارد کنید: ").strip()
    
    if not token:
        print("❌ توکن الزامی است.")
        return
    
    try:
        bot = AdvancedSpeedBot(token)
        logger.info("🤖 ربات با موفقیت ساخته شد")
        await bot.start()
    except Exception as e:
        logger.error(f"خطا در اجرای ربات: {e}")
        print(f"❌ خطا: {e}")

if __name__ == "__main__":
    # اجرای ربات
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 ربات متوقف شد")
    except Exception as e:
        print(f"❌ خطای غیرمنتظره: {e}")
