FROM python:3.10-slim

# تثبيت التبعيات النظامية (بما فيها potrace)
RUN apt-get update && \
    apt-get install -y --no-install-recommends potrace && \
    rm -rf /var/lib/apt/lists/*

# نسخ ملفات المشروع
WORKDIR /app
COPY . .

# تثبيت تبعيات بايثون
RUN pip install --no-cache-dir -r requirements.txt

# تشغيل البوت
CMD ["python", "bot.py"]
