#!/usr/bin/env python3
# session_monitor.py - مانیتور وضعیت session‌ها

import asyncio
import json
import logging
from datetime import datetime
import psutil
from session_manager import create_session_manager

logger = logging.getLogger(__name__)

class SessionMonitor:
    """مانیتور وضعیت session‌ها"""
    
    def __init__(self, check_interval: int = 300):  # 5 دقیقه
        self.check_interval = check_interval
        self.session_manager = None
        self.monitoring_data = {
            'start_time': datetime.now().isoformat(),
            'checks': 0,
            'alerts': [],
            'metrics': []
        }
    
    async def start_monitoring(self):
        """شروع مانیتورینگ"""
        logger.info("Starting session monitor...")
        
        self.session_manager = await create_session_manager()
        
        while True:
            try:
                await self.perform_check()
                await asyncio.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Monitor check failed: {e}")
                await asyncio.sleep(60)
    
    async def perform_check(self):
        """انجام بررسی دوره‌ای"""
        self.monitoring_data['checks'] += 1
        
        # جمع‌آوری متریک‌ها
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'system': self._get_system_metrics(),
            'sessions': await self._get_session_metrics(),
            'alerts': []
        }
        
        # بررسی هشدارها
        alerts = await self._check_alerts(metrics)
        metrics['alerts'] = alerts
        
        if alerts:
            logger.warning(f"Found {len(alerts)} alerts")
            for alert in alerts:
                logger.warning(f"  - {alert['type']}: {alert['message']}")
        
        # ذخیره متریک
        self.monitoring_data['metrics'].append(metrics)
        
        # حفظ فقط آخرین 1000 رکورد
        if len(self.monitoring_data['metrics']) > 1000:
            self.monitoring_data['metrics'] = self.monitoring_data['metrics'][-1000:]
        
        logger.debug(f"Check #{self.monitoring_data['checks']} completed")
    
    def _get_system_metrics(self) -> dict:
        """دریافت متریک‌های سیستم"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024**3),
                'disk_percent': disk.percent,
                'disk_free_gb': disk.free / (1024**3)
            }
        except:
            return {}
    
    async def _get_session_metrics(self) -> dict:
        """دریافت متریک‌های session"""
        if not self.session_manager:
            return {}
        
        report = await self.session_manager.export_session_report()
        
        # محاسبه متریک‌های مهم
        sessions = report.get('sessions', [])
        active_sessions = [s for s in sessions if s.get('is_active')]
        
        return {
            'total_sessions': len(sessions),
            'active_sessions': len(active_sessions),
            'avg_usage_count': (
                sum(s.get('usage_count', 0) for s in sessions) / len(sessions)
                if sessions else 0
            ),
            'error_rate': (
                sum(s.get('error_count', 0) for s in sessions) / 
                sum(s.get('usage_count', 1) for s in sessions)
                if sessions else 0
            ),
            'oldest_session_days': max(
                (s.get('age_days', 0) for s in sessions),
                default=0
            )
        }
    
    async def _check_alerts(self, metrics: dict) -> list:
        """بررسی شرایط هشدار"""
        alerts = []
        
        # بررسی session‌ها
        session_metrics = metrics.get('sessions', {})
        
        if session_metrics.get('total_sessions', 0) == 0:
            alerts.append({
                'type': 'critical',
                'message': 'No sessions available',
                'timestamp': datetime.now().isoformat()
            })
        
        if session_metrics.get('error_rate', 0) > 0.3:  # 30% خطا
            alerts.append({
                'type': 'warning',
                'message': f'High error rate: {session_metrics["error_rate"]:.1%}',
                'timestamp': datetime.now().isoformat()
            })
        
        if session_metrics.get('oldest_session_days', 0) > 30:
            alerts.append({
                'type': 'info',
                'message': f'Old session detected: {session_metrics["oldest_session_days"]} days',
                'timestamp': datetime.now().isoformat()
            })
        
        # بررسی سیستم
        system_metrics = metrics.get('system', {})
        
        if system_metrics.get('disk_percent', 0) > 90:
            alerts.append({
                'type': 'warning',
                'message': f'Low disk space: {system_metrics["disk_percent"]}% used',
                'timestamp': datetime.now().isoformat()
            })
        
        if system_metrics.get('memory_percent', 0) > 90:
            alerts.append({
                'type': 'warning',
                'message': f'High memory usage: {system_metrics["memory_percent"]}%',
                'timestamp': datetime.now().isoformat()
            })
        
        return alerts
    
    async def get_monitoring_report(self) -> dict:
        """دریافت گزارش مانیتورینگ"""
        return {
            'monitoring': self.monitoring_data,
            'current_status': await self._get_current_status(),
            'recommendations': await self._generate_recommendations()
        }
    
    async def _get_current_status(self) -> dict:
        """دریافت وضعیت فعلی"""
        if not self.session_manager:
            return {'status': 'not_initialized'}
        
        try:
            report = await self.session_manager.export_session_report()
            
            # ارزیابی وضعیت
            sessions = report.get('sessions', [])
            active_sessions = [s for s in sessions if s.get('is_active')]
            
            if not active_sessions:
                status = 'critical'
            elif any(s.get('error_count', 0) > 10 for s in sessions):
                status = 'warning'
            else:
                status = 'healthy'
            
            return {
                'status': status,
                'active_sessions': len(active_sessions),
                'total_sessions': len(sessions),
                'last_rotation': (
                    report.get('rotation_history', [])[-1]['timestamp']
                    if report.get('rotation_history') else None
                )
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def _generate_recommendations(self) -> list:
        """تولید توصیه‌ها"""
        recommendations = []
        
        if not self.session_manager:
            return recommendations
        
        report = await self.session_manager.export_session_report()
        sessions = report.get('sessions', [])
        
        # توصیه بر اساس تعداد session
        if len(sessions) < 2:
            recommendations.append({
                'priority': 'high',
                'action': 'create_more_sessions',
                'reason': 'Only one session available. Create backup sessions.',
                'details': 'Run: python enhanced_userbot.py --action rotate'
            })
        
        # توصیه بر اساس خطاها
        high_error_sessions = [
            s for s in sessions 
            if s.get('error_count', 0) > 5
        ]
        
        for session in high_error_sessions:
            recommendations.append({
                'priority': 'medium',
                'action': 'investigate_session',
                'reason': f'Session {session["name"]} has {session["error_count"]} errors',
                'details': f'Check logs for session: {session["name"]}'
            })
        
        # توصیه بر اساس سن session
        old_sessions = [
            s for s in sessions 
            if s.get('age_days', 0) > 20
        ]
        
        for session in old_sessions:
            recommendations.append({
                'priority': 'low',
                'action': 'rotate_old_session',
                'reason': f'Session {session["name"]} is {session["age_days"]} days old',
                'details': 'Consider rotating to a fresh session'
            })
        
        return recommendations

# تابع اصلی مانیتور
async def main():
    """اجرای مانیتور"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Session Monitor')
    parser.add_argument('--interval', type=int, default=300,
                       help='Check interval in seconds')
    parser.add_argument('--report', action='store_true',
                       help='Generate and print report')
    parser.add_argument('--daemon', action='store_true',
                       help='Run as daemon')
    
    args = parser.parse_args()
    
    monitor = SessionMonitor(check_interval=args.interval)
    
    if args.report:
        await monitor.start_monitoring()
        report = await monitor.get_monitoring_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    
    elif args.daemon:
        logger.info("Starting monitor daemon...")
        await monitor.start_monitoring()
    
    else:
        # اجرای یکبار بررسی
        await monitor.perform_check()
        report = await monitor.get_monitoring_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
