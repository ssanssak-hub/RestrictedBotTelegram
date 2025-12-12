#!/usr/bin/env python3
# progress_ui_advanced.py - UI پیشرفته برای نمایش سرعت و پیشرفت با ویژگی‌های حرفه‌ای

from typing import Dict, List, Optional, Tuple, Union, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import time
import math
import statistics
import json
import numpy as np
from datetime import datetime, timedelta
import random
import hashlib
import os
from abc import ABC, abstractmethod

# ================ Enums ================

class OutputFormat(Enum):
    """فرمت‌های خروجی"""
    TEXT = "text"
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"
    PROMETHEUS = "prometheus"

class TransferStatus(Enum):
    """وضعیت‌های انتقال"""
    PENDING = "pending"
    TRANSFERRING = "transferring"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"

class NetworkQuality(Enum):
    """کیفیت شبکه"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNSTABLE = "unstable"

# ================ Core Classes ================

@dataclass
class TransferMetrics:
    """متریک‌های انتقال"""
    transferred: int = 0
    total: int = 0
    speed: float = 0.0
    elapsed: float = 0.0
    remaining: float = 0.0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    speed_history: List[float] = field(default_factory=list)
    latency_history: List[float] = field(default_factory=list)
    error_count: int = 0
    
    @property
    def percent(self) -> float:
        return (self.transferred / self.total * 100) if self.total > 0 else 0.0
    
    @property
    def avg_speed(self) -> float:
        return statistics.mean(self.speed_history) if self.speed_history else 0.0
    
    @property
    def max_speed(self) -> float:
        return max(self.speed_history) if self.speed_history else 0.0
    
    @property
    def min_speed(self) -> float:
        return min(self.speed_history) if self.speed_history else 0.0

@dataclass
class ProgressConfig:
    """تنظیمات نمایش پیشرفت"""
    show_percentage: bool = True
    show_speed: bool = True
    show_time: bool = True
    show_graph: bool = False
    graph_width: int = 30
    graph_height: int = 5
    refresh_rate: float = 0.1  # seconds
    use_colors: bool = True
    show_eta: bool = True
    show_size: bool = True
    compact_mode: bool = False
    language: str = "fa"  # fa, en

# ================ Main Progress UI ================

class ProgressUI:
    """UI اصلی نمایش پیشرفت"""
    
    # رنگ‌های ترمینال
    COLORS = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'reset': '\033[0m',
        'bold': '\033[1m',
        'dim': '\033[2m'
    }
    
    # نمادها
    SYMBOLS = {
        'bar_filled': '█',
        'bar_empty': '░',
        'arrow_right': '→',
        'arrow_up': '↑',
        'arrow_down': '↓',
        'check': '✓',
        'cross': '✗',
        'warning': '⚠',
        'info': 'ℹ',
        'spinner': ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    }
    
    def __init__(self, config: Optional[ProgressConfig] = None):
        self.config = config or ProgressConfig()
        self._spinner_index = 0
        self._last_update_time = time.time()
        self._frame_count = 0
    
    # ================ فرمت‌بندی ================
    
    @staticmethod
    def format_size(bytes_count: int, precision: int = 2) -> str:
        """قالب‌بندی اندازه فایل"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0 or unit == 'TB':
                break
            bytes_count /= 1024.0
        return f"{bytes_count:.{precision}f} {unit}"
    
    @staticmethod
    def format_speed(bytes_per_second: float, precision: int = 2) -> str:
        """قالب‌بندی سرعت"""
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if bytes_per_second < 1024.0 or unit == 'GB/s':
                break
            bytes_per_second /= 1024.0
        return f"{bytes_per_second:.{precision}f} {unit}"
    
    @staticmethod
    def format_time(seconds: float, detailed: bool = False) -> str:
        """قالب‌بندی زمان"""
        if seconds < 60:
            return f"{seconds:.0f} ثانیه" if not detailed else f"{seconds:.1f} ثانیه"
        
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes:.0f}:{seconds:02.0f}"
        
        hours, minutes = divmod(minutes, 60)
        if hours < 24:
            return f"{hours:.0f}:{minutes:02.0f}:{seconds:02.0f}"
        
        days, hours = divmod(hours, 24)
        return f"{days} روز {hours:.0f}:{minutes:02.0f}"
    
    @staticmethod
    def format_timestamp(timestamp: float) -> str:
        """قالب‌بندی timestamp"""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    
    # ================ Progress Bars ================
    
    def create_progress_bar(self, percent: float, width: int = 20, 
                          color_gradient: bool = True) -> str:
        """ایجاد progress bar گرافیکی"""
        if percent < 0:
            percent = 0
        elif percent > 100:
            percent = 100
        
        filled = int(width * percent / 100)
        empty = width - filled
        
        if color_gradient and self.config.use_colors:
            if percent < 30:
                color = self.COLORS['red']
            elif percent < 70:
                color = self.COLORS['yellow']
            else:
                color = self.COLORS['green']
        else:
            color = ''
        
        bar = color + self.SYMBOLS['bar_filled'] * filled + \
              self.COLORS['dim'] + self.SYMBOLS['bar_empty'] * empty + \
              self.COLORS['reset']
        
        return f"[{bar}]"
    
    def create_multi_segment_bar(self, segments: List[Tuple[float, str]], 
                                width: int = 30) -> str:
        """ایجاد progress bar با چندین بخش رنگی"""
        total = sum(s[0] for s in segments)
        if total == 0:
            return "[" + " " * width + "]"
        
        result = []
        for value, color_code in segments:
            segment_width = int(width * value / total)
            if color_code in self.COLORS:
                result.append(self.COLORS[color_code] + 
                            self.SYMBOLS['bar_filled'] * segment_width)
            else:
                result.append(self.SYMBOLS['bar_filled'] * segment_width)
        
        # پر کردن فضای خالی
        total_width = sum(len(r) for r in result if r.startswith('\033'))
        empty_width = width - total_width
        if empty_width > 0:
            result.append(self.COLORS['dim'] + 
                         self.SYMBOLS['bar_empty'] * empty_width)
        
        return "[" + "".join(result) + self.COLORS['reset'] + "]"
    
    # ================ نمایش‌های پیشرفت ================
    
    def create_detailed_progress(self, metrics: TransferMetrics, 
                                show_graph: bool = True) -> str:
        """ایجاد متن پیشرفت با جزئیات کامل"""
        lines = []
        
        # هدر
        lines.append(f"{self.COLORS['bold']}📊 نمایش پیشرفت انتقال{self.COLORS['reset']}")
        lines.append("─" * 40)
        
        # Progress bar
        bar = self.create_progress_bar(metrics.percent, 40)
        lines.append(f"{bar} {metrics.percent:.1f}%")
        
        # اطلاعات اصلی
        if self.config.show_size:
            transferred_fmt = self.format_size(metrics.transferred)
            total_fmt = self.format_size(metrics.total)
            lines.append(f"📦 حجم: {transferred_fmt} / {total_fmt}")
        
        if self.config.show_speed:
            speed_fmt = self.format_speed(metrics.speed)
            avg_speed_fmt = self.format_speed(metrics.avg_speed)
            lines.append(f"⚡ سرعت: {speed_fmt} (متوسط: {avg_speed_fmt})")
        
        if self.config.show_time:
            elapsed_fmt = self.format_time(metrics.elapsed)
            remaining_fmt = self.format_time(metrics.remaining)
            lines.append(f"⏱️ سپری شده: {elapsed_fmt}")
            
            if self.config.show_eta and metrics.remaining > 0:
                eta_time = time.time() + metrics.remaining
                eta_str = datetime.fromtimestamp(eta_time).strftime("%H:%M:%S")
                lines.append(f"⏳ باقیمانده: {remaining_fmt} (تا {eta_str})")
        
        # نمودار سرعت
        if show_graph and metrics.speed_history and len(metrics.speed_history) > 5:
            lines.append("")
            lines.append("📈 نمودار سرعت:")
            lines.append(self.create_speed_graph(metrics.speed_history, 
                                                self.config.graph_width, 
                                                self.config.graph_height))
        
        # آمار اضافی
        if metrics.error_count > 0:
            lines.append(f"{self.COLORS['yellow']}⚠ خطاها: {metrics.error_count}{self.COLORS['reset']}")
        
        return "\n".join(lines)
    
    def create_mini_progress(self, metrics: TransferMetrics) -> str:
        """ایجاد نمایش مینیاتوری"""
        bar = self.create_progress_bar(metrics.percent, 10, False)
        speed_fmt = self.format_speed(metrics.speed)
        return f"{bar} {metrics.percent:.1f}% ⚡{speed_fmt}"
    
    # ================ نمودارها و گراف‌ها ================
    
    def create_speed_graph(self, speed_history: List[float], 
                          width: int = 30, height: int = 5) -> str:
        """ایجاد نمودار سرعت ASCII"""
        if not speed_history or len(speed_history) < 2:
            return "📈 (داده کافی نیست)"
        
        # محدود کردن تاریخچه
        data = speed_history[-width:] if len(speed_history) > width else speed_history
        
        # پیدا کردن محدوده
        min_val = min(data)
        max_val = max(data)
        
        if max_val - min_val < 0.0001:
            return "📈 (داده ثابت)"
        
        # نرمال‌سازی
        normalized = [(val - min_val) / (max_val - min_val) for val in data]
        
        # ایجاد نمودار
        chart_rows = []
        for y in range(height - 1, -1, -1):
            threshold = y / height
            row_chars = []
            
            for value in normalized:
                if value >= threshold:
                    if value >= 0.8:
                        row_chars.append(self.SYMBOLS['bar_filled'])
                    elif value >= 0.5:
                        row_chars.append('▓')
                    elif value >= 0.3:
                        row_chars.append('▒')
                    else:
                        row_chars.append('░')
                else:
                    row_chars.append(' ')
            
            chart_rows.append(''.join(row_chars))
        
        # اضافه کردن محور
        chart_rows.append('─' * len(data))
        
        # مقادیر min/max
        min_fmt = self.format_speed(min_val)
        max_fmt = self.format_speed(max_val)
        chart_rows.append(f"↕️ {min_fmt} – {max_fmt}")
        
        return '\n'.join(chart_rows)
    
    def create_comparison_chart(self, datasets: Dict[str, List[float]], 
                               width: int = 40, height: int = 8) -> str:
        """ایجاد نمودار مقایسه‌ای"""
        if not datasets:
            return "📊 (داده‌ای موجود نیست)"
        
        # رنگ‌های مختلف برای دیتاست‌ها
        colors = [self.COLORS['green'], self.COLORS['blue'], 
                 self.COLORS['yellow'], self.COLORS['magenta']]
        
        # نرمال‌سازی همه دیتاست‌ها
        all_data = []
        for data in datasets.values():
            all_data.extend(data[-width:])
        
        max_val = max(all_data) if all_data else 1
        
        # ایجاد نمودار
        chart = []
        for y in range(height - 1, -1, -1):
            threshold = y / height
            row = [' '] * width
            
            for i, (name, data) in enumerate(datasets.items()):
                color = colors[i % len(colors)]
                for x in range(min(width, len(data))):
                    value = data[x] / max_val if max_val > 0 else 0
                    if value >= threshold:
                        row[x] = color + '█' + self.COLORS['reset']
            
            chart.append(''.join(row))
        
        # اضافه کردن legend
        chart.append('─' * width)
        legend = []
        for i, name in enumerate(datasets.keys()):
            color = colors[i % len(colors)]
            legend.append(f"{color}█{self.COLORS['reset']} {name}")
        
        chart.append(' | '.join(legend))
        
        return '\n'.join(chart)
    
    # ================ انیمیشن‌ها ================
    
    def get_spinner(self, text: str = "") -> str:
        """دریافت اسپینر انیمیشن"""
        frame = self.SYMBOLS['spinner'][self._spinner_index]
        self._spinner_index = (self._spinner_index + 1) % len(self.SYMBOLS['spinner'])
        
        if text:
            return f"{frame} {text}"
        return frame
    
    def create_loading_animation(self, stage: str = "", 
                                details: str = "") -> str:
        """ایجاد انیمیشن لودینگ"""
        spinner = self.get_spinner()
        
        stages = {
            'connecting': "در حال اتصال",
            'downloading': "در حال دانلود",
            'uploading': "در حال آپلود",
            'processing': "در حال پردازش",
            'encrypting': "در حال رمزنگاری",
            'decrypting': "در حال رمزگشایی",
            'compressing': "در حال فشرده‌سازی",
            'extracting': "در حال استخراج",
            'verifying': "در حال تأیید",
            'cleaning': "در حال پاک‌سازی"
        }
        
        stage_text = stages.get(stage, "در حال پردازش")
        
        if details:
            return f"{spinner} {stage_text}: {details}"
        return f"{spinner} {stage_text}..."
    
    # ================ خلاصه‌گیری ================
    
    def create_transfer_summary(self, metrics: TransferMetrics, 
                              transfer_type: str = "download",
                              filename: str = "") -> str:
        """ایجاد خلاصه انتقال"""
        lines = []
        
        emoji = "📥" if transfer_type == "download" else "📤"
        action = "دانلود" if transfer_type == "download" else "آپلود"
        
        lines.append(f"{emoji} {self.COLORS['bold']}{action} تکمیل شد{self.COLORS['reset']}")
        lines.append("=" * 40)
        
        if filename:
            lines.append(f"📁 فایل: {filename}")
        
        lines.append(f"📊 پیشرفت: {metrics.percent:.1f}%")
        lines.append(f"💾 حجم کل: {self.format_size(metrics.total)}")
        lines.append(f"⏱️ زمان کل: {self.format_time(metrics.elapsed, True)}")
        lines.append(f"⚡ سرعت متوسط: {self.format_speed(metrics.avg_speed)}")
        lines.append(f"🚀 حداکثر سرعت: {self.format_speed(metrics.max_speed)}")
        
        # ارزیابی عملکرد
        efficiency = self._calculate_efficiency(metrics)
        lines.append(f"⭐ کارایی: {efficiency['rating']} {efficiency['emoji']}")
        
        # رکوردها
        if metrics.speed_history:
            lines.append(f"📈 نقاط داده: {len(metrics.speed_history)}")
        
        if metrics.error_count > 0:
            lines.append(f"{self.COLORS['yellow']}⚠ خطاهای رخ داده: {metrics.error_count}{self.COLORS['reset']}")
        
        return "\n".join(lines)
    
    def _calculate_efficiency(self, metrics: TransferMetrics) -> Dict:
        """محاسبه کارایی انتقال"""
        if metrics.total == 0 or metrics.elapsed == 0:
            return {"rating": "نامشخص", "emoji": "❓", "score": 0}
        
        # محاسبه نمره کارایی (0-100)
        speed_score = min(100, metrics.avg_speed / (1024 * 1024) * 10)  # 10MB/s = 100
        
        stability_score = 0
        if len(metrics.speed_history) > 10:
            std_dev = statistics.stdev(metrics.speed_history[-10:])
            mean_speed = statistics.mean(metrics.speed_history[-10:])
            if mean_speed > 0:
                cv = std_dev / mean_speed
                stability_score = max(0, 100 - cv * 1000)
        
        error_penalty = metrics.error_count * 5
        total_score = max(0, (speed_score * 0.7 + stability_score * 0.3) - error_penalty)
        
        # تعیین رتبه
        if total_score >= 90:
            return {"rating": "عالی", "emoji": "🚀", "score": total_score}
        elif total_score >= 70:
            return {"rating": "خوب", "emoji": "👍", "score": total_score}
        elif total_score >= 50:
            return {"rating": "متوسط", "emoji": "📶", "score": total_score}
        else:
            return {"rating": "ضعیف", "emoji": "🐌", "score": total_score}

# ================ AIPredictionProgress ================

class AIPredictionProgress:
    """پیش‌بینی هوشمند با الگوریتم‌های ML"""
    
    def __init__(self, ui: ProgressUI):
        self.ui = ui
        self.patterns = []
        self.history_buffer = []
        self.max_history = 100
        
    def predict_completion(self, metrics: TransferMetrics) -> Dict:
        """پیش‌بینی زمان تکمیل با تحلیل الگوهای سرعت"""
        if len(metrics.speed_history) < 5:
            return self._simple_prediction(metrics)
        
        # ذخیره تاریخچه
        self.history_buffer.append({
            'timestamp': time.time(),
            'speed': metrics.speed,
            'transferred': metrics.transferred,
            'remaining': metrics.total - metrics.transferred
        })
        
        if len(self.history_buffer) > self.max_history:
            self.history_buffer.pop(0)
        
        # تحلیل با روش‌های مختلف
        predictions = {
            'linear': self._linear_regression_prediction(metrics),
            'exponential': self._exponential_smoothing_prediction(metrics),
            'pattern': self._pattern_matching_prediction(metrics),
            'neural': self._neural_network_prediction(metrics) if len(self.history_buffer) > 20 else None
        }
        
        # ترکیب پیش‌بینی‌ها
        valid_preds = [p for p in predictions.values() if p is not None]
        if not valid_preds:
            return self._simple_prediction(metrics)
        
        # میانگین وزنی
        weights = {'linear': 0.3, 'exponential': 0.3, 'pattern': 0.2, 'neural': 0.2}
        weighted_remaining = 0
        total_weight = 0
        
        for method, pred in predictions.items():
            if pred is not None:
                weight = weights.get(method, 0.1)
                weighted_remaining += pred['remaining_time'] * weight
                total_weight += weight
        
        avg_remaining = weighted_remaining / total_weight if total_weight > 0 else metrics.remaining
        
        # محاسبه اعتماد
        confidence = self._calculate_confidence(predictions, metrics)
        
        # پیش‌بینی سرعت آینده
        future_speeds = self._predict_future_speeds(metrics)
        
        return {
            'remaining_time': avg_remaining,
            'confidence': confidence,
            'completion_time': time.time() + avg_remaining,
            'future_speeds': future_speeds,
            'method': 'ai_ensemble',
            'predictions': {k: v for k, v in predictions.items() if v is not None},
            'scenarios': self._generate_scenarios(metrics, avg_remaining)
        }
    
    def _simple_prediction(self, metrics: TransferMetrics) -> Dict:
        """پیش‌بینی ساده"""
        if metrics.speed > 0:
            remaining_time = (metrics.total - metrics.transferred) / metrics.speed
        else:
            remaining_time = float('inf')
        
        return {
            'remaining_time': remaining_time,
            'confidence': 0.3,
            'completion_time': time.time() + remaining_time,
            'method': 'simple',
            'scenarios': {
                'optimistic': remaining_time * 0.8,
                'realistic': remaining_time,
                'pessimistic': remaining_time * 1.5
            }
        }
    
    def _linear_regression_prediction(self, metrics: TransferMetrics) -> Optional[Dict]:
        """پیش‌بینی با رگرسیون خطی"""
        if len(metrics.speed_history) < 10:
            return None
        
        try:
            x = np.arange(len(metrics.speed_history))
            y = np.array(metrics.speed_history)
            
            # رگرسیون خطی
            z = np.polyfit(x, y, 1)
            slope = z[0]
            intercept = z[1]
            
            # پیش‌بینی سرعت آینده
            future_speed = slope * len(metrics.speed_history) + intercept
            
            # جلوگیری از سرعت منفی
            future_speed = max(future_speed, 1000)  # حداقل 1KB/s
            
            remaining = metrics.total - metrics.transferred
            remaining_time = remaining / future_speed if future_speed > 0 else float('inf')
            
            return {
                'remaining_time': remaining_time,
                'predicted_speed': future_speed,
                'trend': 'increasing' if slope > 0.01 else 'decreasing' if slope < -0.01 else 'stable',
                'trend_strength': abs(slope),
                'method': 'linear_regression'
            }
        except:
            return None
    
    def _calculate_confidence(self, predictions: Dict, metrics: TransferMetrics) -> float:
        """محاسبه سطح اعتماد پیش‌بینی"""
        if not predictions:
            return 0.0
        
        # عوامل مؤثر در اعتماد
        factors = []
        
        # 1. تعداد نقاط داده
        data_points_factor = min(1.0, len(metrics.speed_history) / 50)
        factors.append(data_points_factor * 0.3)
        
        # 2. همخوانی پیش‌بینی‌ها
        if len(predictions) > 1:
            times = [p['remaining_time'] for p in predictions.values() if p is not None]
            std_dev = statistics.stdev(times) if len(times) > 1 else 0
            mean_time = statistics.mean(times)
            
            if mean_time > 0:
                consistency = max(0, 1 - (std_dev / mean_time))
                factors.append(consistency * 0.4)
        
        # 3. ثبات سرعت
        if len(metrics.speed_history) > 5:
            recent_speeds = metrics.speed_history[-5:]
            cv = statistics.stdev(recent_speeds) / statistics.mean(recent_speeds) \
                 if statistics.mean(recent_speeds) > 0 else 1
            stability = max(0, 1 - cv)
            factors.append(stability * 0.3)
        
        return min(1.0, max(0.0, sum(factors)))
    
    def _generate_scenarios(self, metrics: TransferMetrics, base_remaining: float) -> Dict:
        """تولید سناریوهای مختلف"""
        if not metrics.speed_history:
            return {}
        
        recent_speeds = metrics.speed_history[-10:] if len(metrics.speed_history) >= 10 else metrics.speed_history
        avg_speed = statistics.mean(recent_speeds)
        min_speed = min(recent_speeds)
        max_speed = max(recent_speeds)
        
        remaining = metrics.total - metrics.transferred
        
        return {
            'worst_case': remaining / min_speed if min_speed > 0 else float('inf'),
            'likely_case': base_remaining,
            'best_case': remaining / max_speed if max_speed > 0 else float('inf'),
            'average_case': remaining / avg_speed if avg_speed > 0 else float('inf')
        }
    
    def _predict_future_speeds(self, metrics: TransferMetrics, steps: int = 10) -> List[float]:
        """پیش‌بینی سرعت‌های آینده"""
        if len(metrics.speed_history) < 5:
            return [metrics.speed] * steps
        
        # میانگین متحرک
        window_size = min(5, len(metrics.speed_history))
        last_speeds = metrics.speed_history[-window_size:]
        
        # پیش‌بینی ساده: میانگین اخیر
        avg_speed = statistics.mean(last_speeds)
        
        # کمی تغییر برای واقعی‌تر شدن
        return [avg_speed * (0.9 + 0.2 * random.random()) for _ in range(steps)]

# ================ MultiFileProgress ================

class MultiFileProgress:
    """مدیریت پیشرفت چندین فایل همزمان"""
    
    def __init__(self, ui: ProgressUI):
        self.ui = ui
        self.files: Dict[str, Dict] = {}
        self.overall_metrics = TransferMetrics()
        self.current_file_id: Optional[str] = None
        self.start_time = time.time()
        self.completion_order = []
    
    def add_file(self, file_id: str, filename: str, size: int, 
                priority: int = 1, metadata: Optional[Dict] = None):
        """افزودن فایل جدید"""
        self.files[file_id] = {
            'id': file_id,
            'name': filename,
            'size': size,
            'transferred': 0,
            'priority': priority,
            'status': TransferStatus.PENDING,
            'metrics': TransferMetrics(total=size),
            'metadata': metadata or {},
            'added_time': time.time(),
            'start_time': None,
            'end_time': None,
            'error': None
        }
        
        self.overall_metrics.total += size
    
    def update_file_progress(self, file_id: str, transferred: int, 
                           speed: Optional[float] = None):
        """بروزرسانی پیشرفت فایل"""
        if file_id not in self.files:
            return
        
        file = self.files[file_id]
        old_transferred = file['transferred']
        
        # بروزرسانی فایل
        file['transferred'] = transferred
        file['metrics'].transferred = transferred
        
        if speed is not None:
            file['metrics'].speed = speed
            file['metrics'].speed_history.append(speed)
        
        # بروزرسانی کلی
        delta = transferred - old_transferred
        self.overall_metrics.transferred += delta
        
        # بروزرسانی زمان
        if file['status'] == TransferStatus.PENDING:
            file['status'] = TransferStatus.TRANSFERRING
            file['start_time'] = time.time()
        
        file['metrics'].elapsed = time.time() - (file['start_time'] or time.time())
        
        # بررسی تکمیل
        if transferred >= file['size']:
            self._complete_file(file_id)
    
    def _complete_file(self, file_id: str):
        """علامت‌گذاری فایل به عنوان تکمیل شده"""
        file = self.files[file_id]
        file['status'] = TransferStatus.COMPLETED
        file['end_time'] = time.time()
        file['metrics'].end_time = file['end_time']
        
        self.completion_order.append(file_id)
        
        # بروزرسانی آمار کلی
        self.overall_metrics.completed_files = len([f for f in self.files.values() 
                                                  if f['status'] == TransferStatus.COMPLETED])
    
    def create_dashboard(self, show_details: bool = True) -> str:
        """ایجاد داشبورد مدیریت چند فایل"""
        lines = []
        
        # هدر
        lines.append(f"{self.ui.COLORS['bold']}📁 داشبورد انتقال چند فایلی{self.ui.COLORS['reset']}")
        lines.append("═" * 50)
        
        # آمار کلی
        total_files = len(self.files)
        completed = len([f for f in self.files.values() 
                        if f['status'] == TransferStatus.COMPLETED])
        transferring = len([f for f in self.files.values() 
                           if f['status'] == TransferStatus.TRANSFERRING])
        failed = len([f for f in self.files.values() 
                     if f['status'] == TransferStatus.FAILED])
        
        overall_percent = (self.overall_metrics.transferred / 
                          self.overall_metrics.total * 100) if self.overall_metrics.total > 0 else 0
        
        lines.append(f"📊 وضعیت کلی: {completed}/{total_files} فایل تکمیل شده")
        lines.append(f"   ├─ 🔄 در حال انتقال: {transferring}")
        lines.append(f"   ├─ ❌ ناموفق: {failed}")
        lines.append(f"   └─ ⏳ منتظر: {total_files - completed - transferring - failed}")
        lines.append("")
        
        # Progress bar کلی
        overall_bar = self.ui.create_progress_bar(overall_percent, 40)
        lines.append(f"📈 پیشرفت کلی: {overall_bar} {overall_percent:.1f}%")
        lines.append(f"   📦 حجم: {self.ui.format_size(self.overall_metrics.transferred)} / "
                    f"{self.ui.format_size(self.overall_metrics.total)}")
        lines.append("")
        
        if show_details:
            # لیست فایل‌ها
            lines.append(f"{self.ui.COLORS['dim']}فایل‌ها:{self.ui.COLORS['reset']}")
            
            for file_id, file in sorted(self.files.items(), 
                                       key=lambda x: x[1]['priority'], 
                                       reverse=True):
                status_icons = {
                    TransferStatus.PENDING: "⏳",
                    TransferStatus.TRANSFERRING: "🔄",
                    TransferStatus.COMPLETED: "✅",
                    TransferStatus.FAILED: "❌",
                    TransferStatus.PAUSED: "⏸️",
                    TransferStatus.CANCELLED: "🚫"
                }
                
                icon = status_icons.get(file['status'], "❓")
                percent = (file['transferred'] / file['size'] * 100) if file['size'] > 0 else 0
                
                # نمایش کوتاه
                name_display = file['name']
                if len(name_display) > 30:
                    name_display = name_display[:27] + "..."
                
                if file['status'] == TransferStatus.TRANSFERRING:
                    speed_fmt = self.ui.format_speed(file['metrics'].speed)
                    file_line = f"  {icon} {name_display:<30} {percent:5.1f}% ⚡{speed_fmt}"
                else:
                    file_line = f"  {icon} {name_display:<30} {percent:5.1f}%"
                
                lines.append(file_line)
        
        # زمان تخمینی باقیمانده
        if transferring > 0 and self.overall_metrics.speed > 0:
            remaining = self.overall_metrics.total - self.overall_metrics.transferred
            eta_seconds = remaining / self.overall_metrics.speed
            eta_time = datetime.now() + timedelta(seconds=eta_seconds)
            eta_str = eta_time.strftime("%H:%M:%S")
            
            lines.append("")
            lines.append(f"⏳ تخمین زمان تکمیل: حدود {self.ui.format_time(eta_seconds)} "
                        f"(ساعت {eta_str})")
        
        return "\n".join(lines)
    
    def get_file_stats(self) -> Dict:
        """دریافت آمار فایل‌ها"""
        stats = {
            'total_files': len(self.files),
            'completed': 0,
            'transferring': 0,
            'failed': 0,
            'pending': 0,
            'total_size': self.overall_metrics.total,
            'transferred_size': self.overall_metrics.transferred,
            'average_speed': 0,
            'start_time': self.start_time,
            'current_time': time.time()
        }
        
        speeds = []
        for file in self.files.values():
            if file['status'] == TransferStatus.COMPLETED:
                stats['completed'] += 1
            elif file['status'] == TransferStatus.TRANSFERRING:
                stats['transferring'] += 1
                speeds.append(file['metrics'].speed)
            elif file['status'] == TransferStatus.FAILED:
                stats['failed'] += 1
            elif file['status'] == TransferStatus.PENDING:
                stats['pending'] += 1
        
        if speeds:
            stats['average_speed'] = statistics.mean(speeds)
        
        return stats

# ================ AdaptiveTransferOptimizer ================

class AdaptiveTransferOptimizer:
    """بهینه‌سازی انتقال بر اساس شرایط شبکه"""
    
    def __init__(self):
        self.chunk_sizes = {
            'poor': 4 * 1024,           # 4KB
            'fair': 16 * 1024,          # 16KB
            'good': 64 * 1024,          # 64KB
            'excellent': 256 * 1024,    # 256KB
            'perfect': 1024 * 1024      # 1MB
        }
        
        self.current_chunk_size = self.chunk_sizes['good']
        self.network_quality_history: List[NetworkQuality] = []
        self.optimization_history = []
        self.last_optimization_time = time.time()
        self.optimization_interval = 5  # ثانیه
        
    def analyze_network(self, speed_history: List[float], 
                       latency_samples: List[float],
                       error_rate: float = 0.0) -> Dict:
        """آنالیز کیفیت شبکه"""
        
        if not speed_history:
            return self._get_default_optimization()
        
        # محاسبه متریک‌های شبکه
        recent_speeds = speed_history[-10:] if len(speed_history) >= 10 else speed_history
        
        avg_speed = statistics.mean(recent_speeds) if recent_speeds else 0
        speed_stability = self._calculate_stability(recent_speeds)
        
        avg_latency = statistics.mean(latency_samples) if latency_samples else 100
        latency_stability = self._calculate_stability(latency_samples) if latency_samples else 1
        
        # محاسبه امتیاز کیفیت (0-100)
        quality_score = self._calculate_quality_score(
            avg_speed, speed_stability, avg_latency, latency_stability, error_rate
        )
        
        # تعیین کیفیت شبکه
        if quality_score >= 90:
            quality = NetworkQuality.EXCELLENT
            recommendation = "استفاده از حداکثر chunk size و موازی‌سازی"
        elif quality_score >= 70:
            quality = NetworkQuality.GOOD
            recommendation = "استفاده از compression متوسط و chunk size بالا"
        elif quality_score >= 50:
            quality = NetworkQuality.FAIR
            recommendation = "تنظیمات متعادل"
        elif quality_score >= 30:
            quality = NetworkQuality.POOR
            recommendation = "کاهش chunk size و غیرفعال کردن compression"
        else:
            quality = NetworkQuality.UNSTABLE
            recommendation = "استفاده از chunk size کوچک و retry متعدد"
        
        # ذخیره تاریخچه
        self.network_quality_history.append(quality)
        if len(self.network_quality_history) > 20:
            self.network_quality_history.pop(0)
        
        # تنظیم chunk size
        self.current_chunk_size = self._determine_optimal_chunk_size(
            quality, avg_speed, speed_stability
        )
        
        # تولید تنظیمات بهینه
        optimization = {
            'network_quality': quality,
            'quality_score': quality_score,
            'optimal_chunk_size': self.current_chunk_size,
            'recommendation': recommendation,
            'compression_level': self._determine_compression_level(quality_score),
            'parallel_connections': self._determine_parallel_connections(quality_score),
            'retry_count': self._determine_retry_count(error_rate),
            'timeout': self._determine_timeout(avg_latency),
            'buffer_size': self._determine_buffer_size(avg_speed),
            'metrics': {
                'average_speed': avg_speed,
                'speed_stability': speed_stability,
                'average_latency': avg_latency,
                'latency_stability': latency_stability,
                'error_rate': error_rate
            }
        }
        
        # ذخیره برای تحلیل
        if time.time() - self.last_optimization_time >= self.optimization_interval:
            self.optimization_history.append({
                'timestamp': time.time(),
                **optimization
            })
            self.last_optimization_time = time.time()
            
            # محدود کردن تاریخچه
            if len(self.optimization_history) > 100:
                self.optimization_history.pop(0)
        
        return optimization
    
    def _calculate_quality_score(self, avg_speed: float, speed_stability: float,
                               avg_latency: float, latency_stability: float,
                               error_rate: float) -> float:
        """محاسبه امتیاز کیفیت شبکه"""
        
        # نرمال‌سازی سرعت (0-40 امتیاز)
        speed_score = min(40, (avg_speed / (1024 * 1024)) * 20)  # 2MB/s = 40 امتیاز
        
        # پایداری سرعت (0-20 امتیاز)
        stability_score = speed_stability * 20
        
        # تأخیر (0-25 امتیاز)
        latency_score = max(0, 25 - (avg_latency / 100))  # هر 100ms یک امتیاز کم
        
        # پایداری تأخیر (0-15 امتیاز)
        latency_stability_score = (1 - min(1, latency_stability)) * 15
        
        # نرخ خطا (کسورات)
        error_penalty = error_rate * 100
        
        total = speed_score + stability_score + latency_score + latency_stability_score - error_penalty
        
        return max(0, min(100, total))
    
    def _calculate_stability(self, values: List[float]) -> float:
        """محاسبه پایداری (ضریب تغییرات معکوس)"""
        if len(values) < 2:
            return 1.0
        
        mean_val = statistics.mean(values)
        if mean_val == 0:
            return 0.0
        
        std_dev = statistics.stdev(values)
        cv = std_dev / mean_val
        
        # تبدیل به پایداری (1=کاملاً پایدار، 0=کاملاً ناپایدار)
        return 1 / (1 + cv)
    
    def _determine_optimal_chunk_size(self, quality: NetworkQuality, 
                                    avg_speed: float, stability: float) -> int:
        """تعیین اندازه chunk بهینه"""
        
        base_size = self.chunk_sizes[quality.value]
        
        # تنظیم بر اساس سرعت
        if avg_speed > 10 * 1024 * 1024:  # بیش از 10MB/s
            size_multiplier = 2.0
        elif avg_speed > 5 * 1024 * 1024:  # بیش از 5MB/s
            size_multiplier = 1.5
        elif avg_speed > 1 * 1024 * 1024:  # بیش از 1MB/s
            size_multiplier = 1.2
        else:
            size_multiplier = 1.0
        
        # تنظیم بر اساس پایداری
        stability_multiplier = 0.5 + stability  # 0.5-1.5
        
        final_size = int(base_size * size_multiplier * stability_multiplier)
        
        # محدودیت‌ها
        min_size = 1024  # 1KB
        max_size = 4 * 1024 * 1024  # 4MB
        
        return max(min_size, min(max_size, final_size))
    
    def _determine_compression_level(self, quality_score: float) -> int:
        """تعیین سطح فشرده‌سازی"""
        if quality_score < 30:
            return 0  # بدون فشرده‌سازی
        elif quality_score < 60:
            return 1  # فشرده‌سازی کم
        elif quality_score < 80:
            return 3  # فشرده‌سازی متوسط
        else:
            return 6  # فشرده‌سازی بالا
    
    def _determine_parallel_connections(self, quality_score: float) -> int:
        """تعیین تعداد اتصالات موازی"""
        if quality_score < 20:
            return 1
        elif quality_score < 50:
            return 2
        elif quality_score < 70:
            return 3
        elif quality_score < 85:
            return 4
        else:
            return 5
    
    def _determine_retry_count(self, error_rate: float) -> int:
        """تعیین تعداد تلاش مجدد"""
        if error_rate > 0.1:  # بیش از 10% خطا
            return 5
        elif error_rate > 0.05:  # بیش از 5% خطا
            return 3
        elif error_rate > 0.01:  # بیش از 1% خطا
            return 2
        else:
            return 1
    
    def _determine_timeout(self, avg_latency: float) -> float:
        """تعیین زمان تایم‌اوت"""
        return max(10, avg_latency * 10)  # حداقل 10 ثانیه
    
    def _determine_buffer_size(self, avg_speed: float) -> int:
        """تعیین اندازه بافر"""
        # بافر برای 100ms از داده
        buffer_for_100ms = int(avg_speed * 0.1)
        
        # محدودیت‌ها
        min_buffer = 4 * 1024  # 4KB
        max_buffer = 16 * 1024 * 1024  # 16MB
        
        return max(min_buffer, min(max_buffer, buffer_for_100ms))
    
    def _get_default_optimization(self) -> Dict:
        """دریافت تنظیمات پیش‌فرض"""
        return {
            'network_quality': NetworkQuality.FAIR,
            'quality_score': 50,
            'optimal_chunk_size': self.chunk_sizes['good'],
            'recommendation': "استفاده از تنظیمات پیش‌فرض",
            'compression_level': 2,
            'parallel_connections': 2,
            'retry_count': 3,
            'timeout': 30,
            'buffer_size': 64 * 1024,
            'metrics': {
                'average_speed': 0,
                'speed_stability': 0,
                'average_latency': 100,
                'latency_stability': 0,
                'error_rate': 0
            }
        }
    
    def generate_optimization_report(self, optimization: Dict) -> str:
        """تولید گزارش بهینه‌سازی"""
        quality_emojis = {
            NetworkQuality.EXCELLENT: "🚀",
            NetworkQuality.GOOD: "👍",
            NetworkQuality.FAIR: "📶",
            NetworkQuality.POOR: "🐌",
            NetworkQuality.UNSTABLE: "🌪️"
        }
        
        emoji = quality_emojis.get(optimization['network_quality'], "❓")
        
        lines = []
        lines.append(f"{emoji} {ProgressUI.COLORS['bold']}گزارش بهینه‌سازی شبکه{ProgressUI.COLORS['reset']}")
        lines.append("=" * 50)
        
        lines.append(f"📊 کیفیت شبکه: {optimization['network_quality'].value} "
                    f"({optimization['quality_score']:.1f}/100)")
        
        lines.append(f"🔧 تنظیمات بهینه:")
        lines.append(f"  ├─ Chunk Size: {ProgressUI.format_size(optimization['optimal_chunk_size'])}")
        lines.append(f"  ├─ Compression: Level {optimization['compression_level']}")
        lines.append(f"  ├─ اتصالات موازی: {optimization['parallel_connections']}")
        lines.append(f"  ├─ تلاش مجدد: {optimization['retry_count']}")
        lines.append(f"  ├─ Timeout: {optimization['timeout']} ثانیه")
        lines.append(f"  └─ Buffer: {ProgressUI.format_size(optimization['buffer_size'])}")
        
        lines.append("")
        lines.append(f"💡 پیشنهاد: {optimization['recommendation']}")
        
        return "\n".join(lines)

# ================ RealTimeAnalytics ================

class RealTimeAnalytics:
    """آنالیز لحظه‌ای و گزارش‌گیری"""
    
    def __init__(self):
        self.metrics_buffer: List[Dict] = []
        self.alerts: List[Dict] = []
        self.anomalies: List[Dict] = []
        self.max_buffer_size = 1000
        self.alert_rules = self._get_default_alert_rules()
    
    def track_metric(self, name: str, value: float, 
                    tags: Optional[Dict] = None, timestamp: Optional[float] = None):
        """ردیابی متریک"""
        metric = {
            'timestamp': timestamp or time.time(),
            'name': name,
            'value': value,
            'tags': tags or {}
        }
        
        self.metrics_buffer.append(metric)
        
        # بررسی آلرت
        self._check_alerts(metric)
        
        # بررسی ناهنجاری
        if self._is_anomaly(metric):
            self.anomalies.append({
                **metric,
                'detected_at': time.time(),
                'severity': self._calculate_anomaly_severity(metric)
            })
        
        # محدود کردن اندازه بافر
        if len(self.metrics_buffer) > self.max_buffer_size:
            self.metrics_buffer = self.metrics_buffer[-self.max_buffer_size:]
    
    def _check_alerts(self, metric: Dict):
        """بررسی قوانین آلرت"""
        for rule in self.alert_rules:
            if rule['metric'] == metric['name']:
                if rule['condition'](metric['value']):
                    alert = {
                        'id': f"alert_{len(self.alerts)}_{int(time.time())}",
                        'metric': metric['name'],
                        'value': metric['value'],
                        'threshold': rule['threshold'],
                        'message': rule['message'],
                        'severity': rule['severity'],
                        'timestamp': metric['timestamp'],
                        'triggered_at': time.time()
                    }
                    
                    # جلوگیری از آلرت‌های تکراری
                    if not self._is_duplicate_alert(alert):
                        self.alerts.append(alert)
    
    def _is_anomaly(self, metric: Dict) -> bool:
        """تشخیص ناهنجاری"""
        # فقط برای متریک‌های سرعت
        if metric['name'] != 'transfer_speed':
            return False
        
        # نیاز به حداقل داده
        if len(self.metrics_buffer) < 20:
            return False
        
        # گرفتن تاریخچه
        speed_history = [m['value'] for m in self.metrics_buffer 
                        if m['name'] == 'transfer_speed']
        
        if len(speed_history) < 10:
            return False
        
        # تشخیص با Z-score
        recent_speeds = speed_history[-10:]
        mean_speed = statistics.mean(recent_speeds[:-1])
        std_speed = statistics.stdev(recent_speeds[:-1]) if len(recent_speeds) > 2 else 0
        
        if std_speed == 0:
            return False
        
        z_score = abs(recent_speeds[-1] - mean_speed) / std_speed
        
        # اگر Z-score بیشتر از 3 باشد (خارج از 3 انحراف معیار)
        return z_score > 3.0
    
    def generate_performance_report(self, window_minutes: int = 5) -> Dict:
        """تولید گزارش عملکرد"""
        window_start = time.time() - (window_minutes * 60)
        
        # فیلتر متریک‌های پنجره زمانی
        recent_metrics = [
            m for m in self.metrics_buffer 
            if m['timestamp'] >= window_start
        ]
        
        # گروه‌بندی متریک‌ها
        metrics_by_name = {}
        for metric in recent_metrics:
            if metric['name'] not in metrics_by_name:
                metrics_by_name[metric['name']] = []
            metrics_by_name[metric['name']].append(metric['value'])
        
        # تحلیل‌های مختلف
        analyses = {}
        
        for name, values in metrics_by_name.items():
            if not values:
                continue
            
            analyses[name] = {
                'count': len(values),
                'min': min(values),
                'max': max(values),
                'mean': statistics.mean(values),
                'median': statistics.median(values),
                'std_dev': statistics.stdev(values) if len(values) > 1 else 0,
                'trend': self._calculate_trend(values),
                'percentiles': {
                    '25': np.percentile(values, 25) if values else 0,
                    '50': np.percentile(values, 50) if values else 0,
                    '75': np.percentile(values, 75) if values else 0,
                    '95': np.percentile(values, 95) if values else 0
                }
            }
        
        # شناسایی bottlenecks
        bottlenecks = self._detect_bottlenecks(analyses)
        
        # محاسبه کارایی
        efficiency = self._calculate_efficiency(analyses)
        
        # تولید توصیه‌ها
        recommendations = self._generate_recommendations(analyses, bottlenecks)
        
        return {
            'time_window': f"{window_minutes} دقیقه",
            'metric_count': len(recent_metrics),
            'unique_metrics': len(metrics_by_name),
            'analyses': analyses,
            'bottlenecks': bottlenecks,
            'efficiency_score': efficiency['score'],
            'efficiency_rating': efficiency['rating'],
            'recommendations': recommendations,
            'alerts': self.alerts[-10:],  # آخرین 10 آلرت
            'anomalies': self.anomalies[-5:],  # آخرین 5 ناهنجاری
            'summary_stats': {
                'start_time': window_start,
                'end_time': time.time(),
                'duration_minutes': window_minutes
            }
        }
    
    def _get_default_alert_rules(self) -> List[Dict]:
        """قوانین پیش‌فرض آلرت"""
        return [
            {
                'metric': 'transfer_speed',
                'condition': lambda x: x < 1024,  # کمتر از 1KB/s
                'threshold': 1024,
                'message': 'سرعت انتقال بسیار پایین است',
                'severity': 'warning'
            },
            {
                'metric': 'transfer_speed',
                'condition': lambda x: x == 0,
                'threshold': 0,
                'message': 'انتقال متوقف شده است',
                'severity': 'critical'
            },
            {
                'metric': 'error_rate',
                'condition': lambda x: x > 0.1,  # بیش از 10% خطا
                'threshold': 0.1,
                'message': 'نرخ خطا بسیار بالا است',
                'severity': 'error'
            },
            {
                'metric': 'latency',
                'condition': lambda x: x > 5000,  # بیش از 5 ثانیه
                'threshold': 5000,
                'message': 'تأخیر شبکه بسیار بالا است',
                'severity': 'warning'
            }
        ]
    
    def _is_duplicate_alert(self, alert: Dict, cooldown: int = 60) -> bool:
        """بررسی تکراری بودن آلرت"""
        for existing_alert in self.alerts[-10:]:  # بررسی آخرین 10 آلرت
            if (existing_alert['metric'] == alert['metric'] and
                existing_alert['severity'] == alert['severity'] and
                alert['timestamp'] - existing_alert['timestamp'] < cooldown):
                return True
        return False
    
    def _calculate_trend(self, values: List[float]) -> str:
        """محاسبه روند"""
        if len(values) < 2:
            return "ثابت"
        
        # رگرسیون خطی ساده
        x = np.arange(len(values))
        y = np.array(values)
        
        try:
            slope = np.polyfit(x, y, 1)[0]
            
            if slope > 0.01:
                return "صعودی"
            elif slope < -0.01:
                return "نزولی"
            else:
                return "ثابت"
        except:
            return "نامشخص"
    
    def _detect_bottlenecks(self, analyses: Dict) -> List[Dict]:
        """شناسایی bottlenecks"""
        bottlenecks = []
        
        # بررسی سرعت شبکه
        if 'transfer_speed' in analyses:
            speed_analysis = analyses['transfer_speed']
            if speed_analysis['mean'] < 100 * 1024:  # کمتر از 100KB/s
                bottlenecks.append({
                    'type': 'network_speed',
                    'severity': 'high',
                    'metric': 'transfer_speed',
                    'current_value': speed_analysis['mean'],
                    'recommended_min': 1024 * 1024,  # 1MB/s
                    'description': 'سرعت شبکه بسیار پایین است'
                })
        
        # بررسی تأخیر
        if 'latency' in analyses:
            latency_analysis = analyses['latency']
            if latency_analysis['mean'] > 1000:  # بیش از 1 ثانیه
                bottlenecks.append({
                    'type': 'high_latency',
                    'severity': 'medium',
                    'metric': 'latency',
                    'current_value': latency_analysis['mean'],
                    'recommended_max': 100,
                    'description': 'تأخیر شبکه بسیار بالا است'
                })
        
        # بررسی نرخ خطا
        if 'error_rate' in analyses:
            error_analysis = analyses['error_rate']
            if error_analysis['mean'] > 0.05:  # بیش از 5% خطا
                bottlenecks.append({
                    'type': 'high_error_rate',
                    'severity': 'high',
                    'metric': 'error_rate',
                    'current_value': error_analysis['mean'],
                    'recommended_max': 0.01,
                    'description': 'نرخ خطا بسیار بالا است'
                })
        
        return bottlenecks
    
    def _calculate_efficiency(self, analyses: Dict) -> Dict:
        """محاسبه کارایی"""
        score = 50  # نمره پایه
        
        factors = []
        
        # عامل سرعت
        if 'transfer_speed' in analyses:
            speed = analyses['transfer_speed']['mean']
            speed_score = min(100, (speed / (5 * 1024 * 1024)) * 100)  # 5MB/s = 100
            factors.append(('speed', speed_score, 0.4))
        
        # عامل پایداری
        if 'transfer_speed' in analyses:
            stability = 1 - min(1, analyses['transfer_speed']['std_dev'] / 
                              max(1, analyses['transfer_speed']['mean']))
            stability_score = stability * 100
            factors.append(('stability', stability_score, 0.3))
        
        # عامل خطا
        if 'error_rate' in analyses:
            error_rate = analyses['error_rate']['mean']
            error_score = max(0, 100 - (error_rate * 1000))
            factors.append(('error', error_score, 0.2))
        
        # عامل تأخیر
        if 'latency' in analyses:
            latency = analyses['latency']['mean']
            latency_score = max(0, 100 - (latency / 10))
            factors.append(('latency', latency_score, 0.1))
        
        # محاسبه نمره نهایی
        if factors:
            weighted_sum = sum(score * weight for _, score, weight in factors)
            total_weight = sum(weight for _, _, weight in factors)
            score = weighted_sum / total_weight if total_weight > 0 else 50
        
        # تعیین رتبه
        if score >= 90:
            rating = "عالی"
        elif score >= 70:
            rating = "خوب"
        elif score >= 50:
            rating = "متوسط"
        elif score >= 30:
            rating = "ضعیف"
        else:
            rating = "بسیار ضعیف"
        
        return {
            'score': score,
            'rating': rating,
            'factors': [{'name': name, 'score': s, 'weight': w} 
                       for name, s, w in factors]
        }
    
    def _generate_recommendations(self, analyses: Dict, bottlenecks: List[Dict]) -> List[str]:
        """تولید توصیه‌ها"""
        recommendations = []
        
        for bottleneck in bottlenecks:
            if bottleneck['type'] == 'network_speed':
                recommendations.append(
                    "برای بهبود سرعت شبکه:\n"
                    "  • از اتصال کابلی به جای Wi-Fi استفاده کنید\n"
                    "  • سایر برنامه‌های در حال دانلود را متوقف کنید\n"
                    "  • سرویس اینترنت خود را ارتقا دهید"
                )
            elif bottleneck['type'] == 'high_latency':
                recommendations.append(
                    "برای کاهش تأخیر شبکه:\n"
                    "  • به سرور نزدیک‌تری متصل شوید\n"
                    "  • از VPN استفاده نکنید\n"
                    "  • فایروال و آنتی‌ویروس را بررسی کنید"
                )
            elif bottleneck['type'] == 'high_error_rate':
                recommendations.append(
                    "برای کاهش خطاها:\n"
                    "  • اتصال شبکه خود را بررسی کنید\n"
                    "  • تنظیمات retry را افزایش دهید\n"
                    "  • از اتصال پایدارتری استفاده کنید"
                )
        
        # توصیه‌های عمومی
        if 'transfer_speed' in analyses:
            speed = analyses['transfer_speed']['mean']
            if speed < 1024 * 1024:  # کمتر از 1MB/s
                recommendations.append(
                    "پیشنهاد: از حالت فشرده‌سازی برای کاهش حجم داده استفاده کنید"
                )
        
        if len(recommendations) == 0:
            recommendations.append("عملکرد مطلوب است. تنظیمات فعلی را حفظ کنید.")
        
        return recommendations
    
    def create_analytics_dashboard(self, report: Dict) -> str:
        """ایجاد داشبورد آنالیتیکس"""
        lines = []
        ui = ProgressUI()
        
        lines.append(f"{ui.COLORS['bold']}📈 داشبورد آنالیتیکس لحظه‌ای{ui.COLORS['reset']}")
        lines.append("=" * 60)
        
        # خلاصه
        lines.append(f"📊 خلاصه عملکرد:")
        lines.append(f"  ├─ بازه زمانی: {report['time_window']}")
        lines.append(f"  ├─ تعداد متریک‌ها: {report['metric_count']}")
        lines.append(f"  ├─ متریک‌های منحصربفرد: {report['unique_metrics']}")
        lines.append(f"  └─ امتیاز کارایی: {report['efficiency_score']:.1f}/100 "
                    f"({report['efficiency_rating']})")
        lines.append("")
        
        # متریک‌های کلیدی
        if 'transfer_speed' in report['analyses']:
            speed_analysis = report['analyses']['transfer_speed']
            lines.append(f"⚡ سرعت انتقال:")
            lines.append(f"  ├─ میانگین: {ui.format_speed(speed_analysis['mean'])}")
            lines.append(f"  ├─ میانه: {ui.format_speed(speed_analysis['median'])}")
            lines.append(f"  ├─ محدوده: {ui.format_speed(speed_analysis['min'])} - "
                        f"{ui.format_speed(speed_analysis['max'])}")
            lines.append(f"  └─ روند: {speed_analysis['trend']}")
            lines.append("")
        
        # bottlenecks
        if report['bottlenecks']:
            lines.append(f"⚠ bottlenecks شناسایی شده:")
            for bottleneck in report['bottlenecks']:
                severity_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}.get(
                    bottleneck['severity'], '⚪'
                )
                lines.append(f"  {severity_icon} {bottleneck['description']}")
            lines.append("")
        
        # توصیه‌ها
        if report['recommendations']:
            lines.append(f"💡 توصیه‌ها:")
            for i, recommendation in enumerate(report['recommendations'][:3], 1):
                lines.append(f"  {i}. {recommendation}")
            lines.append("")
        
        # آلرت‌ها
        if report['alerts']:
            lines.append(f"🚨 آلرت‌های اخیر:")
            for alert in report['alerts'][-3:]:
                time_ago = ui.format_time(time.time() - alert['timestamp'])
                severity_icon = {'critical': '🔴', 'error': '🟠', 'warning': '🟡'}.get(
                    alert['severity'], '⚪'
                )
                lines.append(f"  {severity_icon} [{time_ago} پیش] {alert['message']}")
        
        return "\n".join(lines)

# ================ GamificationEngine ================

class GamificationEngine:
    """موتور بازی‌سازی برای تجربه کاربری بهتر"""
    
    def __init__(self):
        self.user_stats = {
            'level': 1,
            'xp': 0,
            'total_xp': 0,
            'total_transfers': 0,
            'total_data': 0,
            'achievements': [],
            'streak_days': 0,
            'last_activity': time.time(),
            'session_start': time.time()
        }
        
        self.achievements_db = self._load_achievements()
        self.levels_db = self._load_levels()
        
    def _load_achievements(self) -> List[Dict]:
        """بارگذاری دستاوردها"""
        return [
            {
                'id': 'speed_demon',
                'name': 'شیطان سرعت 🚀',
                'description': 'رسیدن به سرعت بیش از 50MB/s',
                'condition': lambda stats: stats.get('max_speed', 0) > 50 * 1024 * 1024,
                'xp_reward': 100,
                'icon': '🚀'
            },
            {
                'id': 'marathon',
                'name': 'ماراتن انتقال 📁',
                'description': 'انتقال بیش از 100 فایل',
                'condition': lambda stats: stats.get('total_transfers', 0) >= 100,
                'xp_reward': 150,
                'icon': '📁'
            },
            {
                'id': 'data_hoarder',
                'name': 'ذخیره‌ساز داده 💾',
                'description': 'انتقال بیش از 1TB داده',
                'condition': lambda stats: stats.get('total_data', 0) >= 1024 ** 4,
                'xp_reward': 500,
                'icon': '💾'
            },
            {
                'id': 'perfectionist',
                'name': 'کمال‌گرا ⭐',
                'description': 'اتمام انتقال با 0 خطا',
                'condition': lambda stats: stats.get('error_count', 0) == 0,
                'xp_reward': 50,
                'icon': '⭐'
            },
            {
                'id': 'night_owl',
                'name': 'جغد شب 🦉',
                'description': 'اتمام انتقال بین ساعت 12 شب تا 5 صبح',
                'condition': lambda stats: stats.get('completed_at_hour', 0) in [0, 1, 2, 3, 4],
                'xp_reward': 75,
                'icon': '🦉'
            },
            {
                'id': 'weekend_warrior',
                'name': 'جنگجوی آخر هفته 🎯',
                'description': 'اتمام 10 انتقال در یک روز آخر هفته',
                'condition': lambda stats: stats.get('weekend_transfers', 0) >= 10,
                'xp_reward': 200,
                'icon': '🎯'
            },
            {
                'id': 'early_bird',
                'name': 'سحرخیز 🌅',
                'description': 'آغاز انتقال قبل از ساعت 7 صبح',
                'condition': lambda stats: stats.get('started_at_hour', 0) < 7,
                'xp_reward': 60,
                'icon': '🌅'
            },
            {
                'id': 'consistent',
                'name': 'منظم 📅',
                'description': '7 روز متوالی فعالیت',
                'condition': lambda stats: stats.get('streak_days', 0) >= 7,
                'xp_reward': 300,
                'icon': '📅'
            },
            {
                'id': 'speedster',
                'name': 'سرعت‌بخش ⚡',
                'description': '10 انتقال متوالی با سرعت بیش از 10MB/s',
                'condition': lambda stats: stats.get('high_speed_streak', 0) >= 10,
                'xp_reward': 250,
                'icon': '⚡'
            },
            {
                'id': 'efficient',
                'name': 'کارآمد ♻️',
                'description': 'کارایی بیش از 90% در 5 انتقال متوالی',
                'condition': lambda stats: stats.get('high_efficiency_streak', 0) >= 5,
                'xp_reward': 180,
                'icon': '♻️'
            }
        ]
    
    def _load_levels(self) -> List[Dict]:
        """بارگذاری سطوح"""
        return [
            {'level': 1, 'xp_required': 0, 'title': 'تازه‌کار'},
            {'level': 2, 'xp_required': 100, 'title': 'کارآموز'},
            {'level': 3, 'xp_required': 300, 'title': 'کاربر'},
            {'level': 4, 'xp_required': 600, 'title': 'حرفه‌ای'},
            {'level': 5, 'xp_required': 1000, 'title': 'متخصص'},
            {'level': 6, 'xp_required': 1500, 'title': 'استاد'},
            {'level': 7, 'xp_required': 2100, 'title': 'چیره‌دست'},
            {'level': 8, 'xp_required': 2800, 'title': 'اسطوره'},
            {'level': 9, 'xp_required': 3600, 'title': 'افسانه'},
            {'level': 10, 'xp_required': 4500, 'title': 'باورنکردنی'}
        ]
    
    def update_stats(self, transfer_data: Dict) -> Dict:
        """بروزرسانی آمار کاربر"""
        # بروزرسانی زمان آخرین فعالیت
        now = time.time()
        last_activity = self.user_stats['last_activity']
        
        # بررسی streak
        if now - last_activity > 48 * 3600:  # بیش از 48 ساعت
            self.user_stats['streak_days'] = 1
        elif now - last_activity > 24 * 3600:  # بیش از 24 ساعت
            self.user_stats['streak_days'] += 1
        
        self.user_stats['last_activity'] = now
        
        # بروزرسانی آمار پایه
        self.user_stats['total_transfers'] += 1
        self.user_stats['total_data'] += transfer_data.get('size', 0)
        
        # محاسبه XP
        xp_gained = self._calculate_xp(transfer_data)
        self.user_stats['xp'] += xp_gained
        self.user_stats['total_xp'] += xp_gained
        
        # بررسی دستاوردهای جدید
        new_achievements = []
        for achievement in self.achievements_db:
            if achievement['id'] not in self.user_stats['achievements']:
                if achievement['condition'](transfer_data):
                    self.user_stats['achievements'].append(achievement['id'])
                    self.user_stats['xp'] += achievement['xp_reward']
                    self.user_stats['total_xp'] += achievement['xp_reward']
                    
                    new_achievements.append({
                        'id': achievement['id'],
                        'name': achievement['name'],
                        'description': achievement['description'],
                        'xp_reward': achievement['xp_reward'],
                        'icon': achievement['icon']
                    })
        
        # بررسی ارتقا سطح
        old_level = self.user_stats['level']
        new_level = self._calculate_level(self.user_stats['xp'])
        
        level_up_message = None
        if new_level > old_level:
            self.user_stats['level'] = new_level
            level_up_message = self._create_level_up_message(old_level, new_level)
        
        return {
            'new_achievements': new_achievements,
            'xp_gained': xp_gained,
            'level_up': level_up_message,
            'current_level': new_level,
            'current_xp': self.user_stats['xp'],
            'xp_to_next_level': self._xp_to_next_level(new_level, self.user_stats['xp']),
            'total_achievements': len(self.user_stats['achievements'])
        }
    
    def _calculate_xp(self, transfer_data: Dict) -> int:
        """محاسبه XP کسب شده"""
        base_xp = 10
        
        # پاداش سرعت
        speed_bonus = min(50, transfer_data.get('avg_speed', 0) / (1024 * 1024))  # 1MB/s = 1 XP
        
        # پاداش حجم
        size_bonus = min(100, transfer_data.get('size', 0) / (100 * 1024 * 1024))  # 100MB = 1 XP
        
        # پاداش کارایی
        efficiency_bonus = 0
        if transfer_data.get('efficiency_score', 0) > 90:
            efficiency_bonus = 30
        elif transfer_data.get('efficiency_score', 0) > 70:
            efficiency_bonus = 15
        
        # جریمه خطا
        error_penalty = transfer_data.get('error_count', 0) * 5
        
        # پاداش streak
        streak_bonus = min(self.user_stats['streak_days'] * 2, 20)
        
        total_xp = base_xp + speed_bonus + size_bonus + efficiency_bonus + streak_bonus - error_penalty
        
        return max(1, int(total_xp))
    
    def _calculate_level(self, xp: int) -> int:
        """محاسبه سطح بر اساس XP"""
        for level_info in reversed(self.levels_db):
            if xp >= level_info['xp_required']:
                return level_info['level']
        return 1
    
    def _xp_to_next_level(self, current_level: int, current_xp: int) -> int:
        """XP مورد نیاز برای سطح بعدی"""
        if current_level >= len(self.levels_db):
            return 0
        
        next_level_xp = self.levels_db[current_level]['xp_required']
        return max(0, next_level_xp - current_xp)
    
    def _create_level_up_message(self, old_level: int, new_level: int) -> str:
        """ایجاد پیام ارتقا سطح"""
        old_title = self.levels_db[old_level - 1]['title']
        new_title = self.levels_db[new_level - 1]['title']
        
        celebrations = ['🎉', '🎊', '🥳', '🎈', '👑', '🏆', '⭐', '✨']
        celebration = random.choice(celebrations)
        
        return f"{celebration} تبریک! شما از سطح {old_level} ({old_title}) " \
               f"به سطح {new_level} ({new_title}) ارتقا یافتید! {celebration}"
    
    def create_profile_card(self) -> str:
        """ایجاد کارت پروفایل کاربر"""
        ui = ProgressUI()
        current_level_info = self.levels_db[self.user_stats['level'] - 1]
        next_level_info = self.levels_db[self.user_stats['level']] if \
                         self.user_stats['level'] < len(self.levels_db) else None
        
        # محاسبه پیشرفت سطح
        level_progress = 0
        if next_level_info:
            current_level_xp = current_level_info['xp_required']
            next_level_xp = next_level_info['xp_required']
            level_range = next_level_xp - current_level_xp
            xp_in_level = self.user_stats['xp'] - current_level_xp
            level_progress = (xp_in_level / level_range * 100) if level_range > 0 else 100
        
        lines = []
        lines.append(f"{ui.COLORS['bold']}🎮 پروفایل کاربری{ui.COLORS['reset']}")
        lines.append("=" * 40)
        
        # سطح و XP
        lines.append(f"📊 سطح: {self.user_stats['level']} - {current_level_info['title']}")
        
        if next_level_info:
            progress_bar = ui.create_progress_bar(level_progress, 20)
            lines.append(f"   {progress_bar} {level_progress:.1f}%")
            lines.append(f"   XP: {self.user_stats['xp']:,} / {next_level_info['xp_required']:,}")
        else:
            lines.append(f"   🏆 شما به حداکثر سطح رسیده‌اید!")
            lines.append(f"   XP کل: {self.user_stats['xp']:,}")
        
        lines.append("")
        
        # آمار کلی
        lines.append(f"📈 آمار کلی:")
        lines.append(f"   ├─ انتقال‌ها: {self.user_stats['total_transfers']:,}")
        lines.append(f"   ├─ حجم کل: {ui.format_size(self.user_stats['total_data'])}")
        lines.append(f"   ├─ دستاوردها: {len(self.user_stats['achievements'])}/{len(self.achievements_db)}")
        lines.append(f"   └─ روزهای متوالی: {self.user_stats['streak_days']}")
        
        lines.append("")
        
        # دستاوردهای اخیر
        if self.user_stats['achievements']:
            recent_achievements = self.user_stats['achievements'][-3:]
            lines.append(f"🏅 دستاوردهای اخیر:")
            for achievement_id in recent_achievements:
                achievement = next((a for a in self.achievements_db 
                                  if a['id'] == achievement_id), None)
                if achievement:
                    lines.append(f"   {achievement['icon']} {achievement['name']}")
        
        # جلسه فعلی
        session_duration = time.time() - self.user_stats['session_start']
        if session_duration > 60:
            lines.append("")
            lines.append(f"⏱️ زمان جلسه: {ui.format_time(session_duration)}")
        
        return "\n".join(lines)

# ================ External Integration ================

class ExternalIntegration:
    """یکپارچه‌سازی با سرویس‌های خارجی"""
    
    @staticmethod
    def export_to_prometheus(metrics: Dict, job_name: str = "file_transfer") -> str:
        """خروجی فرمت Prometheus"""
        prometheus_lines = []
        
        # HELP و TYPE
        prometheus_lines.append(f'# HELP transfer_speed_bytes File transfer speed in bytes per second')
        prometheus_lines.append(f'# TYPE transfer_speed_bytes gauge')
        prometheus_lines.append(f'transfer_speed_bytes{{job="{job_name}"}} {metrics.get("speed", 0)}')
        
        prometheus_lines.append(f'# HELP transfer_percent File transfer percentage')
        prometheus_lines.append(f'# TYPE transfer_percent gauge')
        prometheus_lines.append(f'transfer_percent{{job="{job_name}"}} {metrics.get("percent", 0)}')
        
        prometheus_lines.append(f'# HELP transfer_remaining_bytes Remaining bytes to transfer')
        prometheus_lines.append(f'# TYPE transfer_remaining_bytes gauge')
        remaining = metrics.get('total', 0) - metrics.get('transferred', 0)
        prometheus_lines.append(f'transfer_remaining_bytes{{job="{job_name}"}} {remaining}')
        
        prometheus_lines.append(f'# HELP transfer_elapsed_seconds Elapsed time in seconds')
        prometheus_lines.append(f'# TYPE transfer_elapsed_seconds gauge')
        prometheus_lines.append(f'transfer_elapsed_seconds{{job="{job_name}"}} {metrics.get("elapsed", 0)}')
        
        prometheus_lines.append(f'# HELP transfer_errors_total Total number of errors')
        prometheus_lines.append(f'# TYPE transfer_errors_total counter')
        prometheus_lines.append(f'transfer_errors_total{{job="{job_name}"}} {metrics.get("error_count", 0)}')
        
        return '\n'.join(prometheus_lines)
    
    @staticmethod
    def export_to_json(metrics: Dict, pretty: bool = True) -> str:
        """خروجی JSON"""
        export_data = {
            'timestamp': time.time(),
            'timestamp_iso': datetime.now().isoformat(),
            'metrics': {
                'transferred': metrics.get('transferred', 0),
                'total': metrics.get('total', 0),
                'percent': metrics.get('percent', 0),
                'speed': metrics.get('speed', 0),
                'elapsed': metrics.get('elapsed', 0),
                'remaining': metrics.get('remaining', 0),
                'error_count': metrics.get('error_count', 0)
            },
            'formatting': {
                'transferred_fmt': ProgressUI.format_size(metrics.get('transferred', 0)),
                'total_fmt': ProgressUI.format_size(metrics.get('total', 0)),
                'speed_fmt': ProgressUI.format_speed(metrics.get('speed', 0)),
                'elapsed_fmt': ProgressUI.format_time(metrics.get('elapsed', 0)),
                'remaining_fmt': ProgressUI.format_time(metrics.get('remaining', 0))
            },
            'metadata': {
                'version': '1.0.0',
                'exported_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
        if pretty:
            return json.dumps(export_data, indent=2, ensure_ascii=False)
        else:
            return json.dumps(export_data, ensure_ascii=False)
    
    @staticmethod
    def create_grafana_dashboard_config(metrics_list: List[str]) -> Dict:
        """ایجاد تنظیمات داشبورد Grafana"""
        panels = []
        
        # پنل سرعت
        if 'transfer_speed' in metrics_list:
            panels.append({
                'title': 'Transfer Speed',
                'type': 'graph',
                'gridPos': {'h': 8, 'w': 12, 'x': 0, 'y': 0},
                'targets': [
                    {
                        'expr': 'rate(transfer_speed_bytes[5m])',
                        'legendFormat': 'Speed',
                        'refId': 'A'
                    }
                ]
            })
        
        # پنل پیشرفت
        if 'transfer_percent' in metrics_list:
            panels.append({
                'title': 'Transfer Progress',
                'type': 'stat',
                'gridPos': {'h': 4, 'w': 6, 'x': 0, 'y': 8},
                'targets': [
                    {
                        'expr': 'transfer_percent',
                        'legendFormat': 'Progress',
                        'refId': 'A'
                    }
                ],
                'fieldConfig': {
                    'defaults': {
                        'unit': 'percent',
                        'min': 0,
                        'max': 100
                    }
                }
            })
        
        # پنل خطاها
        if 'transfer_errors' in metrics_list:
            panels.append({
                'title': 'Transfer Errors',
                'type': 'stat',
                'gridPos': {'h': 4, 'w': 6, 'x': 6, 'y': 8},
                'targets': [
                    {
                        'expr': 'increase(transfer_errors_total[5m])',
                        'legendFormat': 'Errors',
                        'refId': 'A'
                    }
                ],
                'fieldConfig': {
                    'defaults': {
                        'color': {'mode': 'thresholds'},
                        'thresholds': {
                            'steps': [
                                {'color': 'green', 'value': None},
                                {'color': 'red', 'value': 1}
                            ]
                        }
                    }
                }
            })
        
        return {
            'dashboard': {
                'title': 'File Transfer Monitor',
                'panels': panels,
                'time': {'from': 'now-1h', 'to': 'now'},
                'refresh': '5s'
            },
            'overwrite': True
        }
    
    @staticmethod
    def send_to_webhook(data: Dict, webhook_url: str, 
                       format: str = 'json') -> bool:
        """ارسال داده به وب‌هوک"""
        try:
            import requests
            
            headers = {'Content-Type': 'application/json'}
            
            if format == 'prometheus':
                payload = ExternalIntegration.export_to_prometheus(data)
                headers['Content-Type'] = 'text/plain'
            else:
                payload = ExternalIntegration.export_to_json(data, False)
            
            response = requests.post(webhook_url, data=payload, headers=headers, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            print(f"Error sending to webhook: {e}")
            return False

# ================ Advanced Visualization ================

class AdvancedVisualization:
    """ویژوال‌سازی پیشرفته با ASCII Art"""
    
    @staticmethod
    def create_speed_heatmap(speed_data: List[List[float]], 
                           width: int = 50, height: int = 10) -> str:
        """ایجاد هیت‌مپ سرعت"""
        if not speed_data or not speed_data[0]:
            return "🔥 (داده‌ای موجود نیست)"
        
        # محدود کردن عرض
        data_width = min(width, len(speed_data[0]))
        data = [row[:data_width] for row in speed_data[:height]]
        
        # پیدا کردن max کلی
        max_val = max(max(row) for row in data) if data else 1
        
        # کاراکترهای گرادیان
        gradient = " ░▒▓█"
        
        # ایجاد هیت‌مپ
        heatmap = []
        for row in data:
            heat_row = []
            for val in row:
                # نرمال‌سازی و انتخاب کاراکتر
                if max_val > 0:
                    level = int((val / max_val) * (len(gradient) - 1))
                    level = max(0, min(len(gradient) - 1, level))
                else:
                    level = 0
                heat_row.append(gradient[level])
            heatmap.append(''.join(heat_row))
        
        # اضافه کردن legend
        legend = f"↕️ 0 - {ProgressUI.format_speed(max_val)}"
        heatmap.append('─' * data_width)
        heatmap.append(legend)
        
        return '\n'.join(heatmap)
    
    @staticmethod
    def create_network_topology(nodes: List[Dict], connections: List[Tuple[str, str]]) -> str:
        """نمایش توپولوژی شبکه"""
        topology_lines = []
        
        topology_lines.append("🌐 **توپولوژی شبکه**")
        topology_lines.append("")
        
        # پیدا کردن ریشه (سرور اصلی)
        root_nodes = [node for node in nodes if node.get('type') == 'server']
        
        if root_nodes:
            root = root_nodes[0]
            topology_lines.append(f"    [{root['name']}]")
            topology_lines.append("        │")
        
        # نمایش اتصالات
        for i, (source, target) in enumerate(connections):
            if i == len(connections) - 1:
                prefix = "        └──"
            else:
                prefix = "        ├──"
            
            target_node = next((n for n in nodes if n['id'] == target), None)
            if target_node:
                topology_lines.append(f"{prefix} [{target_node['name']}]")
        
        # اضافه کردن آمار
        topology_lines.append("")
        topology_lines.append(f"📊 آمار:")
        topology_lines.append(f"  • گره‌ها: {len(nodes)}")
        topology_lines.append(f"  • اتصالات: {len(connections)}")
        
        return '\n'.join(topology_lines)
    
    @staticmethod
    def create_radial_progress(percent: float, radius: int = 5) -> str:
        """ایجاد پیشرفت شعاعی"""
        if percent < 0:
            percent = 0
        elif percent > 100:
            percent = 100
        
        # محاسبه زاویه
        angle = 360 * percent / 100
        
        # کاراکترهای دایره
        circle_chars = " .'`^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
        
        lines = []
        for y in range(-radius, radius + 1):
            line = []
            for x in range(-radius, radius + 1):
                # محاسبه فاصله از مرکز
                distance = math.sqrt(x * x + y * y)
                
                if distance <= radius:
                    # محاسبه زاویه
                    point_angle = math.degrees(math.atan2(y, x))
                    if point_angle < 0:
                        point_angle += 360
                    
                    # بررسی آیا نقطه داخل بخش پر شده است
                    if point_angle <= angle:
                        # انتخاب کاراکتر بر اساس فاصله
                        char_index = int((distance / radius) * (len(circle_chars) - 1))
                        line.append(circle_chars[char_index])
                    else:
                        line.append(' ')
                else:
                    line.append(' ')
            
            lines.append(''.join(line))
        
        # اضافه کردن درصد در مرکز
        center_line = lines[radius]
        percent_str = f"{percent:.0f}%"
        start = (len(center_line) - len(percent_str)) // 2
        lines[radius] = center_line[:start] + percent_str + center_line[start + len(percent_str):]
        
        return '\n'.join(lines)

# ================ Main Application ================

class ProgressManager:
    """مدیر اصلی پیشرفت"""
    
    def __init__(self, config: Optional[ProgressConfig] = None):
        self.ui = ProgressUI(config)
        self.ai_predictor = AIPredictionProgress(self.ui)
        self.multi_file = MultiFileProgress(self.ui)
        self.optimizer = AdaptiveTransferOptimizer()
        self.analytics = RealTimeAnalytics()
        self.gamification = GamificationEngine()
        self.visualization = AdvancedVisualization()
        
        self.current_transfer = None
        self.is_running = False
        self.last_display_time = 0
        self.display_interval = 0.1  # ثانیه
        
    def start_transfer(self, filename: str, size: int, 
                      transfer_type: str = "download") -> str:
        """شروع یک انتقال جدید"""
        transfer_id = hashlib.md5(f"{filename}{time.time()}".encode()).hexdigest()[:8]
        
        self.current_transfer = {
            'id': transfer_id,
            'filename': filename,
            'size': size,
            'type': transfer_type,
            'start_time': time.time(),
            'metrics': TransferMetrics(total=size),
            'status': TransferStatus.TRANSFERRING,
            'chunks': [],
            'optimization': None
        }
        
        # تحلیل شبکه اولیه
        self.current_transfer['optimization'] = self.optimizer.analyze_network(
            [], [], 0.0
        )
        
        # شروع آنالیتیکس
        self.analytics.track_metric('transfer_started', 1, {
            'filename': filename,
            'size': size,
            'type': transfer_type
        })
        
        self.is_running = True
        
        return transfer_id
    
    def update_transfer(self, transferred: int, speed: Optional[float] = None,
                       latency: Optional[float] = None, errors: int = 0):
        """بروزرسانی وضعیت انتقال"""
        if not self.current_transfer or not self.is_running:
            return
        
        metrics = self.current_transfer['metrics']
        
        # بروزرسانی متریک‌ها
        old_transferred = metrics.transferred
        metrics.transferred = transferred
        
        if speed is not None:
            metrics.speed = speed
            metrics.speed_history.append(speed)
        
        metrics.elapsed = time.time() - self.current_transfer['start_time']
        metrics.error_count = errors
        
        # محاسبه زمان باقیمانده
        if speed and speed > 0:
            remaining = (metrics.total - transferred) / speed
            metrics.remaining = remaining
        
        # ردیابی آنالیتیکس
        self.analytics.track_metric('transfer_speed', speed or 0)
        self.analytics.track_metric('transfer_progress', metrics.percent)
        
        if latency:
            self.analytics.track_metric('latency', latency)
        
        # بهینه‌سازی پویا (هر 5 ثانیه)
        current_time = time.time()
        if current_time - self.last_display_time > 5:
            self._optimize_transfer()
            self.last_display_time = current_time
        
        # نمایش پیشرفت (با محدودیت نرخ)
        if current_time - self.last_display_time >= self.display_interval:
            self.display_progress()
            self.last_display_time = current_time
        
        # بررسی تکمیل
        if transferred >= metrics.total:
            self.complete_transfer()
    
    def _optimize_transfer(self):
        """بهینه‌سازی انتقال"""
        if not self.current_transfer:
            return
        
        metrics = self.current_transfer['metrics']
        
        # تحلیل شبکه
        optimization = self.optimizer.analyze_network(
            metrics.speed_history[-20:] if len(metrics.speed_history) >= 20 else metrics.speed_history,
            [100],  # تأخیر نمونه
            metrics.error_count / max(1, len(metrics.speed_history))
        )
        
        self.current_transfer['optimization'] = optimization
        
        # ردیابی برای آنالیتیکس
        self.analytics.track_metric('network_quality', optimization['quality_score'])
        self.analytics.track_metric('chunk_size', optimization['optimal_chunk_size'])
    
    def display_progress(self, detailed: bool = True):
        """نمایش پیشرفت"""
        if not self.current_transfer:
            return
        
        metrics = self.current_transfer['metrics']
        
        if detailed:
            # نمایش با جزئیات
            progress_text = self.ui.create_detailed_progress(metrics, show_graph=True)
            
            # اضافه کردن پیش‌بینی هوشمند
            if len(metrics.speed_history) > 10:
                prediction = self.ai_predictor.predict_completion(metrics)
                
                if prediction['confidence'] > 0.5:
                    remaining_fmt = self.ui.format_time(prediction['remaining_time'])
                    confidence_pct = prediction['confidence'] * 100
                    
                    prediction_text = (
                        f"\n🤖 پیش‌بینی هوشمند (اعتماد: {confidence_pct:.0f}%):\n"
                        f"   ⏳ باقیمانده: {remaining_fmt}\n"
                        f"   📊 سناریوها:\n"
                        f"      • بهترین حالت: {self.ui.format_time(prediction['scenarios']['best_case'])}\n"
                        f"      • حالت محتمل: {self.ui.format_time(prediction['scenarios']['likely_case'])}\n"
                        f"      • بدترین حالت: {self.ui.format_time(prediction['scenarios']['worst_case'])}"
                    )
                    
                    progress_text += prediction_text
            
            # اضافه کردن بهینه‌سازی
            if self.current_transfer['optimization']:
                optimization_text = (
                    f"\n🔧 بهینه‌سازی شبکه:\n"
                    f"   Chunk Size: {self.ui.format_size(self.current_transfer['optimization']['optimal_chunk_size'])}\n"
                    f"   کیفیت: {self.current_transfer['optimization']['network_quality'].value} "
                    f"({self.current_transfer['optimization']['quality_score']:.1f}/100)"
                )
                
                progress_text += optimization_text
            
            print("\033[2J\033[H")  # پاک کردن ترمینال
            print(progress_text)
        else:
            # نمایش مینیاتوری
            mini_text = self.ui.create_mini_progress(metrics)
            print(f"\r{mini_text}", end="", flush=True)
    
    def complete_transfer(self):
        """تکمیل انتقال"""
        if not self.current_transfer:
            return
        
        metrics = self.current_transfer['metrics']
        metrics.end_time = time.time()
        self.current_transfer['status'] = TransferStatus.COMPLETED
        self.is_running = False
        
        # ایجاد خلاصه
        summary = self.ui.create_transfer_summary(
            metrics,
            self.current_transfer['type'],
            self.current_transfer['filename']
        )
        
        # گزارش آنالیتیکس
        report = self.analytics.generate_performance_report(5)
        analytics_dashboard = self.analytics.create_analytics_dashboard(report)
        
        # بروزرسانی گیمیفیکیشن
        transfer_data = {
            'size': metrics.total,
            'avg_speed': metrics.avg_speed,
            'max_speed': metrics.max_speed,
            'error_count': metrics.error_count,
            'efficiency_score': report.get('efficiency_score', 50),
            'completed_at_hour': datetime.now().hour
        }
        
        gamification_update = self.gamification.update_stats(transfer_data)
        profile_card = self.gamification.create_profile_card()
        
        # نمایش نتایج
        print("\033[2J\033[H")  # پاک کردن ترمینال
        print(summary)
        print("\n" + "="*60 + "\n")
        print(analytics_dashboard)
        print("\n" + "="*60 + "\n")
        print(profile_card)
        
        # نمایش دستاوردهای جدید
        if gamification_update['new_achievements']:
            print("\n🏆 دستاوردهای جدید:")
            for achievement in gamification_update['new_achievements']:
                print(f"   {achievement['icon']} {achievement['name']} (+{achievement['xp_reward']} XP)")
        
        if gamification_update['level_up']:
            print(f"\n{gamification_update['level_up']}")
        
        # ردیابی تکمیل
        self.analytics.track_metric('transfer_completed', 1, {
            'filename': self.current_transfer['filename'],
            'size': metrics.total,
            'duration': metrics.elapsed,
            'avg_speed': metrics.avg_speed
        })
    
    def add_multiple_files(self, files: List[Tuple[str, int]]):
        """افزودن چندین فایل"""
        for i, (filename, size) in enumerate(files):
            file_id = f"file_{i}_{int(time.time())}"
            self.multi_file.add_file(file_id, filename, size, priority=len(files)-i)
    
    def display_multi_file_dashboard(self):
        """نمایش داشبورد چند فایلی"""
        if not self.multi_file.files:
            print("هیچ فایلی برای نمایش وجود ندارد.")
            return
        
        dashboard = self.multi_file.create_dashboard(show_details=True)
        print("\033[2J\033[H")  # پاک کردن ترمینال
        print(dashboard)
        
        # اضافه کردن پیش‌بینی
        stats = self.multi_file.get_file_stats()
        if stats['average_speed'] > 0:
            remaining = stats['total_size'] - stats['transferred_size']
            eta_seconds = remaining / stats['average_speed']
            
            print(f"\n⏳ تخمین زمان تکمیل همه فایل‌ها: {self.ui.format_time(eta_seconds)}")

# ================ Example Usage ================

def example_usage():
    """نمونه استفاده از کتابخانه پیشرفته"""
    
    # ایجاد مدیر پیشرفت
    config = ProgressConfig(
        show_percentage=True,
        show_speed=True,
        show_time=True,
        show_graph=True,
        graph_width=40,
        graph_height=8,
        use_colors=True,
        show_eta=True,
        compact_mode=False
    )
    
    manager = ProgressManager(config)
    
    print("🚀 شروع انتقال پیشرفته")
    print("="*60)
    
    # شروع یک انتقال
    transfer_id = manager.start_transfer(
        filename="large_file.zip",
        size=500 * 1024 * 1024,  # 500MB
        transfer_type="download"
    )
    
    print(f"شناسه انتقال: {transfer_id}")
    print()
    
    # شبیه‌سازی انتقال
    import random
    
    transferred = 0
    total_size = 500 * 1024 * 1024
    
    while transferred < total_size:
        # شبیه‌سازی سرعت با نوسان
        base_speed = 5 * 1024 * 1024  # 5MB/s
        speed_variation = random.uniform(0.8, 1.2)
        current_speed = base_speed * speed_variation
        
        # شبیه‌سازی chunk
        chunk_size = min(10 * 1024 * 1024, total_size - transferred)  # حداکثر 10MB
        transferred += chunk_size
        
        # شبیه‌سازی تأخیر
        latency = random.uniform(50, 200)  # 50-200ms
        
        # بروزرسانی انتقال
        manager.update_transfer(
            transferred=transferred,
            speed=current_speed,
            latency=latency,
            errors=random.randint(0, 1) if random.random() < 0.05 else 0
        )
        
        # تأخیر برای شبیه‌سازی واقعی
        time.sleep(0.5)
    
    print("\n" + "="*60)
    print("✅ انتقال تکمیل شد!")
    
    # نمونه‌ای از چند فایل
    print("\n" + "="*60)
    print("📁 مدیریت چند فایل")
    
    manager.add_multiple_files([
        ("file1.txt", 1024 * 1024),      # 1MB
        ("file2.jpg", 5 * 1024 * 1024),  # 5MB
        ("file3.zip", 50 * 1024 * 1024), # 50MB
        ("file4.mp4", 200 * 1024 * 1024) # 200MB
    ])
    
    # بروزرسانی پیشرفت فایل‌ها
    for i, (file_id, file_data) in enumerate(manager.multi_file.files.items()):
        progress = min(100, (i + 1) * 25)  # 25% پیشرفت برای هر فایل
        transferred = int(file_data['size'] * progress / 100)
        manager.multi_file.update_file_progress(file_id, transferred, speed=1024*1024)
    
    manager.display_multi_file_dashboard()
    
    # نمونه‌ای از آنالیتیکس
    print("\n" + "="*60)
    print("📊 گزارش آنالیتیکس")
    
    report = manager.analytics.generate_performance_report(1)  # 1 دقیقه گذشته
    dashboard = manager.analytics.create_analytics_dashboard(report)
    print(dashboard)
    
    # نمونه‌ای از گیمیفیکیشن
    print("\n" + "="*60)
    print("🎮 گیمیفیکیشن")
    
    # چند انتقال شبیه‌سازی شده
    for i in range(5):
        transfer_data = {
            'size': random.randint(10, 100) * 1024 * 1024,
            'avg_speed': random.randint(1, 10) * 1024 * 1024,
            'max_speed': random.randint(5, 20) * 1024 * 1024,
            'error_count': random.randint(0, 2),
            'efficiency_score': random.randint(60, 95),
            'completed_at_hour': random.randint(0, 23)
        }
        
        result = manager.gamification.update_stats(transfer_data)
        
        if result['new_achievements']:
            print(f"دستاورد جدید: {result['new_achievements'][0]['name']}")
        
        if result['level_up']:
            print(result['level_up'])
    
    profile = manager.gamification.create_profile_card()
    print(profile)
    
    # نمونه‌ای از export
    print("\n" + "="*60)
    print("📤 Export داده‌ها")
    
    sample_metrics = {
        'transferred': 250 * 1024 * 1024,
        'total': 500 * 1024 * 1024,
        'speed': 5 * 1024 * 1024,
        'elapsed': 50,
        'remaining': 50,
        'error_count': 2
    }
    
    # خروجی Prometheus
    prometheus_output = ExternalIntegration.export_to_prometheus(sample_metrics)
    print("📊 خروجی Prometheus:")
    print(prometheus_output[:200] + "...")
    
    # خروجی JSON
    json_output = ExternalIntegration.export_to_json(sample_metrics, True)
    print("\n📄 خروجی JSON:")
    print(json_output[:300] + "...")

if __name__ == "__main__":
    # نمایش اطلاعات نسخه
    print(f"""
    🚀 Progress UI Advanced - نسخه 2.0.0
    📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    ویژگی‌های اصلی:
    • نمایش پیشرفت پیشرفته با نمودار
    • پیش‌بینی هوشمند زمان تکمیل
    • مدیریت چند فایل همزمان
    • بهینه‌سازی پویا شبکه
    • آنالیتیکس لحظه‌ای
    • گیمیفیکیشن و دستاوردها
    • یکپارچه‌سازی با سرویس‌های خارجی
    • ویژوال‌سازی پیشرفته
    
    """)
    
    # اجرای نمونه
    try:
        example_usage()
    except KeyboardInterrupt:
        print("\n\n👋 خروج از برنامه...")
    except Exception as e:
        print(f"\n❌ خطا: {e}")
        import traceback
        traceback.print_exc()
