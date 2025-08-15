FROM python:3.10-slim

WORKDIR /app

# تثبيت الأدوات النظامية المطلوبة
RUN apt-get update && \
    apt-get install -y \
    potrace \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# تحديث pip أولاً
RUN pip install --upgrade pip

COPY requirements.txt .

# تثبيت متطلبات Python
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
