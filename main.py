#!/usr/bin/env python3
"""
一键启动脚本 - Git增量代码智能审查与测试用例生成系统
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from dotenv import load_dotenv

def print_banner():
    """打印启动横幅"""
    print("=" * 60)
    print("Git Incremental Code Review & Test Generator")
    print("=" * 60)
    print("Features:")
    print("  - Intelligent code review")
    print("  - Auto test case generation")
    print("  - Multi Git providers")
    print("  - MockCelery Task Queue")
    print("=" * 60)

def check_requirements():
    """检查运行环境"""
    print("Checking environment...")
    
    # 检查Python版本
    if sys.version_info < (3, 8):
        print("[ERROR] Python 3.8+ required")
        return False
    
    # 检查依赖
    try:
        import flask
        import yaml
        import requests
        print("[OK] Dependencies ready")
    except ImportError as e:
        print(f"[ERROR] Missing dependency {e}")
        print("[HINT] pip install -r requirements.txt")
        return False
    
    return True

def setup_environment():
    """设置环境"""
    print("Setup environment...")
    
    # 检查配置文件
    config_path = Path("config/systems.yaml")
    if not config_path.exists():
        example_path = Path("config/systems.yaml.example")
        if example_path.exists():
            print("Copying config/systems.yaml from example...")
            import shutil
            shutil.copy(example_path, config_path)
            print("[OK] config/systems.yaml created. Please edit it.")
        else:
            print("[WARN] config template not found")
    
    # 检查环境变量
    if not os.environ.get('DEEPSEEK_API_KEY'):
        print("[WARN] DEEPSEEK_API_KEY not set")
        print("[HINT] setx DEEPSEEK_API_KEY your-api-key (Windows) or export DEEPSEEK_API_KEY=your-api-key (bash)")
    
    return True

def check_task_queue():
    """检查任务队列状态"""
    print("[OK] Using MockCelery task queue mode")
    return True

def start_services():
    """启动服务"""
    print("Starting services...")
    
    print("[INFO] Using MockCelery lightweight task queue mode")
    
    # 启动Flask应用
    print("Starting web server...")
    try:
        from app import create_app
        from app.config_manager import config_manager
        
        app = create_app()
        
        # 获取端口和主机配置
        port = config_manager.get_server_port()
        host = config_manager.get_server_host()
        
        print(f"[OK] Web started at http://{host}:{port}")
        if host == '0.0.0.0':
            print(f"[INFO] Also available at http://localhost:{port}")
        print("[INFO] Stop: Ctrl+C")
        print("=" * 60)
        
        app.run(debug=True, host=host, port=port)
    except KeyboardInterrupt:
        print("Stopping...")
        print("Stopped.")
    except Exception as e:
        print(f"[ERROR] Web start failed: {e}")
        return False
    
    return True

def main():
    """主函数"""
    print_banner()
    # 加载 .env 环境变量
    load_dotenv()
    
    # 检查运行环境
    if not check_requirements():
        sys.exit(1)
    
    # 设置环境
    if not setup_environment():
        sys.exit(1)
    
    # 检查任务队列状态
    if not check_task_queue():
        print("Hints:\n 1) setx DEEPSEEK_API_KEY your-api-key\n 2) edit config/systems.yaml")
        sys.exit(1)
    
    # 启动服务
    start_services()

if __name__ == "__main__":
    main()
