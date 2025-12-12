#!/usr/bin/env python3
# progress_ui.py - UI پیشرفته برای نمایش سرعت و پیشرفت

from typing import Dict, List, Optional
import asyncio
from dataclasses import dataclass
import time
import math

@dataclass
class ProgressUI:
    """UI نمایش پیشرفت"""
    
    @staticmethod
    def create_progress_bar(percent: float, width: int = 20) -> str:
        """ایجاد progress bar گرافیکی"""
        filled = int(width * percent / 100)
        bar = '█' * filled + '░' * (width - filled)
        return f"[{bar}]"
    
    @staticmethod
    def format_size(bytes_count: int) -> str:
        """قالب‌بندی اندازه فایل"""
        if bytes_count >= 1024 ** 3:  # GB
            return f"{bytes_count / (1024 ** 3):.2f} GB"
        elif bytes_count >= 1024 ** 2:  # MB
            return f"{bytes_count / (1024 ** 2):.2f} MB"
        elif bytes_count >= 1024:  # KB
            return f"{bytes_count / 1024:.2f} KB"
        else:
            return f"{bytes_count} B"
    
    @staticmethod
    def format_speed(bytes_per_second: float) -> str:
        """قالب‌بندی سرعت"""
        if bytes_per_second >= 1024 ** 2:  # MB/s
            return f"{bytes_per_second / (1024 ** 2):.2f} MB/s"
        elif bytes_per_second >= 1024:  # KB/s
            return f"{bytes_per_second / 1024:.2f} KB/s"
        else:
            return f"{bytes_per_second:.0f} B/s"
    
    @staticmethod
    def format_time(seconds: float) -> str:
        """قالب‌بندی زمان"""
        if seconds < 60:
            return f"{seconds:.0f} ثانیه"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.0f} دقیقه"
        else:
            hours = seconds / 3600
            return f"{hours:.1f} ساعت"
    
    @staticmethod
    def create_speed_graph(speed_history: List[float], height: int = 5) -> str:
        """ایجاد نمودار سرعت ASCII"""
        if not speed_history:
            return "📈 (داده‌ای موجود نیست)"
        
        max_speed = max(speed_history)
        if max_speed == 0:
            return "📈 (بدون فعالیت)"
        
        # نرمال‌سازی داده‌ها
        normalized = [s / max_speed for s in speed_history]
        
        # ایجاد نمودار
        rows = []
        for row in range(height, 0, -1):
            threshold = row / height
            row_chars = []
            
            for value in normalized[-30:]:  # فقط 30 نقطه آخر
                if value >= threshold:
                    row_chars.append('█')
                else:
                    row_chars.append(' ')
            
            rows.append(''.join(row_chars))
        
        # اضافه کردن محور
        rows.append('─' * 30)
        
        # اضافه کردن مقادیر
        min_val = min(speed_history[-30:]) if len(speed_history) >= 30 else min(speed_history)
        max_val = max(speed_history[-30:]) if len(speed_history) >= 30 else max(speed_history)
        
        rows.append(f"↕️ {ProgressUI.format_speed(min_val)} - {ProgressUI.format_speed(max_val)}")
        
        return '\n'.join(rows)
    
    @staticmethod
    def create_detailed_progress(
        transferred: int,
        total: int,
        speed: float,
        elapsed: float,
        remaining: float
    ) -> str:
        """ایجاد متن پیشرفت با جزئیات"""
        percent = (transferred / total * 100) if total > 0 else 0
        
        # progress bar
        bar = ProgressUI.create_progress_bar(percent)
        
        # اندازه‌ها
        transferred_fmt = ProgressUI.format_size(transferred)
        total_fmt = ProgressUI.format_size(total)
        
        # سرعت
        speed_fmt = ProgressUI.format_speed(speed)
        
        # زمان‌ها
        elapsed_fmt = ProgressUI.format_time(elapsed)
        remaining_fmt = ProgressUI.format_time(remaining)
        
        # تخمین زمان تکمیل
        completion_time = time.time() + remaining
        completion_str = time.strftime("%H:%M:%S", time.localtime(completion_time))
        
        text = (
            f"📊 پیشرفت: {percent:.1f}%\n"
            f"{bar}\n\n"
            f"📦 حجم: {transferred_fmt} / {total_fmt}\n"
            f"⚡ سرعت: {speed_fmt}\n"
            f"⏱️ سپری شده: {elapsed_fmt}\n"
            f"⏳ باقیمانده: {remaining_fmt}\n"
            f"🕒 تکمیل حدود: {completion_str}"
        )
        
        return text
    
    @staticmethod
    def create_mini_progress(percent: float, speed: float) -> str:
        """ایجاد نمایش مینیاتوری پیشرفت"""
        bar = ProgressUI.create_progress_bar(percent, width=10)
        speed_fmt = ProgressUI.format_speed(speed)
        
        return f"{bar} {percent:.1f}% ⚡{speed_fmt}"
    
    @staticmethod
    def create_transfer_summary(
        transfer_type: str,
        file_name: str,
        file_size: int,
        duration: float,
        avg_speed: float
    ) -> str:
        """ایجاد خلاصه انتقال"""
        size_fmt = ProgressUI.format_size(file_size)
        duration_fmt = ProgressUI.format_time(duration)
        speed_fmt = ProgressUI.format_speed(avg_speed)
        
        if transfer_type == 'download':
            emoji = "📥"
            action = "دانلود"
        else:
            emoji = "📤"
            action = "آپلود"
        
        # ارزیابی سرعت
        if avg_speed > 5 * 1024 * 1024:  # > 5 MB/s
            speed_rating = "عالی 🚀"
        elif avg_speed > 1 * 1024 * 1024:  # > 1 MB/s
            speed_rating = "خوب 👍"
        else:
            speed_rating = "متوسط 📶"
        
        text = (
            f"{emoji} <b>{action} تکمیل شد</b>\n\n"
            f"📁 فایل: {file_name}\n"
            f"💾 حجم: {size_fmt}\n"
            f"⏱️ زمان: {duration_fmt}\n"
            f"⚡ سرعت متوسط: {speed_fmt}\n"
            f"⭐ امتیاز سرعت: {speed_rating}\n\n"
            f"<i>عملیات با موفقیت انجام شد.</i>"
        )
        
        return text

class AnimatedProgress:
    """پیشرفت انیمیشنی"""
    
    def __init__(self):
        self.frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.current_frame = 0
    
    def next(self) -> str:
        """فریم بعدی"""
        frame = self.frames[self.current_frame]
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        return frame
    
    def get_spinner(self, text: str = "") -> str:
        """دریافت اسپینر با متن"""
        return f"{self.next()} {text}"
    
    @staticmethod
    def create_loading_animation(stage: str = "") -> str:
        """ایجاد انیمیشن لودینگ"""
        animations = {
            'connecting': ['🔗 اتصال...', '🔗 در حال اتصال...', '🔗 برقراری ارتباط...'],
            'downloading': ['📥 دریافت...', '📥 دانلود...', '📥 در حال دریافت...'],
            'uploading': ['📤 ارسال...', '📤 آپلود...', '📤 در حال ارسال...'],
            'processing': ['⚙️ پردازش...', '⚙️ در حال پردازش...', '⚙️ آماده‌سازی...'],
            'compressing': ['🗜️ فشرده‌سازی...', '🗜️ در حال فشرده‌سازی...'],
            'encrypting': ['🔐 رمزگذاری...', '🔐 در حال رمزگذاری...']
        }
        
        if stage in animations:
            import random
            return random.choice(animations[stage])
        
        return "⏳ در حال پردازش..."

class SpeedChartGenerator:
    """تولیدکننده نمودار سرعت"""
    
    @staticmethod
    def create_speed_chart_ascii(speed_data: List[float], width: int = 50, height: int = 10) -> str:
        """ایجاد نمودار ASCII از داده‌های سرعت"""
        if not speed_data:
            return "📈 (داده‌ای موجود نیست)"
        
        # محدود کردن به آخرین width نقطه
        data = speed_data[-width:] if len(speed_data) > width else speed_data
        
        # پیدا کردن min و max
        min_val = min(data)
        max_val = max(data)
        
        if max_val - min_val < 0.0001:  # داده‌ها یکنواخت
            return "📈 (داده‌های ثابت)"
        
        # نرمال‌سازی به محدوده height
        normalized = [
            int((val - min_val) / (max_val - min_val) * (height - 1))
            for val in data
        ]
        
        # ایجاد نمودار
        chart = []
        for y in range(height - 1, -1, -1):
            row = []
            for val in normalized:
                if val >= y:
                    row.append('█')
                else:
                    row.append(' ')
            chart.append(''.join(row))
        
        # اضافه کردن محور و مقادیر
        chart.append('─' * len(data))
        
        # فرمت مقادیر
        if max_val >= 1024 ** 2:
            min_fmt = f"{min_val / (1024 ** 2):.1f}MB"
            max_fmt = f"{max_val / (1024 ** 2):.1f}MB"
        elif max_val >= 1024:
            min_fmt = f"{min_val / 1024:.1f}KB"
            max_fmt = f"{max_val / 1024:.1f}KB"
        else:
            min_fmt = f"{min_val:.0f}B"
            max_fmt = f"{max_val:.0f}B"
        
        chart.append(f"↕️ {min_fmt} ── {max_fmt}")
        
        return '\n'.join(chart)
    
    @staticmethod
    def create_comparison_chart(
        download_speeds: List[float],
        upload_speeds: List[float],
        width: int = 40
    ) -> str:
        """ایجاد نمودار مقایسه‌ای دانلود/آپلود"""
        if not download_speeds or not upload_speeds:
            return "📊 (داده‌ای موجود نیست)"
        
        # محدود کردن داده‌ها
        download_data = download_speeds[-width:] if len(download_speeds) > width else download_speeds
        upload_data = upload_speeds[-width:] if len(upload_speeds) > width else upload_speeds
        
        # پیدا کردن max کلی
        all_data = download_data + upload_data
        max_val = max(all_data)
        
        if max_val == 0:
            return "📊 (بدون فعالیت)"
        
        # نرمال‌سازی
        download_norm = [d / max_val for d in download_data]
        upload_norm = [u / max_val for u in upload_data]
        
        # ایجاد نمودار (10 سطر)
        chart_lines = []
        for i in range(10, 0, -1):
            threshold = i / 10
            row = []
            
            for d, u in zip(download_norm, upload_norm):
                if d >= threshold and u >= threshold:
                    row.append('▉')  # هر دو
                elif d >= threshold:
                    row.append('▇')  # فقط دانلود
                elif u >= threshold:
                    row.append('▆')  # فقط آپلود
                else:
                    row.append(' ')
            
            chart_lines.append(''.join(row))
        
        # اضافه کردن legend
        chart_lines.append('─' * len(download_data))
        chart_lines.append('📥 دانلود: ▇   📤 آپلود: ▆   هر دو: ▉')
        
        return '\n'.join(chart_lines)

# نمونه استفاده
def example_usage():
    """نمونه استفاده از UI"""
    ui = ProgressUI()
    
    # نمایش progress bar
    print("Progress Bar:")
    print(ui.create_progress_bar(75))
    print()
    
    # نمایش پیشرفت با جزئیات
    print("Detailed Progress:")
    print(ui.create_detailed_progress(
        transferred=150 * 1024 * 1024,  # 150MB
        total=200 * 1024 * 1024,       # 200MB
        speed=5 * 1024 * 1024,         # 5MB/s
        elapsed=30,                    # 30 ثانیه
        remaining=10                   # 10 ثانیه باقیمانده
    ))
    print()
    
    # نمودار سرعت
    chart_gen = SpeedChartGenerator()
    speed_data = [i * 1024 * 1024 for i in range(1, 21)]  # 1MB تا 20MB
    print("Speed Chart:")
    print(chart_gen.create_speed_chart_ascii(speed_data, width=20, height=8))

if __name__ == "__main__":
    example_usage()
