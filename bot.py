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
    except Exception as e:
        logger.error(f"Error forwarding message to admin: {e}")

# --- رد على رسالة المستخدم ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("reply_"):
        message_id = query.data.split("_")[1]
        context.user_data["reply_message_id"] = message_id
        await query.edit_message_text(
            text=query.message.text + "\n\n📝 اكتب ردك هنا:",
            disable_web_page_preview=True
        )
        return REPLY_TO_USER
    elif query.data == "options_menu":
        return await show_options_menu(update, context)
    elif query.data == "developer_info":
        dev_info = "👨‍💻 المدير: أحمد الغريب\n🔗 @ElgharibFonts"
        await query.edit_message_text(dev_info, disable_web_page_preview=True)
    
    return ConversationHandler.END

async def reply_to_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_id = context.user_data.get("reply_message_id")
    if not message_id:
        await update.message.reply_text("❌ خطأ: لا يوجد رقم رسالة للرد عليها.")
        return ConversationHandler.END
    
    messages_data = load_user_messages()
    if message_id not in messages_data["messages"]:
        await update.message.reply_text("❌ خطأ: الرسالة غير موجودة.")
        return ConversationHandler.END
    
    user_message = messages_data["messages"][message_id]
    user_id = user_message["user_id"]
    reply_text = update.message.text
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=reply_text,
            disable_web_page_preview=True
        )
        
        user_message["replied"] = True
        user_message["reply_text"] = reply_text
        user_message["reply_timestamp"] = str(datetime.now())
        save_user_messages(messages_data)
        
        await update.message.reply_text("✅ تم إرسال الرد بنجاح!")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء إرسال الرد: {str(e)}")
    
    del context.user_data["reply_message_id"]
    return ConversationHandler.END

# --- إضافة رد جديد ---
async def start_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإضافة ردود!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🔑 أدخل الكلمة المفتاحية (أو /cancel للإلغاء):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADD_KEYWORD

async def add_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip().lower()
    context.user_data["add_keyword"] = keyword
    await update.message.reply_text(f"📝 أدخل الرد على '{keyword}' (أو /cancel):")
    return ADD_RESPONSE

async def add_response_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = context.user_data.get("add_keyword")
    response = update.message.text.strip()
    
    responses = load_responses()
    responses[keyword] = response
    save_responses(responses)
    
    await update.message.reply_text(f"✅ تم إضافة الرد على '{keyword}' بنجاح!")
    del context.user_data["add_keyword"]
    return ConversationHandler.END

async def cancel_add_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
    if "add_keyword" in context.user_data:
        del context.user_data["add_keyword"]
    if "reply_message_id" in context.user_data:
        del context.user_data["reply_message_id"]
    return ConversationHandler.END

# --- حذف رد ---
async def remove_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لحذف الردود!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ يرجى تحديد الكلمة المفتاحية، مثال: /remove كلمة")
        return
    
    keyword = " ".join(context.args).strip().lower()
    responses = load_responses()
    
    if keyword in responses:
        del responses[keyword]
        save_responses(responses)
        await update.message.reply_text(f"✅ تم حذف الرد على '{keyword}' بنجاح!")
    else:
        await update.message.reply_text(f"❌ الكلمة '{keyword}' غير موجودة!")

# --- إعادة تشغيل البوت ---
async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) not in ADMINS:
        await update.message.reply_text("⚠️ ليس لديك صلاحية لإعادة تشغيل البوت!")
        return
    
    await update.message.reply_text("🔄 جاري إعادة تشغيل البوت...")
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- معالجة الرسائل العامة ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.edited_message
    user = update.effective_user
    chat_type = update.effective_chat.type
    
    if chat_type != ChatType.PRIVATE:
        return
    
    text = message.text.lower() if message.text else None
    
    responses = load_responses()
    for keyword, response in responses.items():
        if keyword in text:
            await message.reply_text(response, disable_web_page_preview=True)
            return
    
    await forward_message_to_admin(context, user, message)

# --- عرض قائمة الخيارات ---
async def show_options_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["1️⃣ تحويل صورة إلى SVG"],
        ["2️⃣ تحويل صيغ الخطوط"],
        ["3️⃣ فك ضغط الملفات"],
        ["❌ إغلاق"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    text = "🎛️ اختر الخيار المطلوب:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
    
    return OPTIONS_MENU

async def handle_options_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    
    if "تحويل صورة إلى SVG" in choice:
        await update.message.reply_text(
            "📸 أرسل الصور (JPG/JPEG) لتحويلها إلى SVG:\n"
            "يمكنك إرسال عدة صور، ثم أرسل 'انتهاء' أو /cancel",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data["svg_images"] = []
        return WAIT_FOR_SVG_IMAGES
    elif "تحويل صيغ الخطوط" in choice:
        await update.message.reply_text(
            "🔤 أرسل ملف الخط (TTF/OTF) للتحويل:",
            reply_markup=ReplyKeyboardRemove()
        )
        return CONVERT_FONT
    elif "فك ضغط الملفات" in choice:
        await update.message.reply_text(
            "📦 أرسل ملف ZIP أو RAR لفك الضغط:",
            reply_markup=ReplyKeyboardRemove()
        )
        return EXTRACT_ARCHIVE
    elif "إغلاق" in choice or "إلغاء" in choice:
        await update.message.reply_text("❌ تم إغلاق القائمة.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    else:
        await update.message.reply_text("❌ خيار غير صالح. يرجى الاختيار من القائمة.")
        return OPTIONS_MENU

# --- تحويل الصور إلى SVG ---
async def wait_for_svg_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    
    if message.text and message.text.lower() == "انتهاء":
        images = context.user_data.get("svg_images", [])
        if not images:
            await update.message.reply_text("❌ لم يتم إرسال أي صور.")
            return await show_options_menu(update, context)
        
        for img_path in images:
            try:
                # تحويل إلى PNM ثم SVG باستخدام potrace
                pnm_path = img_path.replace('.jpg', '.pnm')
                subprocess.run(['convert', img_path, pnm_path], check=True)
                svg_path = img_path.replace('.jpg', '.svg')
                subprocess.run(['potrace', pnm_path, '-s', '-o', svg_path], check=True)
                
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open(svg_path, 'rb'),
                    caption="تم التحويل بواسطة @ElgharibFontsBot"
                )
                
                # تنظيف
                os.remove(img_path)
                os.remove(pnm_path)
                os.remove(svg_path)
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ في تحويل الصورة: {str(e)}")
        
        del context.user_data["svg_images"]
        return await show_options_menu(update, context)
    
    if message.photo:
        photo = message.photo[-1]  # أعلى دقة
        file = await photo.get_file()
        timestamp = int(time.time())
        img_path = f"temp_image_{timestamp}.jpg"
        await file.download_to_drive(img_path)
        context.user_data["svg_images"].append(img_path)
        await update.message.reply_text("✅ تم استلام الصورة. أرسل المزيد أو 'انتهاء'.")
        return WAIT_FOR_SVG_IMAGES
    
    if message.document:
        doc = message.document
        if doc.file_name.lower().endswith(('.jpg', '.jpeg')):
            file = await doc.get_file()
            timestamp = int(time.time())
            img_path = f"temp_image_{timestamp}.jpg"
            await file.download_to_drive(img_path)
            context.user_data["svg_images"].append(img_path)
            await update.message.reply_text("✅ تم استلام الصورة. أرسل المزيد أو 'انتهاء'.")
            return WAIT_FOR_SVG_IMAGES
        else:
            await update.message.reply_text("⚠️ يرجى إرسال صور JPG/JPEG فقط.")
            return WAIT_FOR_SVG_IMAGES
    
    await update.message.reply_text("⚠️ يرجى إرسال صور أو 'انتهاء'.")
    return WAIT_FOR_SVG_IMAGES

# --- تحويل صيغ الخطوط ---
async def convert_font(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ يرجى إرسال ملف خط (TTF/OTF).")
        return CONVERT_FONT
    
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    if not file_name.endswith(('.ttf', '.otf')):
        await update.message.reply_text("⚠️ الملف يجب أن يكون TTF أو OTF.")
        return CONVERT_FONT
    
    keyboard = [["OTF"], ["TTF"], ["🔙 رجوع"], ["❌ إلغاء"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("اختر الصيغة المرغوبة للتحويل إليها:", reply_markup=reply_markup)
    context.user_data["font_file"] = await doc.get_file()
    context.user_data["original_format"] = file_name.split('.')[-1]
    return CHOOSE_FONT_FORMAT

async def choose_font_format(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_format = update.message.text.strip().upper()
    
    if target_format not in ["OTF", "TTF"]:
        if "رجوع" in update.message.text:
            return await show_options_menu(update, context)
        elif "إلغاء" in update.message.text:
            await update.message.reply_text("❌ تم إلغاء العملية.", reply_markup=ReplyKeyboardRemove())
            return ConversationHandler.END
        await update.message.reply_text("❌ خيار غير صالح.")
        return CHOOSE_FONT_FORMAT
    
    file = context.user_data["font_file"]
    original_format = context.user_data["original_format"].upper()
    
    if target_format == original_format:
        await update.message.reply_text(f"⚠️ الملف بالفعل بتنسيق {target_format}.")
        return await show_options_menu(update, context)
    
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{original_format.lower()}", delete=False) as temp_file:
            await file.download_to_drive(temp_file.name)
            font_path = temp_file.name
        
        font = ttLib.TTFont(font_path)
        converted_path = font_path.replace(f".{original_format.lower()}", f".{target_format.lower()}")
        font.save(converted_path)
        
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=open(converted_path, 'rb'),
            caption="تم التحويل بواسطة @ElgharibFontsBot"
        )
        
        os.remove(font_path)
        os.remove(converted_path)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء تحويل الخط: {str(e)}")
    
    del context.user_data["font_file"]
    del context.user_data["original_format"]
    return await show_options_menu(update, context)

# --- فك ضغط الملفات ---
async def extract_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.document:
        await update.message.reply_text("❌ يرجى إرسال ملف ZIP أو RAR.")
        return EXTRACT_ARCHIVE
    
    doc = update.message.document
    file_name = doc.file_name.lower()
    
    if not file_name.endswith(('.zip', '.rar')):
        await update.message.reply_text("⚠️ الملف يجب أن يكون ZIP أو RAR.")
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
            fallbacks=[CommandHandler("cancel", cancel_add_response)],
            per_message=True
        )
        application.add_handler(reply_handler)

        import_handler = ConversationHandler(
            entry_points=[CommandHandler("import", import_responses)],
            states={
                IMPORT_RESPONSES: [MessageHandler(filters.DOCUMENT.ALL, process_import_file)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)]
        )
        application.add_handler(import_handler)

        options_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_callback, pattern="^options_menu$")],
            states={
                OPTIONS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_options_choice)],
                WAIT_FOR_SVG_IMAGES: [MessageHandler((filters.PHOTO | filters.DOCUMENT.IMAGE) & ~filters.COMMAND, wait_for_svg_images)],
                CONVERT_FONT: [MessageHandler(filters.DOCUMENT.ALL & ~filters.COMMAND, convert_font)],
                CHOOSE_FONT_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_font_format)],
                EXTRACT_ARCHIVE: [MessageHandler(filters.DOCUMENT.ALL & ~filters.COMMAND, extract_archive)]
            },
            fallbacks=[CommandHandler("cancel", cancel_add_response)],
            per_message=True
        )
        application.add_handler(options_handler)

        # --- ثالثاً: أضف الـ CallbackQueryHandler العام ---
        application.add_handler(CallbackQueryHandler(button_callback))

        # --- أخيراً: أضف الـ MessageHandler العام (للرسائل غير المعالجة) ---
        application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO | filters.DOCUMENT.ALL, handle_message))
        application.add_handler(MessageHandler(filters.StatusUpdate.ANY, handle_message))

        # --- Start the Bot ---
        print("✅ Bot initialized successfully. Starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)  # إضافة drop_pending_updates لتجاهل الرسائل القديمة

    except Exception as e:
        print(f"❌ Error starting the bot: {str(e)}")
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":

    main()
