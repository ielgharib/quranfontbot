# استخدام نسخة بايثون خفيفة
FROM python:3.12-slim

# تثبيت potrace + التحديث
RUN apt-get update && apt-get install -y potrace && apt-get clean

# تعيين مجلد العمل داخل الحاوية
WORKDIR /app

# نسخ كل الملفات إلى داخل الحاوية
COPY . /app

# تثبيت مكتبات بايثون
RUN pip install --no-cache-dir -r requirements.txt

# تشغيل البوت
CMD ["python", "bot.py"]
