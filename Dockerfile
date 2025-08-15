FROM python:3.10-slim

WORKDIR /app

# تثبيت potrace وأدوات النظام أولاً
RUN apt-get update && apt-get install -y potrace && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "bot.py"]
