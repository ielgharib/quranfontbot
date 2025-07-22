from telegram import Update, ReplyParameters
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
TOKEN = "7949198245:AAHkt-i-lwR9pb5Ix3wvTQBKLFLimIow-34"  # استبدل بتوكن البوت الخاص بك
ADMIN_ID = "5818029353"  # استبدل بآيدي حسابك (يمكن الحصول عليه من @userinfobot)

# --- ملفات التخزين ---
RESPONSES_FILE = "responses.json"
STATS_FILE = "stats.json"

# --- حالات المحادثة ---
ADD_KEYWORD, ADD_RESPONSE = range(2)

# --- تحميل البيانات ---
def load_data(filename, default_data):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # تحويل القوائم إلى مجموعات إذا لزم الأمر
            if "total_users" in data and isinstance(data["total_users"], list):
                data["total_users"] = set(data["total_users"])
            if "total_groups" in data and isinstance(data["total_groups"], list):
                data["total_groups"] = set(data["total_groups"])
            return data
    return default_data.copy()

def save_data(filename, data):
    # تحويل المجموعات إلى قوائم للتخزين
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
    
    message = update.message
    text = message.text.lower() if message.text else ""
    
    responses = load_responses()
    
    for keyword, response in responses.items():
        if keyword.lower() in text:
            if message.reply_to_message:
                reply_params = ReplyParameters(
                    message_id=message.reply_to_message.message_id,
                    chat_id=message.chat.id
                )
                await context.bot.send_message(
                    chat_id=message.chat.id,
                    text=response,
                    reply_parameters=reply_params
                )
            else:
                await message.reply_text(response)
            return

# --- إضافة رد (نظام المحادثة) ---
async def start_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإضافة ردود!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 الرجاء إرسال الكلمة المفتاحية التي تريد إضافة رد لها:\n"
        "أو /cancel لإلغاء العملية"
    )
    return ADD_KEYWORD

async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text
    context.user_data["temp_keyword"] = keyword
    
    await update.message.reply_text(
        f"🔹 الكلمة المحددة: {keyword}\n\n"
        "الرجاء إرسال الرد الذي تريد ربطه بهذه الكلمة:\n"
        "أو /cancel لإلغاء العملية"
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
        f"الرد: {response}"
    )
    return ConversationHandler.END

async def cancel_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "temp_keyword" in context.user_data:
        del context.user_data["temp_keyword"]
    
    await update.message.reply_text("❌ تم إلغاء عملية الإضافة.")
    return ConversationHandler.END

# --- إزالة رد ---
async def remove_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "remove")
    
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لحذف ردود!")
        return
    
    if not context.args:
        await update.message.reply_text("استخدم الأمر هكذا: /remove <الكلمة>")
        return
    
    keyword = ' '.join(context.args)
    responses = load_responses()
    
    if keyword in responses:
        del responses[keyword]
        save_responses(responses)
        await update.message.reply_text(f"✅ تم حذف الرد للكلمة '{keyword}'")
    else:
        await update.message.reply_text(f"❌ لا يوجد رد مسجل للكلمة '{keyword}'")

# --- عرض الردود ---
async def list_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "list")
    
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لعرض الردود!")
        return
    
    responses = load_responses()
    
    if not responses:
        await update.message.reply_text("لا توجد ردود مسجلة بعد.")
        return
    
    message = ["📜 قائمة الردود المسجلة:\n"]
    for keyword, response in responses.items():
        message.append(f"\n🔸 {keyword}:")
        message.append(f"   ↳ {response}")
    
    # تقسيم الرسالة إذا كانت طويلة
    full_message = "\n".join(message)
    if len(full_message) > 4000:
        parts = [full_message[i:i+4000] for i in range(0, len(full_message), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(full_message)

# --- الإحصائيات ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "stats")
    
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⚠️ هذا الأمر متاح للمدير فقط!")
        return
    
    stats = load_stats()
    
    message = [
        "📊 إحصائيات البوت:",
        f"👤 عدد المستخدمين الفريدين: {len(stats['total_users'])}",
        f"👥 عدد المجموعات/القنوات: {len(stats['total_groups'])}",
        "\n📌 الأوامر الأكثر استخدامًا:"
    ]
    
    sorted_commands = sorted(stats["commands_used"].items(), key=lambda x: x[1], reverse=True)[:5]
    for cmd, count in sorted_commands:
        message.append(f"- {cmd}: {count} مرة")
    
    message.extend(["\n⏱ آخر 3 نشاطات:"])
    last_activities = sorted(stats["last_active"].items(), key=lambda x: x[1]["time"], reverse=True)[:3]
    for user_id, activity in last_activities:
        message.append(f"- المستخدم {user_id[:4]}...: {activity['command']} في {activity['time'][:16]}")
    
    await update.message.reply_text("\n".join(message))

# --- التحقق من الصلاحيات ---
async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "admin")
    
    if str(update.effective_user.id) == ADMIN_ID:
        await update.message.reply_text("🎖️ أنت المدير! لديك جميع الصلاحيات.")
    else:
        await update.message.reply_text("👤 أنت مستخدم عادي. فقط المدير يمكنه إدارة الردود.")

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update_stats(update, "start")
    
    start_message = [
        "مرحباً! 👋 أنا بوت الردود التلقائي.",
        "",
        "🎯 كيفية الاستخدام:",
        "- عندما يتم ذكر أي كلمة مسجلة، سأقوم بالرد تلقائياً",
        "- إذا تم الرد على رسالة تحتوي كلمة مسجلة، سأرد على الرسالة الأصلية",
        "",
        "⚙️ الأوامر المتاحة:",
        "/add - إضافة رد جديد (للمدير فقط)",
        "/remove <الكلمة> - حذف رد (للمدير فقط)",
        "/list - عرض كل الردود (للمدير فقط)",
        "/stats - إحصائيات البوت (للمدير فقط)",
        "/admin - التحقق من صلاحياتك",

        "🔧 تم تطوير وبرمجة البوت بواسطة أحمد الغريب",
"- @Am9li9",
"📚 مجموعة نقاشات الخطوط ↓",
"- @ElgharibFonts",
    ]
    
    await update.message.reply_text("\n".join(start_message))

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
    
    # إضافة handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("remove", remove_response))
    application.add_handler(CommandHandler("list", list_responses))
    application.add_handler(CommandHandler("admin", check_admin))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    application.run_polling()

if __name__ == "__main__":
    # إنشاء ملفات التخزين إذا لم تكن موجودة
    if not os.path.exists(RESPONSES_FILE):
        save_responses({})
    if not os.path.exists(STATS_FILE):
        save_stats(load_stats())
    
    main()