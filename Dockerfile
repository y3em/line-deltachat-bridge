FROM python:3.11-slim

# Install essential dependencies
RUN apt-get update && apt-get install -y \
    curl wget unzip libsqlite3-dev build-essential python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install ngrok with architecture detection
RUN arch=$(dpkg --print-architecture) && \
    case ${arch} in \
        "amd64") ARCH="amd64" ;; \
        "arm64") ARCH="arm64" ;; \
        *) ARCH="amd64" ;; \
    esac && \
    wget -q "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-${ARCH}.tgz" -O /tmp/ngrok.tgz && \
    tar -xzf /tmp/ngrok.tgz -C /usr/local/bin && \
    chmod +x /usr/local/bin/ngrok && \
    rm /tmp/ngrok.tgz

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir deltachat-rpc-server

# Create directories
RUN mkdir -p /root/.config/deltachat /tmp/images

# Copy application files
COPY app.py .
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 5000 4040 23123

CMD ["/app/start.sh"]