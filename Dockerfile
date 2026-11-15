
FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Deno globally
ENV DENO_INSTALL=/usr/local

RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y \
    && chmod +x /usr/local/bin/deno

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["bash", "start"]
