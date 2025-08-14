import os
from dotenv import load_dotenv
load_dotenv()  # لقراءة متغيرات البيئة من ملف .env
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
import json
import os
from datetime import datetime
import logging
from telegram.constants import ChatType
import subprocess
from PIL import Image
import tempfile
from fontTools import ttLib
import zipfile
import rarfile  # Requires 'unrar' installed
import time  # For timestamp in file names

# --- الإعدادات الأساسية ---
TOKEN = os.getenv("TELEGRAM_TOKEN")  # بدلاً من التوكن الثابت
ADMINS = ["634869382"]  # قائمة بآيدي المديرين
BROADCAST_CONFIRM = {}  # لتخزين بيانات الإذاعة قبل التأكيد

# --- ملفات التخزين ---
RESPONSES_FILE = "responses.json"
STATS_FILE = "stats.json"
USERS_FILE = "users.json"
MESSAGES_FILE = "user_messages.json"
CHANNEL_FILE = "channel.json"  # ملف لتخزين رابط قناة السورس
SETTINGS_FILE = "settings.json"  # ملف للإعدادات
INLINE_BUTTONS_FILE = "inline_buttons.json"  # ملف للأزرار الشفافة

# --- حالات المحادثة ---
ADD_KEYWORD, ADD_RESPONSE = range(2)
REPLY_TO_USER = range(1)
IMPORT_RESPONSES = range(4)
ADD_CHANNEL = range(5)  # حالة لإضافة رابط القناة
BROADCAST_TYPE, BROADCAST_MESSAGE, BROADCAST_CONFIRMATION = range(3)  # حالات الإذاعة
OPTIONS_MENU, CONVERT_TO_SVG, CONVERT_FONT, EXTRACT_ARCHIVE, CHOOSE_FONT_FORMAT = range(6, 11)  # حالات الخيارات
SETTINGS_MENU, EDIT_WELCOME, EDIT_REPLY_MSG, ADD_INLINE_BUTTON, REMOVE_INLINE_BUTTON = range(11, 16)  # حالات الإعدادات
DISABLE_RESPONSES_GROUP, ENABLE_RESPONSES_GROUP = range(16, 18)  # حالات جديدة لإدارة المجموعات المعطلة

# --- إعداد التسجيل لتصحيح الأخطاء ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تحميل البيانات ---
def load_data(filename, default_data):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "total_users" in data and isinstance(data["total_users"], list):
                    data["total_users"] = set(data["total_users"])
                if "total_groups" in data and isinstance(data["total_groups"], list):
                    data["total_groups"] = set(data["total_groups"])
                if "disabled_response_groups" in data and isinstance(data["disabled_response_groups"], list):
                    data["disabled_response_groups"] = set(data["disabled_response_groups"])
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON in {filename}: {e}")
            return default_data.copy()
    return default_data.copy()

def save_data(filename, data):
    data_to_save = data.copy()
    if "total_users" in data_to_save and isinstance(data_to_save["total_users"], set):
        data_to_save["total_users"] = list(data_to_save["total_users"])
    if "total_groups" in data_to_save and isinstance(data_to_save["total_groups"], set):
        data_to_save["total_groups"] = list(data_to_save["total_groups"])
    if "disabled_response_groups" in data_to_save and isinstance(data_to_save["disabled_response_groups"], set):
        data_to_save["disabled_response_groups"] = list(data_to_save["disabled_response_groups"])
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)

# --- إدارة رابط قناة السورس ---
def load_channel():
    return load_data(CHANNEL_FILE, {"channel_url": None})

def save_channel(channel_data):
    save_data(CHANNEL_FILE, channel_data)

# --- إدارة رسائل المستخدمين ---
def load_user_messages():
    return load_data(MESSAGES_FILE, {"messages": {}})

def save_user_messages(messages_data):
    save_data(MESSAGES_FILE, messages_data)

#اشعار_الادمن
async def notify_admin_on_error(context, error, user_id):
    await context.bot.send_message(
        chat_id=ADMINS[0],
        text=f"⚠️ حدث خطأ:\n\nالخطأ: {str(error)}\nالمستخدم: {user_id}",
        disable_web_page_preview=True
    )
    
# --- إدارة الردود ---
async def export_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "export")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لتصدير الردود!",
            disable_web_page_preview=True
        )
        return
    
    try:
        with open(RESPONSES_FILE, 'rb') as file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file,
                caption=f"📁 ملف الردود الحالي\n📊 عدد الردود: {len(load_responses())}",
                filename="responses_backup.json"
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء تصدير الملف: {str(e)}",
            disable_web_page_preview=True
        )

async def import_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "import")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لاستيراد الردود!",
            disable_web_page_preview=True
        )
        return
    
    await update.message.reply_text(
        "📥 الرجاء إرسال ملف الردود (JSON) ليتم استيراده:\n"
        "أو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return IMPORT_RESPONSES

async def process_import_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text(
            "❌ لم يتم إرسال ملف. يرجى إرسال ملف JSON.",
            disable_web_page_preview=True
        )
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
            f"✅ تم استيراد الردود بنجاح!\n"
            f"📊 عدد الردود الآن: {len(current_responses)}",
            disable_web_page_preview=True
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء استيراد الملف: {str(e)}",
            disable_web_page_preview=True
        )
    return ConversationHandler.END

def load_responses():
    return load_data(RESPONSES_FILE, {})

def save_responses(responses):
    save_data(RESPONSES_FILE, responses)

# --- إدارة الإحصائيات ---
def load_stats():
    stats = load_data(STATS_FILE, {
        "total_users": set(),
        "total_groups": set(),
        "commands_used": {},
        "last_active": {},
        "user_messages": {}  # إضافة عداد رسائل لكل مستخدم في كل مجموعة
    })
    
    # تأكد من وجود المفتاح 'user_messages' إذا كان الملف موجودًا
    if "user_messages" not in stats:
        stats["user_messages"] = {}
    
    return stats

# --- إدارة المستخدمين ---
def load_users():
    return load_data(USERS_FILE, {"users": {}})

def save_users(users_data):
    save_data(USERS_FILE, users_data)

# --- إدارة الإعدادات ---
def load_settings():
    default = {
        "welcome_message": [
            "مرحبًا! 👋 أنا بوت خطوط أحمد الغريب .",
            "",
            "🎯 كيفية الاستخدام:",
            "- عندما يتم ذكر أي كلمة مسجلة، سأقوم بالرد تلقائياً",
            "- يمكنك إرسال رسائل خاصة لي وسيتم توجيهها للإدارة",
            "- استخدم /options للوصول إلى لوحة الخيارات الإضافية",
            "",
            "🔧 تم تطوير وبرمجة البوت بواسطة أحمد الغريب",
            "- @Am9li9",
        ],
        "reply_message": "💬 رد من الإدارة:\n\n{reply_text}",
        "disabled_response_groups": set()
    }
    return load_data(SETTINGS_FILE, default)

def save_settings(settings):
    save_data(SETTINGS_FILE, settings)

# --- إدارة الأزرار الشفافة ---
def load_inline_buttons():
    return load_data(INLINE_BUTTONS_FILE, {"buttons": []})  # list of dicts {"text": "", "url": ""}

def save_inline_buttons(buttons_data):
    save_data(INLINE_BUTTONS_FILE, buttons_data)

# --- إرسال إشعار للمدير ---
async def send_admin_notification(context, user):
    try:
        user_info = f"👤 مستخدم جديد:\n"
        user_info += f"🆔 ID: {user.id}\n"
        user_info += f"📛 الاسم: {user.full_name}\n"
        if user.username:
            user_info += f"🔗 اليوزر: @{user.username}\n"
        
        user_info += f"\n📊 إجمالي المستخدمين الآن: {len(load_users()['users'])+1}"
        
        await context.bot.send_message(
            chat_id=ADMINS[0],
            text=user_info,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error sending admin notification: {e}")

# --- إرسال رسالة المستخدم للمدير ---
async def forward_message_to_admin(context, user, message):
    try:
        messages_data = load_user_messages()
        message_id = str(len(messages_data["messages"]) + 1)
        
        messages_data["messages"][message_id] = {
            "user_id": str(user.id),
            "user_name": user.full_name,
            "username": user.username,
            "message": message.text or message.caption or "[رسالة غير نصية]",
            "timestamp": str(datetime.now()),
            "replied": False,
            "reply_text": None,
            "reply_timestamp": None
        }
        
        save_user_messages(messages_data)
        
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
        admin_message += f"📝 الرسالة: {message.text or message.caption or '[رسالة غير نصية]'}\n"
        admin_message += f"🔢 رقم الرسالة: {message_id}"
        
        await context.bot.send_message(
            chat_id=ADMINS[0],
            text=admin_message,
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        
        return message_id
        
    except Exception as e:
        logger.error(f"Error forwarding message to admin: {e}")
        return None

# --- تحديث الإحصائيات ---
def update_stats(update: Update, command: str = None):
    stats = load_stats()
    
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    
    stats["total_users"].add(user_id)
    
    if update.effective_chat.type in ["group", "supergroup", "channel"]:
        stats["total_groups"].add(chat_id)
    
    if command:
        stats["commands_used"][command] = stats["commands_used"].get(command, 0) + 1
    
    stats["last_active"][user_id] = {
        "time": str(datetime.now()),
        "chat_id": chat_id,
        "command": command or "message"
    }
    
    # تحديث عدد الرسائل للمستخدم في المجموعة
    if update.effective_chat.type in ["group", "supergroup"] and update.message:
        if chat_id not in stats["user_messages"]:
            stats["user_messages"][chat_id] = {}
        stats["user_messages"][chat_id][user_id] = stats["user_messages"][chat_id].get(user_id, 0) + 1
    
    save_data(STATS_FILE, stats)

# --- التحقق من صلاحيات المشرف ---
async def is_admin_or_creator(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    
    if user_id in ADMINS:
        return True
    
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if str(admin.user.id) == user_id:
                return True
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
    
    return False

# --- عرض معلومات العضو ---
async def show_member_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "⚠️ يجب الرد على رسالة المستخدم لعرض معلوماته!",
            disable_web_page_preview=True
        )
        return
    
    if not await is_admin_or_creator(update, context):
        await update.message.reply_text(
            "⚠️ هذا الأمر متاح فقط للمديرين أو مشرفي المجموعة!",
            disable_web_page_preview=True
        )
        return
    
    target_user = update.message.reply_to_message.from_user
    chat_id = str(update.effective_chat.id)
    user_id = str(target_user.id)
    
    stats = load_stats()
    message_count = stats["user_messages"].get(chat_id, {}).get(user_id, 0)
    
    is_admin = False
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if str(admin.user.id) == user_id:
                is_admin = True
                break
    except Exception as e:
        logger.error(f"Error checking admin status for member: {e}")
    
    username = f"@{target_user.username}" if target_user.username else "غير متوفر"
    user_link = f"http://t.me/{target_user.username}" if target_user.username else f"tg://user?id={user_id}"
    rank = "مدير/مشرف" if is_admin else "عضو"

    message = [
        f"👤| الاسم [{target_user.full_name}]({user_link}) ⊰•",
        f"📮| الـ ID •⊱ {user_id} ⊰•",
        f"🎫| اسم المُستخدم •⊱ {username} ⊰•",
        f"🎖| رُتبة المُستخدم •⊱ {rank} ⊰•",
        f"⭐️| جودة التفاعل •⊱ ✘ ⊰•",
        f"📝| عدد الرسائل •⊱ {message_count} ⊰•",
        "➖"
    ]
    
    await update.message.reply_text(
        "\n".join(message),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

# --- معالجة الرسائل المحدثة ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update)
    
    if not update.message and not update.edited_message:
        return
        
    message = update.message or update.edited_message
    original_text = message.text if message.text else (message.caption if message.caption else "")
    
    # تحقق إضافي: إذا كانت الرسالة أمر (تبدأ بـ /)، تخطي handle_message للسماح لـ CommandHandler بالتعامل معها
    if original_text.startswith('/'):
        logger.info(f"Skipping handle_message for command: {original_text}")
        return  # هذا يسمح للأمر بالمرور إلى الـ handler المناسب
    
    # التحقق من كلمات "كشف"، "ايدي"، "معلومات"، "بيانات" عند الرد
    if message.reply_to_message and original_text.lower().strip() in ["كشف", "ايدي", "معلومات", "بيانات"]:
        await show_member_info(update, context)
        return
    
    if original_text and "المطور" in original_text.lower().strip():
        await show_developer_info(update, context)
        return
    
    users_data = load_users()
    user_id = str(update.effective_user.id)
    
    if user_id not in users_data["users"]:
        users_data["users"][user_id] = {
            "name": update.effective_user.full_name,
            "username": update.effective_user.username,
            "first_seen": str(datetime.now())
        }
        save_users(users_data)
        await send_admin_notification(context, update.effective_user)
    
    message = update.message or update.edited_message
    if not message:
        return
    
    is_edited = bool(update.edited_message)
    original_text = message.text if message.text else (message.caption if message.caption else "")
    should_delete = original_text.lstrip().startswith(('.', '/')) if original_text else False
    
    if message.chat.type == ChatType.PRIVATE and str(update.effective_user.id) not in ADMINS:
        responses = load_responses()
        found_responses = []
        used_positions = set()
        sorted_keywords = sorted(responses.keys(), key=len, reverse=True)
        
        for keyword in sorted_keywords:
            if keyword in original_text:
                start_pos = original_text.find(keyword)
                end_pos = start_pos + len(keyword)
                
                overlap = False
                for (used_start, used_end) in used_positions:
                    if not (end_pos <= used_start or start_pos >= used_end):
                        overlap = True
                        break
                
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
            
            sent_message = await context.bot.send_message(
                chat_id=message.chat.id,
                text=combined_response,
                disable_web_page_preview=True
            )
            context.user_data['last_response_id'] = sent_message.message_id
        
        await forward_message_to_admin(context, update.effective_user, message)
        return
    
    responses = load_responses()
    found_responses = []
    used_positions = set()
    current_keywords = set()
    sorted_keywords = sorted(responses.keys(), key=len, reverse=True)
    
    for keyword in sorted_keywords:
        if keyword in original_text:
            start_pos = original_text.find(keyword)
            end_pos = start_pos + len(keyword)
            overlap = False
            for (used_start, used_end) in used_positions:
                if not (end_pos <= used_start or start_pos >= used_end):
                    overlap = True
                    break
            if not overlap:
                found_responses.append({
                    'position': start_pos,
                    'response': responses[keyword],
                    'keyword': keyword
                })
                current_keywords.add(keyword)
                used_positions.add((start_pos, end_pos))
    
    found_responses.sort(key=lambda x: x['position'])
    
    # التحقق من تعطيل الردود في هذه المجموعة
    settings = load_settings()
    chat_id = str(update.effective_chat.id)
    chat_type = update.effective_chat.type
    if chat_type in ["group", "supergroup"] and chat_id in settings["disabled_response_groups"]:
        return  # لا ترد على الكلمات المفتاحية في هذه المجموعة
    
    if found_responses:
        combined_response = "\n".join([f"» {item['response']}" for item in found_responses])
        target_message = message.reply_to_message if message.reply_to_message else message
        
        message_key = f"{message.chat.id}_{message.message_id}"
        
        if is_edited:
            prev_data = context.chat_data.get(message_key, {})
            prev_keywords = prev_data.get('keywords', set())
            if prev_keywords == current_keywords:
                return
            if 'response_id' in prev_data:
                try:
                    await context.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=prev_data['response_id']
                    )
                except Exception as e:
                    logger.error(f"Failed to delete old response: {e}")
        
        if should_delete:
            try:
                await message.delete()
            except Exception as e:
                logger.error(f"Failed to delete message: {e}")
            
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
                logger.error(f"Failed to send reply: {e}")
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
    return

# --- معالجة الأزرار التفاعلية ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"Received callback query: {query.data} from user {query.from_user.id}")
    await query.answer()
    
    if query.data == "options_menu":
        await show_options_menu(update, context)
        return OPTIONS_MENU
    
    if query.data == "settings":
        if str(query.from_user.id) not in ADMINS:
            await query.edit_message_text("⚠️ هذا الأمر متاح للمديرين فقط!")
            return
        await settings_menu(update, context)
        return SETTINGS_MENU
    
    if query.data == "developer_info":
        await show_developer_info(update, context)
        return
    
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

async def reply_to_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_text = update.message.text
    message_id = context.user_data["reply_message_id"]
    messages_data = load_user_messages()
    msg_data = messages_data["messages"][message_id]
    user_id = msg_data["user_id"]
    
    try:
        settings = load_settings()
        formatted_reply = settings["reply_message"].format(reply_text=reply_text)
        
        await context.bot.send_message(
            chat_id=user_id,
            text=formatted_reply,
            disable_web_page_preview=True
        )
        
        messages_data["messages"][message_id]["replied"] = True
        messages_data["messages"][message_id]["reply_text"] = reply_text
        messages_data["messages"][message_id]["reply_timestamp"] = str(datetime.now())
        save_user_messages(messages_data)
        
        await update.message.reply_text(
            f"✅ تم إرسال الرد بنجاح للمستخدم {msg_data['user_name']}!"
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ فشل في إرسال الرد: {str(e)}"
        )
    
    if "reply_message_id" in context.user_data:
        del context.user_data["reply_message_id"]
    
    return ConversationHandler.END

# --- عرض رسائل المستخدمين ---
async def view_user_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "messages")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ هذا الأمر متاح للمديرين فقط!",
            disable_web_page_preview=True
        )
        return
    
    messages_data = load_user_messages()
    
    if not messages_data["messages"]:
        await update.message.reply_text(
            "📭 لا توجد رسائل من المستخدمين بعد.",
            disable_web_page_preview=True
        )
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
    message_list.append(f"⏳ في الانتظار: {sum(1 for msg in messages_data['messages'].values() if not msg['replied'])}")
    message_list.append(f"✅ تم الرد عليها: {sum(1 for msg in messages_data['messages'].values() if msg['replied'])}")
    
    full_message = "\n".join(message_list)
    
    if len(full_message) > 4000:
        parts = [full_message[i:i+4000] for i in range(0, len(full_message), 4000)]
        for part in parts:
            await update.message.reply_text(
                part,
                disable_web_page_preview=True
            )
    else:
        await update.message.reply_text(
            full_message,
            disable_web_page_preview=True
        )

# --- إضافة رد (نظام المحادثة) ---
async def start_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لإضافة ردود!",
            disable_web_page_preview=True
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 الرجاء إرسال الكلمة المفتاحية التي تريد إضافة رد لها:\n"
        "أو /cancel لإلغاء العملية",
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
    
    responses = load_responses()
    responses[keyword] = response
    save_responses(responses)
    
    del context.user_data["temp_keyword"]
    
    await update.message.reply_text(
        f"✅ تم الحفظ بنجاح!\n\n"
        f"الكلمة: {keyword}\n"
        f"الرد: {response}\n\n"
        f"📊 إجمالي الردود الآن: {len(responses)}",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def cancel_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "temp_keyword" in context.user_data:
        del context.user_data["temp_keyword"]
    if "reply_message_id" in context.user_data:
        del context.user_data["reply_message_id"]
    if "font_file_id" in context.user_data:
        del context.user_data["font_file_id"]
    if "font_file_name" in context.user_data:
        del context.user_data["font_file_name"]
    
    await update.message.reply_text(
        "❌ تم إلغاء العملية.",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

# --- إزالة رد ---
async def remove_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "remove")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لحذف ردود!",
            disable_web_page_preview=True
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "استخدم الأمر هكذا: /remove <الكلمة>",
            disable_web_page_preview=True
        )
        return
    
    keyword = ' '.join(context.args)
    responses = load_responses()
    
    if keyword in responses:
        del responses[keyword]
        save_responses(responses)
        await update.message.reply_text(
            f"✅ تم حذف الرد للكلمة '{keyword}'\n\n"
            f"📊 إجمالي الردود الآن: {len(responses)}",
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
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لعرض الردود!",
            disable_web_page_preview=True
        )
        return
    
    responses = load_responses()
    
    if not responses:
        await update.message.reply_text(
            "لا توجد ردود مسجلة بعد.",
            disable_web_page_preview=True
        )
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
            await update.message.reply_text(
                part,
                disable_web_page_preview=True
            )
    else:
        await update.message.reply_text(
            full_message,
            disable_web_page_preview=True
        )

# --- عرض إحصائيات المستخدمين ---
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "users")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ هذا الأمر متاح للمديرين فقط!",
            disable_web_page_preview=True
        )
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
    
    await update.message.reply_text(
        "\n".join(message),
        disable_web_page_preview=True
    )

# --- الإحصائيات ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "stats")
    
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ هذا الأمر متاح للمديرين فقط!",
            disable_web_page_preview=True
        )
        return
    
    stats = load_stats()
    users_data = load_users()
    responses = load_responses()
    messages_data = load_user_messages()
    
    message = [
        "📊 إحصائيات البوت:",
        f"👤 عدد المستخدمين الفريدين: {len(users_data['users'])}",
        f"👥 عدد المجموعات/القنوات: {len(stats['total_groups'])}",
        f"📝 عدد الردود المسجلة: {len(responses)}",
        f"📨 إجمالي رسائل المستخدمين: {len(messages_data['messages'])}",
        f"⏳ رسائل في الانتظار: {sum(1 for msg in messages_data['messages'].values() if not msg['replied'])}",
        "\n📌 الأوامر الأكثر استخدامًا:"
    ]
    
    sorted_commands = sorted(stats["commands_used"].items(), key=lambda x: x[1], reverse=True)[:5]
    for cmd, count in sorted_commands:
        message.append(f"- {cmd}: {count} مرة")
    
    message.extend(["\n⏱ آخر 3 نشاطات:"])
    last_activities = sorted(stats["last_active"].items(), key=lambda x: x[1]["time"], reverse=True)[:3]
    for user_id, activity in last_activities:
        message.append(f"- المستخدم {user_id[:4]}...: {activity['command']} في {activity['time'][:16]}")
    
    await update.message.reply_text(
        "\n".join(message),
        disable_web_page_preview=True
    )

# --- نظام الإذاعة ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمديرين فقط!", disable_web_page_preview=True)
        return

    keyboard = [
        ["📢 للمجموعات فقط", "👤 للمستخدمين فقط"],
        ["🌍 للجميع (مجموعات ومستخدمين)", "🔙 رجوع"],
        ["❌ إلغاء"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)

    await update.message.reply_text(
        "📡 اختر نوع الإذاعة:",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return BROADCAST_TYPE

async def choose_broadcast_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    broadcast_type = update.message.text
    chat_id = str(update.effective_chat.id)
    
    if broadcast_type == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    if broadcast_type == "🔙 رجوع":
        return await start(update, context)
    
    BROADCAST_CONFIRM[chat_id] = {"type": broadcast_type}
    
    keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "✍️ الرجاء إرسال الرسالة التي تريد إذاعتها:",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return BROADCAST_MESSAGE

async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = str(update.effective_chat.id)
    
    if message.text == "🔙 رجوع":
        return await start_broadcast(update, context)
    
    if message.text == "❌ إلغاء":
        if chat_id in BROADCAST_CONFIRM:
            del BROADCAST_CONFIRM[chat_id]
        await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    if chat_id not in BROADCAST_CONFIRM:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", disable_web_page_preview=True)
        return ConversationHandler.END
    
    BROADCAST_CONFIRM[chat_id]["message"] = message.text or message.caption
    BROADCAST_CONFIRM[chat_id]["message_obj"] = message
    
    keyboard = [["✅ نعم، قم بالإرسال", "🔙 رجوع"], ["❌ لا، إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"⚠️ تأكيد الإذاعة:\n\n"
        f"النوع: {BROADCAST_CONFIRM[chat_id]['type']}\n"
        f"الرسالة: {BROADCAST_CONFIRM[chat_id]['message']}\n\n"
        f"عدد المستلمين المتوقع: {await estimate_recipients(BROADCAST_CONFIRM[chat_id]['type'])}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return BROADCAST_CONFIRMATION

async def estimate_recipients(broadcast_type):
    stats = load_stats()
    users_data = load_users()
    
    if broadcast_type == "📢 للمجموعات فقط":
        return len(stats["total_groups"])
    elif broadcast_type == "👤 للمستخدمين فقط":
        return len(users_data["users"])
    else:
        return len(stats["total_groups"]) + len(users_data["users"])

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    chat_id = str(update.effective_chat.id)
    
    if choice == "🔙 رجوع":
        return await choose_broadcast_type(update, context)
    
    if choice == "❌ لا، إلغاء":
        if chat_id in BROADCAST_CONFIRM:
            del BROADCAST_CONFIRM[chat_id]
        await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    if chat_id not in BROADCAST_CONFIRM:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    broadcast_data = BROADCAST_CONFIRM[chat_id]
    message_obj = broadcast_data["message_obj"]
    
    success = 0
    failed = 0
    
    stats = load_stats()
    users_data = load_users()
    
    await update.message.reply_text("⏳ جاري إرسال الإذاعة...", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
    
    if broadcast_data["type"] in ["📢 للمجموعات فقط", "🌍 للجميع (مجموعات ومستخدمين)"]:
        for group_id in stats["total_groups"]:
            try:
                await message_obj.copy(chat_id=group_id)
                success += 1
            except Exception as e:
                logger.error(f"Failed to send to group {group_id}: {e}")
                failed += 1
    
    if broadcast_data["type"] in ["👤 للمستخدمين فقط", "🌍 للجميع (مجموعات ومستخدمين)"]:
        for user_id in users_data["users"]:
            try:
                await message_obj.copy(chat_id=user_id)
                success += 1
            except Exception as e:
                logger.error(f"Failed to send to user {user_id}: {e}")
                failed += 1
    
    del BROADCAST_CONFIRM[chat_id]
    
    await update.message.reply_text(
        f"✅ تم إرسال الإذاعة بنجاح!\n\n"
        f"✅ تمت بنجاح: {success}\n"
        f"❌ فشل في الإرسال: {failed}",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id in BROADCAST_CONFIRM:
        del BROADCAST_CONFIRM[chat_id]
    
    await update.message.reply_text("تم إلغاء عملية الإذاعة.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
    return ConversationHandler.END

# --- التحقق من الصلاحيات ---
async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "admin")
    
    if str(update.effective_user.id) in ADMINS:
        await update.message.reply_text(
            "🎖️ أنت مدير! لديك جميع الصلاحيات.",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            "👤 أنت مستخدم عادي. فقط المدير يمكنه إدارة الردود.",
            disable_web_page_preview=True
        )

# --- إضافة/تعديل رابط قناة السورس ---
async def start_add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لإضافة رابط القناة!",
            disable_web_page_preview=True
        )
        return ConversationHandler.END
    
    channel_data = load_channel()
    current_channel = channel_data["channel_url"] if channel_data["channel_url"] else "لم يتم تعيين رابط بعد"
    
    keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"📢 رابط القناة الحالي: {current_channel}\n\n"
        "الرجاء إرسال رابط القناة الجديد (مثل @ChannelName أو https://t.me/ChannelName):\n"
        "أو /cancel لإلغاء العملية",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return ADD_CHANNEL

async def add_channel_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_url = update.message.text.strip()
    
    if channel_url == "🔙 رجوع":
        return await start(update, context)
    
    if channel_url == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove(), disable_web_page_preview=True)
        return ConversationHandler.END
    
    # التحقق من صحة الرابط
    if not (channel_url.startswith("@") or channel_url.startswith("https://t.me/")):
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "❌ الرابط غير صالح! يجب أن يكون على شكل @ChannelName أو https://t.me/ChannelName\n"
            "الرجاء إرسال رابط صالح أو /cancel لإلغاء العملية",
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )
        return ADD_CHANNEL
    
    channel_data = load_channel()
    channel_data["channel_url"] = channel_url
    save_channel(channel_data)
    
    await update.message.reply_text(
        f"✅ تم حفظ رابط القناة بنجاح: {channel_url}",
        disable_web_page_preview=True
    )
    return ConversationHandler.END

# --- عرض معلومات المطور ---
async def show_developer_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        developer = await context.bot.get_chat(ADMINS[0])
        logger.info(f"Retrieved developer info: {developer}")
        
        developer_name = developer.first_name
        if developer.last_name:
            developer_name += " " + developer.last_name
            
        developer_username = f"@{developer.username}" if developer.username else "لا يوجد"
        developer_bio = developer.bio if developer.bio else "لا يوجد بايو"
        
        message = [
            "👨‍💻 معلومات المطور :",
            f"📛 الاسم: {developer_name}",
            f"🔗 اليوزر: {developer_username}",
            f"📌 البايو: {developer_bio}"
        ]
        
        # إضافة الأزرار الشفافة
        keyboard = [
            [InlineKeyboardButton("📚 نقاشات خطوط أحمد الغريب", url="https://t.me/ElgharibFonts")]
        ]
        
        # إضافة زر القناة إذا كان موجودًا
        channel_data = load_channel()
        if channel_data["channel_url"]:
            keyboard.append([InlineKeyboardButton("📢 قناة خطوط قرآن", url=channel_data["channel_url"])])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # جلب صورة المطور
        developer_photos = await context.bot.get_user_profile_photos(ADMINS[0], limit=1)
        
        if developer_photos.total_count > 0:
            file = await developer_photos.photos[0][-1].get_file()  # أعلى دقة
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=file.file_id,
                caption="\n".join(message),
                reply_markup=reply_markup,
                disable_notification=True
            )
            logger.info("Successfully sent developer photo")
        else:
            await update.message.reply_text(
                "\n".join(message),
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"Error getting developer info: {e}")
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء جلب معلومات المطور: {str(e)}",
            disable_web_page_preview=True
        )

# --- إعادة تشغيل البوت ---
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "restart")
    logger.info(f"Attempting to restart bot for user {update.effective_user.id}")
    
    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type
    
    if chat_type in ["group", "supergroup"]:
        if not await is_admin_or_creator(update, context):
            logger.info(f"User {user_id} is not admin or creator")
            await update.message.reply_text(
                "⚠️ هذا الأمر متاح فقط لمشرفي المجموعة أو المديرين!",
                disable_web_page_preview=True
            )
            return
    elif chat_type == ChatType.PRIVATE:
        if user_id not in ADMINS:
            logger.info(f"User {user_id} is not in ADMINS list")
            await update.message.reply_text(
                "⚠️ هذا الأمر متاح للمديرين فقط!",
                disable_web_page_preview=True
            )
            return
    
    logger.info("Clearing temporary data")
    context.bot_data.clear()
    context.user_data.clear()
    context.chat_data.clear()
    
    logger.info("Sending restart confirmation")
    await update.message.reply_text(
        "🔄 تم إعادة تنشيط البوت وتحسين سرعته.\nتحياتي؛ بوت خطوط أحمد الغريب @quranfontbot",
        disable_web_page_preview=True
    )
    logger.info("Calling start function")
    return await start(update, context)

# --- لوحة الخيارات الجديدة ---
async def show_options_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    keyboard = [
        [KeyboardButton("🖼️ تحويل صورة إلى SVG")],
        [KeyboardButton("🔤 تحويل صيغة خط (TTF ↔ OTF)")],
        [KeyboardButton("📦 فك ضغط ملفات (ZIP/RAR)")],
        [KeyboardButton("🔄 إعادة تشغيل البوت")],
        [KeyboardButton("🔙 رجوع")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    if query:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📋 اختر الوظيفة المرغوبة:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "📋 اختر الوظيفة المرغوبة:",
            reply_markup=reply_markup
        )
    return OPTIONS_MENU

async def handle_options_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "🔙 رجوع":
        return await start(update, context)
    
    if choice == "🖼️ تحويل صورة إلى SVG":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "📤 أرسل صورة JPG/JPEG بخلفية بيضاء وكتابة سوداء (جودة متوسطة إلى عالية).\n"
            "⚠️ يجب الالتزام بالشروط للحصول على نتيجة جيدة.\n"
            "📸 يمكن إرسال حتى 100 صورة دفعة واحدة.",
            reply_markup=reply_markup
        )
        return CONVERT_TO_SVG
    
    elif choice == "🔤 تحويل صيغة خط (TTF ↔ OTF)":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "📤 أرسل ملف خط TTF أو OTF للتحويل إلى الصيغة الأخرى.",
            reply_markup=reply_markup
        )
        return CONVERT_FONT
    
    elif choice == "📦 فك ضغط ملفات (ZIP/RAR)":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "📤 أرسل ملف ZIP أو RAR (حتى 500MB) لفك الضغط.",
            reply_markup=reply_markup
        )
        return EXTRACT_ARCHIVE
    
    elif choice == "🔄 إعادة تشغيل البوت":
        await restart_bot(update, context)
        return ConversationHandler.END
    
    return OPTIONS_MENU

# --- وظيفة تحويل الصورة إلى SVG ---
async def convert_to_svg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await show_options_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    photos = update.message.photo if update.message.photo else []
    documents = [update.message.document] if update.message.document else []
    
    files = []
    if photos:
        # اختيار الصورة ذات الحجم الأكبر (أعلى جودة)
        highest_quality_photo = max(photos, key=lambda p: p.file_size, default=None)
        if highest_quality_photo:
            files = [await highest_quality_photo.get_file()]
    elif documents:
        files = [await doc.get_file() for doc in documents[:100] if doc.file_name.lower().endswith(('.jpg', '.jpeg'))]
    
    if not files:
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("⚠️ يرجى إرسال صورة JPG/JPEG صالحة (سيتم اختيار الأعلى جودة).", reply_markup=reply_markup)
        return CONVERT_TO_SVG
    
    await update.message.reply_text(f"⏳ جاري تحويل {len(files)} صورة...")
    
    for i, file in enumerate(files, 1):
        try:
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as img_file:
                await file.download_to_drive(img_file.name)
                img_path = img_file.name
            
            with tempfile.NamedTemporaryFile(suffix='.pbm', delete=False) as pbm_file:
                pbm_path = pbm_file.name
            
            svg_filename = f"@ElgharibFontsBot - {i}.svg"
            with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as svg_file:
                svg_path = svg_file.name
            
            img = Image.open(img_path).convert("L").point(lambda x: 0 if x < 128 else 255, "1")
            img.save(pbm_path)
            
            subprocess.run(["potrace", pbm_path, "-s", "-o", svg_path], check=True)
            
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=open(svg_path, 'rb'),
                filename=svg_filename,
                caption="تم تحويل الملف بواسطة بوت خطوط أحمد الغريب @quranfontbot"
            )
            
            os.remove(img_path)
            os.remove(pbm_path)
            os.remove(svg_path)
            
        except Exception as e:
            logger.error(f"Error converting image {i}: {e}")
            await update.message.reply_text(f"❌ خطأ في تحويل الصورة {i}: {str(e)}")
    
    return await show_options_menu(update, context)

# --- وظيفة تحويل صيغة الخط ---
async def convert_font(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await show_options_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    if not update.message.document:
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("⚠️ يرجى إرسال ملف خط TTF أو OTF.", reply_markup=reply_markup)
        return CONVERT_FONT
    
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    if not file_name.endswith(('.ttf', '.otf')):
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("⚠️ الصيغة غير مدعومة. فقط TTF أو OTF.", reply_markup=reply_markup)
        return CONVERT_FONT
    
    context.user_data["font_file_id"] = doc.file_id
    context.user_data["font_file_name"] = doc.file_name
    
    keyboard = [["إلى TTF", "إلى OTF"], ["🔙 رجوع"], ["❌ إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text("اختر الصيغة المرغوبة:", reply_markup=reply_markup)
    return CHOOSE_FONT_FORMAT

async def choose_font_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "🔙 رجوع":
        return await show_options_menu(update, context)
    
    if choice == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        if "font_file_id" in context.user_data:
            del context.user_data["font_file_id"]
        if "font_file_name" in context.user_data:
            del context.user_data["font_file_name"]
        return ConversationHandler.END
    
    if choice not in ["إلى TTF", "إلى OTF"]:
        keyboard = [["إلى TTF", "إلى OTF"], ["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("⚠️ اختيار غير صالح.", reply_markup=reply_markup)
        return CHOOSE_FONT_FORMAT
    
    target_ext = '.ttf' if choice == "إلى TTF" else '.otf'
    file_id = context.user_data.get("font_file_id")
    file_name = context.user_data.get("font_file_name")
    
    if not file_id or not file_name:
        await update.message.reply_text("❌ خطأ: الملف مفقود. يرجى البدء من جديد.")
        return await show_options_menu(update, context)
    
    try:
        file = await context.bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], delete=False) as input_file:
            await file.download_to_drive(input_file.name)
            input_path = input_file.name
        
        try:
            font = ttLib.TTFont(input_path)
        except Exception as e:
            logger.error(f"Error loading font file: {e}")
            await update.message.reply_text(f"❌ خطأ في تحميل ملف الخط: {str(e)}")
            os.remove(input_path)
            return await show_options_menu(update, context)
        
        with tempfile.NamedTemporaryFile(suffix=target_ext, delete=False) as output_file:
            output_path = output_file.name
        
        try:
            font.save(output_path)
        except Exception as e:
            logger.error(f"Error saving font file: {e}")
            await update.message.reply_text(f"❌ خطأ في حفظ ملف الخط: {str(e)}")
            os.remove(input_path)
            os.remove(output_path)
            return await show_options_menu(update, context)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(output_path, 'rb'),
            filename=os.path.splitext(file_name)[0] + target_ext,
            caption="تم تحويل الملف بواسطة بوت خطوط أحمد الغريب @quranfontbot"
        )
        
        os.remove(input_path)
        os.remove(output_path)
        
        if "font_file_id" in context.user_data:
            del context.user_data["font_file_id"]
        if "font_file_name" in context.user_data:
            del context.user_data["font_file_name"]
        
    except Exception as e:
        logger.error(f"Error during font conversion: {e}")
        await update.message.reply_text(f"❌ خطأ أثناء التحويل: {str(e)}")
        if os.path.exists("input_path"):
            os.remove("input_path")
        if os.path.exists("output_path"):
            os.remove("output_path")
    
    return await show_options_menu(update, context)

# --- وظيفة فك ضغط الملفات ---
async def extract_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await show_options_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    if not update.message.document:
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("⚠️ يرجى إرسال ملف ZIP أو RAR (حتى 500MB).", reply_markup=reply_markup)
        return EXTRACT_ARCHIVE
    
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    if not file_name.endswith(('.zip', '.rar')):
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("⚠️ الصيغة غير مدعومة. فقط ZIP أو RAR.", reply_markup=reply_markup)
        return EXTRACT_ARCHIVE
    
    if doc.file_size > 500 * 1024 * 1024:  # 500MB
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("⚠️ الملف أكبر من 500MB.", reply_markup=reply_markup)
        return EXTRACT_ARCHIVE
    
    try:
        file = await doc.get_file()
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], delete=False) as archive_file:
            await file.download_to_drive(archive_file.name)
            archive_path = archive_file.name
        
        extract_dir = tempfile.mkdtemp()
        
        if file_name.endswith('.zip'):
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        elif file_name.endswith('.rar'):
            with rarfile.RarFile(archive_path, 'r') as rar_ref:
                rar_ref.extractall(extract_dir)
        
        # إرسال الملفات المفكوكة
        for root, _, files in os.walk(extract_dir):
            for f in files:
                file_path = os.path.join(root, f)
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(file_path, 'rb'),
                    caption="تم فك ضغط الملف بواسطة بوت خطوط أحمد الغريب @quranfontbot"
                )
        
        # تنظيف
        os.remove(archive_path)
        for root, dirs, files in os.walk(extract_dir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(extract_dir)
        
    except Exception as e:
        logger.error(f"Error extracting archive: {e}")
        await update.message.reply_text(f"❌ خطأ أثناء فك الضغط: {str(e)}")
    
    return await show_options_menu(update, context)

# --- لوحة الإعدادات للأدمن ---
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(update.effective_user.id) not in ADMINS:
        if query:
            await query.edit_message_text("⚠️ هذا الأمر للأدمن فقط!")
        else:
            await update.message.reply_text("⚠️ هذا الأمر للأدمن فقط!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("✏️ تعديل رسالة الترحيب", callback_data="edit_welcome"),
         InlineKeyboardButton("📩 تعديل رسالة الرد", callback_data="edit_reply_msg")],
        [InlineKeyboardButton("➕ إضافة زر شفاف", callback_data="add_inline_button"),
         InlineKeyboardButton("➖ حذف زر شفاف", callback_data="remove_inline_button")],
        [InlineKeyboardButton("🚫 تعطيل الردود", callback_data="disable_responses"),
         InlineKeyboardButton("✅ تمكين الردود", callback_data="enable_responses")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="start"),
         InlineKeyboardButton("❌ إنهاء", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text("⚙️ لوحة الإعدادات:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("⚙️ لوحة الإعدادات:", reply_markup=reply_markup)
    return SETTINGS_MENU

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"Received callback query: {query.data} from user {query.from_user.id}")
    await query.answer()
    
    if query.data == "options_menu":
        await show_options_menu(update, context)
        return OPTIONS_MENU
    
    if query.data == "settings":
        if str(query.from_user.id) not in ADMINS:
            await query.edit_message_text("⚠️ هذا الأمر متاح للمديرين فقط!")
            return ConversationHandler.END
        await settings_menu(update, context)
        return SETTINGS_MENU
    
    if query.data == "developer_info":
        await show_developer_info(update, context)
        return ConversationHandler.END
    
    if str(query.from_user.id) not in ADMINS:
        await query.edit_message_text("⚠️ هذا الأمر متاح للمديرين فقط!")
        return ConversationHandler.END
    
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
            return ConversationHandler.END
    
    elif query.data == "view_all_messages":
        messages_data = load_user_messages()
        if not messages_data["messages"]:
            await query.edit_message_text("📭 لا توجد رسائل بعد.")
            return ConversationHandler.END
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
        return ConversationHandler.END
    
    # معالجة خيارات الإعدادات
    if query.data == "edit_welcome":
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="settings"), 
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("أرسل النص الجديد لرسالة الترحيب (استخدم \n للسطور الجديدة):", reply_markup=reply_markup)
        return EDIT_WELCOME
    
    elif query.data == "edit_reply_msg":
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="settings"), 
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("أرسل النص الجديد لرسالة الرد (استخدم {reply_text} لمكان الرد):", reply_markup=reply_markup)
        return EDIT_REPLY_MSG
    
    elif query.data == "add_inline_button":
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="settings"), 
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("أرسل نص الزر ورابط URL مفصولين بفاصلة (مثال: نص الزر,https://example.com):", reply_markup=reply_markup)
        return ADD_INLINE_BUTTON
    
    elif query.data == "remove_inline_button":
        buttons_data = load_inline_buttons()
        if not buttons_data["buttons"]:
            await query.edit_message_text("لا توجد أزرار للحذف.")
            return await settings_menu(update, context)
        keyboard = [[InlineKeyboardButton(btn["text"], callback_data=f"remove_button_{i}")] for i, btn in enumerate(buttons_data["buttons"])]
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="settings"), 
                        InlineKeyboardButton("❌ إلغاء", callback_data="cancel")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("اختر الزر للحذف:", reply_markup=reply_markup)
        return REMOVE_INLINE_BUTTON
    
    elif query.data == "disable_responses":
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="settings"), 
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("أرسل يوزر المجموعة أو رابطها أو IDها لتعطيل الردود فيها:", reply_markup=reply_markup)
        return DISABLE_RESPONSES_GROUP
    
    elif query.data == "enable_responses":
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="settings"), 
                    InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("أرسل يوزر المجموعة أو رابطها أو IDها لتمكين الردود فيها:", reply_markup=reply_markup)
        return ENABLE_RESPONSES_GROUP
    
    elif query.data.startswith("remove_button_"):
        index = int(query.data.split("_")[-1])
        buttons_data = load_inline_buttons()
        if 0 <= index < len(buttons_data["buttons"]):
            removed_button = buttons_data["buttons"].pop(index)
            save_inline_buttons(buttons_data)
            await query.edit_message_text(f"✅ تم حذف الزر '{removed_button['text']}'.")
        else:
            await query.edit_message_text("⚠️ الزر غير موجود!")
        return await settings_menu(update, context)
    
    elif query.data == "cancel":
        await query.edit_message_text("تم إلغاء العملية.")
        return ConversationHandler.END
    
    return ConversationHandler.END

async def handle_settings_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    
    if choice == "🔙 رجوع":
        return await start(update, context)
    
    if choice == "❌ إنهاء":
        await update.message.reply_text("تم إنهاء لوحة الإعدادات.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    if choice == "✏️ تعديل رسالة الترحيب":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("أرسل النص الجديد لرسالة الترحيب (استخدم \n للسطور الجديدة):", reply_markup=reply_markup)
        return EDIT_WELCOME
    
    elif choice == "📩 تعديل رسالة الرد على الرسائل":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("أرسل النص الجديد لرسالة الرد (استخدم {reply_text} لمكان الرد):", reply_markup=reply_markup)
        return EDIT_REPLY_MSG
    
    elif choice == "➕ إضافة زر شفاف":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("أرسل نص الزر ورابط URL مفصولين بفاصلة (مثال: نص الزر,https://example.com):", reply_markup=reply_markup)
        return ADD_INLINE_BUTTON
    
    elif choice == "➖ حذف زر شفاف":
        buttons_data = load_inline_buttons()
        if not buttons_data["buttons"]:
            await update.message.reply_text("لا توجد أزرار للحذف.")
            return await settings_menu(update, context)
        
        keyboard = [[btn["text"]] for btn in buttons_data["buttons"]]
        keyboard.append(["🔙 رجوع"])
        keyboard.append(["❌ إلغاء"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("اختر الزر للحذف:", reply_markup=reply_markup)
        return REMOVE_INLINE_BUTTON
    
    elif choice == "🚫 تعطيل الردود في مجموعة":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("أرسل يوزر المجموعة أو رابطها أو IDها لتعطيل الردود فيها:", reply_markup=reply_markup)
        return DISABLE_RESPONSES_GROUP
    
    elif choice == "✅ تمكين الردود في مجموعة":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("أرسل يوزر المجموعة أو رابطها أو IDها لتمكين الردود فيها:", reply_markup=reply_markup)
        return ENABLE_RESPONSES_GROUP
    
    return SETTINGS_MENU

async def disable_responses_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await settings_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    group_identifier = update.message.text.strip()
    try:
        if group_identifier.startswith('@') or group_identifier.startswith('https://t.me/'):
            chat = await context.bot.get_chat(group_identifier)
            group_id = str(chat.id)
        else:
            group_id = group_identifier
        
        settings = load_settings()
        settings["disabled_response_groups"].add(group_id)
        save_settings(settings)
        await update.message.reply_text(f"✅ تم تعطيل الردود في المجموعة {group_id}.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")
    
    return await settings_menu(update, context)

async def enable_responses_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await settings_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    group_identifier = update.message.text.strip()
    try:
        if group_identifier.startswith('@') or group_identifier.startswith('https://t.me/'):
            chat = await context.bot.get_chat(group_identifier)
            group_id = str(chat.id)
        else:
            group_id = group_identifier
        
        settings = load_settings()
        settings["disabled_response_groups"].discard(group_id)
        save_settings(settings)
        await update.message.reply_text(f"✅ تم تمكين الردود في المجموعة {group_id}.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")
    
    return await settings_menu(update, context)

async def edit_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await settings_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    new_message = update.message.text.split("\n")
    settings = load_settings()
    settings["welcome_message"] = new_message
    save_settings(settings)
    await update.message.reply_text("✅ تم تعديل رسالة الترحيب.")
    return await settings_menu(update, context)

async def edit_reply_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await settings_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    new_message = update.message.text
    settings = load_settings()
    settings["reply_message"] = new_message
    save_settings(settings)
    await update.message.reply_text("✅ تم تعديل رسالة الرد.")
    return await settings_menu(update, context)

async def add_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await settings_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    try:
        text, url = update.message.text.split(",", 1)
        text = text.strip()
        url = url.strip()
        buttons_data = load_inline_buttons()
        buttons_data["buttons"].append({"text": text, "url": url})
        save_inline_buttons(buttons_data)
        await update.message.reply_text("✅ تم إضافة الزر.")
    except:
        await update.message.reply_text("❌ تنسيق غير صحيح. مثال: نص الزر,https://example.com")
    return await settings_menu(update, context)

async def remove_inline_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🔙 رجوع":
        return await settings_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    text_to_remove = update.message.text
    buttons_data = load_inline_buttons()
    buttons_data["buttons"] = [btn for btn in buttons_data["buttons"] if btn["text"] != text_to_remove]
    save_inline_buttons(buttons_data)
    await update.message.reply_text("✅ تم حذف الزر.")
    return await settings_menu(update, context)

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "start")
    logger.info(f"Starting /start command for user {update.effective_user.id}")
    
    users_data = load_users()
    user_id = str(update.effective_user.id)
    
    if user_id not in users_data["users"]:
        users_data["users"][user_id] = {
            "name": update.effective_user.full_name,
            "username": update.effective_user.username,
            "first_seen": str(datetime.now())
        }
        save_users(users_data)
        await send_admin_notification(context, update.effective_user)
    
    settings = load_settings()
    channel_data = load_channel()
    buttons_data = load_inline_buttons()
    
    logger.info(f"Settings: {settings}")
    logger.info(f"Channel data: {channel_data}")
    logger.info(f"Inline buttons: {buttons_data}")
    
    buttons = [
        [
            InlineKeyboardButton("🛠️ لوحة الخيارات", callback_data="options_menu"),
            InlineKeyboardButton("👨‍💻 المطور", callback_data="developer_info")
        ]
    ]
    if channel_data["channel_url"]:
        buttons.append([InlineKeyboardButton("📢 قناة خطوط قرآن", url=channel_data["channel_url"])])
    
    for button in buttons_data["buttons"]:
        buttons.append([InlineKeyboardButton(button["text"], url=button["url"])])
    
    if user_id in ADMINS:
        buttons.append([InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    welcome_message = "\n".join(settings["welcome_message"])
    
    logger.info(f"Sending welcome message: {welcome_message}")
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    logger.info("Welcome message sent successfully")
    return ConversationHandler.END

def main():
    """Main function to initialize and run the Telegram bot."""
    print("🚀 Starting the bot...")

    try:
        # Initialize the Application with the bot token
        application = Application.builder().token(TOKEN).build()

        # --- أولاً: أضف الـ CommandHandlers المباشرة (للأوامر مثل /start) ---
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("add", start_add_response))
        application.add_handler(CommandHandler("remove", remove_response))
        application.add_handler(CommandHandler("list", list_responses))
        application.add_handler(CommandHandler("users", show_users))
        application.add_handler(CommandHandler("stats", show_stats))
        application.add_handler(CommandHandler("messages", view_user_messages))
        application.add_handler(CommandHandler("admin", check_admin))
        application.add_handler(CommandHandler("export", export_responses))
        application.add_handler(CommandHandler("import", import_responses))
        application.add_handler(CommandHandler("channel", start_add_channel))
        application.add_handler(CommandHandler("restart", restart_bot))
        # أضف أي أوامر أخرى هنا إذا كانت موجودة

        # --- ثانياً: أضف الـ ConversationHandlers (التي تبدأ بأوامر أو callbacks) ---
        add_response_handler = ConversationHandler(
            entry_points=[CommandHandler("add", start_add_response)],
            states={
                ADD_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_keyword)],
                ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_response_text)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(add_response_handler)

        reply_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_callback, pattern="^reply_")],
            states={
                REPLY_TO_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_user_message)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(reply_handler)

        import_handler = ConversationHandler(
            entry_points=[CommandHandler("import", import_responses)],
            states={
                IMPORT_RESPONSES: [MessageHandler(filters.Document.ALL, process_import_file)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(import_handler)

        channel_handler = ConversationHandler(
            entry_points=[CommandHandler("channel", start_add_channel)],
            states={
                ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_url)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(channel_handler)

        broadcast_handler = ConversationHandler(
            entry_points=[CommandHandler("broadcast", start_broadcast)],
            states={
                BROADCAST_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_broadcast_type)],
                BROADCAST_MESSAGE: [MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_message)],
                BROADCAST_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_broadcast)]
            },
            fallbacks=[CommandHandler("cancel", cancel_broadcast)]
        )
        application.add_handler(broadcast_handler)

        options_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_callback, pattern="^options_menu$")],
            states={
                OPTIONS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_options_choice)],
                CONVERT_TO_SVG: [MessageHandler(filters.ALL & ~filters.COMMAND, convert_to_svg)],
                CONVERT_FONT: [MessageHandler(filters.ALL & ~filters.COMMAND, convert_font)],
                CHOOSE_FONT_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_font_format)],
                EXTRACT_ARCHIVE: [MessageHandler(filters.ALL & ~filters.COMMAND, extract_archive)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(options_handler)

        settings_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_callback, pattern="^settings$")],
            states={
                SETTINGS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_choice)],
                EDIT_WELCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_welcome)],
                EDIT_REPLY_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_reply_msg)],
                ADD_INLINE_BUTTON: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_inline_button)],
                REMOVE_INLINE_BUTTON: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_inline_button)],
                DISABLE_RESPONSES_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, disable_responses_group)],
                ENABLE_RESPONSES_GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, enable_responses_group)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)],
            per_message=True
        )
        application.add_handler(settings_handler)

        # --- ثالثاً: أضف الـ CallbackQueryHandler العام ---
        application.add_handler(CallbackQueryHandler(button_callback))

        # --- أخيراً: أضف الـ MessageHandler العام (للرسائل غير المعالجة) ---
        application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, handle_message))
        application.add_handler(MessageHandler(filters.UpdateType.EDITED, handle_message))

        # --- Start the Bot ---
        print("✅ Bot initialized successfully. Starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)  # إضافة drop_pending_updates لتجاهل الرسائل القديمة

    except Exception as e:
        print(f"❌ Error starting the bot: {str(e)}")
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":

    main()
