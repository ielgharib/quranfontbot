import os
import sys
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

# --- تحقق ما إذا كان يمكن استخدام الأداة ---
def can_use_tool(chat_type, user_id):
    if chat_type == ChatType.PRIVATE:
        return True
    elif chat_type in [ChatType.GROUP, ChatType.SUPERGROUP] and str(user_id) in ADMINS:
        return True
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

# --- إضافة ردود ---
async def start_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإضافة الردود!")
        return ConversationHandler.END
    await update.message.reply_text("🔑 أرسل الكلمة المفتاحية الجديدة:\nأو /cancel للإلغاء")
    return ADD_KEYWORD

async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()
    responses = load_responses()
    if keyword in responses:
        await update.message.reply_text("⚠️ هذه الكلمة موجودة بالفعل! أرسل كلمة أخرى أو /cancel")
        return ADD_KEYWORD
    context.user_data['new_keyword'] = keyword
    await update.message.reply_text("📝 أرسل الرد المرتبط بهذه الكلمة:\nأو /cancel للإلغاء")
    return ADD_RESPONSE

async def add_response_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    response = update.message.text.strip()
    keyword = context.user_data.get('new_keyword')
    if not keyword:
        await update.message.reply_text("❌ خطأ! ابدأ من جديد بـ /add")
        return ConversationHandler.END
    responses = load_responses()
    responses[keyword] = response
    save_responses(responses)
    await update.message.reply_text(f"✅ تم إضافة الرد بنجاح للكلمة: {keyword}")
    del context.user_data['new_keyword']
    return ConversationHandler.END

# --- حذف رد ---
async def remove_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لحذف الردود!")
        return
    if not context.args:
        await update.message.reply_text("❌ يرجى تحديد الكلمة المفتاحية لحذفها! مثال: /remove كلمة")
        return
    keyword = ' '.join(context.args).strip()
    responses = load_responses()
    if keyword in responses:
        del responses[keyword]
        save_responses(responses)
        await update.message.reply_text(f"✅ تم حذف الرد للكلمة: {keyword}")
    else:
        await update.message.reply_text(f"❌ الكلمة {keyword} غير موجودة!")

# --- إعادة تشغيل البوت ---
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإعادة تشغيل البوت!")
        return
    await update.message.reply_text("🔄 جاري إعادة التشغيل...")
    sys.exit(0)

# --- إلغاء العملية ---
async def cancel_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# --- الرد على رسالة المستخدم ---
async def reply_to_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية للرد!")
        return ConversationHandler.END
    reply_text = update.message.text
    message_id = context.user_data.get("reply_message_id")
    if not message_id:
        await update.message.reply_text("❌ خطأ! لا يوجد رسالة للرد عليها.")
        return ConversationHandler.END
    messages_data = load_user_messages()
    if message_id not in messages_data["messages"]:
        await update.message.reply_text("❌ الرسالة غير موجودة!")
        return ConversationHandler.END
    user_message = messages_data["messages"][message_id]
    user_id = user_message["user_id"]
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=reply_text
        )
        messages_data["messages"][message_id]["replied"] = True
        messages_data["messages"][message_id]["reply_text"] = reply_text
        messages_data["messages"][message_id]["reply_timestamp"] = str(datetime.now())
        save_user_messages(messages_data)
        await update.message.reply_text("✅ تم إرسال الرد بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء إرسال الرد: {str(e)}")
    del context.user_data["reply_message_id"]
    return ConversationHandler.END

# --- وظائف مساعدة للكيبورد ---
def get_options_keyboard():
    keyboard = [
        [InlineKeyboardButton("تحويل صورة إلى SVG", callback_data="option_svg_convert")],
        [InlineKeyboardButton("تحويل صيغة خط", callback_data="option_font_convert")],
        [InlineKeyboardButton("فك ضغط ملف", callback_data="option_extract_archive")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_start")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_svg_menu_keyboard(current_count):
    keyboard = []
    if current_count > 0:
        keyboard.append([InlineKeyboardButton("🚀 بدء التحويل", callback_data="start_svg_convert")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_to_options")])
    keyboard.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel_operation")])
    return InlineKeyboardMarkup(keyboard)

def get_back_cancel_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_options")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_operation")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_font_format_keyboard():
    keyboard = [
        [InlineKeyboardButton("إلى TTF", callback_data="to_ttf"), InlineKeyboardButton("إلى OTF", callback_data="to_otf")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_to_options")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_operation")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- عرض لوحة الخيارات ---
async def show_options_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query if update.callback_query else None
    text = "🎛️ لوحة الخيارات:\nاختر الوظيفة المرغوبة:"
    if query:
        await query.edit_message_text(text, reply_markup=get_options_keyboard())
    else:
        await update.message.reply_text(text, reply_markup=get_options_keyboard())
    return OPTIONS_MENU

# --- عرض معلومات المدير ---
async def show_developer_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    dev_info = "👨‍💻 معلومات المدير:\n\n" \
               "اسم المدير: أحمد الغريب\n" \
               "وصف: مطور البوت\n" \
               "رابط: @ElgharibFonts"
    await query.edit_message_text(dev_info)

# --- معالجة الأزرار التفاعلية ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    logger.info(f"Received callback query: {query.data} from user {query.from_user.id}")
    await query.answer()
    
    if query.data == "options_menu":
        if not can_use_tool(update.effective_chat.type, query.from_user.id):
            await query.edit_message_text("⚠️ لوحة الخيارات متاحة فقط في الخاص أو للمديرين في المجموعات!")
            return
        await show_options_menu(update, context)
        return OPTIONS_MENU
    
    if query.data == "developer_info":
        if not can_use_tool(update.effective_chat.type, query.from_user.id):
            await query.edit_message_text("⚠️ معلومات المدير متاحة فقط في الخاص أو للمديرين في المجموعات!")
            return
        await show_developer_info(update, context)
        return
    
    if query.data.startswith("reply_"):
        message_id = query.data.split("_")[1]
        context.user_data["reply_message_id"] = message_id
        await query.edit_message_text("💬 أرسل الرد الذي تريد إرساله للمستخدم:")
        return REPLY_TO_USER
    
    if query.data == "option_svg_convert":
        if not can_use_tool(update.effective_chat.type, query.from_user.id):
            await query.edit_message_text("⚠️ هذه الوظيفة متاحة فقط في الخاص أو للمديرين في المجموعات!")
            return ConversationHandler.END
        context.user_data['svg_images'] = []
        await query.edit_message_text(
            "📤 أرسل الصور (JPG/JPEG) لتحويلها إلى SVG (حد أقصى 50 صورة).\nيمكنك إرسالها واحدة أو كمجموعة.",
            reply_markup=get_svg_menu_keyboard(0)
        )
        return WAIT_FOR_SVG_IMAGES
    
    if query.data == "option_font_convert":
        if not can_use_tool(update.effective_chat.type, query.from_user.id):
            await query.edit_message_text("⚠️ هذه الوظيفة متاحة فقط في الخاص أو للمديرين في المجموعات!")
            return ConversationHandler.END
        await query.edit_message_text(
            "📁 أرسل ملف الخط (TTF أو OTF) للتحويل.",
            reply_markup=get_back_cancel_keyboard()
        )
        return CONVERT_FONT
    
    if query.data == "option_extract_archive":
        if not can_use_tool(update.effective_chat.type, query.from_user.id):
            await query.edit_message_text("⚠️ هذه الوظيفة متاحة فقط في الخاص أو للمديرين في المجموعات!")
            return ConversationHandler.END
        await query.edit_message_text(
            "📦 أرسل ملف ZIP أو RAR (حتى 500MB) لفك الضغط.",
            reply_markup=get_back_cancel_keyboard()
        )
        return EXTRACT_ARCHIVE
    
    if query.data == "back_to_start":
        await query.edit_message_text("تم الرجوع إلى القائمة الرئيسية.")
        await start(update, context)
        return ConversationHandler.END
    
    if query.data == "start_svg_convert":
        if 'svg_images' not in context.user_data or len(context.user_data['svg_images']) == 0:
            await query.answer("⚠️ أرسل صورة واحدة على الأقل أولاً!")
            return WAIT_FOR_SVG_IMAGES
        await query.edit_message_text("🔄 جاري التحويل إلى SVG...")
        try:
            for idx, img_path in enumerate(context.user_data['svg_images'], 1):
                timestamp = int(time.time())
                pnm_path = f"temp_{timestamp}.pnm"
                svg_path = f"output_{timestamp}.svg"
                subprocess.run(["convert", img_path, pnm_path], check=True)
                subprocess.run(["potrace", pnm_path, "-s", "-o", svg_path], check=True)
                await context.bot.send_document(
                    chat_id=query.message.chat.id,
                    document=open(svg_path, 'rb'),
                    caption=f"تم التحويل بواسطة @ElgharibFontsBot ({idx}/{len(context.user_data['svg_images'])})"
                )
                os.remove(img_path)
                os.remove(pnm_path)
                os.remove(svg_path)
            del context.user_data['svg_images']
        except Exception as e:
            logger.error(f"Error converting to SVG: {e}")
            await query.message.reply_text(f"❌ خطأ أثناء التحويل: {str(e)}")
        await show_options_menu(update, context)
        return OPTIONS_MENU
    
    if query.data == "back_to_options":
        if 'svg_images' in context.user_data:
            for path in context.user_data['svg_images']:
                if os.path.exists(path):
                    os.remove(path)
            del context.user_data['svg_images']
        if "font_file_id" in context.user_data:
            del context.user_data["font_file_id"]
        if "font_file_name" in context.user_data:
            del context.user_data["font_file_name"]
        await query.edit_message_text("تم الرجوع إلى لوحة الخيارات.")
        await show_options_menu(update, context)
        return OPTIONS_MENU
    
    if query.data == "cancel_operation":
        if 'svg_images' in context.user_data:
            for path in context.user_data['svg_images']:
                if os.path.exists(path):
                    os.remove(path)
            del context.user_data['svg_images']
        if "font_file_id" in context.user_data:
            del context.user_data["font_file_id"]
        if "font_file_name" in context.user_data:
            del context.user_data["font_file_name"]
        await query.edit_message_text("تم إلغاء العملية.")
        return ConversationHandler.END
    
    if query.data in ["to_ttf", "to_otf"]:
        choice = "إلى TTF" if query.data == "to_ttf" else "إلى OTF"
        target_ext = '.ttf' if choice == "إلى TTF" else '.otf'
        file_id = context.user_data.get("font_file_id")
        file_name = context.user_data.get("font_file_name")
        
        if not file_id or not file_name:
            await query.edit_message_text("❌ خطأ: الملف مفقود. يرجى البدء من جديد.")
            await show_options_menu(update, context)
            return OPTIONS_MENU
        
        try:
            file = await context.bot.get_file(file_id)
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_name)[1], delete=False) as input_file:
                await file.download_to_drive(input_file.name)
                input_path = input_file.name
            
            try:
                font = ttLib.TTFont(input_path)
            except Exception as e:
                logger.error(f"Error loading font file: {e}")
                await query.message.reply_text(f"❌ خطأ في تحميل ملف الخط: {str(e)}")
                os.remove(input_path)
                await show_options_menu(update, context)
                return OPTIONS_MENU
            
            with tempfile.NamedTemporaryFile(suffix=target_ext, delete=False) as output_file:
                output_path = output_file.name
            
            try:
                font.save(output_path)
            except Exception as e:
                logger.error(f"Error saving font file: {e}")
                await query.message.reply_text(f"❌ خطأ في حفظ ملف الخط: {str(e)}")
                os.remove(input_path)
                os.remove(output_path)
                await show_options_menu(update, context)
                return OPTIONS_MENU
            
            await context.bot.send_document(
                chat_id=query.message.chat.id,
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
            await query.message.reply_text(f"❌ خطأ أثناء التحويل: {str(e)}")
            if os.path.exists("input_path"):
                os.remove("input_path")
            if os.path.exists("output_path"):
                os.remove("output_path")
        
        await show_options_menu(update, context)
        return OPTIONS_MENU

# --- وظيفة استلام الصور لتحويل SVG ---
async def wait_for_svg_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_use_tool(update.effective_chat.type, update.effective_user.id):
        await update.message.reply_text("⚠️ هذه الوظيفة متاحة فقط في الخاص أو للمديرين في المجموعات!")
        return ConversationHandler.END
    
    if 'svg_images' not in context.user_data:
        context.user_data['svg_images'] = []
    
    photos = update.message.photo
    documents = update.message.document if update.message.document else None
    files = []
    
    if photos:
        highest_quality_photo = max(photos, key=lambda p: p.file_size)
        if highest_quality_photo:
            files = [await highest_quality_photo.get_file()]
    elif documents:
        if documents.file_name.lower().endswith(('.jpg', '.jpeg')):
            files = [await documents.get_file()]
    
    if not files:
        await update.message.reply_text("⚠️ يرجى إرسال صورة JPG/JPEG صالحة.", reply_markup=get_svg_menu_keyboard(len(context.user_data['svg_images'])))
        return WAIT_FOR_SVG_IMAGES
    
    for file in files:
        temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
        await file.download_to_drive(temp_file.name)
        context.user_data['svg_images'].append(temp_file.name)
    
    current_count = len(context.user_data['svg_images'])
    remaining = 50 - current_count
    
    if remaining <= 0:
        text = "✅ وصلت إلى الحد الأقصى (50 صورة). اضغط على 'بدء التحويل' لبدء العملية."
    else:
        text = f"📥 تم استلام {current_count} صورة. يمكنك إرسال {remaining} صورة أخرى أو الضغط على 'بدء التحويل'."
    
    await update.message.reply_text(text, reply_markup=get_svg_menu_keyboard(current_count))
    return WAIT_FOR_SVG_IMAGES

# --- وظيفة تحويل صيغة الخط ---
async def convert_font(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_use_tool(update.effective_chat.type, update.effective_user.id):
        await update.message.reply_text("⚠️ هذه الوظيفة متاحة فقط في الخاص أو للمديرين في المجموعات!")
        return ConversationHandler.END
    
    if not update.message.document:
        await update.message.reply_text("⚠️ يرجى إرسال ملف خط TTF أو OTF.", reply_markup=get_back_cancel_keyboard())
        return CONVERT_FONT
    
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    if not file_name.endswith(('.ttf', '.otf')):
        await update.message.reply_text("⚠️ الصيغة غير مدعومة. فقط TTF أو OTF.", reply_markup=get_back_cancel_keyboard())
        return CONVERT_FONT
    
    context.user_data["font_file_id"] = doc.file_id
    context.user_data["font_file_name"] = doc.file_name
    
    await update.message.reply_text("اختر الصيغة المرغوبة:", reply_markup=get_font_format_keyboard())
    return CHOOSE_FONT_FORMAT

# --- وظيفة فك ضغط الملفات ---
async def extract_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not can_use_tool(update.effective_chat.type, update.effective_user.id):
        await update.message.reply_text("⚠️ هذه الوظيفة متاحة فقط في الخاص أو للمديرين في المجموعات!")
        return ConversationHandler.END
    
    if not update.message.document:
        await update.message.reply_text("⚠️ يرجى إرسال ملف ZIP أو RAR (حتى 500MB).", reply_markup=get_back_cancel_keyboard())
        return EXTRACT_ARCHIVE
    
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    if not file_name.endswith(('.zip', '.rar')):
        await update.message.reply_text("⚠️ الصيغة غير مدعومة. فقط ZIP أو RAR.", reply_markup=get_back_cancel_keyboard())
        return EXTRACT_ARCHIVE
    
    if doc.file_size > 500 * 1024 * 1024:  # 500MB
        await update.message.reply_text("⚠️ الملف أكبر من 500MB.", reply_markup=get_back_cancel_keyboard())
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
    
    await show_options_menu(update, context)
    return OPTIONS_MENU

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
        OPTIONS_MENU: [CallbackQueryHandler(button_callback)],
        WAIT_FOR_SVG_IMAGES: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, wait_for_svg_images),
            CallbackQueryHandler(button_callback)
        ],
        CONVERT_FONT: [
            MessageHandler(filters.Document.ALL, convert_font),
            CallbackQueryHandler(button_callback)
        ],
        CHOOSE_FONT_FORMAT: [CallbackQueryHandler(button_callback)],
        EXTRACT_ARCHIVE: [
            MessageHandler(filters.Document.ALL, extract_archive),
            CallbackQueryHandler(button_callback)
        ]
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
