#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
    print("  - MockCelery任务队列")
    print("=" * 60)

def check_requirements():
    """检查运行环境"""
    print("🔍 检查运行环境...")
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print("❌ 错误：需要Python 3.8或更高版本")
        print("   当前版本：{}".format(sys.version))
        return False
    
    print("✅ Python版本：{}".format(sys.version.split()[0]))
    
    # 检查依赖
    required_packages = ['flask', 'yaml', 'requests']
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print("✅ {} 已安装".format(package))
        except ImportError:
            missing_packages.append(package)
            print("❌ {} 未安装".format(package))
    
    if missing_packages:
        print("\n📥 安装缺失的依赖：{}".format(', '.join(missing_packages)))
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

def start_services():
    """启动服务"""
    print("🚀 启动服务...")
    
    print("💡 使用MockCelery轻量级任务队列模式")
    
    # 获取配置
    port = int(os.environ.get('PORT', 5001))
    host = os.environ.get('HOST', '0.0.0.0')
    
    print("🌐 服务地址：http://{}:{}".format(host, port))
    print("⏳ 正在启动...")
    
    # 启动主应用
    try:
        # 添加项目根目录到路径
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from main import main
        main()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
    except Exception as e:
        print("❌ 启动失败：{}".format(e))
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
    
    # 启动服务
    if not start_services():
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
