FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . .

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "openbb_core.api:app", "--host", "0.0.0.0", "--port", "8000"]
