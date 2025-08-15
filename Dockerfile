# Use a slim Python base image matching your script's Python version (3.12.3)
FROM python:3.12-slim

# Install system dependencies for potrace and unrar
RUN apt-get update && apt-get install -y \
    potrace \
    unrar \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements.txt first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Set the entrypoint to run your bot
CMD ["python", "bot.py"]
