#!/usr/bin/env python3
# secure_account_login.py - سیستم ورود امن پیشرفته

import asyncio
import json
import logging
import getpass
import secrets
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

# کتابخانه‌های امنیتی
try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    print("⚠️ Run: pip install cryptography")

try:
    from telethon import TelegramClient
    from telethon.sessions import SQLiteSession
    from telethon.errors import (
        SessionPasswordNeededError,
        PhoneCodeInvalidError,
        PhoneNumberInvalidError,
        FloodWaitError,
        AuthKeyDuplicatedError
    )
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False
    print("⚠️ Run: pip install telethon")

logger = logging.getLogger(__name__)

@dataclass
class SecurityConfig:
    """تنظیمات امنیتی"""
    max_login_attempts: int = 3
    lockout_duration_minutes: int = 30
    session_expiry_days: int = 7
    auto_logout_hours: int = 24
    encrypt_sessions: bool = True
    require_2fa_backup: bool = True
    enable_geo_check: bool = True
    enable_device_fingerprint: bool = True
    rate_limit_per_minute: int = 3
    password_min_length: int = 8

class SessionEncryption:
    """رمزنگاری session"""
    
    def __init__(self, master_key: Optional[str] = None):
        if not HAS_CRYPTOGRAPHY:
            raise ImportError("Cryptography library required")
        
        if master_key:
            self.key = self._derive_key(master_key.encode())
        else:
            import secrets
            self.key = Fernet.generate_key()
        
        self.cipher = Fernet(self.key)
    
    def _derive_key(self, password: bytes, salt: bytes = None) -> bytes:
        """استخراج کلید از رمز"""
        if salt is None:
            salt = secrets.token_bytes(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return base64.urlsafe_b64encode(kdf.derive(password))
    
    def encrypt_session(self, session_data: bytes) -> Tuple[bytes, bytes]:
        """رمزنگاری session"""
        return self.cipher.encrypt(session_data), secrets.token_bytes(12)
    
    def decrypt_session(self, encrypted_data: bytes) -> bytes:
        """رمزگشایی session"""
        return self.cipher.decrypt(encrypted_data)

class SecureAccountLogin:
    """
    سیستم ورود امن پیشرفته
    """
    
    def __init__(self, base_dir: Path = Path("accounts"), 
                 security_config: Optional[SecurityConfig] = None):
        
        self.base_dir = base_dir
        self.sessions_dir = base_dir / "sessions"
        self.credentials_dir = base_dir / "credentials"
        self.lock_dir = base_dir / "locks"
        self.encrypted_dir = base_dir / "encrypted"
        
        # ایجاد پوشه‌ها
        for directory in [self.base_dir, self.sessions_dir, 
                         self.credentials_dir, self.lock_dir,
                         self.encrypted_dir]:
            directory.mkdir(exist_ok=True, mode=0o700)  # محدودیت دسترسی
        
        # تنظیمات امنیتی
        self.security = security_config or SecurityConfig()
        
        # سیستم رمزنگاری
        self.encryption = None
        if self.security.encrypt_sessions and HAS_CRYPTOGRAPHY:
            self.encryption = SessionEncryption()
        
        # Rate limiting
        self.login_attempts: Dict[str, List[datetime]] = {}
        
        logger.info("SecureAccountLogin initialized")
    
    def _get_client_info(self) -> Dict[str, str]:
        """اطلاعات دستگاه برای fingerprinting"""
        import platform
        import uuid
        
        return {
            'platform': platform.platform(),
            'processor': platform.processor(),
            'machine': platform.machine(),
            'python_version': platform.python_version(),
            'device_id': str(uuid.getnode()),
            'login_timestamp': datetime.now().isoformat()
        }
    
    async def _safe_connect(self, client: TelegramClient, 
                          max_retries: int = 3) -> bool:
        """اتصال امن با retry"""
        for attempt in range(max_retries):
            try:
                await client.connect()
                return True
            except Exception as e:
                logger.warning(f"Connection attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return False
    
    def _validate_phone_number(self, phone: str) -> bool:
        """اعتبارسنجی شماره تلفن"""
        import re
        
        patterns = [
            r'^\+[1-9]\d{1,14}$',  # E.164
            r'^\+98[0-9]{10}$',     # ایران
            r'^0[0-9]{10}$',        # ایران بدون +
        ]
        
        for pattern in patterns:
            if re.match(pattern, phone):
                return True
        
        return False
    
    async def login_with_phone(
        self,
        api_id: int,
        api_hash: str,
        phone: Optional[str] = None,
        session_name: Optional[str] = None,
        proxy: Optional[Dict] = None,
        device_info: Optional[Dict] = None
    ) -> Optional[TelegramClient]:
        """
        ورود امن با شماره تلفن
        """
        # درخواست شماره اگر داده نشده
        if not phone:
            phone = await self._get_phone_input()
        
        # اعتبارسنجی شماره
        if not self._validate_phone_number(phone):
            print("❌ شماره تلفن نامعتبر است")
            return None
        
        # بررسی rate limiting
        if not self._check_rate_limit(phone):
            print("⏳ لطفاً چند دقیقه صبر کنید و دوباره تلاش کنید")
            return None
        
        # ایجاد نام session
        if not session_name:
            timestamp = int(datetime.now().timestamp())
            phone_hash = hashlib.sha256(phone.encode()).hexdigest()[:8]
            session_name = f"user_{phone_hash}_{timestamp}"
        
        session_path = self.sessions_dir / f"{session_name}.session"
        
        # اطلاعات دستگاه
        if not device_info:
            device_info = self._get_client_info()
        
        try:
            # ایجاد کلاینت
            client = TelegramClient(
                session=str(session_path),
                api_id=api_id,
                api_hash=api_hash,
                device_model=device_info.get('device_model', 'Unknown'),
                system_version=device_info.get('system_version', '1.0'),
                app_version=device_info.get('app_version', '1.0'),
                lang_code='fa',
                system_lang_code='fa-IR',
                proxy=proxy
            )
            
            # اتصال امن
            if not await self._safe_connect(client):
                print("❌ خطا در اتصال به تلگرام")
                return None
            
            # بررسی session موجود
            if await client.is_user_authorized():
                print("✅ با session موجود وارد شدید")
                return client
            
            # درخواست کد تأیید
            print(f"\n📨 ارسال کد به {phone}...")
            
            try:
                sent = await client.send_code_request(phone)
                phone_code_hash = sent.phone_code_hash
            except FloodWaitError as e:
                print(f"⏳ لطفاً {e.seconds} ثانیه صبر کنید")
                self._update_rate_limit(phone, True)
                return None
            except Exception as e:
                print(f"❌ خطا: {e}")
                return None
            
            # دریافت کد از کاربر
            code = await self._get_code_input(phone)
            
            # تلاش برای ورود
            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash
                )
                print("✅ ورود موفق با کد تأیید")
                
            except SessionPasswordNeededError:
                # نیاز به رمز دو مرحله‌ای
                password = await self._get_2fa_password()
                
                try:
                    await client.sign_in(password=password)
                    print("✅ ورود موفق با رمز دو مرحله‌ای")
                except Exception as e:
                    print(f"❌ رمز دو مرحله‌ای نامعتبر: {e}")
                    return None
            
            except PhoneCodeInvalidError:
                print("❌ کد تأیید نامعتبر")
                self._update_rate_limit(phone, False)
                return None
            
            # تأیید ورود موفق
            if await client.is_user_authorized():
                print(f"\n🎉 ورود موفقیت‌آمیز!")
                
                # ذخیره اطلاعات
                await self._save_account_secure(client, phone, session_name, device_info)
                
                # رمزنگاری session اگر فعال باشد
                if self.encryption:
                    await self._encrypt_session(session_path)
                
                # پاکسازی rate limit
                self._clear_rate_limit(phone)
                
                return client
            
        except AuthKeyDuplicatedError:
            print("❌ این اکانت در دستگاه دیگری وارد شده است")
        except Exception as e:
            print(f"❌ خطای ناشناخته: {e}")
            logger.exception("Login error")
        
        return None
    
    def _check_rate_limit(self, identifier: str) -> bool:
        """بررسی rate limit"""
        if identifier not in self.login_attempts:
            return True
        
        # حذف تلاش‌های قدیمی
        cutoff = datetime.now() - timedelta(minutes=1)
        attempts = [t for t in self.login_attempts[identifier] if t > cutoff]
        
        if len(attempts) >= self.security.rate_limit_per_minute:
            return False
        
        return True
    
    def _update_rate_limit(self, identifier: str, success: bool):
        """به‌روزرسانی rate limit"""
        if identifier not in self.login_attempts:
            self.login_attempts[identifier] = []
        
        self.login_attempts[identifier].append(datetime.now())
        
        # حذف لیست اگر بیش از حد بزرگ شود
        if len(self.login_attempts[identifier]) > 100:
            self.login_attempts[identifier] = self.login_attempts[identifier][-50:]
    
    def _clear_rate_limit(self, identifier: str):
        """پاکسازی rate limit"""
        if identifier in self.login_attempts:
            del self.login_attempts[identifier]
    
    async def _get_phone_input(self) -> str:
        """دریافت شماره تلفن از کاربر"""
        import re
        
        while True:
            print("\n📱 لطفاً شماره تلفن خود را وارد کنید:")
            print("فرمت: +989123456789 یا 09123456789")
            print("برای لغو: exit")
            
            phone = input("شماره: ").strip()
            
            if phone.lower() == 'exit':
                raise KeyboardInterrupt("ورود لغو شد")
            
            # نرمال‌سازی
            if phone.startswith('0'):
                phone = '+98' + phone[1:]
            elif not phone.startswith('+'):
                phone = '+' + phone
            
            # اعتبارسنجی
            if self._validate_phone_number(phone):
                return phone
            
            print("❌ شماره نامعتبر است. لطفاً دوباره تلاش کنید.")
    
    async def _get_code_input(self, phone: str) -> str:
        """دریافت کد تأیید از کاربر"""
        import re
        
        while True:
            print(f"\n📨 کد تأیید به {phone} ارسال شد")
            print("لطفاً کد ۵ رقمی را وارد کنید:")
            print("برای ارسال مجدد کد: resend")
            print("برای لغو: exit")
            
            code = input("کد: ").strip()
            
            if code.lower() == 'exit':
                raise KeyboardInterrupt("ورود لغو شد")
            elif code.lower() == 'resend':
                return 'resend'
            
            if re.match(r'^\d{5}$', code):
                return code
            
            print("❌ کد باید ۵ رقم باشد. لطفاً دوباره تلاش کنید.")
    
    async def _get_2fa_password(self) -> str:
        """دریافت رمز دو مرحله‌ای"""
        while True:
            print("\n🔒 لطفاً رمز دو مرحله‌ای را وارد کنید:")
            print("برای لغو: exit")
            
            password = getpass.getpass("رمز: ")
            
            if password.lower() == 'exit':
                raise KeyboardInterrupt("ورود لغو شد")
            
            if len(password) >= self.security.password_min_length:
                return password
            
            print(f"❌ رمز باید حداقل {self.security.password_min_length} کاراکتر باشد.")
    
    async def _save_account_secure(self, client: TelegramClient, phone: str, 
                                  session_name: str, device_info: Dict):
        """ذخیره ایمن اطلاعات اکانت"""
        try:
            me = await client.get_me()
            
            account_info = {
                'session_name': session_name,
                'phone_hash': hashlib.sha256(phone.encode()).hexdigest(),
                'user_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'phone': phone,
                'is_bot': me.bot,
                'premium': me.premium,
                'login_time': datetime.now().isoformat(),
                'device_fingerprint': device_info,
                'security_level': 'high',
                'last_backup': None,
                'backup_codes': []  # برای backup کدهای 2FA
            }
            
            # ذخیره به صورت رمز شده
            if self.encryption:
                encrypted_data, nonce = self.encryption.encrypt_session(
                    json.dumps(account_info).encode()
                )
                
                save_data = {
                    'encrypted': base64.b64encode(encrypted_data).decode(),
                    'nonce': base64.b64encode(nonce).decode(),
                    'version': '1.0'
                }
            else:
                save_data = account_info
            
            # ذخیره در فایل
            info_file = self.credentials_dir / f"{session_name}.secure"
            with open(info_file, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
            
            # محدودیت دسترسی فایل
            os.chmod(info_file, 0o600)
            
            logger.info(f"Account info saved securely: {session_name}")
            
        except Exception as e:
            logger.error(f"Error saving account info: {e}")
    
    async def _encrypt_session(self, session_path: Path):
        """رمزنگاری فایل session"""
        if not self.encryption:
            return
        
        try:
            # خواندن session
            with open(session_path, 'rb') as f:
                session_data = f.read()
            
            # رمزنگاری
            encrypted_data, nonce = self.encryption.encrypt_session(session_data)
            
            # ذخیره در فایل جداگانه
            encrypted_file = self.encrypted_dir / f"{session_path.name}.enc"
            with open(encrypted_file, 'wb') as f:
                f.write(encrypted_data)
            
            # ذخیره nonce
            nonce_file = self.encrypted_dir / f"{session_path.name}.nonce"
            with open(nonce_file, 'wb') as f:
                f.write(nonce)
            
            # حذف فایل اصلی
            session_path.unlink()
            
            logger.info(f"Session encrypted: {session_path.name}")
            
        except Exception as e:
            logger.error(f"Session encryption error: {e}")
    
    async def _decrypt_session(self, session_name: str) -> Optional[bytes]:
        """رمزگشایی session"""
        if not self.encryption:
            return None
        
        try:
            encrypted_file = self.encrypted_dir / f"{session_name}.session.enc"
            nonce_file = self.encrypted_dir / f"{session_name}.session.nonce"
            
            if not encrypted_file.exists() or not nonce_file.exists():
                return None
            
            # خواندن داده‌ها
            with open(encrypted_file, 'rb') as f:
                encrypted_data = f.read()
            
            with open(nonce_file, 'rb') as f:
                nonce = f.read()
            
            # رمزگشایی
            session_data = self.encryption.decrypt_session(encrypted_data)
            
            return session_data
            
        except Exception as e:
            logger.error(f"Session decryption error: {e}")
            return None
    
    async def validate_session_secure(self, session_name: str,
                                    api_id: int, api_hash: str) -> Tuple[bool, Optional[str]]:
        """اعتبارسنجی امن session"""
        try:
            # بررسی وجود session
            session_path = self.sessions_dir / f"{session_name}.session"
            
            # اگر session رمز شده است، اول رمزگشایی کن
            if self.encryption:
                session_data = await self._decrypt_session(session_name)
                if session_data:
                    # ذخیره موقت برای اعتبارسنجی
                    temp_path = self.sessions_dir / f"temp_{session_name}.session"
                    with open(temp_path, 'wb') as f:
                        f.write(session_data)
                    session_path = temp_path
            
            if not session_path.exists():
                return False, "Session file not found"
            
            # استفاده از SQLiteSession برای اعتبارسنجی
            try:
                session = SQLiteSession(session_path)
                if not session.is_valid():
                    return False, "Invalid session structure"
            except:
                return False, "Cannot parse session file"
            
            # اتصال به تلگرام برای اعتبارسنجی نهایی
            client = TelegramClient(
                session=str(session_path),
                api_id=api_id,
                api_hash=api_hash
            )
            
            try:
                await client.connect()
                
                if not await client.is_user_authorized():
                    return False, "Session not authorized"
                
                # بررسی تاریخ انقضا
                if hasattr(session, 'auth_key'):
                    key_date = getattr(session.auth_key, 'created', None)
                    if key_date:
                        key_age = (datetime.now() - key_date).days
                        if key_age > self.security.session_expiry_days:
                            return False, f"Session expired ({key_age} days old)"
                
                return True, "Valid session"
                
            finally:
                await client.disconnect()
                
                # حذف فایل موقت
                if self.encryption and session_path.name.startswith('temp_'):
                    session_path.unlink()
        
        except Exception as e:
            logger.error(f"Session validation error: {e}")
            return False, f"Validation error: {str(e)}"

# رابط جدید با بهبود UI
class AccountManagerCLI:
    """رابط خط فرمان پیشرفته"""
    
    def __init__(self, api_id: int, api_hash: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.login_manager = SecureAccountLogin()
        self.active_clients = {}
        
    async def run(self):
        """اجرای رابط"""
        import sys
        
        print("\n" + "═" * 60)
        print("🔐 سیستم مدیریت اکانت تلگرام - نسخه امن")
        print("═" * 60)
        
        while True:
            try:
                choice = await self._show_menu()
                
                if choice == '1':
                    await self.login_new_account()
                elif choice == '2':
                    await self.list_accounts()
                elif choice == '3':
                    await self.connect_to_account()
                elif choice == '4':
                    await self.logout_account()
                elif choice == '5':
                    await self.export_account()
                elif choice == '6':
                    await self.import_account()
                elif choice == '7':
                    print("\n👋 خروج...")
                    break
                else:
                    print("\n❌ انتخاب نامعتبر")
            
            except KeyboardInterrupt:
                print("\n\n⚠️ عملیات لغو شد")
                continue
            except Exception as e:
                print(f"\n❌ خطا: {e}")
                logger.exception("CLI error")
    
    async def _show_menu(self) -> str:
        """نمایش منو"""
        menu = """
┌──────────────────────────────────────────────────────┐
│                  منوی مدیریت اکانت                    │
├──────────────────────────────────────────────────────┤
│ 1. 📱 ورود به اکانت جدید                            │
│ 2. 📋 لیست اکانت‌ها                                 │
│ 3. 🔌 اتصال به اکانت                                │
│ 4. 🚪 خروج از اکانت                                 │
│ 5. 📤 export اکانت                                  │
│ 6. 📥 import اکانت                                  │
│ 7. ❌ خروج                                          │
└──────────────────────────────────────────────────────┘
        """
        
        print(menu)
        return input("\n📝 انتخاب شما: ").strip()

# تابع اصلی بهبود یافته
async def main():
    """تابع اصلی با مدیریت خطا"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description='Telegram Secure Account Login System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --login +989123456789
  %(prog)s --list
  %(prog)s --validate mysession
  %(prog)s --interactive
        """
    )
    
    parser.add_argument('--login', metavar='PHONE', 
                       help='Login with phone number')
    parser.add_argument('--list', action='store_true',
                       help='List all accounts')
    parser.add_argument('--validate', metavar='SESSION',
                       help='Validate a session')
    parser.add_argument('--logout', metavar='SESSION',
                       help='Logout from session')
    parser.add_argument('--interactive', action='store_true',
                       help='Run in interactive mode')
    parser.add_argument('--config', default='config.json',
                       help='Config file path')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode')
    
    args = parser.parse_args()
    
    # تنظیم لاگ
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('account_login.log', encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # بارگذاری config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {args.config}")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ Error reading config: {e}")
        sys.exit(1)
    
    api_id = config.get('api_id')
    api_hash = config.get('api_hash')
    
    if not api_id or not api_hash:
        print("❌ api_id or api_hash missing in config")
        sys.exit(1)
    
    # اجرای دستور
    try:
        login_manager = SecureAccountLogin()
        
        if args.interactive:
            cli = AccountManagerCLI(api_id, api_hash)
            await cli.run()
        
        elif args.login:
            print(f"\n🔐 Attempting login for {args.login}")
            client = await login_manager.login_with_phone(
                api_id=api_id,
                api_hash=api_hash,
                phone=args.login
            )
            
            if client:
                print("✅ Login successful")
                await client.disconnect()
            else:
                print("❌ Login failed")
                sys.exit(1)
        
        elif args.list:
            print("\n📋 Available sessions:")
            # Implementation here
        
        elif args.validate:
            is_valid, message = await login_manager.validate_session_secure(
                args.validate, api_id, api_hash
            )
            print(f"\n{'✅' if is_valid else '❌'} {message}")
        
        elif args.logout:
            # Implementation here
            pass
        
        else:
            parser.print_help()
    
    except KeyboardInterrupt:
        print("\n\n👋 Program terminated by user")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        logger.exception("Main error")
        sys.exit(1)

if __name__ == "__main__":
    # بررسی وابستگی‌ها
    if not HAS_TELETHON:
        print("❌ Telethon is required: pip install telethon")
        sys.exit(1)
    
    if not HAS_CRYPTOGRAPHY:
        print("⚠️ For encryption: pip install cryptography")
    
    # اجرا
    asyncio.run(main())
