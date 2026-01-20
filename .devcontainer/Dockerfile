FROM mcr.microsoft.com/devcontainers/python:3.11

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC \
    # 关键：把 Playwright 浏览器安装到镜像内固定目录，避免 ~/.cache 被挂载覆盖
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Playwright 系统依赖 + Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 \
    libdrm2 libx11-6 libx11-xcb1 libxcb1 \
    libxext6 libxi6 libxtst6 \
    libglib2.0-0 \
    fonts-liberation fonts-noto-color-emoji \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# 关键：系统级安装（不进用户目录）
RUN python -m pip install -U pip setuptools wheel \
    && python -m pip install playwright

# 关键：浏览器装到 /ms-playwright（镜像内），并确保所有用户都可读
RUN mkdir -p /ms-playwright \
    && python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright

# 不要再设置 /home/vscode/.local/bin 之类的 PATH
