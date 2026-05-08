FROM python:3.12-slim

ARG GIT_SHA=unknown

# 系统依赖（合并到一个 RUN，且清理 apt 缓存）
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    git \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# 创建用户 & 目录
RUN useradd -m amiya
WORKDIR /app
RUN mkdir -p /app/resources /app/data/local /app/resources/logs

# 固定 Playwright 浏览器路径（避免 /root/.cache 问题）
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV AMIYA_GIT_SHA=${GIT_SHA}

# 装项目依赖
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器（用 root 装 deps）
RUN python -m playwright install --with-deps \
 && chmod -R 755 /ms-playwright \
 && chown -R amiya:amiya /ms-playwright

# 拷贝代码（利用 Docker 缓存）
COPY . /app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
 && chown -R amiya:amiya /app /ms-playwright

# 测试 Playwright 是否可用
RUN python - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto("data:text/html,<h1>ok</h1>")
    b.close()
print("playwright build-test ok")
PY

# 切换用户 & 启动应用
EXPOSE 9000
USER amiya
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "main.py", "web"]
