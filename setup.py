#!/usr/bin/env python3
"""
اسکریپت تنظیم و نصب کامل سیستم
"""

import subprocess
import sys
import platform
import os
import json
from pathlib import Path
from typing import Dict, List, Optional

class DependencyInstaller:
    """نصب کننده هوشمند dependencyها"""
    
    def __init__(self):
        self.os_name = platform.system()
        self.python_version = sys.version_info
        self.project_root = Path.cwd()
        
        # دسته‌بندی dependencyها
        self.dependency_groups = {
            'core': [
                'asyncio', 'aiohttp', 'aiofiles', 'cryptography',
                'python-dotenv', 'psutil', 'colorlog'
            ],
            'telegram': [
                'telethon', 'python-telegram-bot', 'aiogram'
            ],
            'database': [
                'aiosqlite', 'sqlalchemy', 'redis', 'msgpack', 'alembic'
            ],
            'compression': [
                'brotli', 'zstandard', 'lz4'
            ],
            'ai': [
                'torch', 'torchvision', 'numpy', 'scikit-learn',
                'pandas', 'joblib', 'tensorflow'
            ],
            'config': [
                'pydantic', 'pydantic-settings', 'pyyaml', 'tomli', 'watchdog'
            ],
            'api': [
                'fastapi', 'uvicorn[standard]', 'jinja2', 'python-multipart',
                'flask', 'flask-cors', 'flask-admin'
            ],
            'monitoring': [
                'prometheus-client'
            ],
            'development': [
                'pytest', 'pytest-asyncio', 'pytest-cov', 'pytest-mock',
                'black', 'flake8', 'mypy', 'isort', 'autopep8', 'pre-commit',
                'ipython', 'ipdb', 'debugpy', 'sphinx', 'sphinx-rtd-theme'
            ],
            'utilities': [
                'pillow', 'requests', 'click', 'tqdm', 'humanize',
                'gunicorn', 'speedtest-cli'
            ]
        }
        
        self.optional_groups = {
            'cloud': ['boto3', 'google-cloud-storage'],
            'file_processing': ['pypdf', 'python-pptx', 'openpyxl'],
            'communication': ['qrcode', 'phonenumbers', 'python-magic'],
            'reporting': ['reportlab', 'matplotlib', 'seaborn'],
            'network': ['paramiko', 'pysftp']
        }
    
    def check_system(self):
        """بررسی سیستم"""
        print("=" * 60)
        print("🖥️  System Information")
        print("=" * 60)
        print(f"OS: {self.os_name}")
        print(f"Python: {self.python_version.major}.{self.python_version.minor}.{self.python_version.micro}")
        print(f"Architecture: {platform.machine()}")
        print(f"Processor: {platform.processor()}")
        print("=" * 60)
        
        # بررسی حداقل requirements
        if self.python_version.major < 3 or (self.python_version.major == 3 and self.python_version.minor < 8):
            print("❌ Python 3.8 or higher is required")
            sys.exit(1)
        
        # بررسی virtual environment
        if 'VIRTUAL_ENV' not in os.environ:
            print("⚠️  Not running in a virtual environment")
            print("   Consider using: python -m venv venv")
            if input("Create virtual environment? (y/N): ").lower() == 'y':
                self.create_virtual_environment()
        
        return True
    
    def create_virtual_environment(self):
        """ایجاد virtual environment"""
        print("🔧 Creating virtual environment...")
        
        try:
            subprocess.check_call([sys.executable, "-m", "venv", "venv"])
            print("✅ Virtual environment created")
            
            # فعال‌سازی venv
            if self.os_name == "Windows":
                activate_script = self.project_root / "venv" / "Scripts" / "activate"
            else:
                activate_script = self.project_root / "venv" / "bin" / "activate"
            
            print(f"\n📝 To activate:")
            print(f"   Windows: {activate_script}")
            print(f"   Linux/Mac: source {activate_script}")
            print("\n⚠️  Please activate the virtual environment and run this script again.")
            sys.exit(0)
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create virtual environment: {e}")
            return False
    
    def upgrade_pip(self):
        """آپگرید pip"""
        print("⬆️  Upgrading pip...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
            print("✅ pip upgraded")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to upgrade pip: {e}")
    
    def install_group(self, group_name: str, packages: List[str]):
        """نصب یک گروه از packages"""
        print(f"\n📦 Installing {group_name} packages...")
        
        for package in packages:
            print(f"  • {package}")
        
        # نصب همه با هم برای کارایی بهتر
        cmd = [sys.executable, "-m", "pip", "install"] + packages
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"✅ {group_name} installed successfully")
                return True
            else:
                print(f"⚠️  Some packages in {group_name} failed to install")
                print(f"   Error: {result.stderr[:200]}")
                return False
        except Exception as e:
            print(f"❌ Failed to install {group_name}: {e}")
            return False
    
    def install_torch(self):
        """نصب PyTorch مناسب برای سیستم"""
        print("\n🤖 Installing PyTorch...")
        
        if self.os_name == "Windows":
            torch_cmd = [
                sys.executable, "-m", "pip", "install",
                "torch==2.1.2+cpu", "torchvision==0.16.2+cpu",
                "-f", "https://download.pytorch.org/whl/torch_stable.html"
            ]
        elif self.os_name == "Darwin":  # macOS
            if platform.machine() == "arm64":  # Apple Silicon
                torch_cmd = [
                    sys.executable, "-m", "pip", "install",
                    "torch==2.1.2", "torchvision==0.16.2"
                ]
            else:  # Intel
                torch_cmd = [
                    sys.executable, "-m", "pip", "install",
                    "torch==2.1.2", "torchvision==0.16.2"
                ]
        else:  # Linux
            torch_cmd = [
                sys.executable, "-m", "pip", "install",
                "torch==2.1.2", "torchvision==0.16.2"
            ]
        
        try:
            subprocess.check_call(torch_cmd)
            print("✅ PyTorch installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install PyTorch: {e}")
            return False
    
    def create_config_files(self):
        """ایجاد فایل‌های پیکربندی اولیه"""
        print("\n⚙️  Creating configuration files...")
        
        config_dir = self.project_root / "config"
        config_dir.mkdir(exist_ok=True)
        
        # فایل تنظیمات اصلی
        settings = {
            "bot": {
                "enabled": True,
                "bot_token": "YOUR_BOT_TOKEN_HERE",
                "api_id": "YOUR_API_ID",
                "api_hash": "YOUR_API_HASH"
            },
            "userbot": {
                "enabled": False,
                "api_id": "",
                "api_hash": "",
                "phone_number": ""
            },
            "database": {
                "path": "data/database.db",
                "backup_interval": 3600
            },
            "speed": {
                "max_connections": 10,
                "chunk_size_mb": 5,
                "enable_compression": True
            },
            "limits": {
                "max_file_size_mb": 2048,
                "daily_download_limit_mb": 10240,
                "max_concurrent_downloads": 3
            },
            "monitoring": {
                "enable_metrics": True,
                "metrics_port": 9090,
                "update_interval_ms": 500
            },
            "security": {
                "encryption_enabled": False,
                "allowed_file_types": [".*"],
                "blocked_file_types": [".exe", ".bat", ".sh"]
            }
        }
        
        settings_file = config_dir / "settings.json"
        with open(settings_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        print(f"✅ Created {settings_file}")
        
        # فایل .env
        env_content = """# Telegram API Configuration
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
API_ID=YOUR_API_ID
API_HASH=YOUR_API_HASH

# Database
DATABASE_URL=sqlite+aiosqlite:///data/database.db
REDIS_URL=redis://localhost:6379/0

# Security
ENCRYPTION_KEY=GENERATE_A_SECURE_KEY_HERE
SESSION_ENCRYPTION_KEY=ANOTHER_SECURE_KEY_HERE

# Limits
MAX_FILE_SIZE_MB=2048
DAILY_DOWNLOAD_LIMIT_MB=10240

# Monitoring
ENABLE_METRICS=true
METRICS_PORT=9090

# Logging
LOG_LEVEL=INFO
LOG_TO_FILE=true
"""
        
        env_file = self.project_root / ".env.example"
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_content)
        print(f"✅ Created {env_file}")
        
        # ایجاد دایرکتوری‌ها
        directories = ['data', 'logs', 'cache', 'downloads', 'uploads', 'temp', 'backups']
        for dir_name in directories:
            dir_path = self.project_root / dir_name
            dir_path.mkdir(exist_ok=True)
            print(f"✅ Created directory: {dir_name}")
    
    def show_install_menu(self):
        """نمایش منوی نصب"""
        print("\n" + "=" * 60)
        print("📦 Installation Menu")
        print("=" * 60)
        print("1. 🚀 Full Installation (Everything)")
        print("2. ⚡ Production Installation (Core + Telegram + API)")
        print("3. 💻 Development Installation (Full + Dev Tools)")
        print("4. 📱 Minimal Installation (Core only)")
        print("5. 🔧 Custom Installation (Choose packages)")
        print("6. ❌ Exit")
        print("=" * 60)
        
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == "1":
            return self.install_full()
        elif choice == "2":
            return self.install_production()
        elif choice == "3":
            return self.install_development()
        elif choice == "4":
            return self.install_minimal()
        elif choice == "5":
            return self.install_custom()
        elif choice == "6":
            print("👋 Goodbye!")
            sys.exit(0)
        else:
            print("❌ Invalid choice")
            return False
    
    def install_full(self):
        """نصب کامل"""
        print("\n🚀 Installing FULL package...")
        
        # آپگرید pip
        self.upgrade_pip()
        
        # نصب گروه‌های اصلی
        groups_to_install = [
            'core', 'telegram', 'database', 'compression',
            'config', 'api', 'monitoring', 'utilities'
        ]
        
        for group in groups_to_install:
            if group in self.dependency_groups:
                self.install_group(group, self.dependency_groups[group])
        
        # نصب AI (ممکن است زمان‌بر باشد)
        if input("\nInstall AI/ML packages? (y/N): ").lower() == 'y':
            self.install_torch()
            self.install_group('ai', self.dependency_groups['ai'][2:])  # همه به جز torch
        
        # نصب optional packages
        if input("\nInstall optional packages? (y/N): ").lower() == 'y':
            for group_name, packages in self.optional_groups.items():
                if input(f"Install {group_name} packages? (y/N): ").lower() == 'y':
                    self.install_group(group_name, packages)
        
        return True
    
    def install_production(self):
        """نصب برای production"""
        print("\n⚡ Installing PRODUCTION package...")
        
        self.upgrade_pip()
        
        groups_to_install = [
            'core', 'telegram', 'database', 'compression',
            'config', 'api', 'monitoring', 'utilities'
        ]
        
        for group in groups_to_install:
            if group in self.dependency_groups:
                self.install_group(group, self.dependency_groups[group])
        
        return True
    
    def install_development(self):
        """نصب برای توسعه"""
        print("\n💻 Installing DEVELOPMENT package...")
        
        # اول production packages
        self.install_production()
        
        # سپس development packages
        print("\n🔧 Installing development tools...")
        self.install_group('development', self.dependency_groups['development'])
        
        return True
    
    def install_minimal(self):
        """نصب حداقلی"""
        print("\n📱 Installing MINIMAL package...")
        
        self.upgrade_pip()
        
        # فقط core و telegram
        self.install_group('core', self.dependency_groups['core'])
        self.install_group('telegram', self.dependency_groups['telegram'])
        
        return True
    
    def install_custom(self):
        """نصب سفارشی"""
        print("\n🔧 Custom Installation")
        print("=" * 60)
        
        selected_groups = []
        
        for group_name, packages in self.dependency_groups.items():
            if input(f"\nInstall {group_name} packages? (y/N): ").lower() == 'y':
                selected_groups.append((group_name, packages))
        
        for optional_group, packages in self.optional_groups.items():
            if input(f"\nInstall {optional_group} packages? (y/N): ").lower() == 'y':
                selected_groups.append((optional_group, packages))
        
        if not selected_groups:
            print("❌ No packages selected")
            return False
        
        self.upgrade_pip()
        
        for group_name, packages in selected_groups:
            self.install_group(group_name, packages)
        
        return True
    
    def run_post_install(self):
        """اجرای کارهای پس از نصب"""
        print("\n" + "=" * 60)
        print("🔧 Post-installation setup")
        print("=" * 60)
        
        # ایجاد فایل‌های پیکربندی
        if input("Create configuration files? (y/N): ").lower() == 'y':
            self.create_config_files()
        
        # ایجاد ساختار دایرکتوری‌ها
        print("\n📁 Creating directory structure...")
        directories = ['data', 'logs', 'cache', 'downloads', 'uploads', 'temp', 'backups', 'config']
        for dir_name in directories:
            dir_path = self.project_root / dir_name
            dir_path.mkdir(exist_ok=True)
        
        print("✅ Directory structure created")
        
        # نمایش دستورات بعدی
        print("\n" + "=" * 60)
        print("🎉 Installation completed!")
        print("=" * 60)
        print("\n📋 Next steps:")
        print("1. Configure your settings in config/settings.json")
        print("2. Copy .env.example to .env and fill in your credentials")
        print("3. Run the system:")
        print("   python main.py --mode standard")
        print("\n📚 Documentation:")
        print("   Read docs/GETTING_STARTED.md for detailed instructions")
        print("=" * 60)
    
    def run(self):
        """اجرای اصلی"""
        print("=" * 60)
        print("🚀 Telegram Speed System - Complete Installer")
        print("=" * 60)
        
        # بررسی سیستم
        self.check_system()
        
        # نمایش منو و نصب
        if self.show_install_menu():
            self.run_post_install()
        else:
            print("❌ Installation failed")
            sys.exit(1)

def main():
    """تابع اصلی"""
    installer = DependencyInstaller()
    installer.run()

if __name__ == "__main__":
    main()
