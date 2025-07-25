from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
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

# --- حالات المحادثة ---
ADD_KEYWORD, ADD_RESPONSE = range(2)

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

# --- إدارة الردود ---
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

# --- معالجة الرسائل ---
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
    
    message = update.message
    original_text = message.text if message.text else ""
    responses = load_responses()

    # تحضير قوائم الردود
    found_responses = []
    used_positions = set()  # لتجنب التداخل بين الكلمات

    # البحث عن الكلمات المفتاحية بترتيب طولها (من الأطول إلى الأقصر)
    sorted_keywords = sorted(responses.keys(), key=len, reverse=True)
    
    for keyword in sorted_keywords:
        if keyword in original_text:
            start_pos = original_text.find(keyword)
            end_pos = start_pos + len(keyword)
            
            # التحقق من عدم تداخل هذه الكلمة مع كلمات سبق الرد عليها
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
    
    # ترتيب الردود حسب ظهورها في النص الأصلي
    found_responses.sort(key=lambda x: x['position'])
    
    # إرسال الرد الموحد
    if found_responses:
        combined_response = "\n\n".join([item['response'] for item in found_responses])
        
        if message.reply_to_message:
            await context.bot.send_message(
                chat_id=message.chat.id,
                text=combined_response,
                reply_to_message_id=message.reply_to_message.message_id,
                disable_web_page_preview=True
            )
        else:
            await message.reply_text(
                combined_response,
                disable_web_page_preview=True
            )
    return

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
    
    await update.message.reply_text(
        "❌ تم إلغاء عملية الإضافة.",
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
            "استخدم الأمر هكذا: .ازالة <الكلمة>",
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
    
    message = [
        "📊 إحصائيات البوت:",
        f"👤 عدد المستخدمين الفريدين: {len(users_data['users'])}",
        f"👥 عدد المجموعات/القنوات: {len(stats['total_groups'])}",
        f"📝 عدد الردود المسجلة: {len(responses)}",
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
        "- إذا تم الرد على رسالة تحتوي كلمة مسجلة، سأرد على الرسالة الأصلية"
    ]
    
    # إظهار الأوامر فقط للمدير
    if str(update.effective_user.id) in ADMINS:
        start_message.extend([
            "",
            "⚙️ الأوامر الإدارية:",
            ".اضافة - إضافة رد جديد",
            ".ازالة <الكلمة> - حذف رد",
            "/list - عرض كل الردود",
            "/stats - إحصائيات البوت",
            "/users - عرض المستخدمين",
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
    
    # محادثة إضافة الردود (تم تغيير الأمر من add إلى اضافة)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("اضافة", start_add_response)],
        states={
            ADD_KEYWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_keyword)],
            ADD_RESPONSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_response_text)]
        },
        fallbacks=[CommandHandler("cancel", cancel_add_response)]
    )
    
    # محادثة الإذاعة
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", start_broadcast)],
        states={
            "BROADCAST_TYPE": [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_broadcast_type)],
            "BROADCAST_MESSAGE": [MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_message)],
            "BROADCAST_CONFIRMATION": [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_broadcast)]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)]
    )
    
    # إضافة handlers
    application.add_handler(conv_handler)
    application.add_handler(broadcast_conv)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("ازالة", remove_response))
    application.add_handler(CommandHandler("list", list_responses))
    application.add_handler(CommandHandler("admin", check_admin))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("users", show_users))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == "__main__":
    # إنشاء ملفات التخزين إذا لم تكن موجودة
    if not os.path.exists(RESPONSES_FILE):
        save_responses({})
    if not os.path.exists(STATS_FILE):
        save_stats(load_stats())
    if not os.path.exists(USERS_FILE):
        save_users({"users": {}})
    
    main()
