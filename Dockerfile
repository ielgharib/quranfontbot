FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN apt-get update && apt-get install -y potrace  # فقط إذا احتجت للأداة مباشرةً
RUN apt-get update && apt-get install -y potrace
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "bot.py"]