# Use a slim Python base image matching your script's Python version (3.12.3)
FROM python:3.12-slim

# Overwrite apt sources.list to enable contrib, non-free, and non-free-firmware components
RUN echo "deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware" >> /etc/apt/sources.list

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
