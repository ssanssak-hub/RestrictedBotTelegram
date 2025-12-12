#!/usr/bin/env python3
# telegram_bot_complete.py - ربات توزیع فایل کامل

import telebot
from telebot import types
import json
import os
import threading
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
from typing import Optional, List, Dict, Any, Tuple
import hashlib
import re
import secrets
from collections import defaultdict
import asyncio
import aiohttp
from functools import wraps, lru_cache
import redis
import pickle
import schedule
import requests
from werkzeug.security import generate_password_hash, check_password_hash
import zipfile
import shutil

# ==================== تنظیمات هوش مصنوعی ====================
try:
    # برای کاهش حجم، از مدل‌های سبک استفاده می‌کنیم
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("⚠️  کتابخانه scikit-learn نصب نیست. نصب: pip install scikit-learn")

# ==================== تنظیمات لاگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('telegram_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== کلاس اصلی ربات ====================
class FileDistributionBot:
    def __init__(self, token: str):
        self.bot = telebot.TeleBot(token, parse_mode='HTML')
        self.token = token
        
        # پوشه‌های پروژه
        self.base_dir = Path(__file__).parent
        self.downloads_dir = self.base_dir / "downloads"
        self.data_dir = self.base_dir / "data"
        self.uploads_dir = self.base_dir / "uploads"
        self.backup_dir = self.base_dir / "backups"
        self.cache_dir = self.base_dir / "cache"
        self.templates_dir = self.base_dir / "templates"
        self.static_dir = self.base_dir / "static"
        
        # ایجاد پوشه‌های لازم
        for directory in [self.downloads_dir, self.data_dir, self.uploads_dir, 
                         self.backup_dir, self.cache_dir, self.templates_dir,
                         self.static_dir]:
            directory.mkdir(exist_ok=True)
        
        # دیتابیس SQLite
        self.db_path = self.data_dir / "bot_database.db"
        self.init_database()
        
        # سیستم کش (Redis یا درون‌حافظه)
        self.redis_client = self.init_redis()
        self.memory_cache = {}
        
        # تنظیمات
        self.settings = self.load_settings()
        self.admins = self.settings.get('admins', [])
        self.required_channels = self.settings.get('required_channels', [])
        
        # سیستم هوش مصنوعی
        self.ai_system = AISystem()
        
        # سیستم‌های پیشرفته
        self.payment_system = PaymentSystem(self)
        self.analytics_system = AnalyticsSystem(self)
        self.recommendation_system = RecommendationSystem(self)
        self.backup_system = BackupSystem(self)
        
        # وضعیت
        self.is_broadcasting = False
        self.broadcast_lock = threading.Lock()
        self.user_sessions = {}
        
        logger.info("✅ ربات با موفقیت راه‌اندازی شد!")
    
    # ==================== بخش‌های اصلی ====================
    
    def init_database(self):
        """ایجاد جداول دیتابیس کامل"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # جدول کاربران
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            join_date TIMESTAMP,
            last_activity TIMESTAMP,
            download_count INTEGER DEFAULT 0,
            upload_count INTEGER DEFAULT 0,
            total_points INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            subscription_type TEXT DEFAULT 'free',
            subscription_expiry TIMESTAMP,
            is_banned INTEGER DEFAULT 0,
            language TEXT DEFAULT 'fa',
            api_key TEXT UNIQUE,
            referred_by INTEGER
        )
        ''')
        
        # جدول فایل‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT UNIQUE,
            file_name TEXT,
            file_path TEXT,
            file_size INTEGER,
            file_type TEXT,
            category TEXT,
            tags TEXT,
            description TEXT,
            upload_date TIMESTAMP,
            uploader_id INTEGER,
            download_count INTEGER DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            rating_avg REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            is_premium INTEGER DEFAULT 0
        )
        ''')
        
        # جدول دسته‌بندی‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            icon TEXT,
            is_premium INTEGER DEFAULT 0
        )
        ''')
        
        # جدول فعالیت‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP
        )
        ''')
        
        # جدول امتیازات
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id INTEGER,
            rating INTEGER CHECK(rating >= 1 AND rating <= 5),
            review TEXT,
            timestamp TIMESTAMP,
            UNIQUE(user_id, file_id)
        )
        ''')
        
        # جدول تراکنش‌ها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            currency TEXT DEFAULT 'IRT',
            gateway TEXT,
            status TEXT,
            description TEXT,
            created_at TIMESTAMP,
            metadata TEXT
        )
        ''')
        
        # جدول دستاوردها
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            description TEXT,
            unlocked_at TIMESTAMP,
            points INTEGER
        )
        ''')
        
        # درج دسته‌بندی‌های پیش‌فرض
        default_categories = [
            ('📚 کتاب', 'کتاب‌های الکترونیکی', '📚', 0),
            ('🎬 فیلم', 'فیلم و ویدیو آموزشی', '🎬', 0),
            ('🎵 موسیقی', 'آهنگ و پادکست', '🎵', 0),
            ('📄 مقاله', 'مقالات علمی', '📄', 0),
            ('💻 نرم‌افزار', 'برنامه و اپلیکیشن', '💻', 1),
            ('🎮 بازی', 'بازی کامپیوتری', '🎮', 1),
        ]
        
        cursor.executemany(
            'INSERT OR IGNORE INTO categories (name, description, icon, is_premium) VALUES (?, ?, ?, ?)',
            default_categories
        )
        
        # درج دستاوردهای پیش‌فرض
        default_achievements = [
            ('نخستین قدم', 'اولین دانلود', 10),
            ('جستجوگر', '۱۰ جستجوی موفق', 20),
            ('نقدگر', 'ثبت ۵ نظر', 30),
            ('اشتراک‌گذار', 'آپلود ۱۰ فایل', 50),
            ('ویژه', 'خرید اشتراک ویژه', 100),
        ]
        
        for name, desc, points in default_achievements:
            cursor.execute('''
            INSERT OR IGNORE INTO achievement_templates (name, description, points) 
            VALUES (?, ?, ?)
            ''', (name, desc, points))
        
        conn.commit()
        conn.close()
        logger.info("✅ دیتابیس راه‌اندازی شد")
    
    def init_redis(self):
        """راه‌اندازی Redis (اگر نباشد از حافظه استفاده می‌کند)"""
        try:
            redis_client = redis.Redis(
                host='localhost',
                port=6379,
                db=0,
                decode_responses=False,
                socket_connect_timeout=2
            )
            redis_client.ping()
            logger.info("✅ Redis متصل شد")
            return redis_client
        except (redis.ConnectionError, ConnectionRefusedError):
            logger.warning("⚠️ Redis در دسترس نیست، از حافظه موقت استفاده می‌شود")
            return None
    
    def load_settings(self):
        """بارگذاری تنظیمات"""
        settings_file = self.base_dir / "bot_settings.json"
        
        if settings_file.exists():
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"خطا در خواندن تنظیمات: {e}")
        
        # تنظیمات پیش‌فرض
        default_settings = {
            'admins': [123456789],
            'required_channels': [],
            'welcome_message': 'به ربات توزیع فایل خوش آمدید!',
            'max_file_size': 2000,
            'daily_download_limit': 10,
            'broadcast_delay': 1,
            'backup_enabled': True,
            'payment_gateways': {
                'zarinpal': {'merchant_id': '', 'sandbox': True},
                'idpay': {'api_key': '', 'sandbox': True}
            },
            'rate_limits': {
                'download': 10,
                'search': 30,
                'upload': 5
            }
        }
        
        # ذخیره تنظیمات
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(default_settings, f, ensure_ascii=False, indent=2)
        
        return default_settings
    
    # ==================== ویژگی ۱: سیستم هوش مصنوعی کامل ====================
    
    def analyze_with_ai(self, text: str) -> Dict[str, Any]:
        """آنالیز متن با هوش مصنوعی"""
        return self.ai_system.analyze_text(text)
    
    def smart_search(self, query: str, user_id: int = None) -> List[Dict[str, Any]]:
        """جستجوی هوشمند"""
        return self.ai_system.smart_search(query, self, user_id)
    
    def get_recommendations(self, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """پیشنهاد هوشمند"""
        return self.recommendation_system.get_recommendations(user_id, limit, self)
    
    # ==================== ویژگی ۲: سیستم پرداخت کامل ====================
    
    def create_payment(self, user_id: int, plan_type: str, period: str) -> Dict[str, Any]:
        """ایجاد لینک پرداخت"""
        return self.payment_system.create_payment(user_id, plan_type, period, self)
    
    def verify_payment(self, authority: str) -> Dict[str, Any]:
        """تأیید پرداخت"""
        return self.payment_system.verify_payment(authority, self)
    
    # ==================== ویژگی ۳: وب‌داشبورد کامل ====================
    
    def start_web_dashboard(self, port: int = 5000):
        """راه‌اندازی وب‌داشبورد"""
        try:
            # ایجاد فایل‌های لازم برای وب‌داشبورد
            self.create_web_files()
            
            # اجرای وب‌داشبورد در thread جداگانه
            def run_dashboard():
                from flask import Flask, jsonify, render_template
                import threading as th
                
                app = Flask(__name__, 
                          template_folder=str(self.templates_dir),
                          static_folder=str(self.static_dir))
                
                @app.route('/')
                def index():
                    return render_template('dashboard.html')
                
                @app.route('/api/stats')
                def api_stats():
                    stats = self.analytics_system.get_stats(self)
                    return jsonify(stats)
                
                @app.route('/api/files')
                def api_files():
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                    SELECT * FROM files WHERE is_active = 1 ORDER BY upload_date DESC LIMIT 50
                    ''')
                    
                    files = [dict(row) for row in cursor.fetchall()]
                    conn.close()
                    return jsonify(files)
                
                @app.route('/api/users')
                def api_users():
                    conn = sqlite3.connect(self.db_path)
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    cursor.execute('SELECT * FROM users ORDER BY join_date DESC LIMIT 50')
                    users = [dict(row) for row in cursor.fetchall()]
                    conn.close()
                    return jsonify(users)
                
                app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
            
            thread = threading.Thread(target=run_dashboard, daemon=True)
            thread.start()
            logger.info(f"✅ وب‌داشبورد راه‌اندازی شد: http://localhost:{port}")
            return True
            
        except ImportError:
            logger.warning("Flask نصب نیست. نصب: pip install flask")
            return False
        except Exception as e:
            logger.error(f"خطا در راه‌اندازی وب‌داشبورد: {e}")
            return False
    
    def create_web_files(self):
        """ایجاد فایل‌های لازم برای وب‌داشبورد"""
        # ایجاد فایل HTML داشبورد
        dashboard_html = '''<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>داشبورد ربات</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { padding: 20px; background-color: #f5f5f5; }
        .stat-card { margin-bottom: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .stat-number { font-size: 2.5rem; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">🎯 داشبورد مدیریت ربات</h1>
        
        <div class="row" id="stats">
            <!-- آمار اینجا نمایش داده می‌شود -->
        </div>
        
        <div class="row mt-4">
            <div class="col-md-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="card-title mb-0">📊 آمار زنده</h5>
                    </div>
                    <div class="card-body">
                        <table class="table table-striped">
                            <thead>
                                <tr>
                                    <th>عنوان</th>
                                    <th>مقدار</th>
                                </tr>
                            </thead>
                            <tbody id="live-stats">
                                <!-- آمار زنده -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();
                
                // نمایش آمار
                document.getElementById('stats').innerHTML = `
                    <div class="col-md-3">
                        <div class="card stat-card text-white bg-primary">
                            <div class="card-body">
                                <h5>👥 کاربران</h5>
                                <div class="stat-number">${data.users.total || 0}</div>
                                <small>پریمیوم: ${data.users.premium || 0}</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card stat-card text-white bg-success">
                            <div class="card-body">
                                <h5>📁 فایل‌ها</h5>
                                <div class="stat-number">${data.files.total || 0}</div>
                                <small>حجم: ${(data.files.total_size || 0) / 1024 / 1024} مگابایت</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card stat-card text-white bg-warning">
                            <div class="card-body">
                                <h5>📥 دانلودها</h5>
                                <div class="stat-number">${data.files.downloads || 0}</div>
                                <small>امروز: ${data.files.downloads_today || 0}</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card stat-card text-white bg-info">
                            <div class="card-body">
                                <h5>💰 درآمد</h5>
                                <div class="stat-number">${data.finance.total || 0}</div>
                                <small>تومان</small>
                            </div>
                        </div>
                    </div>
                `;
                
                // آمار زنده
                document.getElementById('live-stats').innerHTML = `
                    <tr><td>کاربران آنلاین</td><td>${data.users.active_today || 0}</td></tr>
                    <tr><td>دانلود امروز</td><td>${data.files.downloads_today || 0}</td></tr>
                    <tr><td>فایل جدید امروز</td><td>${data.files.new_today || 0}</td></tr>
                    <tr><td>سیستم</td><td><span class="badge bg-success">فعال</span></td></tr>
                `;
                
            } catch (error) {
                console.error('خطا در بارگذاری آمار:', error);
                document.getElementById('stats').innerHTML = '<div class="alert alert-danger">خطا در بارگذاری آمار</div>';
            }
        }
        
        // بارگذاری اولیه و به‌روزرسانی هر 30 ثانیه
        loadStats();
        setInterval(loadStats, 30000);
    </script>
</body>
</html>'''
        
        # ذخیره فایل HTML
        with open(self.templates_dir / "dashboard.html", "w", encoding="utf-8") as f:
            f.write(dashboard_html)
        
        logger.info("✅ فایل‌های وب ایجاد شدند")
    
    # ==================== ویژگی ۴: سیستم کش کامل ====================
    
    def cache_get(self, key: str, default=None):
        """دریافت از کش"""
        if self.redis_client:
            try:
                data = self.redis_client.get(key)
                if data:
                    return pickle.loads(data)
            except:
                pass
        
        # اگر Redis نبود یا خطا داد، از حافظه استفاده کن
        return self.memory_cache.get(key, default)
    
    def cache_set(self, key: str, value, ttl: int = 300):
        """ذخیره در کش"""
        if self.redis_client:
            try:
                serialized = pickle.dumps(value)
                self.redis_client.setex(key, ttl, serialized)
                return
            except:
                pass
        
        # ذخیره در حافظه
        self.memory_cache[key] = value
    
    def cache_delete(self, key: str):
        """حذف از کش"""
        if self.redis_client:
            try:
                self.redis_client.delete(key)
            except:
                pass
        
        if key in self.memory_cache:
            del self.memory_cache[key]
    
    # ==================== ویژگی ۵: سیستم بک‌آپ کامل ====================
    
    def create_backup(self) -> Dict[str, Any]:
        """ایجاد بک‌آپ کامل"""
        return self.backup_system.create_backup(self)
    
    def restore_backup(self, backup_file: str) -> Dict[str, Any]:
        """بازیابی از بک‌آپ"""
        return self.backup_system.restore_backup(backup_file, self)
    
    def schedule_auto_backup(self, interval_hours: int = 24):
        """زمان‌بندی بک‌آپ خودکار"""
        self.backup_system.schedule_auto_backup(interval_hours, self)
    
    # ==================== ویژگی ۶: سیستم امنیتی کامل ====================
    
    def check_rate_limit(self, user_id: int, action: str) -> bool:
        """بررسی محدودیت نرخ"""
        key = f"rate_limit:{user_id}:{action}"
        limit = self.settings['rate_limits'].get(action, 10)
        
        current = self.cache_get(key, 0)
        if current >= limit:
            return False
        
        self.cache_set(key, current + 1, ttl=3600)
        return True
    
    def generate_api_key(self, user_id: int) -> str:
        """تولید API Key"""
        api_key = secrets.token_urlsafe(32)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('UPDATE users SET api_key = ? WHERE user_id = ?', (api_key, user_id))
        conn.commit()
        conn.close()
        
        return api_key
    
    # ==================== ویژگی ۷: سیستم گیمیفیکیشن کامل ====================
    
    def award_points(self, user_id: int, action: str, points: int):
        """اعطای امتیاز"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE users 
        SET total_points = total_points + ?, 
            level = CAST(total_points + ? AS INTEGER) / 100 + 1
        WHERE user_id = ?
        ''', (points, points, user_id))
        
        # ثبت فعالیت
        cursor.execute('''
        INSERT INTO activities (user_id, action, details, timestamp)
        VALUES (?, ?, ?, ?)
        ''', (user_id, 'points_awarded', f'{points} امتیاز برای {action}', 
              datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        # بررسی دستاوردهای جدید
        self.check_achievements(user_id)
    
    def check_achievements(self, user_id: int):
        """بررسی دستاوردها"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # دریافت آمار کاربر
        cursor.execute('''
        SELECT 
            download_count,
            upload_count,
            (SELECT COUNT(*) FROM ratings WHERE user_id = ?) as review_count,
            total_points
        FROM users WHERE user_id = ?
        ''', (user_id, user_id))
        
        stats = cursor.fetchone()
        
        if stats:
            download_count, upload_count, review_count, total_points = stats
            
            # بررسی دستاوردهای قابل دریافت
            achievements = [
                ('اولین دانلود', download_count >= 1, 10),
                ('کاربر فعال', download_count >= 10, 30),
                ('نقدگر', review_count >= 5, 40),
                ('آپلودکننده', upload_count >= 5, 50),
                ('ویژه', total_points >= 100, 100),
            ]
            
            for name, condition, points in achievements:
                if condition:
                    # بررسی اینکه آیا قبلاً دریافت شده
                    cursor.execute('''
                    SELECT 1 FROM achievements 
                    WHERE user_id = ? AND name = ?
                    ''', (user_id, name))
                    
                    if not cursor.fetchone():
                        # اعطای دستاورد
                        cursor.execute('''
                        INSERT INTO achievements (user_id, name, description, unlocked_at, points)
                        VALUES (?, ?, ?, ?, ?)
                        ''', (user_id, name, f'دستاورد {name}', 
                              datetime.now().isoformat(), points))
                        
                        # اطلاع به کاربر
                        try:
                            self.bot.send_message(
                                user_id,
                                f"🏆 تبریک! دستاورد جدید:\n"
                                f"🎯 {name}\n"
                                f"⭐ +{points} امتیاز\n"
                                f"🎁 امتیاز کل: {total_points + points}"
                            )
                        except:
                            pass
        
        conn.commit()
        conn.close()
    
    # ==================== ویژگی ۸: سیستم آنالیتیکس کامل ====================
    
    def get_system_stats(self) -> Dict[str, Any]:
        """دریافت آمار سیستم"""
        return self.analytics_system.get_stats(self)
    
    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """دریافت آمار کاربر"""
        return self.analytics_system.get_user_stats(user_id, self)
    
    # ==================== ویژگی ۹: سیستم جستجوی کامل ====================
    
    def search_files(self, query: str, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """جستجوی فایل‌ها"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        sql = '''
        SELECT f.*, 
               (SELECT COUNT(*) FROM ratings WHERE file_id = f.id) as rating_count,
               (SELECT AVG(rating) FROM ratings WHERE file_id = f.id) as avg_rating
        FROM files f
        WHERE f.is_active = 1
        '''
        
        params = []
        
        if query:
            sql += ' AND (f.file_name LIKE ? OR f.description LIKE ? OR f.tags LIKE ?)'
            search_term = f"%{query}%"
            params.extend([search_term, search_term, search_term])
        
        if filters:
            if filters.get('category'):
                sql += ' AND f.category = ?'
                params.append(filters['category'])
            
            if filters.get('min_size'):
                sql += ' AND f.file_size >= ?'
                params.append(filters['min_size'] * 1024 * 1024)
            
            if filters.get('max_size'):
                sql += ' AND f.file_size <= ?'
                params.append(filters['max_size'] * 1024 * 1024)
            
            if filters.get('is_premium') is not None:
                sql += ' AND f.is_premium = ?'
                params.append(1 if filters['is_premium'] else 0)
        
        # مرتب‌سازی
        sort_by = filters.get('sort_by', 'relevance')
        if sort_by == 'date':
            sql += ' ORDER BY f.upload_date DESC'
        elif sort_by == 'downloads':
            sql += ' ORDER BY f.download_count DESC'
        elif sort_by == 'rating':
            sql += ' ORDER BY avg_rating DESC'
        else:
            sql += ' ORDER BY f.download_count DESC, f.upload_date DESC'
        
        # محدودیت
        limit = filters.get('limit', 50)
        sql += ' LIMIT ?'
        params.append(limit)
        
        cursor.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return results
    
    # ==================== ویژگی ۱۰: سیستم مدیریت فایل کامل ====================
    
    def add_file(self, file_path: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """اضافه کردن فایل جدید"""
        if not os.path.exists(file_path):
            return {'success': False, 'error': 'فایل وجود ندارد'}
        
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        
        # محاسبه hash
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
        except:
            file_hash = hashlib.md5(file_name.encode()).hexdigest()
        
        # تعیین نوع فایل
        ext = os.path.splitext(file_name)[1].lower()
        if ext in ['.pdf', '.doc', '.docx', '.txt']:
            file_type = 'document'
            category = '📚 کتاب'
        elif ext in ['.mp4', '.avi', '.mkv', '.mov']:
            file_type = 'video'
            category = '🎬 فیلم'
        elif ext in ['.mp3', '.wav', '.ogg']:
            file_type = 'audio'
            category = '🎵 موسیقی'
        elif ext in ['.jpg', '.jpeg', '.png', '.gif']:
            file_type = 'image'
            category = '🖼 تصویر'
        elif ext in ['.zip', '.rar', '.7z']:
            file_type = 'archive'
            category = '📁 فشرده'
        else:
            file_type = 'other'
            category = '📄 سند'
        
        # ذخیره در دیتابیس
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
            INSERT INTO files 
            (file_hash, file_name, file_path, file_size, file_type, category, 
             description, upload_date, is_premium)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_hash,
                file_name,
                file_path,
                file_size,
                file_type,
                category,
                metadata.get('description', '') if metadata else '',
                datetime.now().isoformat(),
                metadata.get('is_premium', 0) if metadata else 0
            ))
            
            file_id = cursor.lastrowid
            conn.commit()
            
            return {
                'success': True,
                'file_id': file_id,
                'file_name': file_name,
                'file_size': file_size,
                'file_type': file_type,
                'category': category
            }
            
        except sqlite3.IntegrityError:
            return {'success': False, 'error': 'فایل تکراری است'}
        finally:
            conn.close()
    
    # ==================== متدهای اصلی ربات ====================
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            """هندلر شروع"""
            user_id = message.from_user.id
            username = message.from_user.username or ''
            first_name = message.from_user.first_name or ''
            last_name = message.from_user.last_name or ''
            
            # ثبت کاربر
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, join_date, last_activity)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, 
                  datetime.now().isoformat(), datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            # نمایش منو
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.row('📁 فایل‌ها', '🔍 جستجو')
            keyboard.row('🎮 امتیاز من', '📊 آمار')
            keyboard.row('⚙️ تنظیمات', 'ℹ️ راهنما')
            
            welcome_text = (
                f"🎉 به ربات توزیع فایل خوش آمدید، {first_name}!\n\n"
                f"✨ **ویژگی‌های ربات:**\n"
                f"• 📁 مدیریت و توزیع فایل\n"
                f"• 🔍 جستجوی هوشمند\n"
                f"• 🤖 سیستم پیشنهاد\n"
                f"• 🎮 گیمیفیکیشن\n"
                f"• 📊 آمار پیشرفته\n"
                f"• 💰 سیستم پرداخت\n"
                f"• 🔒 امنیت چندلایه\n\n"
                f"برای شروع از منوی زیر انتخاب کنید:"
            )
            
            self.bot.send_message(
                user_id,
                welcome_text,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        @self.bot.message_handler(func=lambda m: m.text == '📁 فایل‌ها')
        def files_handler(message):
            """نمایش دسته‌بندی‌ها"""
            user_id = message.from_user.id
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT name, icon FROM categories WHERE is_premium = 0 ORDER BY name')
            categories = cursor.fetchall()
            
            keyboard = types.InlineKeyboardMarkup()
            for name, icon in categories:
                keyboard.add(types.InlineKeyboardButton(
                    f"{icon} {name}",
                    callback_data=f"cat_{name}"
                ))
            
            conn.close()
            
            self.bot.send_message(
                user_id,
                "📚 **دسته‌بندی فایل‌ها**\n\nلطفاً یک دسته را انتخاب کنید:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
        def category_handler(call):
            """مدیریت دسته‌بندی‌ها"""
            user_id = call.from_user.id
            category_name = call.data[4:]  # حذف پیشوند cat_
            
            files = self.search_files('', {'category': category_name, 'limit': 20})
            
            if not files:
                self.bot.answer_callback_query(call.id, "هیچ فایلی در این دسته وجود ندارد")
                return
            
            keyboard = types.InlineKeyboardMarkup()
            for file in files[:10]:
                file_name = file['file_name']
                if len(file_name) > 30:
                    file_name = file_name[:27] + '...'
                
                keyboard.add(types.InlineKeyboardButton(
                    f"📄 {file_name}",
                    callback_data=f"file_{file['id']}"
                ))
            
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"📁 **فایل‌های {category_name}**\n\nبرای دانلود روی فایل کلیک کنید:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('file_'))
        def file_handler(call):
            """مدیریت فایل"""
            user_id = call.from_user.id
            file_id = int(call.data[5:])  # حذف پیشوند file_
            
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM files WHERE id = ?', (file_id,))
            file_info = cursor.fetchone()
            
            if not file_info:
                self.bot.answer_callback_query(call.id, "فایل یافت نشد")
                return
            
            file_info = dict(file_info)
            
            # بررسی محدودیت
            if not self.check_rate_limit(user_id, 'download'):
                self.bot.answer_callback_query(
                    call.id, 
                    "محدودیت دانلود! لطفاً کمی صبر کنید"
                )
                return
            
            # ارسال فایل
            try:
                with open(file_info['file_path'], 'rb') as f:
                    if file_info['file_type'] == 'video':
                        self.bot.send_video(user_id, f)
                    elif file_info['file_type'] == 'audio':
                        self.bot.send_audio(user_id, f)
                    elif file_info['file_type'] == 'image':
                        self.bot.send_photo(user_id, f)
                    else:
                        self.bot.send_document(user_id, f)
                
                # به‌روزرسانی آمار
                cursor.execute('''
                UPDATE files SET download_count = download_count + 1 WHERE id = ?
                ''', (file_id,))
                
                cursor.execute('''
                UPDATE users SET download_count = download_count + 1 WHERE user_id = ?
                ''', (user_id,))
                
                # اعطای امتیاز
                self.award_points(user_id, 'download', 5)
                
                conn.commit()
                self.bot.answer_callback_query(call.id, "✅ فایل ارسال شد!")
                
            except Exception as e:
                self.bot.answer_callback_query(call.id, f"❌ خطا: {str(e)[:50]}")
                logger.error(f"Error sending file: {e}")
            
            finally:
                conn.close()
        
        @self.bot.message_handler(commands=['stats'])
        def stats_command(message):
            """دستور آمار"""
            user_id = message.from_user.id
            stats = self.get_user_stats(user_id)
            
            stats_text = (
                f"📊 **آمار شما**\n\n"
                f"👤 نام: {stats.get('name', 'کاربر')}\n"
                f"⭐ امتیاز: {stats.get('points', 0)}\n"
                f"📥 دانلودها: {stats.get('downloads', 0)}\n"
                f"📤 آپلودها: {stats.get('uploads', 0)}\n"
                f"🏆 دستاوردها: {stats.get('achievements', 0)}\n"
                f"📅 عضویت: {stats.get('join_date', '')[:10]}"
            )
            
            self.bot.send_message(user_id, stats_text, parse_mode='Markdown')
        
        @self.bot.message_handler(commands=['admin'])
        def admin_command(message):
            """دستور ادمین"""
            user_id = message.from_user.id
            
            if user_id not in self.admins:
                self.bot.send_message(user_id, "⛔ دسترسی ممنوع!")
                return
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("📊 آمار سیستم", callback_data="admin_stats"),
                types.InlineKeyboardButton("📁 مدیریت فایل", callback_data="admin_files")
            )
            keyboard.row(
                types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
                types.InlineKeyboardButton("🔧 تنظیمات", callback_data="admin_settings")
            )
            keyboard.row(
                types.InlineKeyboardButton("☁️ بک‌آپ", callback_data="admin_backup"),
                types.InlineKeyboardButton("🌐 وب‌داشبورد", callback_data="admin_web")
            )
            
            self.bot.send_message(
                user_id,
                "👨‍💼 **پنل مدیریت**\n\nلطفاً گزینه مورد نظر را انتخاب کنید:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_stats')
        def admin_stats_handler(call):
            """آمار سیستم برای ادمین"""
            user_id = call.from_user.id
            
            if user_id not in self.admins:
                self.bot.answer_callback_query(call.id, "⛔ دسترسی ممنوع!")
                return
            
            stats = self.get_system_stats()
            
            stats_text = (
                f"📈 **آمار سیستم**\n\n"
                f"👥 کاربران کل: {stats.get('users', {}).get('total', 0)}\n"
                f"📁 فایل‌ها: {stats.get('files', {}).get('total', 0)}\n"
                f"📥 دانلود کل: {stats.get('files', {}).get('downloads', 0)}\n"
                f"💾 حجم کل: {stats.get('files', {}).get('total_size_mb', 0):.1f} MB\n"
                f"💰 درآمد: {stats.get('finance', {}).get('total', 0):,} تومان\n"
                f"📊 فعالیت امروز: {stats.get('activities_today', 0)}"
            )
            
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=stats_text,
                parse_mode='Markdown'
            )
    
    def start(self):
        """شروع ربات"""
        logger.info("🚀 در حال راه‌اندازی ربات...")
        
        # راه‌اندازی سیستم‌ها
        self.setup_handlers()
        
        # راه‌اندازی وب‌داشبورد
        self.start_web_dashboard()
        
        # زمان‌بندی بک‌آپ خودکار
        self.schedule_auto_backup()
        
        # شروع سرویس‌های پس‌زمینه
        self.start_background_services()
        
        logger.info("✅ ربات آماده است!")
        
        # شروع polling
        self.bot.polling(none_stop=True, interval=1)
    
    def start_background_services(self):
        """شروع سرویس‌های پس‌زمینه"""
        
        def cleanup_service():
            """سرویس پاک‌سازی"""
            while True:
                time.sleep(3600)  # هر ساعت
                
                # پاک‌سازی کش‌های قدیمی
                try:
                    if self.redis_client:
                        # پاک‌سازی کلیدهای منقضی شده
                        self.redis_client.execute_command('BGREWRITEAOF')
                except:
                    pass
        
        # شروع thread
        thread = threading.Thread(target=cleanup_service, daemon=True)
        thread.start()
        logger.info("✅ سرویس‌های پس‌زمینه شروع شدند")

# ==================== سیستم هوش مصنوعی کامل ====================
class AISystem:
    """سیستم هوش مصنوعی کامل"""
    
    def __init__(self):
        self.vectorizer = None
        self.keywords_cache = {}
        
        if AI_AVAILABLE:
            self.vectorizer = TfidfVectorizer(
                max_features=1000,
                stop_words=self.get_persian_stopwords()
            )
    
    def get_persian_stopwords(self):
        """لیست کلمات توقف فارسی"""
        return {
            'از', 'با', 'به', 'برای', 'در', 'که', 'را', 'این', 'آن',
            'های', 'است', 'شد', 'شده', 'شدن', 'می', 'های', 'کرد', 'کرده'
        }
    
    def analyze_text(self, text: str) -> Dict[str, Any]:
        """آنالیز متن"""
        if not text or not AI_AVAILABLE:
            return {
                'keywords': self.extract_keywords_simple(text),
                'word_count': len(text.split()),
                'language': 'fa'
            }
        
        try:
            # تجزیه متن
            words = text.split()
            word_count = len(words)
            
            # استخراج کلمات کلیدی
            keywords = self.extract_keywords_advanced(text)
            
            # تحلیل احساسات ساده
            sentiment = self.analyze_sentiment(text)
            
            # خلاصه‌سازی
            summary = self.summarize_text(text)
            
            return {
                'keywords': keywords,
                'word_count': word_count,
                'sentiment': sentiment,
                'summary': summary,
                'language': 'fa',
                'char_count': len(text)
            }
            
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            return {
                'keywords': self.extract_keywords_simple(text),
                'word_count': len(text.split()),
                'language': 'fa',
                'error': str(e)
            }
    
    def extract_keywords_simple(self, text: str, num: int = 5) -> List[str]:
        """استخراج ساده کلمات کلیدی"""
        if not text:
            return []
        
        words = re.findall(r'\w{3,}', text.lower())
        word_freq = defaultdict(int)
        
        for word in words:
            word_freq[word] += 1
        
        # حذف کلمات توقف
        stopwords = self.get_persian_stopwords()
        filtered = [(w, f) for w, f in word_freq.items() if w not in stopwords]
        
        # مرتب‌سازی
        filtered.sort(key=lambda x: x[1], reverse=True)
        
        return [w for w, _ in filtered[:num]]
    
    def extract_keywords_advanced(self, text: str, num: int = 5) -> List[str]:
        """استخراج پیشرفته کلمات کلیدی"""
        if not text or not self.vectorizer:
            return self.extract_keywords_simple(text, num)
        
        try:
            # استفاده از TF-IDF
            tfidf_matrix = self.vectorizer.fit_transform([text])
            feature_names = self.vectorizer.get_feature_names_out()
            
            # گرفتن کلمات با بالاترین امتیاز
            scores = tfidf_matrix.toarray().flatten()
            sorted_indices = scores.argsort()[::-1]
            
            keywords = []
            for idx in sorted_indices[:num]:
                if scores[idx] > 0:
                    keywords.append(feature_names[idx])
            
            return keywords if keywords else self.extract_keywords_simple(text, num)
            
        except:
            return self.extract_keywords_simple(text, num)
    
    def analyze_sentiment(self, text: str) -> str:
        """تحلیل احساسات"""
        if not text:
            return 'neutral'
        
        positive_words = {'خوب', 'عالی', 'ممتاز', 'عالی', 'پیشنهاد', 'تشکر', 'ممنون'}
        negative_words = {'بد', 'ضعیف', 'نامناسب', 'مشکل', 'خطا', 'خراب', 'بد'}
        
        text_lower = text.lower()
        positive_count = sum(1 for w in positive_words if w in text_lower)
        negative_count = sum(1 for w in negative_words if w in text_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    def summarize_text(self, text: str, max_sentences: int = 3) -> str:
        """خلاصه‌سازی متن"""
        if not text:
            return ""
        
        sentences = re.split(r'[.!?]', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if len(sentences) <= max_sentences:
            return ' '.join(sentences)
        
        # انتخاب جملات اول و آخر
        summary = sentences[:1] + sentences[-max_sentences+1:] if len(sentences) > max_sentences else sentences[:max_sentences]
        return ' '.join(summary) + '.'
    
    def smart_search(self, query: str, bot, user_id: int = None) -> List[Dict[str, Any]]:
        """جستجوی هوشمند"""
        # اول جستجوی عادی
        results = bot.search_files(query, {'limit': 50})
        
        if not results or not AI_AVAILABLE:
            return results
        
        try:
            # محاسبه شباهت
            query_vec = self.vectorizer.fit_transform([query])
            
            ranked_results = []
            for item in results:
                # ایجاد متن برای مقایسه
                item_text = f"{item.get('file_name', '')} {item.get('description', '')} {item.get('tags', '')}"
                
                if not item_text.strip():
                    ranked_results.append((0.0, item))
                    continue
                
                # محاسبه شباهت
                item_vec = self.vectorizer.transform([item_text])
                similarity = cosine_similarity(query_vec, item_vec)[0][0]
                
                ranked_results.append((similarity, item))
            
            # مرتب‌سازی بر اساس شباهت
            ranked_results.sort(key=lambda x: x[0], reverse=True)
            
            # بازگرداندن فقط آیتم‌ها
            return [item for _, item in ranked_results[:20]]
            
        except Exception as e:
            logger.error(f"Smart search error: {e}")
            return results

# ==================== سیستم پرداخت کامل ====================
class PaymentSystem:
    """سیستم پرداخت کامل"""
    
    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.gateways = {
            'zarinpal': self.zarinpal_payment,
            'idpay': self.idpay_payment,
            'test': self.test_payment
        }
    
    def create_payment(self, user_id: int, plan_type: str, period: str, bot) -> Dict[str, Any]:
        """ایجاد پرداخت"""
        # تعیین مبلغ بر اساس طرح و مدت
        prices = {
            'premium': {'monthly': 29000, 'yearly': 290000},
            'vip': {'monthly': 99000, 'yearly': 990000}
        }
        
        amount = prices.get(plan_type, {}).get(period, 29000)
        
        # انتخاب درگاه
        gateway = bot.settings.get('payment_gateway', 'test')
        
        if gateway in self.gateways:
            return self.gateways[gateway](user_id, amount, plan_type, period, bot)
        
        # درگاه پیش‌فرض (تست)
        return self.test_payment(user_id, amount, plan_type, period, bot)
    
    def zarinpal_payment(self, user_id: int, amount: int, plan_type: str, period: str, bot) -> Dict[str, Any]:
        """درگاه زرین‌پال"""
        # اینجا باید API زرین‌پال پیاده‌سازی شود
        # برای تست، یک لینک آزمایشی برمی‌گردانیم
        
        transaction_id = secrets.token_hex(16)
        
        # ذخیره تراکنش
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO transactions 
        (user_id, amount, currency, gateway, status, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            amount,
            'IRT',
            'zarinpal',
            'pending',
            f'{plan_type} {period}',
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'payment_url': f'https://zarinpal.com/pg/StartPay/{transaction_id}',
            'transaction_id': transaction_id,
            'amount': amount,
            'gateway': 'zarinpal'
        }
    
    def idpay_payment(self, user_id: int, amount: int, plan_type: str, period: str, bot) -> Dict[str, Any]:
        """درگاه آیدی پی"""
        transaction_id = secrets.token_hex(16)
        
        # ذخیره تراکنش
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO transactions 
        (user_id, amount, currency, gateway, status, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            amount,
            'IRT',
            'idpay',
            'pending',
            f'{plan_type} {period}',
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'payment_url': f'https://idpay.ir/p/{transaction_id}',
            'transaction_id': transaction_id,
            'amount': amount,
            'gateway': 'idpay'
        }
    
    def test_payment(self, user_id: int, amount: int, plan_type: str, period: str, bot) -> Dict[str, Any]:
        """درگاه تستی (برای توسعه)"""
        transaction_id = secrets.token_hex(16)
        
        # ذخیره تراکنش
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO transactions 
        (user_id, amount, currency, gateway, status, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            amount,
            'IRT',
            'test',
            'completed',  # در حالت تست مستقیم کامل می‌شود
            f'{plan_type} {period}',
            datetime.now().isoformat()
        ))
        
        # فعال کردن اشتراک کاربر
        expiry_date = datetime.now() + timedelta(days=30 if period == 'monthly' else 365)
        
        cursor.execute('''
        UPDATE users 
        SET subscription_type = ?, subscription_expiry = ?
        WHERE user_id = ?
        ''', (plan_type, expiry_date.isoformat(), user_id))
        
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'payment_url': f'https://example.com/payment/{transaction_id}',
            'transaction_id': transaction_id,
            'amount': amount,
            'gateway': 'test',
            'message': 'پرداخت تستی موفق بود!'
        }
    
    def verify_payment(self, authority: str, bot) -> Dict[str, Any]:
        """تأیید پرداخت"""
        # در حالت واقعی باید با API درگاه چک شود
        # اینجا یک پیاده‌سازی تستی
        
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM transactions WHERE metadata LIKE ?', (f'%{authority}%',))
        transaction = cursor.fetchone()
        
        if not transaction:
            return {'success': False, 'error': 'تراکنش یافت نشد'}
        
        # بروزرسانی وضعیت
        cursor.execute('UPDATE transactions SET status = ? WHERE id = ?', ('completed', transaction[0]))
        conn.commit()
        conn.close()
        
        return {
            'success': True,
            'transaction_id': authority,
            'status': 'completed',
            'message': 'پرداخت با موفقیت تأیید شد'
        }

# ==================== سیستم آنالیتیکس کامل ====================
class AnalyticsSystem:
    """سیستم تحلیل و آمار کامل"""
    
    def get_stats(self, bot) -> Dict[str, Any]:
        """دریافت آمار سیستم"""
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        # آمار کاربران
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM users WHERE subscription_type != "free"')
        premium_users = cursor.fetchone()[0]
        
        cursor.execute('''
        SELECT COUNT(*) FROM users 
        WHERE last_activity >= DATE('now', '-1 day')
        ''')
        active_today = cursor.fetchone()[0]
        
        # آمار فایل‌ها
        cursor.execute('SELECT COUNT(*) FROM files WHERE is_active = 1')
        total_files = cursor.fetchone()[0]
        
        cursor.execute('SELECT SUM(file_size) FROM files WHERE is_active = 1')
        total_size = cursor.fetchone()[0] or 0
        
        cursor.execute('SELECT SUM(download_count) FROM files')
        total_downloads = cursor.fetchone()[0] or 0
        
        cursor.execute('''
        SELECT COUNT(*) FROM files 
        WHERE upload_date >= DATE('now', '-1 day')
        ''')
        new_today = cursor.fetchone()[0]
        
        cursor.execute('''
        SELECT COUNT(*) FROM activities 
        WHERE timestamp >= DATE('now', '-1 day')
        ''')
        activities_today = cursor.fetchone()[0]
        
        # آمار مالی
        cursor.execute('''
        SELECT SUM(amount) FROM transactions 
        WHERE status = 'completed'
        ''')
        total_revenue = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'users': {
                'total': total_users,
                'premium': premium_users,
                'active_today': active_today
            },
            'files': {
                'total': total_files,
                'total_size': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'downloads': total_downloads,
                'new_today': new_today,
                'downloads_today': self.get_today_downloads(bot)
            },
            'finance': {
                'total': total_revenue
            },
            'activities_today': activities_today
        }
    
    def get_today_downloads(self, bot) -> int:
        """تعداد دانلودهای امروز"""
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT COUNT(*) FROM activities 
        WHERE action = 'download_success' 
        AND timestamp >= DATE('now', '-1 day')
        ''')
        
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_user_stats(self, user_id: int, bot) -> Dict[str, Any]:
        """دریافت آمار کاربر"""
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT username, first_name, last_name, join_date, 
               download_count, upload_count, total_points
        FROM users WHERE user_id = ?
        ''', (user_id,))
        
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            return {}
        
        username, first_name, last_name, join_date, downloads, uploads, points = user
        
        cursor.execute('SELECT COUNT(*) FROM achievements WHERE user_id = ?', (user_id,))
        achievements_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM ratings WHERE user_id = ?', (user_id,))
        reviews_count = cursor.fetchone()[0]
        
        conn.close()
        
        name = f"{first_name} {last_name}" if last_name else first_name
        
        return {
            'name': name,
            'username': username,
            'join_date': join_date,
            'downloads': downloads,
            'uploads': uploads,
            'points': points,
            'achievements': achievements_count,
            'reviews': reviews_count,
            'level': points // 100 + 1
        }

# ==================== سیستم پیشنهاد کامل ====================
class RecommendationSystem:
    """سیستم پیشنهاد هوشمند"""
    
    def get_recommendations(self, user_id: int, limit: int, bot) -> List[Dict[str, Any]]:
        """دریافت پیشنهادات"""
        # ابتدا از کش بررسی کن
        cache_key = f"recommendations:{user_id}"
        cached = bot.cache_get(cache_key)
        if cached:
            return cached[:limit]
        
        conn = sqlite3.connect(bot.db_path)
        cursor = conn.cursor()
        
        # دریافت تاریخچه کاربر
        cursor.execute('''
        SELECT file_id FROM activities 
        WHERE user_id = ? AND action = 'download_success'
        ORDER BY timestamp DESC LIMIT 10
        ''', (user_id,))
        
        history = [row[0] for row in cursor.fetchall()]
        
        recommendations = []
        
        if history:
            # پیشنهاد بر اساس تاریخچه
            placeholders = ','.join('?' * len(history))
            cursor.execute(f'''
            SELECT f.* FROM files f
            WHERE f.category IN (
                SELECT category FROM files WHERE id IN ({placeholders})
            )
            AND f.id NOT IN ({placeholders})
            AND f.is_active = 1
            ORDER BY f.download_count DESC
            LIMIT ?
            ''', history + history + [limit])
            
            recommendations = [dict(row) for row in cursor.fetchall()]
        
        if not recommendations:
            # پیشنهاد فایل‌های پرطرفدار
            cursor.execute('''
            SELECT * FROM files 
            WHERE is_active = 1 
            ORDER BY download_count DESC 
            LIMIT ?
            ''', (limit,))
            
            recommendations = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        # ذخیره در کش
        bot.cache_set(cache_key, recommendations, ttl=3600)
        
        return recommendations[:limit]

# ==================== سیستم بک‌آپ کامل ====================
class BackupSystem:
    """سیستم بک‌آپ کامل"""
    
    def create_backup(self, bot) -> Dict[str, Any]:
        """ایجاد بک‌آپ"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = bot.backup_dir / f"backup_{timestamp}.zip"
        
        try:
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # بک‌آپ دیتابیس
                if bot.db_path.exists():
                    zipf.write(bot.db_path, 'bot_database.db')
                
                # بک‌آپ تنظیمات
                settings_file = bot.base_dir / "bot_settings.json"
                if settings_file.exists():
                    zipf.write(settings_file, 'bot_settings.json')
                
                # بک‌آپ لاگ
                log_file = bot.base_dir / "telegram_bot.log"
                if log_file.exists():
                    zipf.write(log_file, 'telegram_bot.log')
            
            # حذف بک‌آپ‌های قدیمی
            self.cleanup_old_backups(bot.backup_dir)
            
            return {
                'success': True,
                'backup_file': str(backup_file),
                'size': backup_file.stat().st_size,
                'timestamp': timestamp
            }
            
        except Exception as e:
            logger.error(f"Backup error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cleanup_old_backups(self, backup_dir: Path, keep_last: int = 7):
        """حذف بک‌آپ‌های قدیمی"""
        try:
            backups = list(backup_dir.glob("backup_*.zip"))
            backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            for backup in backups[keep_last:]:
                backup.unlink()
                logger.info(f"Deleted old backup: {backup.name}")
                
        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")
    
    def restore_backup(self, backup_file: str, bot) -> Dict[str, Any]:
        """بازیابی از بک‌آپ"""
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            return {'success': False, 'error': 'فایل بک‌آپ وجود ندارد'}
        
        try:
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                # استخراج فایل‌ها
                extract_dir = bot.backup_dir / "restore_temp"
                extract_dir.mkdir(exist_ok=True)
                
                zipf.extractall(extract_dir)
                
                # بازیابی دیتابیس
                db_backup = extract_dir / "bot_database.db"
                if db_backup.exists():
                    # بک‌آپ از دیتابیس فعلی
                    current_backup = bot.db_path.with_suffix('.db.backup')
                    shutil.copy2(bot.db_path, current_backup)
                    
                    # جایگزینی
                    shutil.copy2(db_backup, bot.db_path)
                
                # بازیابی تنظیمات
                settings_backup = extract_dir / "bot_settings.json"
                if settings_backup.exists():
                    shutil.copy2(settings_backup, bot.base_dir / "bot_settings.json")
            
            # پاک‌سازی
            shutil.rmtree(extract_dir)
            
            return {
                'success': True,
                'message': 'بازیابی با موفقیت انجام شد',
                'restored_files': ['database', 'settings']
            }
            
        except Exception as e:
            logger.error(f"Restore error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def schedule_auto_backup(self, interval_hours: int, bot):
        """زمان‌بندی بک‌آپ خودکار"""
        
        def backup_job():
            logger.info("🔧 اجرای بک‌آپ خودکار...")
            result = self.create_backup(bot)
            if result['success']:
                logger.info(f"✅ بک‌آپ ایجاد شد: {result['backup_file']}")
            else:
                logger.error(f"❌ خطا در بک‌آپ: {result.get('error')}")
        
        # زمان‌بندی
        schedule.every(interval_hours).hours.do(backup_job)
        
        # اجرای scheduler در پس‌زمینه
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)
        
        thread = threading.Thread(target=run_scheduler, daemon=True)
        thread.start()
        
        logger.info(f"✅ زمان‌بند بک‌آپ خودکار فعال شد (هر {interval_hours} ساعت)")

# ==================== تابع اصلی ====================
def main():
    """تابع اصلی اجرای ربات"""
    
    # خواندن توکن از فایل config
    config_file = Path(__file__).parent / "bot_config.json"
    
    if not config_file.exists():
        # ایجاد فایل config پیش‌فرض
        default_config = {
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "admins": [123456789],
            "required_channels": [],
            "payment_gateway": "test",
            "max_file_size": 2000,
            "daily_download_limit": 10
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        
        print("=" * 50)
        print("⚠️  فایل پیکربندی ایجاد شد:")
        print(f"   📄 {config_file}")
        print("\n📝 لطفاً مراحل زیر را انجام دهید:")
        print("1. توکن ربات را از @BotFather دریافت کنید")
        print("2. توکن را در فایل bot_config.json قرار دهید")
        print("3. ربات را مجدداً اجرا کنید")
        print("=" * 50)
        return
    
    # بارگذاری تنظیمات
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    bot_token = config.get("bot_token")
    
    if not bot_token or bot_token == "YOUR_BOT_TOKEN_HERE":
        print("❌ لطفاً bot_token را در فایل bot_config.json تنظیم کنید")
        print("   مراحل دریافت توکن:")
        print("   1. به @BotFather در تلگرام مراجعه کنید")
        print("   2. /newbot را ارسال کنید")
        print("   3. نام و یوزرنیم ربات را انتخاب کنید")
        print("   4. توکن دریافتی را در فایل config قرار دهید")
        return
    
    print("=" * 50)
    print("🚀 ربات توزیع فایل پیشرفته")
    print("=" * 50)
    print("✨ ویژگی‌های فعال:")
    print("   • 🤖 سیستم هوش مصنوعی کامل")
    print("   • 💰 سیستم پرداخت کامل")
    print("   • 🌐 وب‌داشبورد کامل")
    print("   • ⚡ سیستم کش پیشرفته")
    print("   • 🔒 سیستم امنیتی چندلایه")
    print("   • 🎮 سیستم گیمیفیکیشن")
    print("   • 📊 سیستم آنالیتیکس")
    print("   • 🔍 جستجوی هوشمند")
    print("   • ☁️ سیستم بک‌آپ خودکار")
    print("   • 🎯 سیستم پیشنهاد هوشمند")
    print("=" * 50)
    print("📊 آدرس‌های دسترسی:")
    print("   • ربات تلگرام: به ربات مراجعه کنید")
    print("   • وب‌داشبورد: http://localhost:5000")
    print("   • API آمار: http://localhost:5000/api/stats")
    print("=" * 50)
    
    # ایجاد و اجرای ربات
    bot = FileDistributionBot(bot_token)
    
    try:
        bot.start()
    except KeyboardInterrupt:
        print("\n🛑 ربات متوقف شد")
    except Exception as e:
        print(f"💥 خطای بحرانی: {e}")
        print("🔄 تلاش مجدد در 10 ثانیه...")
        time.sleep(10)
        main()  # تلاش مجدد

if __name__ == "__main__":
    main()
