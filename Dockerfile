
FROM python:3.10-slim

ENV DENO_INSTALL=/root/.deno
ENV PATH="/root/.deno/bin:${PATH}"

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        ffmpeg \
        unzip \
        curl \
        git \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Deno
RUN curl -fsSL https://deno.land/install.sh | sh && \
    deno --version && \
    ffmpeg -version

COPY requirements.txt ./

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

EXPOSE 10000

CMD ["bash", "start"]
