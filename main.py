"""
Telegram Speed Download/Upload System - نسخه پیشرفته
ویژگی‌ها:
1. دانلود/آپلود با سرعت real-time
2. مانیتورینگ و بهینه‌سازی هوشمند
3. رابط تلگرام و API
4. هوش مصنوعی برای پیش‌بینی سرعت
5. مدیریت کامل منابع و خطاها
"""

import asyncio
import logging
import sys
import signal
from pathlib import Path
from typing import Dict, Any, Optional
import argparse

# اضافه کردن مسیر به sys.path
sys.path.append(str(Path(__file__).parent))

# Import modules
try:
    from bot.bot_core import TelegramBot
    from userbot.userbot_core import UserBotManager
    from core.database import DatabaseManager
    from core.limits_manager import LimitsManager
    from core.speed_optimizer import SpeedOptimizer
    HAS_TELEGRAM_MODULES = True
except ImportError:
    HAS_TELEGRAM_MODULES = False
    logger = logging.getLogger(__name__)
    logger.warning("Telegram modules not found, running in API-only mode")

# Import new speed system modules
from config.settings import config_manager, SpeedSettings
from core.monitor import AdaptiveSpeedMonitor, speed_monitor
from core.optimizer import IntelligentSpeedOptimizer, speed_optimizer
from core.ai_predictor import AISpeedPredictor, ai_predictor
from core.network_analyzer import NetworkAnalyzer
from interfaces.api_server import APIServer
from interfaces.telegram_ui import TelegramSpeedBot
from utils.cache_manager import CacheManager
from utils.encryption import EncryptionManager

# تنظیمات لاگ پیشرفته
def setup_logging(debug: bool = False, log_to_file: bool = True):
    """تنظیمات پیشرفته لاگ‌گیری"""
    
    log_level = logging.DEBUG if debug else logging.INFO
    
    # فرمت رنگی برای console
    class ColorFormatter(logging.Formatter):
        COLORS = {
            'DEBUG': '\033[36m',  # Cyan
            'INFO': '\033[32m',   # Green
            'WARNING': '\033[33m', # Yellow
            'ERROR': '\033[31m',   # Red
            'CRITICAL': '\033[41m', # Red background
            'RESET': '\033[0m'
        }
        
        def format(self, record):
            log_message = super().format(record)
            color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            return f"{color}{log_message}{self.COLORS['RESET']}"
    
    handlers = []
    
    # Handler برای console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    handlers.append(console_handler)
    
    # Handler برای فایل
    if log_to_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_dir / 'speed_system.log',
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
        handlers.append(file_handler)
    
    # تنظیم logging root
    logging.basicConfig(
        level=log_level,
        handlers=handlers
    )
    
    # تنظیم log level برای برخی کتابخانه‌ها
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

class AdvancedSpeedManager:
    """مدیریت پیشرفته سیستم سرعت"""
    
    def __init__(self, mode: str = 'all'):
        self.mode = mode
        self.config = config_manager.settings
        self.components: Dict[str, Any] = {}
        self.is_running = False
        
        # Signal handlers برای graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"AdvancedSpeedManager initialized in {mode} mode")
    
    async def initialize(self):
        """مقداردهی اولیه کامل سیستم"""
        try:
            logger.info("🚀 Initializing Advanced Speed System...")
            
            # 1. اعتبارسنجی تنظیمات
            await self._validate_config()
            
            # 2. ایجاد دایرکتوری‌های لازم
            self._create_directories()
            
            # 3. مقداردهی کامپوننت‌های اصلی
            await self._initialize_core_components()
            
            # 4. مقداردهی رابط‌های کاربری (بر اساس mode)
            await self._initialize_interfaces()
            
            # 5. شروع سرویس‌های پس‌زمینه
            await self._start_background_services()
            
            # 6. تست سلامت سیستم
            await self._health_check()
            
            self.is_running = True
            logger.info("✅ Advanced Speed System initialized successfully!")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize system: {e}")
            await self.shutdown()
            raise
    
    async def _validate_config(self):
        """اعتبارسنجی کامل تنظیمات"""
        errors = config_manager.validate_all()
        if errors:
            logger.warning(f"Configuration warnings: {errors}")
        
        # اعتبارسنجی ضروری‌ها
        essential_settings = [
            ('performance.thread_pool_size', 1, 64),
            ('network.timeout_seconds', 5, 300),
            ('caching.memory_cache_mb', 10, 1024),
        ]
        
        for setting, min_val, max_val in essential_settings:
            keys = setting.split('.')
            value = self.config.dict()
            for key in keys:
                value = value.get(key, {})
            
            if isinstance(value, (int, float)):
                if not (min_val <= value <= max_val):
                    logger.warning(f"Setting {setting} = {value} is outside recommended range [{min_val}, {max_val}]")
    
    def _create_directories(self):
        """ایجاد دایرکتوری‌های سیستم"""
        directories = [
            'cache',
            'logs',
            'stats',
            'backups',
            'models',
            'user_profiles',
            'downloads',
            'uploads',
            'temp'
        ]
        
        for dir_name in directories:
            path = Path(dir_name)
            path.mkdir(exist_ok=True, parents=True)
            logger.debug(f"Directory created/verified: {dir_name}")
    
    async def _initialize_core_components(self):
        """مقداردهی کامپوننت‌های اصلی"""
        logger.info("Initializing core components...")
        
        # 1. سیستم مانیتورینگ
        self.components['monitor'] = AdaptiveSpeedMonitor(self.config)
        logger.info("✓ Speed Monitor initialized")
        
        # 2. سیستم بهینه‌سازی
        self.components['optimizer'] = IntelligentSpeedOptimizer(self.config)
        logger.info("✓ Speed Optimizer initialized")
        
        # 3. هوش مصنوعی پیش‌بینی
        self.components['ai_predictor'] = AISpeedPredictor()
        logger.info("✓ AI Predictor initialized")
        
        # 4. آنالایزر شبکه
        self.components['network_analyzer'] = NetworkAnalyzer()
        logger.info("✓ Network Analyzer initialized")
        
        # 5. سیستم کش
        self.components['cache_manager'] = CacheManager(self.config.caching)
        logger.info("✓ Cache Manager initialized")
        
        # 6. سیستم رمزنگاری
        self.components['encryption'] = EncryptionManager()
        logger.info("✓ Encryption Manager initialized")
        
        # 7. دیتابیس (اگر modules تلگرام موجود باشند)
        if HAS_TELEGRAM_MODULES:
            self.components['database'] = DatabaseManager()
            await self.components['database'].initialize()
            logger.info("✓ Database initialized")
            
            self.components['limits_manager'] = LimitsManager()
            await self.components['limits_manager'].load_config()
            logger.info("✓ Limits Manager initialized")
        
        logger.info("All core components initialized successfully")
    
    async def _initialize_interfaces(self):
        """مقداردهی رابط‌های کاربری"""
        logger.info(f"Initializing interfaces for {self.mode} mode...")
        
        # همیشه API Server را شروع کن
        if self.config.monitoring.get('enable_api', True):
            self.components['api_server'] = APIServer()
            logger.info("✓ API Server initialized")
        
        # Telegram Bot (اگر mode مناسب باشد و modules موجود)
        if self.mode in ['all', 'telegram', 'bot'] and HAS_TELEGRAM_MODULES:
            bot_config = self.config.get('telegram', {})
            
            if bot_config.get('enabled', True):
                # دو گزینه: ربات کلاسیک یا ربات سرعت پیشرفته
                use_advanced_bot = bot_config.get('use_advanced_bot', True)
                
                if use_advanced_bot:
                    # ربات پیشرفته با نمایش سرعت
                    self.components['telegram_bot'] = TelegramSpeedBot(
                        token=bot_config.get('bot_token'),
                        speed_monitor=self.components['monitor'],
                        speed_optimizer=self.components['optimizer']
                    )
                    logger.info("✓ Advanced Telegram Bot initialized")
                else:
                    # ربات کلاسیک
                    self.components['telegram_bot'] = TelegramBot(
                        token=bot_config.get('bot_token'),
                        api_id=bot_config.get('api_id'),
                        api_hash=bot_config.get('api_hash'),
                        db=self.components.get('database'),
                        limits=self.components.get('limits_manager'),
                        speed_optimizer=self.components['optimizer']
                    )
                    logger.info("✓ Classic Telegram Bot initialized")
        
        # UserBot Manager (اگر فعال باشد)
        userbot_config = self.config.get('userbot', {})
        if (self.mode in ['all', 'userbot'] and 
            HAS_TELEGRAM_MODULES and 
            userbot_config.get('enabled', False)):
            
            self.components['userbot_manager'] = UserBotManager(
                api_id=userbot_config.get('api_id'),
                api_hash=userbot_config.get('api_hash'),
                db=self.components.get('database'),
                limits=self.components.get('limits_manager'),
                speed_optimizer=self.components['optimizer']
            )
            await self.components['userbot_manager'].initialize()
            logger.info("✓ UserBot Manager initialized")
    
    async def _start_background_services(self):
        """شروع سرویس‌های پس‌زمینه"""
        logger.info("Starting background services...")
        
        background_tasks = []
        
        # شروع API Server
        if 'api_server' in self.components:
            api_task = asyncio.create_task(
                self.components['api_server'].start()
            )
            background_tasks.append(('api_server', api_task))
        
        # شروع Telegram Bot (در صورت استفاده از ربات پیشرفته)
        if 'telegram_bot' in self.components:
            if isinstance(self.components['telegram_bot'], TelegramSpeedBot):
                bot_task = asyncio.create_task(
                    self.components['telegram_bot'].start()
                )
                background_tasks.append(('telegram_bot', bot_task))
        
        # شروع UserBot Manager
        if 'userbot_manager' in self.components:
            userbot_task = asyncio.create_task(
                self.components['userbot_manager'].start()
            )
            background_tasks.append(('userbot_manager', userbot_task))
        
        # ذخیره tasks برای مدیریت بعدی
        self.components['background_tasks'] = dict(background_tasks)
        
        logger.info(f"Started {len(background_tasks)} background services")
    
    async def _health_check(self):
        """بررسی سلامت سیستم"""
        logger.info("Running system health check...")
        
        health_status = {}
        
        # بررسی کامپوننت‌های اصلی
        for name, component in self.components.items():
            if hasattr(component, 'get_status'):
                try:
                    status = await component.get_status()
                    health_status[name] = {
                        'status': 'healthy',
                        'details': status
                    }
                except Exception as e:
                    health_status[name] = {
                        'status': 'unhealthy',
                        'error': str(e)
                    }
            else:
                health_status[name] = {'status': 'unknown'}
        
        # لاگ وضعیت سلامت
        unhealthy = [name for name, status in health_status.items() 
                    if status['status'] != 'healthy']
        
        if unhealthy:
            logger.warning(f"Unhealthy components: {unhealthy}")
        else:
            logger.info("✓ All components are healthy")
        
        return health_status
    
    async def run_periodic_tasks(self):
        """اجرای کارهای دوره‌ای سیستم"""
        tasks = [
            self._update_system_stats(),
            self._cleanup_resources(),
            self._check_for_updates(),
            self._backup_system_data(),
            self._optimize_performance()
        ]
        
        for task in tasks:
            try:
                await task
            except Exception as e:
                logger.error(f"Periodic task error: {e}")
    
    async def _update_system_stats(self):
        """به‌روزرسانی آمار سیستم"""
        stats = {
            'timestamp': asyncio.get_event_loop().time(),
            'monitor': await self.components['monitor'].get_system_overview(),
            'optimizer': await self.components['optimizer'].get_performance_report(),
            'ai_predictor': await self.components['ai_predictor'].get_performance_report(),
            'active_transfers': len(self.components['monitor'].active_transfers),
        }
        
        # ذخیره آمار در دیتابیس یا فایل
        if 'database' in self.components:
            await self.components['database'].save_system_stats(stats)
        
        # لاگ هر 5 دقیقه
        if int(stats['timestamp']) % 300 < 1:
            logger.info(f"📊 System Stats: {stats['monitor']}")
    
    async def _cleanup_resources(self):
        """پاکسازی منابع"""
        # پاکسازی کش
        if 'cache_manager' in self.components:
            await self.components['cache_manager'].cleanup()
        
        # پاکسازی فایل‌های موقت
        temp_dir = Path('temp')
        if temp_dir.exists():
            for file in temp_dir.glob('*'):
                if file.is_file():
                    # حذف فایل‌های قدیمی‌تر از 1 ساعت
                    if file.stat().st_mtime < asyncio.get_event_loop().time() - 3600:
                        file.unlink(missing_ok=True)
    
    async def _check_for_updates(self):
        """بررسی به‌روزرسانی‌ها"""
        # اینجا می‌توان به GitHub API وصل شد
        # فعلاً فقط لاگ می‌کنیم
        pass
    
    async def _backup_system_data(self):
        """پشتیبان‌گیری از داده‌های سیستم"""
        import shutil
        import datetime
        
        backup_dir = Path('backups')
        backup_dir.mkdir(exist_ok=True)
        
        # فقط یک بار در ساعت پشتیبان بگیر
        current_hour = datetime.datetime.now().hour
        if current_hour % 2 == 0:  # هر 2 ساعت
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f'system_backup_{timestamp}.zip'
            
            try:
                # پشتیبان از داده‌های مهم
                important_dirs = ['stats', 'models', 'user_profiles', 'config']
                
                import zipfile
                with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for dir_name in important_dirs:
                        dir_path = Path(dir_name)
                        if dir_path.exists():
                            for file in dir_path.rglob('*'):
                                if file.is_file():
                                    arcname = file.relative_to(Path('.'))
                                    zipf.write(file, arcname)
                
                logger.info(f"✅ System backup created: {backup_path}")
                
                # حذف پشتیبان‌های قدیمی (بیش از 7 روز)
                for backup_file in backup_dir.glob('*.zip'):
                    file_age = datetime.datetime.now().timestamp() - backup_file.stat().st_mtime
                    if file_age > 7 * 24 * 3600:  # 7 روز
                        backup_file.unlink()
                        
            except Exception as e:
                logger.error(f"Backup error: {e}")
    
    async def _optimize_performance(self):
        """بهینه‌سازی عملکرد سیستم"""
        # جمع‌آوری زباله
        import gc
        gc.collect()
        
        # بهینه‌سازی مدل‌های AI
        if 'ai_predictor' in self.components:
            await self.components['ai_predictor'].retrain_if_needed()
    
    async def get_system_status(self) -> Dict[str, Any]:
        """دریافت وضعیت کامل سیستم"""
        status = {
            'running': self.is_running,
            'mode': self.mode,
            'components': {},
            'health': await self._health_check(),
            'performance': {
                'monitor': await self.components['monitor'].get_system_overview(),
                'optimizer': await self.components['optimizer'].get_performance_report(),
                'ai_predictor': await self.components['ai_predictor'].get_performance_report(),
            },
            'timestamp': asyncio.get_event_loop().time(),
            'uptime': getattr(self, '_start_time', 0)
        }
        
        return status
    
    async def shutdown(self, emergency: bool = False):
        """خاموش کردن graceful سیستم"""
        if not self.is_running:
            return
        
        logger.info("🛑 Shutting down Advanced Speed System...")
        self.is_running = False
        
        # توقف تمام کامپوننت‌ها
        shutdown_tasks = []
        
        for name, component in self.components.items():
            if hasattr(component, 'shutdown'):
                logger.info(f"Shutting down {name}...")
                shutdown_task = component.shutdown()
                if asyncio.iscoroutine(shutdown_task):
                    shutdown_tasks.append(shutdown_task)
        
        # اجرای shutdownها
        if shutdown_tasks:
            try:
                await asyncio.gather(*shutdown_tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Shutdown error: {e}")
        
        # لغو background tasks
        for task_name, task in self.components.get('background_tasks', {}).items():
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled background task: {task_name}")
        
        logger.info("✅ Advanced Speed System shutdown complete")
    
    def _signal_handler(self, signum, frame):
        """مدیریت signals برای graceful shutdown"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        asyncio.create_task(self.shutdown())
    
    async def run(self):
        """اجرای اصلی سیستم"""
        try:
            await self.initialize()
            self._start_time = asyncio.get_event_loop().time()
            
            logger.info("""
            🚀 Advanced Speed System is RUNNING!
            
            Features:
            • Real-time speed monitoring
            • AI-powered optimization
            • Multi-interface support
            • Advanced error recovery
            • Comprehensive analytics
            
            Press Ctrl+C to stop the system.
            """)
            
            # حلقه اصلی
            last_stats_time = 0
            while self.is_running:
                await asyncio.sleep(1)
                
                # اجرای کارهای دوره‌ای هر 30 ثانیه
                current_time = asyncio.get_event_loop().time()
                if current_time - last_stats_time > 30:
                    last_stats_time = current_time
                    await self.run_periodic_tasks()
                
                # بررسی وضعیت سیستم
                if current_time % 60 < 1:  # هر دقیقه
                    status = await self.get_system_status()
                    if status['health'].get('unhealthy_count', 0) > 0:
                        logger.warning("System health issues detected")
        
        except KeyboardInterrupt:
            logger.info("👋 Received keyboard interrupt")
        except Exception as e:
            logger.error(f"💥 Fatal system error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.shutdown()

# تابع اصلی اجرا
async def main():
    """تابع اصلی اجرای سیستم"""
    parser = argparse.ArgumentParser(
        description='Advanced Speed Download/Upload System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode all --debug
  python main.py --mode api --port 8080
  python main.py --mode telegram --config custom_config.json
        """
    )
    
    parser.add_argument('--mode', 
                       choices=['all', 'api', 'telegram', 'userbot', 'core'],
                       default='all',
                       help='System operation mode')
    
    parser.add_argument('--config',
                       default='config/settings.json',
                       help='Path to configuration file')
    
    parser.add_argument('--port',
                       type=int,
                       default=8080,
                       help='API server port')
    
    parser.add_argument('--debug',
                       action='store_true',
                       help='Enable debug mode')
    
    parser.add_argument('--log-to-file',
                       action='store_true',
                       default=True,
                       help='Log to file')
    
    parser.add_argument('--no-log-to-file',
                       action='store_false',
                       dest='log_to_file',
                       help='Disable logging to file')
    
    parser.add_argument('--test',
                       action='store_true',
                       help='Run in test mode')
    
    parser.add_argument('--profile',
                       action='store_true',
                       help='Enable performance profiling')
    
    args = parser.parse_args()
    
    # تنظیم لاگ‌گیری
    setup_logging(debug=args.debug, log_to_file=args.log_to_file)
    
    # تنظیم پورت API
    if 'api_server' in config_manager.settings.dict():
        config_manager.settings['api_server']['port'] = args.port
    
    # حالت تست
    if args.test:
        logger.info("🧪 Running in test mode...")
        await run_tests()
        return
    
    # Performance profiling
    if args.profile:
        logger.info("📊 Performance profiling enabled")
        import cProfile
        profiler = cProfile.Profile()
        profiler.enable()
    
    try:
        # ایجاد و اجرای سیستم
        system = AdvancedSpeedManager(mode=args.mode)
        await system.run()
        
    except KeyboardInterrupt:
        logger.info("System stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # توقف profiling
        if args.profile:
            profiler.disable()
            profile_file = Path('performance_profile.prof')
            profiler.dump_stats(profile_file)
            logger.info(f"Profile saved to {profile_file}")

async def run_tests():
    """اجرای تست‌های سیستم"""
    import subprocess
    import sys
    
    test_modules = [
        'tests/test_monitor.py',
        'tests/test_optimizer.py',
        'tests/test_ai.py',
        'tests/test_api.py'
    ]
    
    results = []
    for test_module in test_modules:
        if Path(test_module).exists():
            logger.info(f"Running tests from {test_module}...")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_module, "-v"],
                capture_output=True,
                text=True
            )
            results.append((test_module, result.returncode))
    
    # نمایش نتایج
    logger.info("\n" + "="*50)
    logger.info("TEST RESULTS")
    logger.info("="*50)
    
    all_passed = True
    for test_module, returncode in results:
        status = "✅ PASSED" if returncode == 0 else "❌ FAILED"
        logger.info(f"{test_module}: {status}")
        if returncode != 0:
            all_passed = False
    
    if all_passed:
        logger.info("\n🎉 All tests passed!")
    else:
        logger.error("\n⚠️ Some tests failed!")
        sys.exit(1)

# اجرای مستقیم
if __name__ == "__main__":
    asyncio.run(main())
