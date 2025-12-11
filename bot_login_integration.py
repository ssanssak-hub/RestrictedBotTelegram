#!/usr/bin/env python3
# bot_login_integration.py - رباتی که می‌تواند به اکانت کاربر وارد شود

import telebot
from telebot import types
import asyncio
import json
from pathlib import Path
from threading import Thread
from queue import Queue
from account_login import AccountManager

# صف برای ارتباط بین threadها
login_queue = Queue()
result_queue = Queue()

class LoginBot:
    """ربات تلگرام برای ورود به اکانت کاربران"""
    
    def __init__(self, token: str, api_id: int, api_hash: str):
        self.bot = telebot.TeleBot(token)
        self.api_id = api_id
        self.api_hash = api_hash
        self.account_manager = None
        self.user_sessions = {}  # user_id -> session_name
        
        # استارت thread برای پردازش login
        self._start_login_thread()
        
        # تنظیم هندلرها
        self.setup_handlers()
    
    def _start_login_thread(self):
        """شروع thread برای پردازش login"""
        def login_worker():
            # ایجاد event loop جدید برای thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # ایجاد account manager
            self.account_manager = AccountManager(self.api_id, self.api_hash)
            
            while True:
                try:
                    # دریافت درخواست از صف
                    task = login_queue.get()
                    
                    if task['type'] == 'login':
                        result = loop.run_until_complete(
                            self._process_login_request(task)
                        )
                        result_queue.put(result)
                    
                    elif task['type'] == 'logout':
                        result = loop.run_until_complete(
                            self._process_logout_request(task)
                        )
                        result_queue.put(result)
                    
                    login_queue.task_done()
                    
                except Exception as e:
                    print(f"Login worker error: {e}")
                    result_queue.put({'error': str(e)})
        
        thread = Thread(target=login_worker, daemon=True)
        thread.start()
    
    async def _process_login_request(self, task: dict) -> dict:
        """پردازش درخواست login"""
        user_id = task['user_id']
        phone = task['phone']
        
        try:
            from account_login import SecureAccountLogin
            
            login_manager = SecureAccountLogin()
            
            # ورود به اکانت
            client = await login_manager.login_with_phone(
                api_id=self.api_id,
                api_hash=self.api_hash,
                phone=phone
            )
            
            if client:
                me = await client.get_me()
                session_name = client.session.filename.replace('.session', '')
                
                # ذخیره در manager
                self.account_manager.active_clients[session_name] = {
                    'info': {
                        'session_name': session_name,
                        'user_id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name
                    },
                    'client': client,
                    'last_used': asyncio.get_event_loop().time()
                }
                
                # ذخیره ارتباط کاربر با session
                self.user_sessions[user_id] = session_name
                
                return {
                    'success': True,
                    'session_name': session_name,
                    'user_info': {
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                        'username': me.username,
                        'user_id': me.id
                    }
                }
            else:
                return {'success': False, 'error': 'Login failed'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def _process_logout_request(self, task: dict) -> dict:
        """پردازش درخواست logout"""
        user_id = task['user_id']
        
        if user_id not in self.user_sessions:
            return {'success': False, 'error': 'No active session'}
        
        session_name = self.user_sessions[user_id]
        
        try:
            success = await self.account_manager.logout_account(session_name)
            
            if success:
                del self.user_sessions[user_id]
                return {'success': True}
            else:
                return {'success': False, 'error': 'Logout failed'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def setup_handlers(self):
        """تنظیم هندلرهای ربات"""
        
        @self.bot.message_handler(commands=['start'])
        def start_handler(message):
            """منوی اصلی"""
            keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
            keyboard.row('🔐 ورود به اکانت', '🚪 خروج از اکانت')
            keyboard.row('👤 اطلاعات اکانت', '📋 اکانت‌های من')
            keyboard.row('ℹ️ راهنما', '⚙️ تنظیمات')
            
            self.bot.send_message(
                message.chat.id,
                "👋 به ربات مدیریت اکانت تلگرام خوش آمدید!\n\n"
                "با این ربات می‌توانید به اکانت تلگرام خود وارد شوید "
                "و از امکانات آن استفاده کنید.",
                reply_markup=keyboard
            )
        
        @self.bot.message_handler(func=lambda m: m.text == '🔐 ورود به اکانت')
        def login_handler(message):
            """ورود به اکانت"""
            msg = self.bot.send_message(
                message.chat.id,
                "📱 لطفاً شماره تلفن تلگرام خود را ارسال کنید:\n\n"
                "فرمت: +989123456789 یا 09123456789\n\n"
                "⚠️ توجه: این شماره فقط برای ورود استفاده می‌شود و ذخیره نمی‌شود."
            )
            
            self.bot.register_next_step_handler(msg, process_phone_number)
        
        def process_phone_number(message):
            """پردازش شماره تلفن"""
            phone = message.text.strip()
            
            # نرمال‌سازی شماره
            if phone.startswith('0'):
                phone = '+98' + phone[1:]
            elif not phone.startswith('+'):
                phone = '+' + phone
            
            # ارسال به صف پردازش
            login_queue.put({
                'type': 'login',
                'user_id': message.from_user.id,
                'phone': phone
            })
            
            # اطلاع به کاربر
            self.bot.send_message(
                message.chat.id,
                "⏳ در حال ارسال کد تأیید...\n"
                "لطفاً کمی صبر کنید."
            )
            
            # منتظر نتیجه بمان
            Thread(target=wait_for_login_result, 
                  args=(message.chat.id, message.from_user.id)).start()
        
        def wait_for_login_result(chat_id, user_id):
            """انتظار برای نتیجه login"""
            result = result_queue.get()
            
            if result.get('success'):
                user_info = result['user_info']
                
                self.bot.send_message(
                    chat_id,
                    f"✅ ورود موفق!\n\n"
                    f"👤 نام: {user_info['first_name']} {user_info['last_name'] or ''}\n"
                    f"📱 یوزرنیم: @{user_info['username'] or 'ندارد'}\n"
                    f"🆔 آیدی: {user_info['user_id']}\n\n"
                    f"حالا می‌توانید از امکانات ربات استفاده کنید."
                )
            else:
                error = result.get('error', 'خطای ناشناخته')
                self.bot.send_message(
                    chat_id,
                    f"❌ ورود ناموفق\n\n"
                    f"خطا: {error}\n\n"
                    f"لطفاً دوباره تلاش کنید."
                )
        
        @self.bot.message_handler(func=lambda m: m.text == '🚪 خروج از اکانت')
        def logout_handler(message):
            """خروج از اکانت"""
            user_id = message.from_user.id
            
            if user_id not in self.user_sessions:
                self.bot.send_message(
                    message.chat.id,
                    "⚠️ شما وارد هیچ اکانتی نشده‌اید."
                )
                return
            
            # ارسال درخواست logout
            login_queue.put({
                'type': 'logout',
                'user_id': user_id
            })
            
            self.bot.send_message(
                message.chat.id,
                "⏳ در حال خروج از اکانت..."
            )
            
            # منتظر نتیجه
            Thread(target=wait_for_logout_result, 
                  args=(message.chat.id,)).start()
        
        def wait_for_logout_result(chat_id):
            """انتظار برای نتیجه logout"""
            result = result_queue.get()
            
            if result.get('success'):
                self.bot.send_message(
                    chat_id,
                    "✅ از اکانت خارج شدید.\n\n"
                    "همه session‌ها حذف شدند."
                )
            else:
                error = result.get('error', 'خطای ناشناخته')
                self.bot.send_message(
                    chat_id,
                    f"❌ خطا در خروج\n\n{error}"
                )
        
        @self.bot.message_handler(func=lambda m: m.text == '👤 اطلاعات اکانت')
        def account_info_handler(message):
            """نمایش اطلاعات اکانت"""
            user_id = message.from_user.id
            
            if user_id not in self.user_sessions:
                self.bot.send_message(
                    message.chat.id,
                    "⚠️ لطفاً ابتدا وارد اکانت شوید."
                )
                return
            
            # در اینجا باید اطلاعات از account_manager خوانده شود
            # این یک پیاده‌سازی ساده است
            self.bot.send_message(
                message.chat.id,
                "📋 اطلاعات اکانت:\n\n"
                "👤 نام: نمایش داده می‌شود\n"
                "📱 یوزرنیم: نمایش داده می‌شود\n"
                "🆔 آیدی: نمایش داده می‌شود\n"
                "📅 زمان ورود: نمایش داده می‌شود\n\n"
                "⚠️ این بخش نیاز به تکمیل دارد."
            )
        
        @self.bot.message_handler(commands=['help'])
        def help_handler(message):
            """راهنما"""
            help_text = """
📖 راهنمای ربات مدیریت اکانت:

🔐 **ورود به اکانت**:
1. روی '🔐 ورود به اکانت' کلیک کنید
2. شماره تلفن تلگرام خود را وارد کنید
3. کد تأیید ارسال شده را در تلگرام وارد کنید
4. اگر اکانت رمز دو مرحله‌ای دارد، آن را وارد کنید

🚪 **خروج از اکانت**:
1. روی '🚪 خروج از اکانت' کلیک کنید
2. تأیید کنید
3. همه session‌ها حذف می‌شوند

👤 **اطلاعات اکانت**:
نمایش اطلاعات اکانت وارد شده

📋 **اکانت‌های من**:
نمایش همه اکانت‌های وارد شده

⚠️ **هشدارهای امنیتی**:
- شماره تلفن شما ذخیره نمی‌شود
- session‌ها رمزگذاری می‌شوند
- بعد از 24 ساعت غیرفعالی، auto-logout می‌شوید
- فقط از اکانت خودتان استفاده کنید

❓ **پشتیبانی**:
برای سوالات و مشکلات با ادمین تماس بگیرید.
"""
            
            self.bot.send_message(message.chat.id, help_text)
    
    def start(self):
        """شروع ربات"""
        print("🤖 ربات مدیریت اکانت شروع به کار کرد...")
        self.bot.polling(none_stop=True)

# تابع اصلی
def main():
    """شروع ربات"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Telegram Account Login Bot')
    parser.add_argument('--token', required=True, help='Bot token from @BotFather')
    parser.add_argument('--config', default='config.json', help='Config file path')
    
    args = parser.parse_args()
    
    # بارگذاری config
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Config file not found: {args.config}")
        return
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    api_id = config.get('api_id')
    api_hash = config.get('api_hash')
    
    if not api_id or not api_hash:
        print("❌ api_id or api_hash not found in config")
        return
    
    # ایجاد و اجرای ربات
    bot = LoginBot(args.token, api_id, api_hash)
    bot.start()

if __name__ == "__main__":
    main()
