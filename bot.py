from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from fontTools.ttLib import TTFont
from io import BytesIO
from datetime import datetime
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)

import sqlite3
import os
import json  # <-- أضف هذا مع بقية الاستيرادات
import tempfile
import shutil

# --- الإعدادات الأساسية ---
TOKEN = "7926558096:AAEiSSyGzXbqJQLCTRoPdaeffSuQ6e6_e1E"
ADMINS = ["634869382"]  # قائمة بآيدي المديرين
DATABASE_FILE = "bot_database.db"

# --- حالات المحادثة ---
ADD_KEYWORD, ADD_RESPONSE = range(2)
REPLY_TO_USER = range(1)
EDIT_KEYWORD, EDIT_RESPONSE = range(2, 4)
IMPORT_RESPONSES = range(4)
FONT_CONVERSION, CHOOSE_FORMAT, RECEIVE_FONT = range(5, 8)

# --- تهيئة قاعدة البيانات ---
def init_database():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # إنشاء جدول الردود
    cursor.execute('''CREATE TABLE IF NOT EXISTS responses
                     (keyword TEXT PRIMARY KEY, response TEXT)''')
    
    # إنشاء جدول الإحصائيات
    cursor.execute('''CREATE TABLE IF NOT EXISTS stats
                     (stat_name TEXT PRIMARY KEY, stat_value TEXT)''')
    
    # إنشاء جدول المستخدمين
    cursor.execute('''CREATE TABLE IF NOT EXISTS users
                     (user_id TEXT PRIMARY KEY, name TEXT, username TEXT, first_seen TEXT)''')
    
    # إنشاء جدول رسائل المستخدمين
    cursor.execute('''CREATE TABLE IF NOT EXISTS user_messages
                     (message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT, user_name TEXT, username TEXT,
                      message TEXT, timestamp TEXT,
                      replied INTEGER DEFAULT 0, reply_text TEXT, reply_timestamp TEXT)''')
    
    # إنشاء جدول المجموعات
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups
                     (group_id TEXT PRIMARY KEY)''')
    
    # إنشاء جدول الأوامر المستخدمة
    cursor.execute('''CREATE TABLE IF NOT EXISTS commands_used
                     (command TEXT PRIMARY KEY, count INTEGER)''')
    
    # إنشاء جدول النشاطات الأخيرة
    cursor.execute('''CREATE TABLE IF NOT EXISTS last_active
                     (user_id TEXT PRIMARY KEY, time TEXT, chat_id TEXT, command TEXT)''')
    
    conn.commit()
    conn.close()
# --- بعد init_database() مباشرة ---

def migrate_from_json():
    """هجرة البيانات من ملفات JSON القديمة إلى SQLite"""
    JSON_FILES = {
        'responses': 'responses.json',
        'stats': 'stats.json',
        'users': 'users.json',
        'messages': 'user_messages.json'
    }
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    try:
        # التحقق إذا كانت الهجرة قد تمت من قبل
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='migration'")
        if cursor.fetchone():
            print("✅ الهجرة تمت من قبل")
            return
        
        print("🔍 بدء عملية هجرة البيانات من JSON إلى SQLite...")
        
        # 1. هجرة الردود (الأولوية الأهم)
        if os.path.exists(JSON_FILES['responses']):
            with open(JSON_FILES['responses'], 'r', encoding='utf-8') as f:
                responses = json.load(f)
                for keyword, response in responses.items():
                    cursor.execute("INSERT OR IGNORE INTO responses (keyword, response) VALUES (?, ?)", 
                                 (keyword, response))
                print(f"🔄 تم هجرة {len(responses)} ردًا من responses.json")
        
        # 2. هجرة المستخدمين
        if os.path.exists(JSON_FILES['users']):
            with open(JSON_FILES['users'], 'r', encoding='utf-8') as f:
                users_data = json.load(f)
                if 'users' in users_data:
                    for user_id, user_info in users_data['users'].items():
                        cursor.execute("INSERT OR IGNORE INTO users (user_id, name, username, first_seen) VALUES (?, ?, ?, ?)",
                                     (user_id, user_info.get('name'), user_info.get('username'), user_info.get('first_seen')))
                    print(f"🔄 تم هجرة {len(users_data['users'])} مستخدمًا من users.json")
        
        # 3. هجرة الرسائل
        if os.path.exists(JSON_FILES['messages']):
            with open(JSON_FILES['messages'], 'r', encoding='utf-8') as f:
                messages_data = json.load(f)
                if 'messages' in messages_data:
                    for msg_id, msg_info in messages_data['messages'].items():
                        cursor.execute("""INSERT OR IGNORE INTO user_messages 
                                      (message_id, user_id, user_name, username, message, timestamp, replied, reply_text, reply_timestamp)
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                     (int(msg_id), msg_info.get('user_id'), msg_info.get('user_name'), 
                                      msg_info.get('username'), msg_info.get('message'), msg_info.get('timestamp'),
                                      int(msg_info.get('replied', 0)), msg_info.get('reply_text'), msg_info.get('reply_timestamp')))
                    print(f"🔄 تم هجرة {len(messages_data['messages'])} رسالة من user_messages.json")
        
        # 4. هجرة الإحصائيات
        if os.path.exists(JSON_FILES['stats']):
            with open(JSON_FILES['stats'], 'r', encoding='utf-8') as f:
                stats_data = json.load(f)
                
                if 'total_groups' in stats_data:
                    for group_id in stats_data['total_groups']:
                        cursor.execute("INSERT OR IGNORE INTO groups (group_id) VALUES (?)", (group_id,))
                    print(f"🔄 تم هجرة {len(stats_data['total_groups'])} مجموعة من stats.json")
                
                if 'commands_used' in stats_data:
                    for cmd, count in stats_data['commands_used'].items():
                        cursor.execute("INSERT OR IGNORE INTO commands_used (command, count) VALUES (?, ?)", (cmd, count))
                    print(f"🔄 تم هجرة {len(stats_data['commands_used'])} أمرًا من stats.json")
                
                if 'last_active' in stats_data:
                    for user_id, activity in stats_data['last_active'].items():
                        cursor.execute("INSERT OR IGNORE INTO last_active (user_id, time, chat_id, command) VALUES (?, ?, ?, ?)",
                                     (user_id, activity.get('time'), activity.get('chat_id'), activity.get('command')))
                    print(f"🔄 تم هجرة {len(stats_data['last_active'])} نشاطًا من stats.json")
        
        # وضع علامة أن الهجرة تمت
        cursor.execute("CREATE TABLE IF NOT EXISTS migration (id INTEGER PRIMARY KEY, migrated_at TEXT)")
        cursor.execute("INSERT INTO migration (migrated_at) VALUES (?)", (str(datetime.now()),))
        conn.commit()
        print("🎉 تمت هجرة جميع البيانات بنجاح!")
    
    except Exception as e:
        print(f"❌ خطأ في الهجرة: {str(e)}")
        conn.rollback()
    finally:
        conn.close()

# --- وظائف قاعدة البيانات ---
def get_db_connection():
    return sqlite3.connect(DATABASE_FILE)

# --- إدارة الردود ---
def load_responses():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, response FROM responses")
    responses = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return responses

def save_responses(responses):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM responses")
    for keyword, response in responses.items():
        cursor.execute("INSERT INTO responses (keyword, response) VALUES (?, ?)", (keyword, response))
    conn.commit()
    conn.close()

def add_response(keyword, response):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO responses (keyword, response) VALUES (?, ?)", (keyword, response))
    conn.commit()
    conn.close()

def remove_response(keyword):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM responses WHERE keyword=?", (keyword,))
    conn.commit()
    conn.close()

# --- إدارة المستخدمين ---
def load_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, username, first_seen FROM users")
    users = {"users": {row[0]: {"name": row[1], "username": row[2], "first_seen": row[3]} for row in cursor.fetchall()}}
    conn.close()
    return users

def save_user(user_id, name, username, first_seen):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, username, first_seen) VALUES (?, ?, ?, ?)",
                   (user_id, name, username, first_seen))
    conn.commit()
    conn.close()

def get_total_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# --- إدارة المجموعات ---
def add_group(group_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO groups (group_id) VALUES (?)", (group_id,))
    conn.commit()
    conn.close()

def get_total_groups():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM groups")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# --- إدارة رسائل المستخدمين ---
def save_user_message(user_id, user_name, username, message_text):
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = str(datetime.now())
    cursor.execute("INSERT INTO user_messages (user_id, user_name, username, message, timestamp) VALUES (?, ?, ?, ?, ?)",
                   (user_id, user_name, username, message_text, timestamp))
    message_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return message_id

def update_user_message_reply(message_id, reply_text):
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = str(datetime.now())
    cursor.execute("UPDATE user_messages SET replied=1, reply_text=?, reply_timestamp=? WHERE message_id=?",
                   (reply_text, timestamp, message_id))
    conn.commit()
    conn.close()

def load_user_messages():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, user_id, user_name, username, message, timestamp, replied, reply_text, reply_timestamp FROM user_messages")
    messages = {"messages": {}}
    for row in cursor.fetchall():
        messages["messages"][str(row[0])] = {
            "user_id": row[1],
            "user_name": row[2],
            "username": row[3],
            "message": row[4],
            "timestamp": row[5],
            "replied": bool(row[6]),
            "reply_text": row[7],
            "reply_timestamp": row[8]
        }
    conn.close()
    return messages

def get_pending_messages_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_messages WHERE replied=0")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_replied_messages_count():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_messages WHERE replied=1")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# --- إدارة الأوامر المستخدمة ---
def update_command_stats(command):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO commands_used (command, count) VALUES (?, 0)", (command,))
    cursor.execute("UPDATE commands_used SET count = count + 1 WHERE command=?", (command,))
    conn.commit()
    conn.close()

def get_top_commands(limit=5):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT command, count FROM commands_used ORDER BY count DESC LIMIT ?", (limit,))
    top_commands = cursor.fetchall()
    conn.close()
    return top_commands

# --- إدارة النشاطات الأخيرة ---
def update_last_active(user_id, time, chat_id, command):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO last_active (user_id, time, chat_id, command) VALUES (?, ?, ?, ?)",
                   (user_id, time, chat_id, command))
    conn.commit()
    conn.close()

def get_recent_activities(limit=3):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, time, chat_id, command FROM last_active ORDER BY time DESC LIMIT ?", (limit,))
    activities = cursor.fetchall()
    conn.close()
    return activities

# --- تصدير الردود ---
async def export_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "export")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لتصدير الردود!", disable_web_page_preview=True)
        return
    
    try:
        responses = load_responses()
        temp_file = "responses_backup.json"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(responses, f, ensure_ascii=False, indent=4)
        
        with open(temp_file, 'rb') as file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file,
                caption=f"📁 ملف الردود الحالي\n📊 عدد الردود: {len(responses)}",
                filename="responses_backup.json"
            )
        
        os.remove(temp_file)
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء تصدير الملف: {str(e)}", disable_web_page_preview=True)

# --- استيراد الردود ---
async def import_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "import")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لاستيراد الردود!", disable_web_page_preview=True)
        return
    
    await update.message.reply_text(
        "📥 الرجاء إرسال ملف الردود (JSON) ليتم استيراده:\nأو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return IMPORT_RESPONSES

async def process_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ لم يتم إرسال ملف. يرجى إرسال ملف JSON.", disable_web_page_preview=True)
        return IMPORT_RESPONSES
    
    try:
        file = await update.message.document.get_file()
        await file.download_to_drive("temp_responses.json")
        
        with open("temp_responses.json", 'r', encoding='utf-8') as f:
            imported_data = json.load(f)
        
        if not isinstance(imported_data, dict):
            raise ValueError("تنسيق الملف غير صحيح")
        
        current_responses = load_responses()
        for key, value in imported_data.items():
            if key not in current_responses:
                current_responses[key] = value
        
        save_responses(current_responses)
        os.remove("temp_responses.json")
        
        await update.message.reply_text(
            f"✅ تم استيراد الردود بنجاح!\n📊 عدد الردود الآن: {len(current_responses)}",
            disable_web_page_preview=True
        )
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء استيراد الملف: {str(e)}", disable_web_page_preview=True)
    return ConversationHandler.END

# --- تعديل الردود ---
async def start_edit_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لتعديل الردود!", disable_web_page_preview=True)
        return ConversationHandler.END
    
    responses = load_responses()
    if not responses:
        await update.message.reply_text("❌ لا توجد ردود مسجلة لتعديلها.", disable_web_page_preview=True)
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(keyword, callback_data=f"edit_{keyword}")] for keyword in responses.keys()]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📝 اختر الرد الذي تريد تعديله:",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return EDIT_KEYWORD

async def edit_keyword_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyword = query.data.split("_")[1]
    context.user_data["edit_keyword"] = keyword
    
    await query.edit_message_text(
        f"🔹 الكلمة المحددة: {keyword}\n\n"
        "اختر ما تريد تعديله:\n"
        "1. تعديل الكلمة نفسها\n"
        "2. تعديل الرد فقط\n"
        "3. تعديل الكلمة والرد معاً\n\n"
        "أرسل الرقم المناسب أو /cancel للإلغاء",
        disable_web_page_preview=True
    )
    return EDIT_RESPONSE

async def process_edit_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    keyword = context.user_data["edit_keyword"]
    
    if choice not in ["1", "2", "3"]:
        await update.message.reply_text("❌ خيار غير صحيح. يرجى إرسال 1، 2 أو 3.", disable_web_page_preview=True)
        return EDIT_RESPONSE
    
    context.user_data["edit_choice"] = choice
    
    if choice == "1":
        await update.message.reply_text("✍️ الرجاء إرسال الكلمة الجديدة:", disable_web_page_preview=True)
    elif choice == "2":
        await update.message.reply_text(f"✍️ الرجاء إرسال الرد الجديد للكلمة '{keyword}':", disable_web_page_preview=True)
    else:
        await update.message.reply_text(
            "✍️ الرجاء إرسال الكلمة الجديدة ثم الرد الجديد في رسالة واحدة بهذا الشكل:\n"
            "الكلمة الجديدة\nالرد الجديد",
            disable_web_page_preview=True
        )
    
    return EDIT_RESPONSE

async def save_edited_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = context.user_data["edit_choice"]
    old_keyword = context.user_data["edit_keyword"]
    responses = load_responses()
    response_text = responses[old_keyword]
    new_text = update.message.text
    
    try:
        if choice == "1":
            responses[new_text] = response_text
            remove_response(old_keyword)
            add_response(new_text, response_text)
            message = f"✅ تم تغيير الكلمة من '{old_keyword}' إلى '{new_text}'"
        elif choice == "2":
            responses[old_keyword] = new_text
            add_response(old_keyword, new_text)
            message = f"✅ تم تحديث الرد للكلمة '{old_keyword}'"
        else:
            parts = new_text.split("\n", 1)
            if len(parts) != 2:
                raise ValueError("يجب إرسال الكلمة والرد في سطرين منفصلين")
            
            new_keyword, new_response = parts
            remove_response(old_keyword)
            add_response(new_keyword, new_response)
            responses[new_keyword] = new_response
            message = f"✅ تم تغيير الكلمة من '{old_keyword}' إلى '{new_keyword}' وتحديث الرد"
        
        await update.message.reply_text(
            f"{message}\n📊 عدد الردود الآن: {len(responses)}",
            disable_web_page_preview=True
        )
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء التعديل: {str(e)}", disable_web_page_preview=True)
    
    if "edit_keyword" in context.user_data:
        del context.user_data["edit_keyword"]
    if "edit_choice" in context.user_data:
        del context.user_data["edit_choice"]
    
    return ConversationHandler.END

# --- إرسال إشعار للمدير ---
async def send_admin_notification(context, user):
    try:
        user_info = f"👤 مستخدم جديد:\n"
        user_info += f"🆔 ID: {user.id}\n"
        user_info += f"📛 الاسم: {user.full_name}\n"
        if user.username:
            user_info += f"🔗 اليوزر: @{user.username}\n"
        
        user_info += f"\n📊 إجمالي المستخدمين الآن: {get_total_users()}"
        
        await context.bot.send_message(
            chat_id=ADMINS[0],
            text=user_info,
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Error sending admin notification: {e}")

# --- إرسال رسالة المستخدم للمدير ---
async def forward_message_to_admin(context, user, message):
    try:
        message_text = message.text or message.caption or "[رسالة غير نصية]"
        message_id = save_user_message(str(user.id), user.full_name, user.username, message_text)
        
        keyboard = [
            [InlineKeyboardButton("💬 رد على هذه الرسالة", callback_data=f"reply_{message_id}")],
            [InlineKeyboardButton("📋 عرض جميع الرسائل", callback_data="view_all_messages")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        admin_message = f"📨 رسالة جديدة من مستخدم:\n\n"
        admin_message += f"👤 الاسم: {user.full_name}\n"
        admin_message += f"🆔 ID: {user.id}\n"
        if user.username:
            admin_message += f"🔗 اليوزر: @{user.username}\n"
        admin_message += f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        admin_message += f"📝 الرسالة: {message_text}\n"
        admin_message += f"🔢 رقم الرسالة: {message_id}"
        
        await context.bot.send_message(
            chat_id=ADMINS[0],
            text=admin_message,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
        return message_id
    except Exception as e:
        print(f"Error forwarding message to admin: {e}")
        return None

# --- تحديث الإحصائيات ---
def update_stats(update: Update, command: str = None):
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    
    # تحديث المستخدمين
    if update.effective_user:
        save_user(user_id, update.effective_user.full_name, update.effective_user.username, str(datetime.now()))
    
    # تحديث المجموعات
    if update.effective_chat.type in ["group", "supergroup", "channel"]:
        add_group(chat_id)
    
    # تحديث الأوامر المستخدمة
    if command:
        update_command_stats(command)
    
    # تحديث النشاط الأخير
    update_last_active(user_id, str(datetime.now()), chat_id, command or "message")

# --- معالجة الرسائل ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update)
    
    message = update.message or update.edited_message
    if not message:
        return
    
    is_edited = bool(update.edited_message)
    original_text = message.text if message.text else (message.caption if message.caption else "")
    should_delete = original_text.lstrip().startswith(('.', '/')) if original_text else False
    
    # إذا كانت رسالة خاصة وليست من مدير
    if message.chat.type == "private" and str(update.effective_user.id) not in ADMINS:
        responses = load_responses()
        found_responses = []
        used_positions = set()
        
        # نظام الردود التلقائية في الخاص
        for keyword in sorted(responses.keys(), key=len, reverse=True):
            if keyword in original_text:
                start_pos = original_text.find(keyword)
                end_pos = start_pos + len(keyword)
                
                overlap = any(not (end_pos <= used_start or start_pos >= used_end) 
                            for (used_start, used_end) in used_positions)
                
                if not overlap:
                    found_responses.append({
                        'position': start_pos,
                        'response': responses[keyword],
                        'keyword': keyword
                    })
                    used_positions.add((start_pos, end_pos))
        
        if found_responses:
            found_responses.sort(key=lambda x: x['position'])
            combined_response = "\n".join([f"» {item['response']}" for item in found_responses])
            await context.bot.send_message(
                chat_id=message.chat.id,
                text=combined_response,
                reply_to_message_id=message.message_id,
                disable_web_page_preview=True
            )
        
        await forward_message_to_admin(context, update.effective_user, message)
        return
    
    # نظام الردود العادية في المجموعات
    responses = load_responses()
    found_responses = []
    used_positions = set()
    current_keywords = set()
    
    for keyword in sorted(responses.keys(), key=len, reverse=True):
        if keyword in original_text:
            start_pos = original_text.find(keyword)
            end_pos = start_pos + len(keyword)
            
            overlap = any(not (end_pos <= used_start or start_pos >= used_end) 
                         for (used_start, used_end) in used_positions)
            
            if not overlap:
                found_responses.append({
                    'position': start_pos,
                    'response': responses[keyword],
                    'keyword': keyword
                })
                current_keywords.add(keyword)
                used_positions.add((start_pos, end_pos))
    
    found_responses.sort(key=lambda x: x['position'])
    
    if found_responses:
        combined_response = "\n".join([f"» {item['response']}" for item in found_responses])
        target_message = message.reply_to_message if message.reply_to_message else message
        
        message_key = f"{message.chat.id}_{message.message_id}"
        
        if is_edited:
            prev_keywords = context.chat_data.get(message_key, {}).get('keywords', set())
            if prev_keywords == current_keywords:
                return
                
            if 'response_id' in context.chat_data.get(message_key, {}):
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=context.chat_data[message_key]['response_id']
                    )
                except Exception as e:
                    print(f"Failed to delete old response: {e}")
        
        if should_delete:
            try:
                await message.delete()
            except Exception as e:
                print(f"Failed to delete message: {e}")
            
            try:
                sent_message = await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=combined_response,
                    reply_to_message_id=target_message.message_id,
                    disable_web_page_preview=True
                )
                context.chat_data[message_key] = {
                    'keywords': current_keywords,
                    'response_id': sent_message.message_id
                }
            except Exception as e:
                print(f"Failed to send reply: {e}")
                sent_message = await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=combined_response,
                    disable_web_page_preview=True
                )
                context.chat_data[message_key] = {
                    'keywords': current_keywords,
                    'response_id': sent_message.message_id
                }
        else:
            sent_message = await context.bot.send_message(
                chat_id=message.chat.id,
                text=combined_response,
                reply_to_message_id=target_message.message_id,
                disable_web_page_preview=True
            )
            context.chat_data[message_key] = {
                'keywords': current_keywords,
                'response_id': sent_message.message_id
            }

# --- معالجة الأزرار التفاعلية ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if str(query.from_user.id) not in ADMINS:
        await query.edit_message_text("⚠️ هذا الأمر متاح للمديرين فقط!")
        return
    
    if query.data.startswith("reply_"):
        message_id = query.data.split("_")[1]
        context.user_data["reply_message_id"] = message_id
        
        messages_data = load_user_messages()
        if message_id in messages_data["messages"]:
            msg_data = messages_data["messages"][message_id]
            await query.edit_message_text(
                f"💬 الرد على الرسالة رقم {message_id}\n\n"
                f"👤 المستخدم: {msg_data['user_name']}\n"
                f"📝 الرسالة: {msg_data['message']}\n\n"
                f"الرجاء كتابة ردك الآن:"
            )
            return REPLY_TO_USER
        else:
            await query.edit_message_text("❌ لم يتم العثور على الرسالة!")
    
    elif query.data == "view_all_messages":
        messages_data = load_user_messages()
        if not messages_data["messages"]:
            await query.edit_message_text("📭 لا توجد رسائل بعد.")
            return
        
        message_list = "📨 جميع رسائل المستخدمين:\n\n"
        for msg_id, msg_data in messages_data["messages"].items():
            status = "✅ تم الرد" if msg_data["replied"] else "⏳ في الانتظار"
            message_list += f"🔢 {msg_id}: {msg_data['user_name']} - {status}\n"
            message_list += f"   📝 {msg_data['message'][:50]}...\n\n"
        
        if len(message_list) > 4000:
            parts = [message_list[i:i+4000] for i in range(0, len(message_list), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await query.edit_message_text(part)
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat.id,
                        text=part,
                        disable_web_page_preview=True
                    )
        else:
            await query.edit_message_text(message_list)

# --- الرد على رسالة مستخدم ---
async def reply_to_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمديرين فقط!")
        return ConversationHandler.END
    
    reply_text = update.message.text
    message_id = context.user_data.get("reply_message_id")
    
    if not message_id:
        await update.message.reply_text("❌ حدث خطأ، لم يتم العثور على رقم الرسالة.")
        return ConversationHandler.END
    
    messages_data = load_user_messages()
    if message_id not in messages_data["messages"]:
        await update.message.reply_text("❌ لم يتم العثور على الرسالة!")
        return ConversationHandler.END
    
    msg_data = messages_data["messages"][message_id]
    user_id = msg_data["user_id"]
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💬 رد من الإدارة:\n\n{reply_text}",
            disable_web_page_preview=True
        )
        
        update_user_message_reply(int(message_id), reply_text)
        await update.message.reply_text(f"✅ تم إرسال الرد بنجاح للمستخدم {msg_data['user_name']}!")
    except Exception as e:
        await update.message.reply_text(f"❌ فشل في إرسال الرد: {str(e)}")
    
    if "reply_message_id" in context.user_data:
        del context.user_data["reply_message_id"]
    
    return ConversationHandler.END

# --- عرض رسائل المستخدمين ---
async def view_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "messages")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمديرين فقط!", disable_web_page_preview=True)
        return
    
    messages_data = load_user_messages()
    
    if not messages_data["messages"]:
        await update.message.reply_text("📭 لا توجد رسائل من المستخدمين بعد.", disable_web_page_preview=True)
        return
    
    sorted_messages = sorted(
        messages_data["messages"].items(),
        key=lambda x: x[1]["timestamp"],
        reverse=True
    )[:10]
    
    message_list = ["📨 آخر 10 رسائل من المستخدمين:\n"]
    
    for msg_id, msg_data in sorted_messages:
        status = "✅ تم الرد" if msg_data["replied"] else "⏳ في الانتظار"
        message_list.append(f"\n🔢 رقم الرسالة: {msg_id}")
        message_list.append(f"👤 المستخدم: {msg_data['user_name']}")
        message_list.append(f"📝 الرسالة: {msg_data['message'][:100]}...")
        message_list.append(f"⏰ الوقت: {msg_data['timestamp'][:16]}")
        message_list.append(f"📊 الحالة: {status}")
        if msg_data["replied"]:
            message_list.append(f"💬 الرد: {msg_data['reply_text'][:50]}...")
    
    message_list.append(f"\n📊 إجمالي الرسائل: {len(messages_data['messages'])}")
    message_list.append(f"⏳ في الانتظار: {get_pending_messages_count()}")
    message_list.append(f"✅ تم الرد عليها: {get_replied_messages_count()}")
    
    full_message = "\n".join(message_list)
    
    if len(full_message) > 4000:
        parts = [full_message[i:i+4000] for i in range(0, len(full_message), 4000)]
        for part in parts:
            await update.message.reply_text(part, disable_web_page_preview=True)
    else:
        await update.message.reply_text(full_message, disable_web_page_preview=True)

# --- إضافة رد ---
async def start_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإضافة ردود!", disable_web_page_preview=True)
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 الرجاء إرسال الكلمة المفتاحية التي تريد إضافة رد لها:\nأو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return ADD_KEYWORD

async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text
    context.user_data["temp_keyword"] = keyword
    
    await update.message.reply_text(
        f"🔹 الكلمة المحددة: {keyword}\n\n"
        "الرجاء إرسال الرد الذي تريد ربطه بهذه الكلمة:\n"
        "أو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return ADD_RESPONSE

async def add_response_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = context.user_data["temp_keyword"]
    response = update.message.text
    
    add_response(keyword, response)
    del context.user_data["temp_keyword"]
    
    await update.message.reply_text(
        f"✅ تم الحفظ بنجاح!\n\n"
        f"الكلمة: {keyword}\n"
        f"الرد: {response}\n\n"
        f"📊 إجمالي الردود الآن: {len(load_responses())}",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def cancel_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "temp_keyword" in context.user_data:
        del context.user_data["temp_keyword"]
    if "reply_message_id" in context.user_data:
        del context.user_data["reply_message_id"]
    
    await update.message.reply_text("❌ تم إلغاء العملية.", disable_web_page_preview=True)
    return ConversationHandler.END

# --- إزالة رد ---
async def remove_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "remove")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لحذف ردود!", disable_web_page_preview=True)
        return
    
    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا: /remove <الكلمة>", disable_web_page_preview=True)
        return
    
    keyword = ' '.join(context.args)
    responses = load_responses()
    
    if keyword in responses:
        remove_response(keyword)
        await update.message.reply_text(
            f"✅ تم حذف الرد للكلمة '{keyword}'\n\n"
            f"📊 إجمالي الردود الآن: {len(load_responses())}",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            f"❌ لا يوجد رد مسجل للكلمة '{keyword}'",
            disable_web_page_preview=True
        )

# --- عرض الردود ---
async def list_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "list")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لعرض الردود!", disable_web_page_preview=True)
        return
    
    responses = load_responses()
    
    if not responses:
        await update.message.reply_text("لا توجد ردود مسجلة بعد.", disable_web_page_preview=True)
        return
    
    message = ["📜 قائمة الردود المسجلة:\n"]
    for keyword, response in responses.items():
        message.append(f"\n🔸 {keyword}:")
        message.append(f"   ↳ {response}")
    
    message.append(f"\n\n📊 إجمالي الردود: {len(responses)}")
    
    full_message = "\n".join(message)
    if len(full_message) > 4000:
        parts = [full_message[i:i+4000] for i in range(0, len(full_message), 4000)]
        for part in parts:
            await update.message.reply_text(part, disable_web_page_preview=True)
    else:
        await update.message.reply_text(full_message, disable_web_page_preview=True)

# --- عرض إحصائيات المستخدمين ---
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "users")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمديرين فقط!", disable_web_page_preview=True)
        return
    
    users_data = load_users()
    total_users = len(users_data["users"])
    
    message = [
        f"📊 إحصائيات المستخدمين:",
        f"👥 إجمالي المستخدمين: {total_users}",
        f"\n🆔 آخر 5 مستخدمين:"
    ]
    
    last_users = sorted(users_data["users"].items(), key=lambda x: x[1].get("first_seen", ""), reverse=True)[:5]
    
    for user_id, user_info in last_users:
        user_line = f"\n- {user_info.get('name', 'Unknown')}"
        if user_info.get('username'):
            user_line += f" (@{user_info['username']})"
        user_line += f" - {user_id}"
        message.append(user_line)
    
    await update.message.reply_text("\n".join(message), disable_web_page_preview=True)

# --- الإحصائيات ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "stats")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمديرين فقط!", disable_web_page_preview=True)
        return
    
    message = [
        "📊 إحصائيات البوت:",
        f"👤 عدد المستخدمين الفريدين: {get_total_users()}",
        f"👥 عدد المجموعات/القنوات: {get_total_groups()}",
        f"📝 عدد الردود المسجلة: {len(load_responses())}",
        f"📨 إجمالي رسائل المستخدمين: {len(load_user_messages()['messages'])}",
        f"⏳ رسائل في الانتظار: {get_pending_messages_count()}",
        f"✅ رسائل تم الرد عليها: {get_replied_messages_count()}",
        "\n📌 الأوامر الأكثر استخدامًا:"
    ]
    
    top_commands = get_top_commands(5)
    for cmd, count in top_commands:
        message.append(f"- {cmd}: {count} مرة")
    
    message.extend(["\n⏱ آخر 3 نشاطات:"])
    last_activities = get_recent_activities(3)
    for user_id, time, chat_id, command in last_activities:
        message.append(f"- المستخدم {user_id[:4]}...: {command} في {time[:16]}")
    
    await update.message.reply_text("\n".join(message), disable_web_page_preview=True)

# --- نظام الإذاعة ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمديرين فقط!", disable_web_page_preview=True)
        return

    keyboard = [
        ["📢 للمجموعات فقط", "👤 للمستخدمين فقط"],
        ["🌍 للجميع (مجموعات ومستخدمين)", "❌ إلغاء"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "📡 اختر نوع الإذاعة:",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return "BROADCAST_TYPE"

async def choose_broadcast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broadcast_type = update.message.text
    chat_id = str(update.effective_chat.id)
    
    if broadcast_type == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    context.user_data["broadcast_type"] = broadcast_type
    
    await update.message.reply_text(
        "✍️ الرجاء إرسال الرسالة التي تريد إذاعتها:",
        reply_markup=ReplyKeyboardRemove(),
        disable_web_page_preview=True
    )
    return "BROADCAST_MESSAGE"

async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = str(update.effective_chat.id)
    
    if "broadcast_type" not in context.user_data:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", disable_web_page_preview=True)
        return ConversationHandler.END
    
    context.user_data["broadcast_message"] = message.text or message.caption
    context.user_data["broadcast_message_obj"] = message
    
    keyboard = [["✅ نعم، قم بالإرسال", "❌ لا، إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"⚠️ تأكيد الإذاعة:\n\n"
        f"النوع: {context.user_data['broadcast_type']}\n"
        f"الرسالة: {context.user_data['broadcast_message']}\n\n"
        f"عدد المستلمين المتوقع: {await estimate_recipients(context.user_data['broadcast_type'])}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return "BROADCAST_CONFIRMATION"

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    chat_id = str(update.effective_chat.id)
    
    if choice == "❌ لا، إلغاء":
        await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    if "broadcast_type" not in context.user_data or "broadcast_message_obj" not in context.user_data:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    broadcast_type = context.user_data["broadcast_type"]
    message_obj = context.user_data["broadcast_message_obj"]
    
    success = 0
    failed = 0
    
    await update.message.reply_text("⏳ جاري إرسال الإذاعة...", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
    
    if broadcast_type in ["📢 للمجموعات فقط", "🌍 للجميع (مجموعات ومستخدمين)"]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT group_id FROM groups")
        groups = cursor.fetchall()
        conn.close()
        
        for group_id in groups:
            try:
                await message_obj.copy(chat_id=group_id[0])
                success += 1
            except Exception as e:
                print(f"Failed to send to group {group_id[0]}: {e}")
                failed += 1
    
    if broadcast_type in ["👤 للمستخدمين فقط", "🌍 للجميع (مجموعات ومستخدمين)"]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        
        for user_id in users:
            try:
                await message_obj.copy(chat_id=user_id[0])
                success += 1
            except Exception as e:
                print(f"Failed to send to user {user_id[0]}: {e}")
                failed += 1
    
    await update.message.reply_text(
        f"✅ تم إرسال الإذاعة بنجاح!\n\n"
        f"✅ تمت بنجاح: {success}\n"
        f"❌ فشل في الإرسال: {failed}",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
    return ConversationHandler.END
# --- تحويل صيغ الخطوط ---
async def start_font_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["TTF إلى OTF", "OTF إلى TTF"],
        ["إلغاء"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "🔄 اختر نوع التحويل:",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return CHOOSE_FORMAT

async def choose_conversion_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "إلغاء":
        await update.message.reply_text("تم الإلغاء.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    context.user_data["conversion_type"] = choice
    await update.message.reply_text(
        "📤 الرجاء إرسال ملف الخط الذي تريد تحويله:",
        reply_markup=ReplyKeyboardRemove(),
        disable_web_page_preview=True
    )
    return RECEIVE_FONT

async def process_font_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ لم يتم إرسال ملف. يرجى إرسال ملف الخط.")
        return RECEIVE_FONT
    
    try:
        file = await update.message.document.get_file()
        
        # إنشاء مجلد مؤقت
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, update.message.document.file_name)
        await file.download_to_drive(input_path)
        
        # تحديد نوع التحويل
        conversion_type = context.user_data["conversion_type"]
        output_ext = ".otf" if conversion_type == "TTF إلى OTF" else ".ttf"
        output_path = os.path.join(temp_dir, f"converted{output_ext}")
        
        # عملية التحويل
        font = TTFont(input_path)
        font.save(output_path)
        
        # إرسال الملف المحول
        with open(output_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                caption=f"✅ تم التحويل بنجاح إلى {output_ext.upper()}",
                filename=f"converted{output_ext}"
            )
        
        # تنظيف الملفات المؤقتة
        shutil.rmtree(temp_dir)
        
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء التحويل: {str(e)}")
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir)
    
    return ConversationHandler.END

async def cancel_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء عملية التحويل.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# --- التحقق من الصلاحيات ---
async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "admin")
    
    if str(update.effective_user.id) in ADMINS:
        await update.message.reply_text("🎖️ أنت مدير! لديك جميع الصلاحيات.", disable_web_page_preview=True)
    else:
        await update.message.reply_text("👤 أنت مستخدم عادي. فقط المدير يمكنه إدارة الردود.", disable_web_page_preview=True)

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "start")
    
    user_id = str(update.effective_user.id)
    save_user(user_id, update.effective_user.full_name, update.effective_user.username, str(datetime.now()))
    await send_admin_notification(context, update.effective_user)
    
    start_message = [
        "مرحبًا! 👋 أنا بوت الخطوط التلقائي.",
        "",
        "🎯 كيفية الاستخدام:",
        "- عندما يتم ذكر أي كلمة مسجلة، سأقوم بالرد تلقائياً",
        "- إذا تم الرد على رسالة تحتوي كلمة مسجلة، سأرد على الرسالة الأصلية",
        "- يمكنك إرسال رسائل خاصة لي وسيتم توجيهها للإدارة"
    ]
    
    if str(update.effective_user.id) in ADMINS:
        start_message.extend([
            "",
            "⚙️ الأوامر الإدارية:",
            "/add - إضافة رد جديد",
            "/edit - تعديل رد موجود",
            "/remove <الكلمة> - حذف رد",
            "/list - عرض كل الردود",
            "/stats - إحصائيات البوت",
            "/users - عرض المستخدمين",
            "/messages - عرض رسائل المستخدمين",
            "/broadcast - إرسال إذاعة للمستخدمين",
            "/export - تصدير الردود",
            "/import - استيراد الردود"
            "/convert - تحويل صيغ الخطوط"  # <-- أضف هذا السطر

        ])
    
    start_message.extend([
        "",
        "🔧 تم تطوير وبرمجة البوت بواسطة أحمد الغريب",
        "- @Am9li9",
        "📚 مجموعة نقاشات الخطوط ↓",
        "- @ElgharibFonts",
    ])
    
    await update.message.reply_text("\n".join(start_message), disable_web_page_preview=True)
# --- الدالة الرئيسية ---
def main():
    # تهيئة قاعدة البيانات
    init_database()
    migrate_from_json()

    application = Application.builder().token(TOKEN).build()
    
    # محادثة إضافة الردود
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", start_add_response)],
        states={
            ADD_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_keyword)],
            ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_response_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)],
        per_message=True
    )
    
    # محادثة تعديل الردود
    edit_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", start_edit_response)],
        states={
            EDIT_KEYWORD: [CallbackQueryHandler(edit_keyword_choice, pattern="^edit_")],
            EDIT_RESPONSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_edit_choice),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_response)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)],
        per_message=True
    )
    
    # محادثة استيراد الردود
    import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("import", import_responses)],
        states={
            IMPORT_RESPONSES: [MessageHandler(filters.Document.ALL | filters.TEXT & ~filters.COMMAND, process_import_file)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    # محادثة الرد على المستخدمين
    reply_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^reply_")],
        states={
            REPLY_TO_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_user_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)],
        per_message=True
    )
    
    # محادثة الإذاعة
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast)],
        states={
            "BROADCAST_TYPE": [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_broadcast_type)],
            "BROADCAST_MESSAGE": [MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_message)],
            "BROADCAST_CONFIRMATION": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_broadcast)]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)]
    )
    
    # محادثة تحويل الخطوط
    font_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("convert", start_font_conversion)],
        states={
            CHOOSE_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_conversion_type)],
            RECEIVE_FONT: [MessageHandler(filters.Document.ALL & ~filters.COMMAND, process_font_file)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversion)]
    )
    
    # تسجيل المعالجات
    application.add_handler(add_conv_handler)
    application.add_handler(edit_conv_handler)
    application.add_handler(import_conv_handler)
    application.add_handler(reply_conv_handler)
    application.add_handler(broadcast_conv_handler)
    application.add_handler(font_conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("remove", remove_response))
    application.add_handler(CommandHandler("list", list_responses))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("users", show_users))
    application.add_handler(CommandHandler("messages", view_user_messages))
    application.add_handler(CommandHandler("admin", check_admin))
    application.add_handler(CommandHandler("export", export_responses))
    application.add_handler(CommandHandler("import", import_responses))
    application.add_handler(CommandHandler("edit", start_edit_response))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    
    print("🤖 البوت يعمل الآن...")
    application.run_polling()