FROM python:3.13-slim

WORKDIR /app

# 安装编译依赖（asyncmy 需要 gcc 和 Python 头文件编译 C 扩展）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理器
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 先复制依赖定义文件，利用 Docker 缓存层
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --no-dev --frozen

# 复制应用代码
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
