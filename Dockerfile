# 使用官方Python运行时作为父镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 设置时区为上海（跨平台兼容）
# 如果是 Alpine
#RUN apk add --no-cache tzdata \
# && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
# && echo "Asia/Shanghai" > /etc/timezone

# 如果是 Debian/Ubuntu
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y tzdata \
 && ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
 && dpkg-reconfigure -f noninteractive tzdata\
 git \
 curl \
 && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai

# 复制requirements文件并安装Python依赖
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/config /app/data /app/logs /app/cache

# 设置目录权限
RUN chmod -R 755 /app/config /app/data /app/logs /app/cache

# 暴露端口
EXPOSE 5001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# 启动命令
CMD ["python", "main.py"]
