#!/usr/bin/env python3
"""
跨平台启动脚本 - Git增量代码智能审查与测试用例生成系统
支持Windows、Linux、macOS
"""

import os
import sys
import platform
import subprocess
import time
from pathlib import Path
from dotenv import load_dotenv

def print_banner():
    """打印启动横幅"""
    print("=" * 60)
    print("🚀 Git增量代码智能审查与测试用例生成系统")
    print("=" * 60)
    print("Features:")
    print("  - 智能代码审查")
    print("  - 自动测试用例生成")
    print("  - 多Git平台支持")
    print("  - 可选Redis（默认禁用）")
    print("=" * 60)

def check_requirements():
    """检查运行环境"""
    print("🔍 检查运行环境...")
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ 错误：需要Python 3.8或更高版本")
        print(f"   当前版本：{sys.version}")
        return False
    
    print(f"✅ Python版本：{sys.version.split()[0]}")
    
    # 检查依赖
    required_packages = ['flask', 'yaml', 'requests']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package} 已安装")
        except ImportError:
            missing_packages.append(package)
            print(f"❌ {package} 未安装")
    
    if missing_packages:
        print(f"\n📥 安装缺失的依赖：{', '.join(missing_packages)}")
        print("💡 运行：pip install -r requirements.txt")
        return False
    
    print("✅ 所有依赖已就绪")
    return True

def setup_environment():
    """设置环境"""
    print("🔧 设置环境...")
    
    # 加载.env文件
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)
        print("✅ 已加载.env文件")
    
    # 检查配置文件
    config_path = Path("config/systems.yaml")
    if not config_path.exists():
        print("❌ 配置文件不存在：config/systems.yaml")
        print("💡 请手动创建配置文件")
        return False
    
    print("✅ 配置文件就绪")
    
    # 检查环境变量
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        print("⚠️  警告：未设置DEEPSEEK_API_KEY环境变量")
        print("💡 请设置：export DEEPSEEK_API_KEY='your-api-key'")
        print("💡 或在.env文件中配置")
    else:
        print("✅ API密钥已配置")
    
    return True

def check_redis_status():
    """检查Redis状态"""
    use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'
    
    if use_redis:
        print("🔍 检查Redis连接...")
        try:
            # 尝试连接Redis
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0, socket_timeout=5)
            r.ping()
            print("✅ Redis连接正常")
            return True
        except Exception as e:
            print(f"❌ Redis连接失败：{e}")
            print("💡 请启动Redis服务或设置USE_REDIS=false")
            return False
    else:
        print("ℹ️  Redis已禁用（使用MockCelery模式）")
        return True

def start_services():
    """启动服务"""
    print("🚀 启动服务...")
    
    use_redis = os.environ.get('USE_REDIS', 'false').lower() == 'true'
    
    if use_redis:
        print("💡 生产模式：请确保Redis服务已启动")
        print("💡 启动Worker：python celery_worker.py")
    else:
        print("💡 开发模式：使用MockCelery，无需额外服务")
    
    # 获取配置
    port = int(os.environ.get('PORT', 5001))
    host = os.environ.get('HOST', '0.0.0.0')
    
    print(f"🌐 服务地址：http://{host}:{port}")
    print("⏳ 正在启动...")
    
    # 启动主应用
    try:
        from main import main
        main()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
    except Exception as e:
        print(f"❌ 启动失败：{e}")
        return False
    
    return True

def main():
    """主函数"""
    print_banner()
    
    # 检查环境
    if not check_requirements():
        return 1
    
    # 设置环境
    if not setup_environment():
        return 1
    
    # 检查Redis
    if not check_redis_status():
        return 1
    
    # 启动服务
    if not start_services():
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
