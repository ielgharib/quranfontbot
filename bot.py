from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
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

# --- الإعدادات الأساسية ---
TOKEN = "8121446313:AAGEUUnViMDuf504BDm-cgBpdUk33CnJq-M"
ADMINS = ["634869382"]  # قائمة بآيدي المديرين
BROADCAST_CONFIRM = {}  # لتخزين بيانات الإذاعة قبل التأكيد

# --- ملفات التخزين ---
RESPONSES_FILE = "responses.json"
STATS_FILE = "stats.json"
USERS_FILE = "users.json"
MESSAGES_FILE = "user_messages.json"
CHANNEL_FILE = "channel.json"  # ملف لتخزين رابط قناة السورس

# --- حالات المحادثة ---
ADD_KEYWORD, ADD_RESPONSE = range(2)
REPLY_TO_USER = range(1)
IMPORT_RESPONSES = range(4)
ADD_CHANNEL = range(5)  # حالة لإضافة رابط القناة

# --- إعداد التسجيل لتصحيح الأخطاء ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تحميل البيانات ---
def load_data(filename, default_data):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "total_users" in data and isinstance(data["total_users"], list):
                data["total_users"] = set(data["total_users"])
            if "total_groups" in data and isinstance(data["total_groups"], list):
                data["total_groups"] = set(data["total_groups"])
            return data
    return default_data.copy()

def save_data(filename, data):
    data_to_save = data.copy()
    if "total_users" in data_to_save and isinstance(data_to_save["total_users"], set):
        data_to_save["total_users"] = list(data_to_save["total_users"])
    if "total_groups" in data_to_save and isinstance(data_to_save["total_groups"], set):
        data_to_save["total_groups"] = list(data_to_save["total_groups"])
    
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
    
    # التصحيح هنا: استبدال save_stats بـ save_data
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

async def reply_to_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_text = update.message.text
    message_id = context.user_data["reply_message_id"]
    messages_data = load_user_messages()
    msg_data = messages_data["messages"][message_id]
    user_id = msg_data["user_id"]
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💬 رد من الإدارة:\n\n{reply_text}",
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
    
    BROADCAST_CONFIRM[chat_id] = {"type": broadcast_type}
    
    await update.message.reply_text(
        "✍️ الرجاء إرسال الرسالة التي تريد إذاعتها:",
        reply_markup=ReplyKeyboardRemove(),
        disable_web_page_preview=True
    )
    return "BROADCAST_MESSAGE"

async def receive_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = str(update.effective_chat.id)
    
    if chat_id not in BROADCAST_CONFIRM:
        await update.message.reply_text("حدث خطأ، يرجى البدء من جديد.", disable_web_page_preview=True)
        return ConversationHandler.END
    
    BROADCAST_CONFIRM[chat_id]["message"] = message.text or message.caption
    BROADCAST_CONFIRM[chat_id]["message_obj"] = message
    
    keyboard = [["✅ نعم، قم بالإرسال", "❌ لا، إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        f"⚠️ تأكيد الإذاعة:\n\n"
        f"النوع: {BROADCAST_CONFIRM[chat_id]['type']}\n"
        f"الرسالة: {BROADCAST_CONFIRM[chat_id]['message']}\n\n"
        f"عدد المستلمين المتوقع: {await estimate_recipients(BROADCAST_CONFIRM[chat_id]['type'])}",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )
    return "BROADCAST_CONFIRMATION"

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
    
    if choice == "❌ لا، إلغاء":
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
    
    await update.message.reply_text(
        f"📢 رابط القناة الحالي: {current_channel}\n\n"
        "الرجاء إرسال رابط القناة الجديد (مثل @ChannelName أو https://t.me/ChannelName):\n"
        "أو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return ADD_CHANNEL

async def add_channel_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_url = update.message.text.strip()
    
    # التحقق من صحة الرابط
    if not (channel_url.startswith("@") or channel_url.startswith("https://t.me/")):
        await update.message.reply_text(
            "❌ الرابط غير صالح! يجب أن يكون على شكل @ChannelName أو https://t.me/ChannelName\n"
            "الرجاء إرسال رابط صالح أو /cancel لإلغاء العملية",
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
            "👨‍💻 معلومات المطور:",
            f"📛 الاسم: {developer_name}",
            f"🔗 اليوزر: {developer_username}",
            f"📌 البايو: {developer_bio}"
        ]
        
        # إضافة الأزرار الشفافة
        keyboard = [
            [InlineKeyboardButton("📚 مجموعة نقاشات الخطوط", url="https://t.me/ElgharibFonts")]
        ]
        
        # إضافة زر القناة إذا كان موجودًا
        channel_data = load_channel()
        if channel_data["channel_url"]:
            keyboard.append([InlineKeyboardButton("📢 قناة الخطوط", url=channel_data["channel_url"])])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if developer.photo:
            try:
                file = await developer.photo.get_big_file()
                photo_file = await file.download_to_drive()
                with open(photo_file, 'rb') as f:
                    photo_bytes = f.read()
                
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo_bytes,
                    caption="\n".join(message),
                    reply_markup=reply_markup,
                    disable_notification=True
                )
                photo_file.unlink()
                logger.info("Successfully downloaded and sent developer photo")
            except Exception as e:
                logger.error(f"Error downloading photo: {e}")
                await update.message.reply_text(
                    "\n".join(message),
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
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

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "start")
    
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
    
    start_message = [
        "مرحبًا! 👋 أنا بوت الخطوط التلقائي.",
        "",
        "🎯 كيفية الاستخدام:",
        "- عندما يتم ذكر أي كلمة مسجلة، سأقوم بالرد تلقائياً",
        "- إذا تم الرد على رسالة تحتوي كلمة مسجلة، سأرد على الرسالة الأصلية",
        "- يمكنك إرسال رسائل خاصة لي وسيتم توجيهها للإدارة",
        "",
        "🔧 تم تطوير وبرمجة البوت بواسطة أحمد الغريب",
        "- @Am9li9",
    ]
    
    # إنشاء الأزرار الشفافة
    keyboard = [
        [InlineKeyboardButton("👨‍💻 معلومات المطور", url="https://t.me/Am9li9")],
        [InlineKeyboardButton("📚 مجموعة نقاشات الخطوط", url="https://t.me/ElgharibFonts")]
    ]
    
    # إضافة زر القناة إذا كان موجودًا
    channel_data = load_channel()
    if channel_data["channel_url"]:
        keyboard.append([InlineKeyboardButton("📢 قناة السورس", url=channel_data["channel_url"])])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if str(update.effective_user.id) in ADMINS:
        start_message.extend([
            "",
            "⚙️ الأوامر الإدارية:",
            "/add - إضافة رد جديد",
            "/remove <الكلمة> - حذف رد",
            "/list - عرض كل الردود",
            "/stats - إحصائيات البوت",
            "/users - عرض المستخدمين",
            "/messages - عرض رسائل المستخدمين",
            "/broadcast - إرسال إذاعة للمستخدمين",
            "/export - تصدير الردود",
            "/import - استيراد الردود",
            "/addchannel - إضافة/تعديل رابط قناة السورس",
            "/developer - عرض معلومات المطور",
            "✍️ اكتب 'المطور' لعرض معلومات المطور"
        ])
    
    await update.message.reply_text(
        "\n".join(start_message),
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

# --- الدالة الرئيسية ---
def main():
    application = Application.builder().token(TOKEN).build()
    
    add_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", start_add_response)],
        states={
            ADD_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_keyword)],
            ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_response_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    import_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("import", import_responses)],
        states={
            IMPORT_RESPONSES: [MessageHandler(filters.Document.ALL | filters.TEXT & ~filters.COMMAND, process_import_file)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    reply_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^reply_")],
        states={
            REPLY_TO_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_user_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast)],
        states={
            "BROADCAST_TYPE": [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_broadcast_type)],
            "BROADCAST_MESSAGE": [MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_message)],
            "BROADCAST_CONFIRMATION": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_broadcast)]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)]
    )
    
    add_channel_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addchannel", start_add_channel)],
        states={
            ADD_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_url)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    application.add_handler(add_conv_handler)
    application.add_handler(import_conv_handler)
    application.add_handler(reply_conv_handler)
    application.add_handler(broadcast_conv_handler)
    application.add_handler(add_channel_conv_handler)
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
    application.add_handler(CommandHandler("developer", show_developer_info))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    
    print("🤖 البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()