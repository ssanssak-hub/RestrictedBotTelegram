#!/usr/bin/env python3
# session_manager_factory.py - Factory برای ایجاد Session Manager

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import signal
from dataclasses import dataclass, asdict
from enum import Enum
import traceback

from session_manager_advanced import AdvancedSessionManager, SessionConfig, SessionStatus
from config_loader import ConfigLoader, load_config

logger = logging.getLogger(__name__)

class InitPhase(Enum):
    """مراحل راه‌اندازی"""
    CONFIG_LOADING = "config_loading"
    MANAGER_CREATION = "manager_creation"
    SESSION_VALIDATION = "session_validation"
    CLEANUP = "cleanup"
    REPORTING = "reporting"
    COMPLETED = "completed"

@dataclass
class InitResult:
    """نتیجه راه‌اندازی"""
    success: bool
    manager: Optional[AdvancedSessionManager] = None
    error: Optional[str] = None
    warnings: list = None
    metrics: Dict[str, Any] = None
    duration_seconds: float = 0.0
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.metrics is None:
            self.metrics = {}

class SessionManagerFactory:
    """Factory برای ایجاد و مدیریت Session Manager"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("session_config.json")
        self.config_loader = None
        self.initialization_timeout = 30  # ثانیه
        self.max_retries = 3
        self.retry_delay = 2  # ثانیه
        
        # وضعیت factory
        self.is_initialized = False
        self.init_history = []
        self.last_init_time = None
        self.active_manager = None
        
    async def create_manager(self, 
                           config: Optional[SessionConfig] = None,
                           background_tasks: bool = True) -> InitResult:
        """
        ایجاد Session Manager با قابلیت‌های پیشرفته
        
        Args:
            config: تنظیمات اختیاری (اگر نباشد از فایل خوانده می‌شود)
            background_tasks: اجرای عملیات در پس‌زمینه
        """
        start_time = datetime.now()
        current_phase = InitPhase.CONFIG_LOADING
        warnings = []
        metrics = {}
        
        try:
            logger.info("Starting AdvancedSessionManager initialization...")
            
            # مرحله 1: بارگذاری کانفیگ
            current_phase = InitPhase.CONFIG_LOADING
            manager_config = await self._load_or_create_config(config)
            
            # مرحله 2: ایجاد مدیر
            current_phase = InitPhase.MANAGER_CREATION
            manager = await self._create_manager_instance(manager_config)
            
            # مرحله 3: اعتبارسنجی session‌ها
            current_phase = InitPhase.SESSION_VALIDATION
            validation_result = await self._validate_sessions(manager)
            warnings.extend(validation_result.get('warnings', []))
            
            # مرحله 4: عملیات اولیه (همزمان یا پس‌زمینه)
            if background_tasks:
                # اجرای عملیات سنگین در پس‌زمینه
                asyncio.create_task(self._run_background_init_tasks(manager))
            else:
                # اجرای همزمان
                await self._run_init_tasks(manager)
            
            # مرحله 5: ثبت وضعیت
            current_phase = InitPhase.COMPLETED
            self.active_manager = manager
            self.is_initialized = True
            self.last_init_time = datetime.now()
            
            # محاسبه متریک‌ها
            duration = (datetime.now() - start_time).total_seconds()
            metrics.update({
                'init_duration_seconds': duration,
                'total_sessions': len(manager.metadata.get('sessions', {})),
                'active_sessions': len([
                    s for s in manager.metadata.get('sessions', {}).values()
                    if s.get('status') == SessionStatus.ACTIVE.value
                ]),
                'warnings_count': len(warnings),
                'config_source': 'file' if config is None else 'parameter'
            })
            
            # ثبت در تاریخچه
            self.init_history.append({
                'timestamp': datetime.now().isoformat(),
                'success': True,
                'duration': duration,
                'phase': current_phase.value
            })
            
            logger.info(f"AdvancedSessionManager initialized successfully in {duration:.2f}s")
            
            return InitResult(
                success=True,
                manager=manager,
                warnings=warnings,
                metrics=metrics,
                duration_seconds=duration
            )
            
        except asyncio.TimeoutError as e:
            error_msg = f"Initialization timeout in phase {current_phase.value}: {str(e)}"
            logger.error(error_msg)
            return self._handle_init_failure(
                current_phase, error_msg, start_time, warnings
            )
            
        except Exception as e:
            error_msg = f"Initialization failed in phase {current_phase.value}: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            
            # تلاش مجدد
            if self.max_retries > 0:
                logger.info(f"Retrying initialization ({self.max_retries} attempts left)")
                await asyncio.sleep(self.retry_delay)
                self.max_retries -= 1
                return await self.create_manager(config, background_tasks)
            
            return self._handle_init_failure(
                current_phase, error_msg, start_time, warnings
            )
    
    async def _load_or_create_config(self, config: Optional[SessionConfig]) -> SessionConfig:
        """بارگذاری یا ایجاد کانفیگ"""
        if config is not None:
            logger.debug("Using provided SessionConfig")
            return config
        
        # بارگذاری از فایل
        try:
            self.config_loader = load_config()
            config_data = self.config_loader.config_data
            
            # تبدیل JSON به SessionConfig
            sm_settings = config_data.get('session_manager_settings', {})
            
            return SessionConfig(
                max_sessions=sm_settings.get('max_sessions_per_user', 5),
                session_lifetime_hours=sm_settings.get('session_lifetime_hours', 168),
                auto_rotate=sm_settings.get('auto_rotation', {}).get('enabled', True),
                rotate_after_errors=sm_settings.get('auto_rotation', {})
                    .get('error_based_rotation', {}).get('max_errors', 3),
                rotate_after_requests=sm_settings.get('auto_rotation', {})
                    .get('usage_based_rotation', {}).get('max_requests', 1000),
                backup_count=sm_settings.get('backup', {}).get('count', 10),
                encryption_enabled=sm_settings.get('encryption', {}).get('enabled', True),
                compression_enabled=sm_settings.get('backup', {})
                    .get('compression', {}).get('enabled', True),
                geo_diversity=sm_settings.get('session_creation', {})
                    .get('geo_diversity_enabled', False),
                device_rotation=sm_settings.get('session_creation', {})
                    .get('generate_device_info', True),
                use_proxy_pool=config_data.get('telethon_client_settings', {})
                    .get('proxy_settings', {}).get('enabled', False),
                enable_metrics=sm_settings.get('performance', {})
                    .get('caching', {}).get('enabled', True),
                enable_health_check=True,
                session_timeout_seconds=config_data.get('telethon_client_settings', {})
                    .get('connection', {}).get('timeout', 30),
                max_concurrent_requests=sm_settings.get('performance', {})
                    .get('resource_limits', {}).get('max_concurrent_sessions', 20),
                rate_limit_per_minute=sm_settings.get('rate_limiting', {})
                    .get('limits', {}).get('requests_per_minute', 60)
            )
            
        except Exception as e:
            logger.warning(f"Failed to load config from file: {e}. Using defaults.")
            return SessionConfig()  # پیش‌فرض
    
    async def _create_manager_instance(self, config: SessionConfig) -> AdvancedSessionManager:
        """ایجاد instance از Session Manager با timeout"""
        try:
            # ایجاد با timeout
            manager = await asyncio.wait_for(
                asyncio.to_thread(AdvancedSessionManager, config=config),
                timeout=10
            )
            logger.debug("SessionManager instance created")
            return manager
            
        except asyncio.TimeoutError:
            logger.warning("SessionManager creation timeout, retrying without timeout")
            return AdvancedSessionManager(config=config)
    
    async def _validate_sessions(self, manager: AdvancedSessionManager) -> Dict[str, Any]:
        """اعتبارسنجی session‌ها با محدودیت زمان"""
        try:
            # اعتبارسنجی با timeout
            validation = await asyncio.wait_for(
                manager.validate_all_sessions(),
                timeout=5
            )
            
            warnings = []
            if validation.get('invalid'):
                invalid_count = len(validation['invalid'])
                warnings.append(f"Found {invalid_count} invalid sessions")
                logger.warning(f"Invalid sessions: {validation['invalid']}")
            
            if validation.get('needs_attention'):
                attention_count = len(validation['needs_attention'])
                warnings.append(f"{attention_count} sessions need attention")
                
            return {
                'validation': validation,
                'warnings': warnings
            }
            
        except asyncio.TimeoutError:
            logger.warning("Session validation timeout, skipping detailed validation")
            return {'warnings': ['Session validation timed out']}
    
    async def _run_background_init_tasks(self, manager: AdvancedSessionManager):
        """اجرای عملیات اولیه در پس‌زمینه"""
        try:
            # 1. پاکسازی داده‌های قدیمی
            asyncio.create_task(self._safe_cleanup(manager))
            
            # 2. تولید گزارش اولیه
            asyncio.create_task(self._safe_generate_report(manager))
            
            # 3. شروع مانیتورینگ سلامت
            await manager._start_health_monitor()
            
        except Exception as e:
            logger.error(f"Background init tasks failed: {e}")
    
    async def _run_init_tasks(self, manager: AdvancedSessionManager):
        """اجرای عملیات اولیه به صورت همزمان"""
        try:
            # پاکسازی با محدودیت زمان
            await asyncio.wait_for(
                self._safe_cleanup(manager),
                timeout=10
            )
            
            # گزارش با محدودیت زمان
            await asyncio.wait_for(
                self._safe_generate_report(manager),
                timeout=5
            )
            
            # شروع مانیتورینگ
            await manager._start_health_monitor()
            
        except asyncio.TimeoutError:
            logger.warning("Some init tasks timed out, continuing...")
        except Exception as e:
            logger.error(f"Init tasks failed: {e}")
    
    async def _safe_cleanup(self, manager: AdvancedSessionManager) -> bool:
        """پاکسازی ایمن"""
        try:
            await manager._cleanup_old_data()
            logger.debug("Cleanup completed successfully")
            return True
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
            return False
    
    async def _safe_generate_report(self, manager: AdvancedSessionManager) -> bool:
        """تولید گزارش ایمن"""
        try:
            report = await manager.export_comprehensive_report()
            health_status = report.get('health_status', 'unknown')
            total_sessions = report.get('system_info', {}).get('total_sessions', 0)
            
            logger.info(f"Initial health status: {health_status}")
            logger.info(f"Total sessions: {total_sessions}")
            
            # ذخیره گزارش اولیه
            await self._save_initial_report(report)
            return True
            
        except Exception as e:
            logger.warning(f"Report generation failed: {e}")
            return False
    
    async def _save_initial_report(self, report: Dict[str, Any]):
        """ذخیره گزارش اولیه"""
        try:
            report_dir = Path("reports/initial")
            report_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = report_dir / f"initial_report_{timestamp}.json"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str, ensure_ascii=False)
            
            logger.debug(f"Initial report saved to {report_file}")
            
        except Exception as e:
            logger.warning(f"Failed to save initial report: {e}")
    
    def _handle_init_failure(self, phase: InitPhase, error: str, 
                           start_time: datetime, warnings: list) -> InitResult:
        """مدیریت خطای راه‌اندازی"""
        duration = (datetime.now() - start_time).total_seconds()
        
        # ثبت در تاریخچه
        self.init_history.append({
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'phase': phase.value,
            'error': error,
            'duration': duration
        })
        
        return InitResult(
            success=False,
            error=error,
            warnings=warnings,
            metrics={'init_duration_seconds': duration},
            duration_seconds=duration
        )
    
    async def shutdown_manager(self, manager: AdvancedSessionManager, force: bool = False):
        """خاموش کردن ایمن Session Manager"""
        try:
            logger.info("Shutting down SessionManager...")
            
            if force:
                # خاموش کردن فوری
                await manager.close()
            else:
                # خاموش کردن تدریجی
                await self._graceful_shutdown(manager)
            
            self.active_manager = None
            self.is_initialized = False
            logger.info("SessionManager shutdown completed")
            
        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
    
    async def _graceful_shutdown(self, manager: AdvancedSessionManager):
        """خاموش کردن تدریجی"""
        try:
            # 1. توقف مانیتورینگ
            if manager.health_check_task:
                manager.health_check_task.cancel()
                try:
                    await manager.health_check_task
                except asyncio.CancelledError:
                    pass
            
            # 2. ذخیره وضعیت نهایی
            await manager._save_encrypted_metadata()
            
            # 3. بستن connection‌ها
            await manager.close()
            
            # 4. تولید گزارش خاتمه
            await self._generate_shutdown_report(manager)
            
        except Exception as e:
            logger.warning(f"Graceful shutdown step failed: {e}")
            await manager.close()  # خاموش کردن فوری
    
    async def _generate_shutdown_report(self, manager: AdvancedSessionManager):
        """تولید گزارش خاتمه"""
        try:
            report = {
                'shutdown_time': datetime.now().isoformat(),
                'total_sessions': len(manager.metadata.get('sessions', {})),
                'active_sessions': len([
                    s for s in manager.metadata.get('sessions', {}).values()
                    if s.get('status') == SessionStatus.ACTIVE.value
                ]),
                'checks_performed': manager.metrics.get('checks_performed', 0),
                'session_rotations': manager.metrics.get('session_rotations', 0),
                'init_history': self.init_history[-5:]  # آخرین 5 رکورد
            }
            
            report_dir = Path("reports/shutdown")
            report_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = report_dir / f"shutdown_report_{timestamp}.json"
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str, ensure_ascii=False)
            
            logger.debug(f"Shutdown report saved to {report_file}")
            
        except Exception as e:
            logger.debug(f"Failed to generate shutdown report: {e}")
    
    def get_init_status(self) -> Dict[str, Any]:
        """دریافت وضعیت راه‌اندازی"""
        return {
            'is_initialized': self.is_initialized,
            'last_init_time': self.last_init_time.isoformat() if self.last_init_time else None,
            'total_init_attempts': len(self.init_history),
            'successful_inits': len([h for h in self.init_history if h.get('success')]),
            'last_error': next(
                (h['error'] for h in reversed(self.init_history) if h.get('error')), 
                None
            ),
            'active_manager': bool(self.active_manager)
        }

# ============================================
# توابع اصلی برای backward compatibility
# ============================================

_factory = SessionManagerFactory()

async def create_advanced_session_manager(
    config: Optional[SessionConfig] = None,
    background_init: bool = True,
    timeout: Optional[int] = None
) -> AdvancedSessionManager:
    """
    ایجاد instance از Session Manager پیشرفته (نسخه بهبود یافته)
    
    Args:
        config: تنظیمات دلخواه (اختیاری)
        background_init: اجرای عملیات اولیه در پس‌زمینه
        timeout: محدودیت زمان برای راه‌اندازی (ثانیه)
    
    Returns:
        AdvancedSessionManager instance
    
    Raises:
        RuntimeError: اگر راه‌اندازی ناموفق باشد
    """
    global _factory
    
    # تنظیم timeout اگر ارائه شده
    if timeout is not None:
        _factory.initialization_timeout = timeout
    
    # ایجاد مدیر
    result = await _factory.create_manager(config, background_init)
    
    if not result.success:
        raise RuntimeError(f"Failed to create SessionManager: {result.error}")
    
    if result.warnings:
        for warning in result.warnings:
            logger.warning(f"Init warning: {warning}")
    
    logger.info(
        f"SessionManager created successfully in {result.duration_seconds:.2f}s. "
        f"Sessions: {result.metrics.get('total_sessions', 0)}"
    )
    
    return result.manager

async def shutdown_all_managers(force: bool = False):
    """خاموش کردن تمام مدیران"""
    global _factory
    
    if _factory.active_manager:
        await _factory.shutdown_manager(_factory.active_manager, force)
    
    logger.info("All managers shutdown")

def get_session_manager_status() -> Dict[str, Any]:
    """دریافت وضعیت مدیر session"""
    global _factory
    return _factory.get_init_status()

# ============================================
# Context Manager برای مدیریت خودکار
# ============================================

class SessionManagerContext:
    """Context Manager برای مدیریت خودکار Session Manager"""
    
    def __init__(self, config: Optional[SessionConfig] = None, 
                 background_init: bool = True):
        self.config = config
        self.background_init = background_init
        self.manager = None
    
    async def __aenter__(self) -> AdvancedSessionManager:
        """ورود به context"""
        self.manager = await create_advanced_session_manager(
            config=self.config,
            background_init=self.background_init
        )
        return self.manager
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """خروج از context"""
        if self.manager:
            try:
                await shutdown_all_managers(force=(exc_type is not None))
            except Exception as e:
                logger.error(f"Error during context exit: {e}")
        
        # اگر خطایی رخ داده، آن را دوباره raise کن
        return False

# ============================================
# مثال استفاده
# ============================================

async def example_usage():
    """مثال استفاده از توابع جدید"""
    
    # روش 1: استفاده مستقیم
    try:
        manager = await create_advanced_session_manager(
            background_init=True,
            timeout=30
        )
        
        # استفاده از مدیر
        report = await manager.export_comprehensive_report()
        print(f"System health: {report['health_status']}")
        
        # خاموش کردن
        await shutdown_all_managers()
        
    except RuntimeError as e:
        print(f"Failed: {e}")
    
    # روش 2: استفاده با Context Manager
    async with SessionManagerContext(background_init=True) as manager:
        # انجام عملیات
        sessions = await manager.validate_all_sessions()
        print(f"Valid sessions: {len(sessions.get('valid', []))}")
    
    # روش 3: استفاده با factory
    factory = SessionManagerFactory()
    result = await factory.create_manager()
    
    if result.success:
        print(f"Manager created with {result.metrics['total_sessions']} sessions")
        await factory.shutdown_manager(result.manager)

async def quick_start():
    """راه‌اندازی سریع برای محیط production"""
    from session_manager_advanced import SessionConfig
    
    # تنظیمات production
    prod_config = SessionConfig(
        max_sessions=5,
        session_lifetime_hours=168,
        encryption_enabled=True,
        auto_rotate=True,
        backup_count=15,
        enable_health_check=True,
        rate_limit_per_minute=30
    )
    
    # راه‌اندازی با timeout
    try:
        manager = await asyncio.wait_for(
            create_advanced_session_manager(
                config=prod_config,
                background_init=True
            ),
            timeout=15
        )
        
        # بررسی وضعیت
        status = get_session_manager_status()
        print(f"Manager status: {status}")
        
        return manager
        
    except asyncio.TimeoutError:
        logger.error("Startup timeout")
        raise
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

if __name__ == "__main__":
    # اجرای مثال
    import asyncio
    asyncio.run(example_usage())
