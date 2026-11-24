# ---- build (C++ bot + libntgcalls shared library) ----
FROM ubuntu:24.04 AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
        g++ cmake make curl unzip ca-certificates libcurl4-openssl-dev zlib1g-dev libmongoc-dev nlohmann-json3-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*
ARG NTG_VERSION=v2.1.0
# Optional but recommended: pin the exact archive. Get it with:  sha256sum ntgcalls.linux-x86_64-shared_libs.zip
# (build with --build-arg NTG_SHA256_X86_64=<hex>). If empty, the build prints a warning and continues.
ARG NTG_SHA256_X86_64=""
ARG NTG_SHA256_ARM64=""
WORKDIR /src
COPY . .
RUN set -eu; \
    ARCH=$(uname -m); \
    if [ "$ARCH" = "x86_64" ]; then NTG=x86_64; SHA="$NTG_SHA256_X86_64"; else NTG=arm64; SHA="$NTG_SHA256_ARM64"; fi; \
    mkdir -p third_party/ntgcalls/lib third_party/ntgcalls/include /tmp/ntg; \
    curl -fsSL "https://github.com/pytgcalls/ntgcalls/releases/download/${NTG_VERSION}/ntgcalls.linux-${NTG}-shared_libs.zip" -o /tmp/ntg.zip; \
    if [ -n "$SHA" ]; then echo "$SHA  /tmp/ntg.zip" | sha256sum -c -; \
    else echo "WARNING: NTG_SHA256 not set; the libntgcalls download is NOT checksum verified" >&2; fi; \
    unzip -q /tmp/ntg.zip -d /tmp/ntg; \
    LIB="$(find /tmp/ntg -name libntgcalls.so | head -n1)"; HDR="$(find /tmp/ntg -name ntgcalls.h | head -n1)"; \
    [ -n "$LIB" ] && [ -n "$HDR" ] || { echo "ERROR: libntgcalls.so / ntgcalls.h not found in the archive" >&2; find /tmp/ntg | head -n 40 >&2; exit 1; }; \
    cp "$LIB" third_party/ntgcalls/lib/; cp "$HDR" third_party/ntgcalls/include/; \
    rm -rf /tmp/ntg /tmp/ntg.zip
# WITH_NTGCALLS=ON is explicit: if the library were missing, configuring fails instead of silently producing a
# voice-less bot (which exits at start-up with "this build has no libntgcalls").
RUN cmake -B build -DCMAKE_BUILD_TYPE=Release -DWITH_NTGCALLS=ON -DNTGCALLS_DIR=/src/third_party/ntgcalls \
    && cmake --build build -j2 --target cpp-bot

# ---- runtime ----
FROM ubuntu:24.04
# yt-dlp: the standalone release binary (no Python needed). Set YTDLP_VERSION to a release tag (for example 2026.08.19)
# to pin it; the bot also runs `yt-dlp -U` at start (disable with YTDLP_UPDATE=False).
ARG YTDLP_VERSION=latest
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg curl ca-certificates libcurl4 libssl3 zlib1g libmongoc-1.0-0t64 \
    && if [ "$(uname -m)" = "x86_64" ]; then YT=yt-dlp_linux; else YT=yt-dlp_linux_aarch64; fi \
    && if [ "$YTDLP_VERSION" = "latest" ]; then URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/$YT"; \
       else URL="https://github.com/yt-dlp/yt-dlp/releases/download/$YTDLP_VERSION/$YT"; fi \
    && curl -fsSL "$URL" -o /usr/local/bin/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp && yt-dlp --version \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /src/build/cpp-bot /app/cpp-bot
COPY --from=build /src/third_party/ntgcalls/lib/libntgcalls.so /app/lib/libntgcalls.so
COPY strings /app/strings
COPY Bad/telegram_schema /app/telegram_schema
ENV LD_LIBRARY_PATH=/app/lib
# Fail the image build (not the running dyno) if the voice library cannot load its own dependencies.
RUN ! ldd /app/lib/libntgcalls.so | grep "not found" \
    && ! ldd /app/cpp-bot | grep "not found"
STOPSIGNAL SIGTERM
CMD ["/app/cpp-bot"]
