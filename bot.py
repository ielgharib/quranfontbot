import os
from dotenv import load_dotenv
load_dotenv()  # لتحميل متغيرات البيئة من ملف .env
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
from datetime import datetime
import logging
from telegram.constants import ChatType
from telegram.constants import ParseMode
# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("TELEGRAM_TOKEN") or "7780931009:AAFkwcVo6pbABBS5NiNuAzi0-P13GQB3hiw"  # النسخة الاحتياطية لأغراض الاختبار
ADMINS = ["634869382"]  # قائمة بآيدي المديرين

# --- ملفات التخزين ---
RESPONSES_FILE = "responses.json"

# --- حالات المحادثة ---
(
    ADD_KEYWORD, ADD_RESPONSE,
    IMPORT_RESPONSES
) = range(3)

# --- إعداد التسجيل لتصحيح الأخطاء ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تحميل البيانات ---
def load_data(filename, default_data):
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON in {filename}: {e}")
            return default_data.copy()
    return default_data.copy()

def save_data(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# --- إدارة الردود ---
def load_responses():
    return load_data(RESPONSES_FILE, {})

def save_responses(responses):
    save_data(RESPONSES_FILE, responses)

# --- تصدير الردود ---
async def export_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لتصدير الردود!",
            disable_web_page_preview=True
        )
        return
    
    responses = load_responses()
    if not responses:
        await update.message.reply_text(
            "❌ لا توجد ردود لتصديرها!",
            disable_web_page_preview=True
        )
        return
    
    try:
        with open(RESPONSES_FILE, 'rb') as file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file,
                caption=f"📁 ملف الردود الحالي\n📊 عدد الردود: {len(responses)}",
                filename="responses_backup.json"
            )
    except Exception as e:
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء تصدير الملف: {str(e)}",
            disable_web_page_preview=True
        )

# --- استيراد الردود ---
async def import_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text(
            "⚠️ ليس لديك صلاحية لاستيراد الردود!",
            disable_web_page_preview=True
        )
        return IMPORT_RESPONSES
    
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
        document = update.message.document
        if not document.file_name.lower().endswith('.json'):
            raise ValueError("الملف يجب أن يكون بتنسيق JSON.")
        
        file = await document.get_file()
        temp_file_path = "temp_responses.json"
        await file.download_to_drive(temp_file_path)
        
        with open(temp_file_path, 'r', encoding='utf-8') as f:
            imported_data = json.load(f)
        
        if not isinstance(imported_data, dict):
            raise ValueError("تنسيق الملف غير صحيح. يجب أن يكون قاموس {keyword: response}.")
        
        current_responses = load_responses()
        added_count = 0
        updated_count = 0
        for key, value in imported_data.items():
            if key in current_responses:
                if current_responses[key] != value:
                    current_responses[key] = value
                    updated_count += 1
            else:
                current_responses[key] = value
                added_count += 1
        
        save_responses(current_responses)
        os.remove(temp_file_path)
        
        summary = f"✅ تم استيراد الردود بنجاح!\n"
        summary += f"➕ إضافة جديدة: {added_count}\n"
        summary += f"🔄 تحديث موجود: {updated_count}\n"
        summary += f"📊 إجمالي الردود الآن: {len(current_responses)}"
        
        await update.message.reply_text(summary, disable_web_page_preview=True)
    except Exception as e:
        if os.path.exists("temp_responses.json"):
            os.remove("temp_responses.json")
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء استيراد الملف: {str(e)}",
            disable_web_page_preview=True
        )
    return ConversationHandler.END

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

# --- معالجة الرسائل المحدثة ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message and not update.edited_message:
        return
        
    message = update.message or update.edited_message
    original_text = message.text if message.text else (message.caption if message.caption else "")
    
    # تحقق إضافي: إذا كانت الرسالة أمر (تبدأ بـ /)، تخطي handle_message للسماح لـ CommandHandler بالتعامل معها
    if original_text.startswith('/'):
        logger.info(f"Skipping handle_message for command: {original_text}")
        return  # هذا يسمح للأمر بالمرور إلى الـ handler المناسب
    
    message = update.message or update.edited_message
    if not message:
        return
    
    is_edited = bool(update.edited_message)
    original_text = message.text if message.text else (message.caption if message.caption else "")
    should_delete = original_text.lstrip().startswith(('.', '/')) if original_text else False
    
    if message.chat.type == ChatType.PRIVATE and str(update.effective_user.id) not in ADMINS:
        await context.bot.send_message(
            chat_id=message.chat.id,
            text="عُذرًا، البوت لا يستقبل الرسائل.\nللتواصل واستفسارات الخطوط\nتواصل عبر نقاشات خطوط أحمد الغريب\n@ElgharibFonts",
            disable_web_page_preview=True
        )
        return
    
    responses = load_responses()
    found_responses = []
    used_positions = set()
    current_keywords = set()
    sorted_keywords = sorted(responses.keys(), key=len, reverse=True)
    
    for keyword in sorted_keywords:
        is_english = any(c.isascii() and c.isalpha() for c in keyword)
        if is_english:
            lower_text = original_text.lower()
            lower_keyword = keyword.lower()
            start_pos = lower_text.find(lower_keyword)
        else:
            start_pos = original_text.find(keyword)
        if start_pos != -1:
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
        # إذا كانت هناك كلمة مفتاحية واحدة فقط، استخدم تنسيق الاقتباس
        if len(found_responses) == 1:
            keyword = found_responses[0]['keyword']
            response = found_responses[0]['response']
            combined_response = f"> {keyword}\n\n{response}"
        else:
            # إذا كانت هناك أكثر من كلمة مفتاحية، استخدم التنسيق العادي
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
                    parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
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
                    parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
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
                parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
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
    
    if query.data == "developer_info":
        await show_developer_info(update, context)
        return

# --- إضافة رد (نظام المحادثة) ---
async def start_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإضافة ردود!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📝 الرجاء إرسال الكلمة المفتاحية التي تريد إضافة رد لها:\n"
        "أو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return ADD_KEYWORD

async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()
    if not keyword:
        await update.message.reply_text(
            "⚠️ الكلمة المفتاحية لا يمكن أن تكون فارغة! أعد المحاولة.",
            disable_web_page_preview=True
        )
        return ADD_KEYWORD
    
    context.user_data["temp_keyword"] = keyword
    
    await update.message.reply_text(
        f"🔹 الكلمة المحددة: {keyword}\n\n"
        "الرجاء إرسال الرد الذي تريد ربطه بهذه الكلمة (يمكن استخدام تنسيق Markdown):\n"
        "أو /cancel لإلغاء العملية",
        disable_web_page_preview=True
    )
    return ADD_RESPONSE

async def add_response_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = context.user_data.get("temp_keyword")
    if not keyword:
        await update.message.reply_text(
            "❌ خطأ: الكلمة المفتاحية مفقودة. يرجى البدء من جديد بـ /add",
            disable_web_page_preview=True
        )
        return ConversationHandler.END
    
    response = update.message.text.strip()
    if not response:
        await update.message.reply_text(
            "⚠️ الرد لا يمكن أن يكون فارغاً! أعد المحاولة.",
            disable_web_page_preview=True
        )
        return ADD_RESPONSE
    
    responses = load_responses()
    if keyword in responses:
        await update.message.reply_text(
            f"⚠️ الكلمة '{keyword}' موجودة بالفعل. سيتم تحديث الرد.",
            disable_web_page_preview=True
        )
    
    responses[keyword] = response
    save_responses(responses)
    
    del context.user_data["temp_keyword"]
    
    await update.message.reply_text(
        f"✅ تم الحفظ بنجاح!\n\n"
        f"الكلمة: {keyword}\n"
        f"الرد: {response}\n\n"
        f"📊 إجمالي الردود الآن: {len(responses)}",
        parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
        disable_web_page_preview=True
    )
    return ConversationHandler.END

# --- إزالة رد ---
async def remove_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    keyword = ' '.join(context.args).strip()
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

# --- إلغاء العملية ---
async def cancel_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "temp_keyword" in context.user_data:
        del context.user_data["temp_keyword"]
    
    await update.message.reply_text(
        "❌ تم إلغاء العملية.",
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
            "👨‍💻 معلومات المدير :",
            f"📛 الاسم: {developer_name}",
            f"🔗 اليوزر: {developer_username}",
            f"📌 البايو: {developer_bio}"
        ]
        
        # إضافة الأزرار الشفافة
        keyboard = [
            [InlineKeyboardButton("📚 نقاشات خطوط أحمد الغريب", url="https://t.me/ElgharibFonts")]
        ]
        
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
                disable_notification=True,
                parse_mode=ParseMode.MARKDOWN  # تفعيل تنسيق النص
            )
            logger.info("Successfully sent developer photo")
        else:
            await update.message.reply_text(
                "\n".join(message),
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
                disable_web_page_preview=True
            )
            
    except Exception as e:
        logger.error(f"Error getting developer info: {e}")
        await update.message.reply_text(
            f"❌ حدث خطأ أثناء جلب معلومات المطور: {str(e)}",
            parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
            disable_web_page_preview=True
        )

# --- إعادة تشغيل البوت ---
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Attempting to restart bot for user {update.effective_user.id}")
    
    user_id = str(update.effective_user.id)
    chat_type = update.effective_chat.type
    
    if chat_type in ["group", "supergroup"]:
        if not await is_admin_or_creator(update, context):
            logger.info(f"User {user_id} is not admin or creator")
            await update.message.reply_text(
                "�OR هذا الأمر متاح فقط لمشرفي المجموعة أو المديرين!",
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
        "🔄 تم إعادة تنشيط البوت وتحسين سرعته.\nتحياتي؛ بوت خطوط أحمد الغريب @ElgharibFontsBot",
        parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
        disable_web_page_preview=True
    )
    logger.info("Calling start function")
    return await start(update, context)

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Starting /start command for user {update.effective_user.id}")
    
    buttons = [
        [
            InlineKeyboardButton("👨‍💻 معلومات المدير", callback_data="developer_info")
        ],
        [
            InlineKeyboardButton("📖 قناة خطوط قرآن", url="https://t.me/QuranFont")  # افتراض رابط القناة، يمكن تعديله
        ],
        [
            InlineKeyboardButton("📚 نقاشات خطوط أحمد الغريب", url="https://t.me/ElgharibFonts")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    welcome_message = "\n".join([
            "السلام عليكم ورحمة الله وبركاته 🌿",
            "اللهمَّ صلِّ وسلِّم على نبينا مُحمَّد",
            "",
            "البوت مخصص لتوفير الخطوط كافةً،",
            "عن طريق كتابة اسم الخط المطلوب. ",
            "",
            "💬 نقاشات خطوط أحمد الغريب:",
            "@ElgharibFonts",
            "",
        ])
    
    logger.info(f"Sending welcome message: {welcome_message}")
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
        disable_web_page_preview=True
    )
    logger.info("Welcome message sent successfully")
    return ConversationHandler.END

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض جميع أوامر البوت"""
    
    help_text = [
        "📜 قائمة أوامر البوت:",
        "",
        "🔹 /start - بدء استخدام البوت وعرض رسالة الترحيب",
        "🔹 /help - عرض هذه القائمة",
        "",
        "🛠️ أوامر المديرين:",
        "🔹 /add - إضافة رد جديد",
        "🔹 /remove <الكلمة> - حذف رد",
        "🔹 /export - تصدير ملف الردود",
        "🔹 /import - استيراد ملف الردود",
        "🔹 /restart - إعادة تشغيل البوت",
        "",
        "💡 يمكنك استخدام الأوامر مباشرة أو عبر لوحة الأزرار التفاعلية."
    ]
    
    buttons = []
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        "\n".join(help_text),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN,  # تفعيل تنسيق النص
        disable_web_page_preview=True
    )

def main():
    """Main function to initialize and run the Telegram bot."""
    print("🚀 Starting the bot...")

    try:
        # Initialize the Application with the bot token
        application = Application.builder().token(TOKEN).build()

        # --- أولاً: أضف الـ CommandHandlers المباشرة (للأوامر مثل /start) ---
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("remove", remove_response))
        application.add_handler(CommandHandler("export", export_responses))
        application.add_handler(CommandHandler("restart", restart_bot))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cancel", cancel_add_response))

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

        import_handler = ConversationHandler(
            entry_points=[CommandHandler("import", import_responses)],
            states={
                IMPORT_RESPONSES: [MessageHandler(filters.Document.ALL, process_import_file)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(import_handler)

        # --- ثالثاً: أضف الـ CallbackQueryHandler العام ---
        application.add_handler(CallbackQueryHandler(button_callback))

        # --- أخيراً: أضف الـ MessageHandler العام (للرسائل غير المعالجة) ---
        application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL, handle_message))
        application.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE, handle_message))

        # --- Start the Bot ---
        print("✅ Bot initialized successfully. Starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)  # إضافة drop_pending_updates لتجاهل الرسائل القديمة

    except Exception as e:
        print(f"❌ Error starting the bot: {str(e)}")
        logger.error(f"Error in main: {e}")
        raise

if __name__ == "__main__":
    main()
