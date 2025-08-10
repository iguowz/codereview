#!/bin/bash

# 设置编码
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

echo "============================================================"
echo "🚀 Git增量代码智能审查与测试用例生成系统"
echo "============================================================"
echo

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到Python3，请先安装Python 3.8+"
    exit 1
fi

# 检查Python版本
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ 错误：需要Python 3.8或更高版本，当前版本：$python_version"
    exit 1
fi

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv .venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source .venv/bin/activate

# 检查依赖
echo "🔍 检查依赖..."
if ! python3 -c "import flask" &> /dev/null; then
    echo "📥 安装依赖..."
    pip install -r requirements.txt
fi

# 检查配置文件
if [ ! -f "config/systems.yaml" ]; then
    if [ -f "config/systems.yaml.example" ]; then
        echo "📋 复制配置文件..."
        cp config/systems.yaml.example config/systems.yaml
        echo "✅ 配置文件已创建，请编辑 config/systems.yaml"
    else
        echo "❌ 错误：配置文件模板不存在"
        exit 1
    fi
fi

# 检查环境变量
if [ -z "$DEEPSEEK_API_KEY" ]; then
    echo "⚠️  警告：未设置DEEPSEEK_API_KEY环境变量"
    echo "💡 请设置：export DEEPSEEK_API_KEY='your-api-key'"
    echo "💡 或者创建.env文件：echo 'DEEPSEEK_API_KEY=your-api-key' > .env"
fi

echo
echo "🚀 启动系统..."
echo "💡 提示："
echo "   1. 设置环境变量：export DEEPSEEK_API_KEY='your-api-key'"
echo "   2. 编辑配置文件：config/systems.yaml"
echo "   3. 任务队列模式：export USE_REDIS=false（MockCelery，默认）"
echo "   4. 生产模式：export USE_REDIS=true（需要Redis和Worker）"
echo "   5. 自定义端口：export PORT=8080（默认5001）"
echo "   6. 自定义主机：export HOST=127.0.0.1（默认0.0.0.0）"
echo

# 检查任务队列配置
use_redis=${USE_REDIS:-false}
if [ "$use_redis" = "true" ]; then
    echo "🔍 检查Redis连接..."
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null; then
            echo "✅ Redis连接正常"
        else
            echo "❌ Redis连接失败，请启动Redis服务"
            echo "💡 启动Redis：redis-server"
            echo "💡 或切换到MockCelery：export USE_REDIS=false"
        fi
    else
        echo "⚠️  未安装redis-cli，无法测试连接"
    fi
    echo "💡 记得启动Celery Worker：python celery_worker.py"
else
    echo "ℹ️  使用MockCelery模式（开发环境）"
fi
echo

# 启动应用
python3 main.py
