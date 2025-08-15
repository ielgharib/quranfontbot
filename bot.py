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
import subprocess
from PIL import Image
import tempfile
from fontTools import ttLib
import zipfile
import rarfile  # Requires 'unrar' installed
import time  # For timestamp in file names

# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("TELEGRAM_TOKEN") or "7780931009:AAFkwcVo6pbABBS5NiNuAzi0-P13GQB3hiw"  # النسخة الاحتياطية لأغراض الاختبار
ADMINS = ["634869382"]  # قائمة بآيدي المديرين

# --- ملفات التخزين ---
RESPONSES_FILE = "responses.json"
MESSAGES_FILE = "user_messages.json"
USERS_FILE = "users.json"

# --- حالات المحادثة ---
(
    ADD_KEYWORD, ADD_RESPONSE,
    REPLY_TO_USER,
    IMPORT_RESPONSES,
    OPTIONS_MENU, CONVERT_TO_SVG, CONVERT_FONT, EXTRACT_ARCHIVE, CHOOSE_FONT_FORMAT,
    WAIT_FOR_SVG_IMAGES
) = range(10)

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

# --- إدارة المستخدمين (للإشعار فقط) ---
def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return set(json.load(f))
    return set()

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(list(users), f)

# --- إدارة رسائل المستخدمين ---
def load_user_messages():
    return load_data(MESSAGES_FILE, {"messages": {}})

def save_user_messages(messages_data):
    save_data(MESSAGES_FILE, messages_data)

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

# --- إرسال إشعار للمدير ---
async def send_admin_notification(context, user):
    try:
        user_info = f"👤 مستخدم جديد:\n"
        user_info += f"🆔 ID: {user.id}\n"
        user_info += f"📛 الاسم: {user.full_name}\n"
        if user.username:
            user_info += f"🔗 اليوزر: @{user.username}\n"
        
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
            [InlineKeyboardButton("💬 رد على هذه الرسالة", callback_data=f"reply_{message_id}")]
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
    logger.info(f"Received callback query: {query.data} from user {query.from_user.id}")
    await query.answer()
    
    if query.data == "options_menu":
        await show_options_menu(update, context)
        return OPTIONS_MENU
    
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

async def reply_to_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_text = update.message.text
    message_id = context.user_data["reply_message_id"]
    messages_data = load_user_messages()
    msg_data = messages_data["messages"][message_id]
    user_id = msg_data["user_id"]
    
    try:
        formatted_reply = "💬 رد من الإدارة:\n\n{reply_text}".format(reply_text=reply_text)
        
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
        "الرجاء إرسال الرد الذي تريد ربطه بهذه الكلمة:\n"
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
    if "reply_message_id" in context.user_data:
        del context.user_data["reply_message_id"]
    
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
        "🔄 تم إعادة تنشيط البوت وتحسين سرعته.\nتحياتي؛ بوت خطوط أحمد الغريب @ElgharibFontsBot",
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
    
    elif choice == "🖼️ تحويل صورة إلى SVG":
        keyboard = [["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
        "📤 يمكنك إرسال ما يصل إلى 50 صورة JPG/JPEG دفعة واحدة.\n"
        "⚠️ يجب أن تكون الصور بخلفية بيضاء وكتابة سوداء (جودة متوسطة إلى عالية).\n"
        "🚀 بعد إرسال جميع الصور، اضغط على 'بدء التحويل' لبدء العملية.\n\n"
        "الرجاء إرسال الصور الآن:",
        reply_markup=reply_markup
    )
    # تهيئة قائمة لتخزين الصور
        context.user_data['svg_images'] = []
        return WAIT_FOR_SVG_IMAGES
    
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
async def wait_for_svg_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "🚀 بدء التحويل":
        if not context.user_data.get('svg_images'):
            await update.message.reply_text("❌ لا توجد صور لتحويلها.")
            return await show_options_menu(update, context)
        
        await update.message.reply_text("⏳ جاري تحويل الصور إلى SVG... قد تستغرق العملية بعض الوقت.")
        
        for i, img_path in enumerate(context.user_data['svg_images'], 1):
            try:
                with tempfile.NamedTemporaryFile(suffix='.pbm', delete=False) as pbm_file:
                    pbm_path = pbm_file.name
                
                svg_filename = f"@ElgharibFontsBot - {i}.svg"
                with tempfile.NamedTemporaryFile(suffix='.svg', delete=False) as svg_file:
                    svg_path = svg_file.name
                
                # تحويل الصورة
                img = Image.open(img_path).convert("L").point(lambda x: 0 if x < 128 else 255, "1")
                img.save(pbm_path)
                # تطوير: إضافة خيارات potrace لتحسين الجودة (opttolerance لدقة أعلى، turdsize لإزالة الشوائب الصغيرة، tight لإزالة الفراغات)
                subprocess.run(["potrace", pbm_path, "-s", "--opttolerance", "0.2", "--turdsize", "2", "--tight", "-o", svg_path], check=True)
                
                # إرسال الملف
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(svg_path, 'rb'),
                    filename=svg_filename,
                    caption="تم التحويل بواسطة @ElgharibFontsBot"
                )
                
                # تنظيف الملفات المؤقتة
                os.remove(pbm_path)
                os.remove(svg_path)
                os.remove(img_path)
                
            except Exception as e:
                logger.error(f"Error converting image {i}: {e}")
                await update.message.reply_text(f"❌ خطأ في تحويل الصورة {i}: {str(e)}")
        
        # تنظيف البيانات
        if 'svg_images' in context.user_data:
            del context.user_data['svg_images']
        
        keyboard = [["🎛️ العودة إلى القائمة الرئيسية"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            f"✅ تم تحويل جميع الصور بنجاح!",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    if update.message.text == "🔙 رجوع":
        # تنظيف الملفات المؤقتة
        for img_path in context.user_data.get('svg_images', []):
            if os.path.exists(img_path):
                os.remove(img_path)
        if 'svg_images' in context.user_data:
            del context.user_data['svg_images']
        return await show_options_menu(update, context)
    
    if update.message.text == "❌ إلغاء":
        # تنظيف الملفات المؤقتة
        for img_path in context.user_data.get('svg_images', []):
            if os.path.exists(img_path):
                os.remove(img_path)
        if 'svg_images' in context.user_data:
            del context.user_data['svg_images']
        await update.message.reply_text("تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    
    photos = update.message.photo if update.message.photo else []
    documents = [update.message.document] if update.message.document else []
    
    files = []
    if photos:
        highest_quality_photo = max(photos, key=lambda p: p.file_size, default=None)
        if highest_quality_photo:
            files = [await highest_quality_photo.get_file()]
    elif documents:
        files = [await doc.get_file() for doc in documents if doc.file_name.lower().endswith(('.jpg', '.jpeg'))]
    
    if not files:
        await update.message.reply_text("⚠️ يرجى إرسال صورة JPG/JPEG صالحة.")
        return WAIT_FOR_SVG_IMAGES
    
    # تخزين الملفات المؤقتة
    for file in files:
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        await file.download_to_drive(temp_file.name)
        context.user_data['svg_images'].append(temp_file.name)
    
    remaining = 50 - len(context.user_data['svg_images'])
    
    if remaining <= 0:
        keyboard = [["🚀 بدء التحويل"], ["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            "✅ وصلت إلى الحد الأقصى (50 صورة). اضغط على 'بدء التحويل' لبدء العملية.",
            reply_markup=reply_markup
        )
        return WAIT_FOR_SVG_IMAGES
    else:
        keyboard = [["🚀 بدء التحويل"], ["🔙 رجوع"], ["❌ إلغاء"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text(
            f"📥 تم استلام {len(context.user_data['svg_images'])} صورة. يمكنك إرسال {remaining} صورة أخرى أو الضغط على 'بدء التحويل'.",
            reply_markup=reply_markup
        )
        return WAIT_FOR_SVG_IMAGES
    
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
            caption="تم التحويل بواسطة @ElgharibFontsBot"
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
                    caption="تم الفك بواسطة @ElgharibFontsBot"
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

# --- بدء البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Starting /start command for user {update.effective_user.id}")
    
    user_id = str(update.effective_user.id)
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        save_users(users)
        await send_admin_notification(context, update.effective_user)
    
    buttons = [
        [
            InlineKeyboardButton("🎛️ أدوات البوت", callback_data="options_menu"),
            InlineKeyboardButton("👨‍💻 معلومات المدير", callback_data="developer_info")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(buttons)
    welcome_message = "\n".join([
            "السلام عليكم ورحمة الله وبركاته 🌿",
            "",
            "حيّاكم الله أخواتي وإخواني 💬",
            "",
            "🤖 البوت مخصص لتوفير الخطوط كافةً،",
            "ولبعض المهام المتنوعة مثل:",
            "1️⃣ تحويل الصورة إلى فيكتور SVG",
            "2️⃣ فك ضغط الملفات واستخراجها",
            "3️⃣ تحويل صيغ الخطوط من TTF إلى OTF",
            "",
            "💬 نقاشات خطوط أحمد الغريب:",
            "@ElgharibFonts",
            "",
        ])
    
    logger.info(f"Sending welcome message: {welcome_message}")
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode="Markdown",
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
        "🎛️ أوامر الخيارات:",
        "🔸 /options - عرض لوحة الخيارات (تحويل الصور، الخطوط، إلخ)",
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
    
    buttons.append([InlineKeyboardButton("🎛️ أدوات البوت", callback_data="options_menu")])
    
    reply_markup = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        "\n".join(help_text),
        reply_markup=reply_markup,
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

        options_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(button_callback, pattern="^options_menu$")],
    states={
        OPTIONS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_options_choice)],
        WAIT_FOR_SVG_IMAGES: [MessageHandler(filters.ALL & ~filters.COMMAND, wait_for_svg_images)],
        CONVERT_FONT: [MessageHandler(filters.ALL & ~filters.COMMAND, convert_font)],
        CHOOSE_FONT_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_font_format)],
        EXTRACT_ARCHIVE: [MessageHandler(filters.ALL & ~filters.COMMAND, extract_archive)]
    },
    fallbacks=[CommandHandler("cancel", cancel_add_response)]
       )
        application.add_handler(options_handler)

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
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":

    main()

