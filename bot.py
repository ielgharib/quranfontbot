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

# --- الإعدادات الأساسية ---
TOKEN = "7926558096:AAEiSSyGzXbqJQLCTRoPdaeffSuQ6e6_e1E"
ADMINS = ["634869382"]  # قائمة بآيدي المديرين (استبدل 123456789 بآيدي المدير الجديد)
BROADCAST_CONFIRM = {}  # لتخزين بيانات الإذاعة قبل التأكيد

# --- ملفات التخزين ---
RESPONSES_FILE = "responses.json"
STATS_FILE = "stats.json"
USERS_FILE = "users.json"  # ملف جديد لتخزين معلومات المستخدمين
MESSAGES_FILE = "user_messages.json"  # ملف جديد لتخزين رسائل المستخدمين

# --- حالات المحادثة ---
ADD_KEYWORD, ADD_RESPONSE = range(2)
REPLY_TO_USER = range(1)

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
        # إنشاء ملف مؤقت
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

def load_responses():
    return load_data(RESPONSES_FILE, {})

def save_responses(responses):
    save_data(RESPONSES_FILE, responses)

# --- إدارة الإحصائيات ---
def load_stats():
    return load_data(STATS_FILE, {
        "total_users": set(),
        "total_groups": set(),
        "commands_used": {},
        "last_active": {}
    })

def save_stats(stats):
    save_data(STATS_FILE, stats)

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
            chat_id=ADMINS[0],  # إرسال الإشعار للمدير الأول
            text=user_info,
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Error sending admin notification: {e}")

# --- إرسال رسالة المستخدم للمدير ---
async def forward_message_to_admin(context, user, message):
    try:
        # حفظ الرسالة في قاعدة البيانات
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
        
        # إرسال الرسالة للمدير مع أزرار الرد
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
        print(f"Error forwarding message to admin: {e}")
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
    
    save_stats(stats)

# --- معالجة الرسائل المحدثة ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update)
    
    # تسجيل المستخدم إذا كان جديداً
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
    
    # تحقق إذا كانت الرسالة معدلة
    is_edited = bool(update.edited_message)
    
    original_text = message.text if message.text else ""
    
    # تحقق مما إذا بدأت الرسالة بـ . أو / (بعد إزالة أي مسافات)
    should_delete = original_text.lstrip().startswith(('.', '/'))
    
    # إذا كانت رسالة خاصة وليست من مدير، أرسلها للمدير
    if message.chat.type == "private" and str(update.effective_user.id) not in ADMINS:
        # ... (الكود الخاص بالرسائل الخاصة يبقى كما هو)
        return
    
    # المعالجة العادية للرسائل في المجموعات أو من المديرين
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
        combined_response = "\n\n".join([item['response'] for item in found_responses])
        target_message = message.reply_to_message if message.reply_to_message else message
        
        # إذا كانت الرسالة معدلة، نتحقق من التغييرات في الكلمات المفتاحية
        if is_edited and 'last_response_id' in context.user_data:
            old_keywords = context.user_data.get('last_keywords', set())
            
            # إذا لم تتغير الكلمات المفتاحية، لا نقوم بأي شيء
            if old_keywords == current_keywords:
                return
                
            # إذا تغيرت الكلمات المفتاحية، نحذف الرد القديم
            try:
                await context.bot.delete_message(
                    chat_id=message.chat.id,
                    message_id=context.user_data['last_response_id']
                )
            except Exception as e:
                print(f"Failed to delete previous response: {e}")
        
        # إرسال الرد الجديد وحفظ البيانات
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
                context.user_data.update({
                    'last_response_id': sent_message.message_id,
                    'last_keywords': current_keywords
                })
            except Exception as e:
                print(f"Failed to send reply: {e}")
                sent_message = await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=combined_response,
                    disable_web_page_preview=True
                )
                context.user_data.update({
                    'last_response_id': sent_message.message_id,
                    'last_keywords': current_keywords
                })
        else:
            sent_message = await context.bot.send_message(
                chat_id=message.chat.id,
                text=combined_response,
                reply_to_message_id=target_message.message_id,
                disable_web_page_preview=True
            )
            context.user_data.update({
                'last_response_id': sent_message.message_id,
                'last_keywords': current_keywords
            })
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
        # إرسال الرد للمستخدم
        await context.bot.send_message(
            chat_id=user_id,
            text=f"💬 رد من الإدارة:\n\n{reply_text}",
            disable_web_page_preview=True
        )
        
        # تحديث حالة الرسالة
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
    
    # تنظيف البيانات المؤقتة
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
    
    # عرض آخر 10 رسائل
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
    
    # عرض آخر 5 مستخدمين
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
    else:  # للجميع
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
    
    # إرسال الإذاعة
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
                print(f"Failed to send to group {group_id}: {e}")
                failed += 1
    
    if broadcast_data["type"] in ["👤 للمستخدمين فقط", "🌍 للجميع (مجموعات ومستخدمين)"]:
        for user_id in users_data["users"]:
            try:
                await message_obj.copy(chat_id=user_id)
                success += 1
            except Exception as e:
                print(f"Failed to send to user {user_id}: {e}")
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

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "start")
    
    # تسجيل المستخدم إذا كان جديداً
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
        "- يمكنك إرسال رسائل خاصة لي وسيتم توجيهها للإدارة"
    ]
    
    # إظهار الأوامر فقط للمدير
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
            "/broadcast - إرسال إذاعة للمستخدمين"
        ])
    
    start_message.extend([
        "",
        "🔧 تم تطوير وبرمجة البوت بواسطة أحمد الغريب",
        "- @Am9li9",
        "📚 مجموعة نقاشات الخطوط ↓",
        "- @ElgharibFonts",
    ])
    
    await update.message.reply_text(
        "\n".join(start_message),
        disable_web_page_preview=True
    )

# --- الدالة الرئيسية ---
def main():
    application = Application.builder().token(TOKEN).build()
    
    # محادثة إضافة الردود
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", start_add_response)],
        states={
            ADD_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_keyword)],
            ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_response_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    # محادثة الرد على المستخدمين
    reply_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^reply_")],
        states={
            REPLY_TO_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_user_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
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
    
    # تسجيل المعالجات
    application.add_handler(conv_handler)
    application.add_handler(reply_conv_handler)
    application.add_handler(broadcast_conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("remove", remove_response))
    application.add_handler(CommandHandler("list", list_responses))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("users", show_users))
    application.add_handler(CommandHandler("messages", view_user_messages))
    application.add_handler(CommandHandler("admin", check_admin))
    application.add_handler(CommandHandler("export", export_responses))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    
    print("🤖 البوت يعمل الآن...")
    application.run_polling()

if __name__ == "__main__":
    main()
